import io
import os
import random
from tempfile import NamedTemporaryFile
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session
from PIL import Image
import models, schemas
from database import get_db
from face_service import get_deepface
from utils import (
    send_otp_mail,
    create_access_token,
    pwd_context,
    UPLOAD_DIR,
    PROFILE_URL_PREFIX,
    normalize_email,
)
from profile_storage import (
    ProfileStorageError,
    delete_profile_image,
    profile_object_path,
    upload_profile_image,
    uses_supabase_storage,
)

router = APIRouter(tags=["Authentication"])
MAX_FACE_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/request-otp")
async def request_otp(request: schemas.OTPRequest, db: Session = Depends(get_db)):
    normalized_email = normalize_email(request.email)

    # bail early if email is already taken
    if db.query(models.User).filter(
        func.lower(models.User.email) == normalized_email,
    ).first():
        raise HTTPException(status_code=400, detail="This email is already registered.")

    # bumail.net = student, anything else = guest
    domain = normalized_email.split("@")[-1]
    account_type = "student" if domain == "bumail.net" else "general"

    otp_code = str(random.randint(100000, 999999))

    # clear any old OTP for this email before issuing a new one
    db.query(models.UserOTP).filter(
        func.lower(models.UserOTP.email) == normalized_email,
    ).delete(synchronize_session=False)
    db.add(models.UserOTP(email=normalized_email, otp_code=otp_code))
    db.commit()

    try:
        await send_otp_mail(normalized_email, otp_code)
        return {"message": f"OTP sent to {normalized_email}", "account_type": account_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/verify-otp")
def verify_otp(request: schemas.OTPVerify, db: Session = Depends(get_db)):
    normalized_email = normalize_email(request.email)
    db_otp = db.query(models.UserOTP).filter(
        func.lower(models.UserOTP.email) == normalized_email,
        models.UserOTP.otp_code == request.otp,
    ).first()
    if not db_otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    return {"message": "OTP Verified Successfully!"}


@router.post("/register")
async def register(
    email: str = Form(...),
    otp: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    student_id: str = Form(None),
    faculty: str = Form(None),
    department: str = Form(None),
    phone: str = Form(None),
    face_image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    normalized_email = normalize_email(email)

    # re-verify OTP at registration time so you can't skip step 2
    db_otp = db.query(models.UserOTP).filter(
        func.lower(models.UserOTP.email) == normalized_email,
        models.UserOTP.otp_code == otp,
    ).first()
    if not db_otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    local_file_path = None
    temporary_file_path = None
    profile_url = None
    uploaded_object_path = None
    keep_local_file = False

    # Normalize the image once. DeepFace needs a local path, while production
    # storage receives the normalized JPEG bytes below.
    try:
        image_data = await face_image.read(MAX_FACE_IMAGE_BYTES + 1)
        if len(image_data) > MAX_FACE_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Face image is too large.")
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        image.thumbnail((200, 200))
        normalized_image = io.BytesIO()
        image.save(normalized_image, "JPEG", quality=85)
        normalized_image_data = normalized_image.getvalue()

        if uses_supabase_storage():
            with NamedTemporaryFile(
                prefix="smart-lab-face-",
                suffix=".jpg",
                delete=False,
            ) as temporary_file:
                temporary_file.write(normalized_image_data)
                temporary_file_path = temporary_file.name
            file_path = temporary_file_path
        else:
            file_name = f"{uuid4().hex}.jpg"
            local_file_path = os.path.join(UPLOAD_DIR, file_name)
            with open(local_file_path, "wb") as local_file:
                local_file.write(normalized_image_data)
            profile_url = f"{PROFILE_URL_PREFIX}/{file_name}"
            file_path = local_file_path
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to process image file.")

    # enforce_detection=True raises an exception if no face is found
    try:
        embedding_objs = get_deepface().represent(
            img_path=file_path,
            model_name="Facenet",
            enforce_detection=True,
        )
        face_embedding_vector = embedding_objs[0]["embedding"]
    except Exception:
        if temporary_file_path and os.path.exists(temporary_file_path):
            os.remove(temporary_file_path)
        if local_file_path and os.path.exists(local_file_path):
            os.remove(local_file_path)
        raise HTTPException(status_code=400, detail="No face detected in the image.")

    try:
        # bcrypt silently truncates at 72 bytes, so we do it explicitly
        hashed_password = pwd_context.hash(password)
        new_user = models.User(
            email=normalized_email,
            password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            profile_pic=None,
            face_embedding=face_embedding_vector,
        )
        db.add(new_user)
        db.flush()  # get new_user.id before inserting child records

        if uses_supabase_storage():
            uploaded_object_path = profile_object_path(new_user.id)
            await upload_profile_image(uploaded_object_path, normalized_image_data)
            new_user.profile_pic = uploaded_object_path
        else:
            new_user.profile_pic = profile_url

        db.add(models.UserPoints(user_id=new_user.id, points=100))

        domain = normalized_email.split("@")[-1]
        role_name = "student" if domain == "bumail.net" else "guest"
        role = db.query(models.Role).filter(models.Role.name == role_name).first()

        if domain == "bumail.net":
            db.add(models.Student(
                student_id=student_id,
                user_id=new_user.id,
                faculty=faculty,
                department=department,
                is_active=True,
            ))
        else:
            # guests start inactive — they need admin approval before they can log in
            db.add(models.UserPassport(phone=phone, user_id=new_user.id, is_active=False))

        if role:
            db.add(models.UserRole(user_id=new_user.id, role_id=role.id))

        db.delete(db_otp)  # OTP is single-use
        db.commit()
        keep_local_file = True
        return {"message": "Registration successful!"}
    except ProfileStorageError:
        db.rollback()
        if uploaded_object_path:
            await delete_profile_image(uploaded_object_path)
        raise HTTPException(
            status_code=503,
            detail="Profile image storage is unavailable. Please try again later.",
        )
    except Exception as e:
        db.rollback()
        if uploaded_object_path:
            await delete_profile_image(uploaded_object_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temporary_file_path and os.path.exists(temporary_file_path):
            os.remove(temporary_file_path)
        if local_file_path and not keep_local_file and os.path.exists(local_file_path):
            os.remove(local_file_path)


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    normalized_email = normalize_email(form_data.username)
    user = db.query(models.User).filter(
        func.lower(models.User.email) == normalized_email,
    ).first()

    # bcrypt 72-byte limit — keep consistent with register
    safe_pwd = form_data.password.encode("utf-8")[:72].decode("utf-8", "ignore")
    if not user or not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user_role = db.query(models.Role.name).join(models.UserRole).filter(
        models.UserRole.user_id == user.id
    ).first()
    role_name = user_role[0] if user_role else "guest"

    # guests can't log in until admin approves them
    if role_name == "guest":
        passport = db.query(models.UserPassport).filter(models.UserPassport.user_id == user.id).first()
        if passport and not passport.is_active:
            raise HTTPException(status_code=403, detail="Your account is pending admin approval.")

    access_token = create_access_token(
        data={"sub": normalize_email(user.email), "role": role_name},
    )
    return {"access_token": access_token, "token_type": "bearer"}
