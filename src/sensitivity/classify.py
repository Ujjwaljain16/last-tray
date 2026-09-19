"""Robustness classification: one transparent rule set (registry.CLASSIFICATION), applied identically to every metric and scenario."""
from __future__ import annotations

from src.sensitivity.registry import CLASSIFICATION, CLASS_ORDER


def deltas(metric_id: str, baseline: float, value: float) -> tuple[float, float]:
    """(absolute delta, relative delta as a fraction of the baseline)."""
    absolute = value - baseline
    return absolute, (absolute / baseline if baseline else 0.0)


def classify(metric_id: str, baseline: float | None, value: float | None) -> str:
    """STABLE | SENSITIVE | CONDITIONAL, or BLOCKED when there is no value to compare."""
    if baseline is None or value is None:
        return "BLOCKED"
    rule = CLASSIFICATION[metric_id]
    absolute, relative = deltas(metric_id, baseline, value)
    size = abs(relative) if rule["kind"] == "relative" else abs(absolute)
    if size < rule["stable_below"]:
        return "STABLE"
    return "SENSITIVE" if size < rule["sensitive_below"] else "CONDITIONAL"


def worst(classes: list[str]) -> str:
    """The most severe class in the list; STABLE only if every member is STABLE."""
    return max(classes, key=CLASS_ORDER.index) if classes else "BLOCKED"
