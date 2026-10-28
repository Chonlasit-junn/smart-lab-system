import os
import threading
from contextlib import contextmanager
from functools import lru_cache


FACE_MODEL_NAME = "Facenet"
_gatekeeper_inference = threading.BoundedSemaphore(1)


class FaceServiceBusy(Exception):
    """The bounded Gatekeeper inference slot is occupied."""


@contextmanager
def gatekeeper_inference_slot():
    # The deployment has one API worker. Do not accumulate unbounded AI jobs
    # or hold a database connection while waiting for this CPU slot.
    if not _gatekeeper_inference.acquire(timeout=0.25):
        raise FaceServiceBusy()
    try:
        yield
    finally:
        _gatekeeper_inference.release()


@lru_cache(maxsize=1)
def get_deepface():
    """Load DeepFace lazily so normal API startup stays lightweight."""
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "2")

    from deepface import DeepFace

    return DeepFace
