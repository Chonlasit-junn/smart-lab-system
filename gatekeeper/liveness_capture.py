"""Bounded collection of fresh, single-person camera samples."""

from dataclasses import dataclass, replace
import time

import cv2

from face_capture import crop_face, face_motion_score, same_face_track
from liveness_policy import LivenessDecision, evaluate_liveness


@dataclass(frozen=True)
class CaptureResult:
    decision: LivenessDecision
    identity_frame: object


def collect_liveness(*, snapshot, detect, predict, is_current, stop_event,
                     generation, threshold=0.72, sample_count=5, required_passes=4,
                     interval=0.12, timeout=3.0, min_motion=2.0, crop_scale=2.7, clock=time.monotonic):
    deadline = clock() + timeout
    scores, motions = [], []
    first_frame = first_face = identity_frame = None
    last_sequence = None
    failure = None
    while clock() < deadline:
        if not is_current(generation):
            return None
        packet = snapshot()
        if (packet is not None and packet.generation == generation
                and packet.sequence != last_sequence and 0 <= clock() - packet.captured_at <= 1.0):
            last_sequence = packet.sequence
            faces = detect(packet.frame)
            if len(faces) > 1:
                failure = "multiple_faces"
                break
            if len(faces) == 1:
                face = faces[0]
                if first_face is not None and not same_face_track(first_face, face):
                    failure = "face_changed"
                    break
                if first_frame is None:
                    first_frame, first_face = packet.frame, face
                else:
                    motions.append(face_motion_score(first_frame, packet.frame, first_face))
                crop = crop_face(packet.frame, face, crop_scale)
                if crop.size and len(scores) < sample_count:
                    scores.append(float(predict(cv2.resize(crop, (80, 80)))))
                    identity_frame = packet.frame
                # Keep the first five scores: never discard weak predictions
                # until a lucky series passes. Extra frames only allow motion.
                decision = evaluate_liveness(
                    scores, motions, threshold=threshold, required_samples=sample_count,
                    required_passes=required_passes, min_motion_score=min_motion,
                    required_motion_samples=2,
                )
                if len(scores) >= sample_count and (decision.accepted or decision.reason != "no_motion"):
                    return CaptureResult(decision, packet.frame)
        if stop_event.wait(interval):
            return None
    if not is_current(generation):
        return None
    decision = evaluate_liveness(
        scores, motions, threshold=threshold, required_samples=sample_count,
        required_passes=required_passes, min_motion_score=min_motion, required_motion_samples=2,
    )
    if failure:
        decision = replace(decision, accepted=False, reason=failure)
    return CaptureResult(decision, identity_frame)
