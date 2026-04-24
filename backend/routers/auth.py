import io
import os
import random
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from PIL import Image
from deepface import DeepFace

import models, schemas
from database import get_db
from utils import send_otp_mail, create_access_token, pwd_context, UPLOAD_DIR

router = APIRouter(tags=["Authentication"])

@router.post("/request-otp")
async def request_otp(request: schemas.OTPRequest, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="This email is already registered.")

    domain = request.email.split("@")[-1]
    account_type = "student" if domain == "bumail.net" else "general"

    otp_code = str(random.randint(100000, 999999))
    db.query(models.UserOTP).filter(models.UserOTP.email == request.email).delete()
    new_otp = models.UserOTP(email=request.email, otp_code=otp_code)
    db.add(new_otp)
    db.commit()
    
    try:
        await send_otp_mail(request.email, otp_code)
        return {"message": f"OTP sent to {request.email}", "account_type": account_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@router.post("/verify-otp")
def verify_otp(request: schemas.OTPVerify, db: Session = Depends(get_db)):
    db_otp = db.query(models.UserOTP).filter(models.UserOTP.email == request.email, models.UserOTP.otp_code == request.otp).first()
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
    phone: str = Form(None),
    face_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_otp = db.query(models.UserOTP).filter(models.UserOTP.email == email, models.UserOTP.otp_code == otp).first()
    if not db_otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    
    try:
        image_data = await face_image.read()
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        image.thumbnail((200, 200)) 
        safe_email = email.replace("@", "_").replace(".", "_")
        file_path = f"{UPLOAD_DIR}/{safe_email}.jpg"
        image.save(file_path, "JPEG", quality=85)
    except:
        raise HTTPException(status_code=400, detail="Failed to process image file.")

    try:
        embedding_objs = DeepFace.represent(img_path=file_path, model_name="Facenet", enforce_detection=True)
        face_embedding_vector = embedding_objs[0]["embedding"]
    except:
        if os.path.exists(file_path): os.remove(file_path)
        raise HTTPException(status_code=400, detail="No face detected in the image.")

    try:
        hashed_password = pwd_context.hash(password.encode('utf-8')[:72].decode('utf-8', 'ignore'))
        new_user = models.User(
            email=email, password=hashed_password,
            first_name=first_name, last_name=last_name,
            profile_pic=file_path, face_embedding=face_embedding_vector
        )
        db.add(new_user)
        db.flush() 
        
        domain = email.split("@")[-1]
        role_name = "student" if domain == "bumail.net" else "guest"
        role = db.query(models.Role).filter(models.Role.name == role_name).first()
        
        if domain == "bumail.net":
            db.add(models.Student(student_id=student_id, user_id=new_user.id))
        else:
            db.add(models.UserPassport(phone=phone, user_id=new_user.id))
            
        if role:
            db.add(models.UserRole(user_id=new_user.id, role_id=role.id))
        
        db.delete(db_otp)
        db.commit()
        return {"message": "Registration successful!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    safe_pwd = form_data.password.encode('utf-8')[:72].decode('utf-8', 'ignore')
    
    if not user or not pwd_context.verify(safe_pwd, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user_role = db.query(models.Role.name).join(models.UserRole).filter(models.UserRole.user_id == user.id).first()
    role_name = user_role[0] if user_role else "guest"

    access_token = create_access_token(data={"sub": user.email, "role": role_name})
    return {"access_token": access_token, "token_type": "bearer"}