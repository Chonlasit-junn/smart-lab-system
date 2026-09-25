import hmac
import os
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import models
from database import get_db
from device_registry import require_registered_device
from face_service import FACE_MODEL_NAME, get_deepface
from sqlalchemy import func
from time_utils import utc_now
from utils import normalize_email

router = APIRouter(tags=["Gatekeeper"])
MAX_FACE_IMAGE_BYTES = 5 * 1024 * 1024
FACE_SEARCH_BATCH_SIZE = 512
DEFAULT_FACE_MATCH_MAX_COSINE_DISTANCE = 0.40
DEFAULT_LIVENESS_THRESHOLD = 0.72
GATEKEEPER_DEVICE_PREFIX = "gatekeeper-"
GATEKEEPER_API_KEY = os.getenv("GATEKEEPER_API_KEY")


class ScanData(BaseModel):
    email: str = Field(..., description="email the AI identified at the door")
    lab_id: int
    score: float = Field(..., description="anti-spoofing confidence score")
    is_real: bool = Field(..., description="False if the model thinks it's a photo/spoof")


class ScanResponse(BaseModel):
    message: str
    user_name: str


class IdentifyResponse(BaseModel):
    message: str
    user_id: int
    user_name: str
    liveness_score: float
    face_distance: float
    face_distance_threshold: float


def _float_setting(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _find_closest_face_user(users, probe_embedding):
    """Find the nearest registered face using one vectorized cosine pass."""
    probe = np.asarray(probe_embedding, dtype=np.float32)
    if probe.ndim != 1 or not np.isfinite(probe).all():
        return None, None

    probe_norm = float(np.linalg.norm(probe))
    if not np.isfinite(probe_norm) or probe_norm == 0:
        return None, None

    matching_users = []
    embeddings = []
    norms = []
    best_user = None
    best_distance = None

    def compare_batch():
        nonlocal best_user, best_distance
        if not matching_users:
            return

        matrix = np.stack(embeddings)
        distances = 1.0 - (matrix @ probe) / (np.asarray(norms) * probe_norm)
        best_index = int(np.argmin(distances))
        batch_distance = float(distances[best_index])
        if best_distance is None or batch_distance < best_distance:
            best_user = matching_users[best_index]
            best_distance = batch_distance

        matching_users.clear()
        embeddings.clear()
        norms.clear()

    for user in users:
        raw_embedding = getattr(user, "face_embedding", None)
        if raw_embedding is None:
            continue
        try:
            embedding = np.asarray(raw_embedding, dtype=np.float32)
        except (TypeError, ValueError):
            continue
        if (
            embedding.ndim != 1
            or embedding.shape != probe.shape
            or not np.isfinite(embedding).all()
        ):
            continue

        norm = float(np.linalg.norm(embedding))
        if not np.isfinite(norm) or norm == 0:
            continue
        matching_users.append(user)
        embeddings.append(embedding)
        norms.append(norm)
        if len(matching_users) >= FACE_SEARCH_BATCH_SIZE:
            compare_batch()

    compare_batch()
    return best_user, best_distance


def resolve_gatekeeper_lab(
    db: Session,
    *,
    device_id: Optional[str],
    device_token: Optional[str],
    lab_code: Optional[str],
    gatekeeper_key: Optional[str],
) -> models.Lab:
    """Resolve a Gatekeeper's Lab from its registered credential.

    The shared API key path remains available for older kiosks only when the
    Backend explicitly has a legacy key configured.
    """
    if device_id or device_token:
        device = require_registered_device(db, device_id, device_token)
        if not device.device_id.startswith(GATEKEEPER_DEVICE_PREFIX):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This device is not a Gatekeeper.")
        lab = db.query(models.Lab).filter(models.Lab.id == device.lab_id).first()
    else:
        if not GATEKEEPER_API_KEY or not hmac.compare_digest(gatekeeper_key or "", GATEKEEPER_API_KEY):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This camera must be registered before use.",
            )
        if not str(lab_code or "").strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Lab code is required.")
        lab = db.query(models.Lab).filter(models.Lab.code == lab_code.strip()).first()

    if not lab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found.")
    if lab.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lab is not available.")
    return lab


@router.post("/gatekeeper/identify", response_model=IdentifyResponse, status_code=status.HTTP_200_OK)
def identify_face(
    lab_code: Optional[str] = Form(None),
    liveness_score: float = Form(...),
    face_image: UploadFile = File(...),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    gatekeeper_key: Optional[str] = Header(default=None, alias="X-Gatekeeper-Key"),
    db: Session = Depends(get_db),
):
    """Verify liveness output and identify the closest stored face embedding.

    This endpoint verifies identity but intentionally does not create a
    LabAccessLog; Gatekeeper access logging is handled separately.
    """
    if not 0 <= liveness_score <= 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid liveness score.")

    liveness_threshold = _float_setting(
        "GATEKEEPER_LIVENESS_THRESHOLD",
        DEFAULT_LIVENESS_THRESHOLD,
    )
    if liveness_score < liveness_threshold:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Liveness check failed.")

    resolve_gatekeeper_lab(
        db,
        device_id=device_id,
        device_token=device_token,
        lab_code=lab_code,
        gatekeeper_key=gatekeeper_key,
    )

    image_data = face_image.file.read(MAX_FACE_IMAGE_BYTES + 1)
    if len(image_data) > MAX_FACE_IMAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Face image is too large.")

    image_buffer = np.frombuffer(image_data, dtype=np.uint8)
    image = cv2.imdecode(image_buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid face image.")

    try:
        embedding_objects = get_deepface().represent(
            img_path=image,
            model_name=FACE_MODEL_NAME,
            detector_backend="opencv",
            enforce_detection=True,
            align=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to detect a face.") from exc

    if len(embedding_objects) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exactly one face is required.")

    probe_embedding = np.asarray(embedding_objects[0]["embedding"], dtype=np.float32)
    users = db.query(
        models.User.id,
        models.User.first_name,
        models.User.last_name,
        models.User.face_embedding,
    ).filter(models.User.face_embedding.is_not(None)).yield_per(FACE_SEARCH_BATCH_SIZE)
    best_user, best_distance = _find_closest_face_user(users, probe_embedding)

    match_threshold = _float_setting(
        "FACE_MATCH_MAX_COSINE_DISTANCE",
        DEFAULT_FACE_MATCH_MAX_COSINE_DISTANCE,
    )
    if best_user is None or best_distance is None or best_distance > match_threshold:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Face identity could not be verified.")

    return IdentifyResponse(
        message="Face identity verified.",
        user_id=best_user.id,
        user_name=f"{best_user.first_name} {best_user.last_name}",
        liveness_score=liveness_score,
        face_distance=best_distance,
        face_distance_threshold=match_threshold,
    )


@router.post("/gatekeeper/scan", response_model=ScanResponse, status_code=status.HTTP_200_OK)
def record_scan(data: ScanData, db: Session = Depends(get_db)):
    if not data.is_real:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Spoofing detected.")

    user = db.query(models.User).filter(
        func.lower(models.User.email) == normalize_email(data.email),
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access denied: User not found.")

    lab = db.query(models.Lab).filter(models.Lab.id == data.lab_id).first()
    if not lab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access denied: Lab not found.")

    try:
        scan_time = utc_now()
        db.add(models.LabAccessLog(
            lab_id=data.lab_id,
            user_id=user.id,
            entry_time=scan_time,
            exit_time=scan_time,
            access_type="entry",
            status="success",
            device_used="AI Gatekeeper Kiosk",
            session_status="completed",
            end_reason="gatekeeper_scan",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"DB error: {str(e)}")

    return ScanResponse(message="Access Granted", user_name=f"{user.first_name} {user.last_name}")
