"""Camera-only face detection and motion evidence; no identity or access grants."""

import math
from pathlib import Path

import cv2
import numpy as np


class FaceDetector:
    def __init__(self, base_dir):
        root = Path(base_dir) / "Silent-Face-Anti-Spoofing/resources/detection_model"
        self.net = cv2.dnn.readNetFromCaffe(
            str(root / "deploy.prototxt"), str(root / "Widerface-RetinaFace.caffemodel"),
        )

    def detect(self, frame):
        height, width = frame.shape[:2]
        # Preserve aspect ratio. Use the bundled upstream detector, including
        # its NMS, but keep ALL faces instead of upstream get_bbox's argmax.
        ratio = width / height
        small = cv2.resize(frame, (int(256 * math.sqrt(ratio)), int(256 / math.sqrt(ratio))))
        self.net.setInput(cv2.dnn.blobFromImage(small, 1, mean=(104, 117, 123)), "data")
        rows = self.net.forward("detection_out").reshape(-1, 7)
        faces = []
        for row in rows:
            if not np.isfinite(row).all() or row[2] < 0.6:
                continue
            left, top, right, bottom = row[3:7] * [width, height, width, height]
            x, y = max(0, int(left)), max(0, int(top))
            right, bottom = min(width, int(right) + 1), min(height, int(bottom) + 1)
            if right > x and bottom > y:
                faces.append((x, y, right - x, bottom - y))
        return faces


def crop_face(frame, face, scale=2.7):
    """Match Silent-Face's context crop, shifting at edges instead of clipping."""
    x, y, width, height = face
    frame_h, frame_w = frame.shape[:2]
    scale = min(max(1.0, scale), (frame_w - 1) / width, (frame_h - 1) / height)
    crop_w, crop_h = width * scale, height * scale
    left = max(0, min(x + width / 2 - crop_w / 2, frame_w - 1 - crop_w))
    top = max(0, min(y + height / 2 - crop_h / 2, frame_h - 1 - crop_h))
    return frame[int(top):int(top + crop_h) + 1, int(left):int(left + crop_w) + 1]


def same_face_track(first, current):
    x, y, w, h = first
    a, b, c, d = current
    overlap = max(0, min(x+w, a+c)-max(x, a)) * max(0, min(y+h, b+d)-max(y, b))
    return overlap / max(1, w*h + c*d - overlap) >= 0.3


def face_motion_score(previous, current, face):
    """Median tracked facial displacement as percent of face size.

    Track texture in raw frames, not the recentered crop or mean brightness.
    Forward/backward agreement rejects unstable matches. This supplements the
    anti-spoof model; motion alone never proves a live person.
    """
    if previous.shape != current.shape:
        return 0.0
    before = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    after = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    x, y, w, h = face
    mask = np.zeros_like(before)
    mask[y + h//5:y + 4*h//5, x + w//5:x + 4*w//5] = 255
    points = cv2.goodFeaturesToTrack(before, maxCorners=40, qualityLevel=0.02, minDistance=4, mask=mask)
    if points is None or len(points) < 6:
        return 0.0
    moved, status, _ = cv2.calcOpticalFlowPyrLK(before, after, points, None)
    if moved is None:
        return 0.0
    returned, back_status, _ = cv2.calcOpticalFlowPyrLK(after, before, moved, None)
    if returned is None:
        return 0.0
    valid = (status.ravel() == 1) & (back_status.ravel() == 1)
    valid &= np.linalg.norm((returned - points).reshape(-1, 2), axis=1) < 1.0
    if valid.sum() < 6:
        return 0.0
    displacement = (moved - points).reshape(-1, 2)[valid]
    median = np.median(displacement, axis=0)
    consistent = np.linalg.norm(displacement - median, axis=1) <= max(1.0, np.linalg.norm(median) * 0.5)
    if consistent.mean() < 0.7:
        return 0.0
    return float(100 * np.linalg.norm(median) / max(w, h))
