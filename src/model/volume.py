"""fact_daily_volume: observed valid sessions per service date and population, with the approved FLAG-ONLY volume flags.

`sessions` is Observed Valid Sessions (registered-export population is M3's basis). It is an observation of what the export contains,
not restaurant demand. Flags describe a day; no day is ever excluded, and an irregular day is not a data error.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from src.config import Config

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def build_daily_volume(sessions: list[dict[str, Any]], cfg: Config) -> list[dict[str, Any]]:
    v = cfg.thresholds.volume
    primary = cfg.populations.primary.code.value
    days: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        if s["service_date"]:
            days[(s["service_date"], s["population"])].append(s)
    rows = []
    for (day, pop), ss in sorted(days.items()):
        valid = [s for s in ss if not s["is_quarantined"] and s["modellable_event_count"] > 0]
        if not valid:                                      # a date with no observed valid session is not a service day
            continue
        weekday = WEEKDAYS[date.fromisoformat(day).weekday()]
        n = len(valid)
        observed = "high" if n >= v.high_regime_min_sessions else "low"
        is_primary = pop == primary
        expected = v.expected_regime_by_weekday.get(weekday) if is_primary else None
        rows.append({
            "service_date": day, "population": pop, "weekday": weekday, "is_primary_population": is_primary, "sessions": n,
            "quarantined_sessions": sum(s["is_quarantined"] for s in ss), "events": sum(s["modellable_event_count"] for s in valid),
            "observed_regime": observed, "expected_regime": expected, "low_observed_volume_day": bool(is_primary and n < v.high_regime_min_sessions),
            "volume_irregularity": bool(expected is not None and observed != expected),
            "source_snapshot_id": ss[0]["source_snapshot_id"], "source_files": ";".join(sorted({f for s in valid for f in s["source_files"].split(";")})),
        })
    return rows
