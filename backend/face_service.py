import os
import threading
from contextlib import contextmanager
from functools import lru_cache


FACE_MODEL_NAME = "Facenet"
FACE_REPRESENT_OPTIONS = {
    "model_name": FACE_MODEL_NAME,
    "detector_backend": "opencv",
    "enforce_detection": True,
    "align": True,
}
_face_inference = threading.BoundedSemaphore(1)


class FaceServiceBusy(Exception):
    """The shared registration/Gatekeeper inference slot is occupied."""


class FaceImageError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def single_face_embedding(objects):
    """Enrollment and entry use the same count/quality checks.

    Never choose the largest or first face from a multi-person image.
    """
    if not objects:
        raise FaceImageError("face_not_detected", "No face detected in the image.")
    if len(objects) != 1:
        raise FaceImageError("exactly_one_face_required", "Exactly one face is required.")
    area = objects[0].get("facial_area") or {}
    if area and min(area.get("w", 0), area.get("h", 0)) < 40:
        raise FaceImageError("face_too_small", "Face is too small. Please move closer to the camera.")
    return objects[0]["embedding"]


@contextmanager
def face_inference_slot():
    # The deployment has one API worker. Do not accumulate unbounded AI jobs
    # or hold a database connection while waiting for this CPU slot.
    if not _face_inference.acquire(timeout=0.25):
        raise FaceServiceBusy()
    try:
        yield
    finally:
        _face_inference.release()


# Preserve callers while both entry points share the same CPU budget.
gatekeeper_inference_slot = face_inference_slot


@lru_cache(maxsize=1)
def get_deepface():
    """Load DeepFace lazily so normal API startup stays lightweight."""
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "2")

    from deepface import DeepFace

    return DeepFace
