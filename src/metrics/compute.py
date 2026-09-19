"""Metric COMPUTATION: pure functions from canonical session rows to numbers. No wording, no thresholds, no approved values here.

Every function takes the population it must use as an explicit argument; the caller (src/metrics/evaluate.py) gets it from the metric's
contract. Interpretation and limitation text live in src/metrics/contracts.py, presentation in evaluate.py.

Null handling: a NULL weight or component count is EXCLUDED from a statistic and counted in `n_null_excluded`; it is never read as 0.
An empty population raises (a median of nothing is not 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from src.metrics.inputs import SessionRow
from src.metrics.populations import select
from src.metrics.stats import median, percentile_linear

P90 = 0.90


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    population: str
    value: float | int | None
    numerator: int | None = None
    denominator: int | None = None
    n_population: int = 0            # sessions in the named population
    n_used: int = 0                  # sessions that contributed a value
    n_null_excluded: int = 0         # sessions in the population left out because the field is NULL
    detail: dict[str, Any] = field(default_factory=dict)


def _weights(rows: Iterable[SessionRow]) -> tuple[list[int], int]:
    rows = list(rows)
    values = [s.derived_selected_meal_weight_g for s in rows if s.derived_selected_meal_weight_g is not None]
    return values, len(rows) - len(values)


def m1_median_selected_weight(sessions: list[SessionRow], population: str) -> MetricResult:
    rows = select(sessions, population)
    weights, nulls = _weights(rows)
    return MetricResult("M1", population, median(weights), n_population=len(rows), n_used=len(weights), n_null_excluded=nulls,
                        detail={"method": "median", "min": min(weights), "max": max(weights)})


def m2_p90_selected_weight(sessions: list[SessionRow], population: str) -> MetricResult:
    rows = select(sessions, population)
    weights, nulls = _weights(rows)
    return MetricResult("M2", population, percentile_linear(weights, P90), n_population=len(rows), n_used=len(weights), n_null_excluded=nulls,
                        detail={"method": "percentile_linear", "q": P90, "min": min(weights), "max": max(weights)})


def m3_observed_valid_sessions(sessions: list[SessionRow], population: str) -> MetricResult:
    rows = select(sessions, population)
    return MetricResult("M3", population, len(rows), n_population=len(rows), n_used=len(rows),
                        detail={"by_service_date": _by_date(rows)})


def _by_date(rows: list[SessionRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in rows:
        if s.service_date:
            counts[s.service_date] = counts.get(s.service_date, 0) + 1
    return dict(sorted(counts.items()))


def m4_median_distinct_components(sessions: list[SessionRow], population: str) -> MetricResult:
    rows = select(sessions, population)
    counts = [s.distinct_component_count for s in rows if s.distinct_component_count is not None]
    distribution: dict[int, int] = {}
    for c in counts:
        distribution[c] = distribution.get(c, 0) + 1
    return MetricResult("M4", population, median(counts), n_population=len(rows), n_used=len(counts), n_null_excluded=len(rows) - len(counts),
                        detail={"method": "median", "distribution": dict(sorted(distribution.items()))})


def m5_core_readiness(sessions: list[SessionRow], numerator_population: str, denominator_population: str) -> MetricResult:
    num, den = select(sessions, numerator_population), select(sessions, denominator_population)
    if not den:
        raise ValueError("M5 denominator is empty")
    return MetricResult("M5", numerator_population, 100 * len(num) / len(den), numerator=len(num), denominator=len(den), n_population=len(den), n_used=len(num),
                        detail={"denominator_population": denominator_population, "quarantined_in_denominator": sum(s.is_quarantined for s in den)})


def s1_weather_coverage(sessions: list[SessionRow], population: str) -> MetricResult:
    rows = select(sessions, population)
    matched = [s for s in rows if s.weather_matched]
    status: dict[str, int] = {}
    for s in rows:
        status[s.weather_join_status] = status.get(s.weather_join_status, 0) + 1
    return MetricResult("S1", population, 100 * len(matched) / len(rows), numerator=len(matched), denominator=len(rows), n_population=len(rows), n_used=len(matched),
                        detail={"join_status": dict(sorted(status.items())),
                                "r_1h_null_sessions": sum(1 for s in matched if s.weather_r_1h_null), "ri_10min_null_sessions": sum(1 for s in matched if s.weather_ri_10min_null)})


def s2_warn_free_rate(sessions: list[SessionRow], population: str, *, include_event_level: bool = False) -> MetricResult:
    """Sessions that are core-ready and carry no session-level WARN (B04, B07, T04, T05, I06), over the whole eligible population.
    With include_event_level=True (the DIAGNOSTIC variant only) event-level WARNs (B02, I02) also disqualify."""
    rows = select(sessions, population)
    clean = [s for s in rows if s.core_ready and not s.has_session_warn and not (include_event_level and s.has_event_warn)]
    warned = [s for s in rows if s.core_ready and s.has_session_warn]
    return MetricResult("S2D" if include_event_level else "S2", population, 100 * len(clean) / len(rows), numerator=len(clean), denominator=len(rows),
                        n_population=len(rows), n_used=len(clean),
                        detail={"with_session_level_warn": len(warned), "not_core_ready": sum(1 for s in rows if not s.core_ready),
                                "event_level_only_warn": sum(1 for s in rows if s.core_ready and s.has_event_warn and not s.has_session_warn)})
