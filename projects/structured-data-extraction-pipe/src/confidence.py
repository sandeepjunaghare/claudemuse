"""Field-level confidence and human-review routing (TR8/FR5).

Route a document to a human when it's genuinely uncertain or contradictory; auto-accept
the rest. "Uncertain" = a fail-fast failure, an arithmetic conflict, or any field whose
self-reported confidence falls below a calibrated threshold. Thresholds are calibrated on
a labeled set — not guessed — and audited per type and field (see `audit.py`).
"""

from typing import Dict, List, Optional, Tuple

import config
from schemas import FailureEnvelope, Route


def min_confidence(confidence: Dict[str, float]) -> Optional[float]:
    """Lowest field confidence, or None when nothing was reported."""
    return min(confidence.values()) if confidence else None


def route_decision(
    confidence: Dict[str, float],
    conflict_detected: bool,
    failure: Optional[FailureEnvelope] = None,
    threshold: float = None,
) -> Route:
    """Decide auto-accept vs human review. A failure or conflict always routes to a human;
    otherwise a low-confidence field does."""
    threshold = config.DEFAULT_CONFIDENCE_THRESHOLD if threshold is None else threshold
    if failure is not None:
        return "human_review"
    if conflict_detected:
        return "human_review"
    low = min_confidence(confidence)
    if low is not None and low < threshold:
        return "human_review"
    return "auto_accept"


def calibrate(samples: List[Tuple[float, bool]], candidates: Optional[List[float]] = None) -> float:
    """Pick the confidence threshold that best separates correct from incorrect on a
    labeled set.

    `samples` are `(min_field_confidence, was_correct)` pairs. We choose the threshold that
    maximizes routing accuracy: correct extractions auto-accepted (conf >= threshold) plus
    incorrect ones sent to review (conf < threshold). Ties break toward the higher (more
    conservative) threshold. Falls back to the configured default on an empty set.
    """
    if not samples:
        return config.DEFAULT_CONFIDENCE_THRESHOLD
    cands = candidates or sorted({c for c, _ in samples} | {0.0, 1.0})
    best_threshold = config.DEFAULT_CONFIDENCE_THRESHOLD
    best_score = -1
    for t in cands:
        score = sum(
            1
            for conf, correct in samples
            if (correct and conf >= t) or (not correct and conf < t)
        )
        if score >= best_score:  # >= => prefer the higher (more conservative) threshold
            best_score = score
            best_threshold = t
    return best_threshold
