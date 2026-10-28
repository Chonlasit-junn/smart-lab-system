import io
import os
from tempfile import NamedTemporaryFile
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.security import OAuth2PasswordRequestForm
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from PIL import Image, ImageOps
import models, schemas
import otp_service
from access_policy import account_denial, primary_role
from login_security import enforce_login_limits, password_matches, INVALID_LOGIN
from password_policy import validate_new_password, PASSWORD_POLICY_ERROR
from database import get_db
from face_service import (
    get_deepface, FACE_REPRESENT_OPTIONS, FaceImageError, single_face_embedding,
    face_inference_slot, FaceServiceBusy,
)
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
from phone_utils import normalize_phone_number

router = APIRouter(tags=["Authentication"])
MAX_FACE_IMAGE_BYTES = 5 * 1024 * 1024


def _prepare_registration_face(image_data, password):
    """Connection-free, bounded worker; never leave a biometric temp file behind."""
    with face_inference_slot():
        try:
            with Image.open(io.BytesIO(image_data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1024, 1024))
            inference = io.BytesIO()
            image.save(inference, "JPEG", quality=95)
            image.thumbnail((200, 200))
            avatar = io.BytesIO()
            image.save(avatar, "JPEG", quality=85)
        except Exception:
            raise HTTPException(400, "Failed to process image file.") from None

        temporary_path = None
        try:
            with NamedTemporaryFile(prefix="smart-lab-face-", suffix=".jpg", delete=False) as temporary:
                temporary_path = temporary.name
                temporary.write(inference.getvalue())
            try:
                objects = get_deepface().represent(img_path=temporary_path, **FACE_REPRESENT_OPTIONS)
                embedding = single_face_embedding(objects)
            except FaceImageError as exc:
                raise HTTPException(400, str(exc)) from None
            except ValueError:
                raise HTTPException(400, "No face detected in the image.") from None
            except Exception:
                raise HTTPException(503, "Face recognition is unavailable. Please try again later.") from None
            # bcrypt is CPU work too; keep it off the async event loop.
            return embedding, avatar.getvalue(), pwd_context.hash(password)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)


@router.post("/request-otp", dependencies=[Depends(otp_service.enforce_ip_rate_limit)])
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

    challenge_id, otp_code = await run_in_threadpool(otp_service.reserve_otp, db, normalized_email)
    try:
        await send_otp_mail(normalized_email, otp_code)
    except Exception:
        await run_in_threadpool(otp_service.finish_delivery, db, normalized_email, challenge_id, success=False)
    timing = await run_in_threadpool(otp_service.finish_delivery, db, normalized_email, challenge_id, success=True)
    return {"message": f"OTP sent to {normalized_email}", "account_type": account_type, **timing}


@router.post("/verify-otp", dependencies=[Depends(otp_service.enforce_ip_rate_limit)])
def verify_otp(request: schemas.OTPVerify, db: Session = Depends(get_db)):
    normalized_email = normalize_email(request.email)
    otp_service.verify_otp(db, normalized_email, request.otp)
    return {"message": "OTP Verified Successfully!"}


@router.post("/register", dependencies=[Depends(otp_service.enforce_ip_rate_limit)])
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
    try:
        validate_new_password(password)
    except ValueError:
        raise HTTPException(status_code=422, detail=PASSWORD_POLICY_ERROR) from None
    normalized_email = normalize_email(email)
    if normalized_email.split("@")[-1] != "bumail.net":
        try:
            phone = normalize_phone_number(phone)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid phone number.") from None

    # re-verify OTP at registration time so you can't skip step 2
    challenge_id = await run_in_threadpool(otp_service.verify_otp, db, normalized_email, otp)

    # verify_otp commits its preflight and releases the connection/row lock.
    # Do not query the database again until the worker has completed. The same
    # issuance is rechecked and consumed atomically at the final commit below.
    image_data = await face_image.read(MAX_FACE_IMAGE_BYTES + 1)
    if len(image_data) > MAX_FACE_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Face image is too large.")
    try:
        face_embedding_vector, normalized_image_data, hashed_password = await run_in_threadpool(
            _prepare_registration_face, image_data, password,
        )
    except FaceServiceBusy:
        raise HTTPException(
            503, "Face recognition is busy. Please try again.", headers={"Retry-After": "1"},
        ) from None

    local_file_path = None
    uploaded_object_path = None
    keep_local_file = False
    try:
        profile_url = None
        if not uses_supabase_storage():
            file_name = f"{uuid4().hex}.jpg"
            local_file_path = os.path.join(UPLOAD_DIR, file_name)
            with open(local_file_path, "wb") as local_file:
                local_file.write(normalized_image_data)
            profile_url = f"{PROFILE_URL_PREFIX}/{file_name}"
        new_user = models.User(
            email=normalized_email,
            password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            profile_pic=None,
            face_embedding=face_embedding_vector,
        )
        db.add(new_user)
        # Unique-key waits must not block the async event loop while another
        # registration is awaiting profile storage.
        await run_in_threadpool(db.flush)  # get new_user.id before child records

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

        # No external I/O after this lock: authorize the exact issuance at the
        # final boundary, atomically with account creation and OTP consumption.
        await run_in_threadpool(
            otp_service.verify_otp, db, normalized_email, otp, consume=True,
            expected_challenge_id=challenge_id,
        )
        await run_in_threadpool(db.commit)
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
    except HTTPException:
        db.rollback()
        if uploaded_object_path:
            await delete_profile_image(uploaded_object_path)
        raise
    except IntegrityError:
        db.rollback()
        if uploaded_object_path:
            await delete_profile_image(uploaded_object_path)
        raise HTTPException(status_code=409, detail="Registration details are already in use.")
    except Exception:
        db.rollback()
        if uploaded_object_path:
            await delete_profile_image(uploaded_object_path)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")
    finally:
        if local_file_path and not keep_local_file and os.path.exists(local_file_path):
            os.remove(local_file_path)


@router.post("/login", response_model=schemas.Token, dependencies=[Depends(enforce_login_limits)])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    normalized_email = normalize_email(form_data.username)
    user = db.query(models.User).filter(
        func.lower(models.User.email) == normalized_email,
    ).first()

    if not password_matches(form_data.password, user.password if user else None):
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)

    denial = account_denial(db, user.id)
    if denial is not None:
        raise HTTPException(status_code=403, detail=denial[1])
    role_name = primary_role(db, user.id)

    access_token = create_access_token(
        data={"sub": normalize_email(user.email), "role": role_name, "auth_version": user.auth_version},
    )
    return {"access_token": access_token, "token_type": "bearer"}
