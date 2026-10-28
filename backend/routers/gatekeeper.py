import hmac
import math
import os
from typing import Literal, Optional
from types import SimpleNamespace

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import models
from database import get_db
from device_registry import clean_device_id, require_registered_device
from face_service import FACE_MODEL_NAME, FaceServiceBusy, gatekeeper_inference_slot, get_deepface
from routers.points import is_user_banned
from routers.users import require_admin_user
from time_utils import as_lab_naive, utc_now

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
    access_granted: bool
    scan_id: int
    user_id: int
    user_name: str
    lab_id: int
    booking_id: int
    liveness_score: float
    face_distance: float
    face_distance_threshold: float


def _float_setting(name: str, fallback: float, *, maximum: float = 1.0) -> float:
    try:
        value = float(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback
    return value if math.isfinite(value) and 0 <= value <= maximum else fallback


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
    require_active: bool = True,
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
    if require_active and lab.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lab is not available.")
    return lab


def _save_scan(
    db, lab, device_id, *, decision, reason_code, liveness_score,
    user_id=None, booking_id=None, face_distance=None, scanned_at=None,
):
    scan = models.GatekeeperScanLog(
        lab_id=lab.id,
        lab_code=lab.code,
        device_id=clean_device_id(device_id),
        user_id=user_id,
        booking_id=booking_id,
        decision=decision,
        reason_code=reason_code,
        liveness_score=liveness_score,
        face_distance=face_distance,
        scanned_at=scanned_at or utc_now(),
    )
    try:
        db.add(scan)
        db.flush()
        scan_id = scan.id
        db.commit()
        return scan_id
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail={
            "code": "scan_history_unavailable",
            "message": "Unable to save scan history. Access was not granted.",
        }) from None


def _deny_scan(db, lab, device_id, *, code, message, status_code=403, **evidence):
    scan_id = _save_scan(
        db, lab, device_id, decision="denied", reason_code=code, **evidence,
    )
    raise HTTPException(status_code=status_code, detail={
        "code": code, "message": message, "scan_id": scan_id,
    })


def _account_entry_denial(db, user_id):
    role_names = {name for (name,) in db.query(models.Role.name).join(
        models.UserRole, models.UserRole.role_id == models.Role.id,
    ).filter(models.UserRole.user_id == user_id).all()}
    passport = db.query(models.UserPassport).filter(
        models.UserPassport.user_id == user_id,
    ).first()
    if (
        (("guest" in role_names or not role_names) and (passport is None or not passport.is_active))
        or (passport is not None and not passport.is_active)
    ):
        return "guest_approval_required", "Guest approval is required before entry."
    student = db.query(models.Student).filter(models.Student.user_id == user_id).first()
    if student is not None and not student.is_active:
        return "account_inactive", "This account is not active."
    # Reuse the existing Ban rule without creating point rows or daily bonuses.
    if is_user_banned(user_id, db) is not None:
        return "user_banned", "This account has an active ban."
    return None


@router.post("/gatekeeper/identify", response_model=IdentifyResponse, status_code=status.HTTP_200_OK)
def identify_face(
    lab_code: Optional[str] = Form(None),
    liveness_score: float = Form(...),
    face_image: Optional[UploadFile] = File(None),
    device_id: Optional[str] = Form(None),
    device_token: Optional[str] = Form(None),
    liveness_passed: bool = Form(True),
    liveness_reason: Optional[str] = Form(None, max_length=64),
    gatekeeper_key: Optional[str] = Header(default=None, alias="X-Gatekeeper-Key"),
    db: Session = Depends(get_db),
):
    """Authorize entry and commit its audit record before returning a grant."""
    lab = resolve_gatekeeper_lab(
        db,
        device_id=device_id,
        device_token=device_token,
        lab_code=lab_code,
        gatekeeper_key=gatekeeper_key,
        require_active=False,
    )
    evidence = {"liveness_score": liveness_score}
    if not math.isfinite(liveness_score) or not 0 <= liveness_score <= 1:
        _deny_scan(
            db, lab, device_id, code="invalid_liveness_score", message="Invalid liveness score.",
            status_code=422, liveness_score=None,
        )
    if lab.status != "active":
        _deny_scan(
            db, lab, device_id, code="lab_unavailable", message="Lab is not available.", **evidence,
        )
    liveness_threshold = _float_setting(
        "GATEKEEPER_LIVENESS_THRESHOLD", DEFAULT_LIVENESS_THRESHOLD,
    )
    if liveness_passed is not True or liveness_score < liveness_threshold:
        reason = "liveness_no_motion" if liveness_reason == "no_motion" else "liveness_failed"
        _deny_scan(
            db, lab, device_id, code=reason, message="Liveness check failed.", **evidence,
        )

    if face_image is None:
        _deny_scan(
            db, lab, device_id, code="invalid_face_image", message="A face image is required.",
            status_code=422, **evidence,
        )

    image_data = face_image.file.read(MAX_FACE_IMAGE_BYTES + 1)
    if len(image_data) > MAX_FACE_IMAGE_BYTES:
        _deny_scan(
            db, lab, device_id, code="face_image_too_large", message="Face image is too large.",
            status_code=413, **evidence,
        )

    image_buffer = np.frombuffer(image_data, dtype=np.uint8)
    try:
        image = cv2.imdecode(image_buffer, cv2.IMREAD_COLOR) if image_buffer.size else None
    except cv2.error:
        image = None
    if image is None:
        _deny_scan(
            db, lab, device_id, code="invalid_face_image", message="Invalid face image.",
            status_code=400, **evidence,
        )

    # Authentication above performs only SELECTs. Release its transaction before
    # model loading/inference (or waiting for a slot) so other API traffic can use
    # the small shared connection pool. No authorization result is cached.
    original_lab_id, original_lab_code = lab.id, lab.code
    db.rollback()
    failure = None
    try:
        with gatekeeper_inference_slot():
            embedding_objects = get_deepface().represent(
                img_path=image,
                model_name=FACE_MODEL_NAME,
                detector_backend="opencv",
                enforce_detection=True,
                align=True,
            )
    except FaceServiceBusy:
        failure = ("face_service_busy", "Face recognition is busy. Please try again.", 503)
    except ValueError:
        failure = ("face_not_detected", "Unable to detect a face.", 400)
    except Exception:
        failure = ("face_service_unavailable", "Face recognition is unavailable.", 503)

    # Re-read camera credentials/Lab after the connection-free phase: a camera
    # can be revoked or reassigned while AI is running. Revoked credentials never
    # authorize; an inactive Lab still receives its normal denied audit record.
    try:
        current_lab = resolve_gatekeeper_lab(
            db, device_id=device_id, device_token=device_token, lab_code=lab_code,
            gatekeeper_key=gatekeeper_key, require_active=False,
        )
    except HTTPException:
        # This scan authenticated before AI began, so retain a denied audit even
        # if its credential was revoked in flight. Initially invalid credentials
        # still exit before inference and never pollute the audit history.
        exists = db.query(models.Lab.id).filter(models.Lab.id == original_lab_id).first()
        audit_lab = SimpleNamespace(id=original_lab_id if exists else None, code=original_lab_code)
        _deny_scan(
            db, audit_lab, device_id, code="camera_unavailable",
            message="Camera authorization changed. Please contact an administrator.", **evidence,
        )
    if current_lab.id != original_lab_id:
        _deny_scan(
            db, current_lab, device_id, code="lab_unavailable",
            message="Camera Lab changed. Please scan again.", **evidence,
        )
    lab = current_lab
    if lab.status != "active":
        _deny_scan(db, lab, device_id, code="lab_unavailable", message="Lab is not available.", **evidence)
    if failure is not None:
        _deny_scan(
            db, lab, device_id, code=failure[0], message=failure[1], status_code=failure[2], **evidence,
        )

    if len(embedding_objects) != 1:
        _deny_scan(
            db, lab, device_id, code="exactly_one_face_required", message="Exactly one face is required.",
            status_code=400, **evidence,
        )

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
        maximum=2.0,
    )
    if best_user is None or best_distance is None or best_distance > match_threshold:
        _deny_scan(
            db, lab, device_id, code="face_not_recognized", message="Face identity could not be verified.",
            face_distance=best_distance, **evidence,
        )

    evidence.update(user_id=best_user.id, face_distance=best_distance)
    denial = _account_entry_denial(db, best_user.id)
    if denial is not None:
        _deny_scan(db, lab, device_id, code=denial[0], message=denial[1], **evidence)

    # Evaluate after face inference, using Bangkok's date/time and an exclusive
    # slot end. Scanning does not check in or consume the Agent's reservation.
    decision_time = utc_now()
    lab_time = as_lab_naive(decision_time)
    booking = db.query(models.Booking).filter(
        models.Booking.user_id == best_user.id,
        models.Booking.lab_id == lab.id,
        models.Booking.booking_date == lab_time.date(),
        models.Booking.start_time <= lab_time.time(),
        models.Booking.end_time > lab_time.time(),
        models.Booking.status.in_(("reserved", "attended")),
    ).order_by(models.Booking.start_time.asc(), models.Booking.id.asc()).first()
    if booking is None:
        _deny_scan(
            db, lab, device_id, code="booking_required", message="No current booking for this Lab.",
            scanned_at=decision_time, **evidence,
        )

    booking_id, lab_id = booking.id, lab.id
    scan_id = _save_scan(
        db, lab, device_id, decision="granted", reason_code="access_granted",
        booking_id=booking_id, scanned_at=decision_time, **evidence,
    )

    return IdentifyResponse(
        message="Lab entry authorized.",
        access_granted=True,
        scan_id=scan_id,
        user_id=best_user.id,
        user_name=f"{best_user.first_name} {best_user.last_name}",
        lab_id=lab_id,
        booking_id=booking_id,
        liveness_score=liveness_score,
        face_distance=best_distance,
        face_distance_threshold=match_threshold,
    )


@router.get("/admin/gatekeeper/scans")
def get_scan_history(
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[int] = Query(None, gt=0),
    lab_id: Optional[int] = Query(None, gt=0),
    user_id: Optional[int] = Query(None, gt=0),
    device_id: Optional[str] = Query(None, min_length=1, max_length=128),
    decision: Optional[Literal["granted", "denied"]] = Query(None),
    _admin: models.User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    scan = models.GatekeeperScanLog
    query = db.query(scan, models.User.first_name, models.User.last_name).outerjoin(
        models.User, models.User.id == scan.user_id,
    )
    for column, value in (
        (scan.lab_id, lab_id), (scan.user_id, user_id),
        (scan.device_id, device_id), (scan.decision, decision),
    ):
        if value is not None:
            query = query.filter(column == value)
    if before_id is not None:
        query = query.filter(scan.id < before_id)
    try:
        rows = query.order_by(scan.id.desc()).limit(limit + 1).all()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Scan history is unavailable.") from None
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "data": [{
            "id": row.id,
            "lab_id": row.lab_id,
            "lab_code": row.lab_code,
            "device_id": row.device_id,
            "user_id": row.user_id,
            "user_name": f"{first_name} {last_name}" if first_name is not None else None,
            "booking_id": row.booking_id,
            "decision": row.decision,
            "reason_code": row.reason_code,
            "liveness_score": row.liveness_score,
            "face_distance": row.face_distance,
            "scanned_at": row.scanned_at,
        } for row, first_name, last_name in rows],
        "has_more": has_more,
        "next_before_id": rows[-1][0].id if has_more and rows else None,
    }


@router.post("/gatekeeper/scan", response_model=ScanResponse, deprecated=True)
def record_scan(data: ScanData, db: Session = Depends(get_db)):
    # An email and a caller-supplied boolean cannot authorize physical entry.
    raise HTTPException(status_code=410, detail={
        "code": "legacy_scan_disabled",
        "message": "Use /gatekeeper/identify with a registered camera and a face image.",
    })
