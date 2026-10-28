"""Public upstream demo crops and deterministic synthetic inputs, no user data."""

from pathlib import Path
import math

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parents[1]


def samples():
    result = []
    # Fixed original detector/crop fixtures preserve the ONNX conversion
    # baseline. These exercise model parity, not the current capture policy;
    # current end-to-end detection has separate face_capture regressions.
    detector_dir = BASE_DIR / "Silent-Face-Anti-Spoofing/resources/detection_model"
    detector = cv2.dnn.readNetFromCaffe(
        str(detector_dir / "deploy.prototxt"), str(detector_dir / "Widerface-RetinaFace.caffemodel"),
    )
    for name in ("image_T1.jpg", "image_F1.jpg", "image_F2.jpg"):
        image = cv2.imread(str(BASE_DIR / "Silent-Face-Anti-Spoofing/images/sample" / name))
        if image is None:
            raise ValueError(f"Missing upstream validation sample: {name}")
        height, width = image.shape[:2]
        ratio = width / height
        small = cv2.resize(image, (int(192 * math.sqrt(ratio)), int(192 / math.sqrt(ratio))))
        detector.setInput(cv2.dnn.blobFromImage(small, 1, mean=(104, 117, 123)), "data")
        detections = detector.forward("detection_out").squeeze()
        box = detections[int(np.argmax(detections[:, 2])), 3:7] * [width, height, width, height]
        x, y, right, bottom = box
        x, y, fw, fh = int(x), int(y), int(right - x + 1), int(bottom - y + 1)
        px, py = int(fw * 1.7 / 2), int(fh * 1.7 / 2)
        crop = cv2.resize(image[max(0, y-py):min(height, y+fh+py), max(0, x-px):min(width, x+fw+px)], (80, 80))
        variants = {
            "original": crop, "flip": cv2.flip(crop, 1),
            "dark": np.clip(crop.astype(np.float32) * 0.65, 0, 255).astype(np.uint8),
            "bright": np.clip(crop.astype(np.float32) * 1.25 + 10, 0, 255).astype(np.uint8),
            "blur": cv2.GaussianBlur(crop, (5, 5), 0),
            "shift": np.roll(crop, 2, axis=1),
            "jpeg": cv2.imdecode(cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 60])[1], cv2.IMREAD_COLOR),
        }
        result.extend((f"{name}:{variant}", pixels) for variant, pixels in variants.items())
    for value in (0, 64, 128, 255):
        result.append((f"solid:{value}", np.full((80, 80, 3), value, dtype=np.uint8)))
    gradient = np.tile(np.linspace(0, 255, 80, dtype=np.uint8), (80, 1))
    result.append(("gradient", np.stack((gradient, gradient.T, 255-gradient), axis=-1)))
    rng = np.random.default_rng(20261028)
    result.extend((f"noise:{i}", rng.integers(0, 256, (80, 80, 3), dtype=np.uint8)) for i in range(24))
    return result
