"""Decision helpers for multi-sample liveness checks."""

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class LivenessDecision:
    accepted: bool
    score: float
    sample_count: int
    passed_samples: int
    motion_detected: bool
    reason: str


def _bounded_values(values: Iterable[float], lower: float, upper: float) -> list[float]:
    result = []
    for value in values:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if isfinite(numeric_value) and lower <= numeric_value <= upper:
            result.append(numeric_value)
    return result


def evaluate_liveness(
    scores: Iterable[float],
    motion_scores: Iterable[float],
    *,
    threshold: float,
    required_samples: int,
    required_passes: int,
    min_motion_score: float,
) -> LivenessDecision:
    """Require a multi-frame liveness consensus and observable motion."""
    valid_scores = _bounded_values(scores, 0.0, 1.0)
    valid_motion_scores = _bounded_values(motion_scores, 0.0, float("inf"))
    passed_samples = sum(score >= threshold for score in valid_scores)
    motion_detected = any(score >= min_motion_score for score in valid_motion_scores)
    representative_score = float(median(valid_scores)) if valid_scores else 0.0

    if len(valid_scores) < required_samples:
        reason = "insufficient_samples"
    elif passed_samples < required_passes:
        reason = "insufficient_liveness_passes"
    elif not motion_detected:
        reason = "no_motion"
    else:
        reason = "accepted"

    return LivenessDecision(
        accepted=reason == "accepted",
        score=representative_score,
        sample_count=len(valid_scores),
        passed_samples=passed_samples,
        motion_detected=motion_detected,
        reason=reason,
    )
