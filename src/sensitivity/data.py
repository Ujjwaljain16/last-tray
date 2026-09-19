"""The sensitivity working set, built ONLY from the verified canonical model tables (never staging, never raw files).

One `Agg` per session key carries every per-session quantity a scenario may need, computed here once from the canonical event and session
tables. Scenarios select and re-weigh these aggregates; they never mutate a table. The baseline set (population D) is the approved
measurement population, taken from the canonical `core_ready` flag.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.config import Config
from src.metrics.inputs import MetricInputs

REG = "registered_export"
NON = "non_registered_export"


@dataclass
class Agg:
    key: str
    session_id: str
    population: str
    service_date: str | None
    quarantined: bool
    core_ready: bool
    weight: int | None                      # canonical derived_selected_meal_weight_g
    w_nonrepeat: int | None                 # sum over every event that is not an exact repeat (used only by what-if inclusion of quarantined sessions)
    w_incl_repeats: int | None              # sum over every event, repeats included (used only by the duplicate what-if)
    comps_norm: frozenset[str]
    comps_raw: frozenset[str]
    scales: frozenset[str]
    n_modellable: int
    span_s: int | None
    has_session_warn: bool
    has_event_warn: bool
    events: list[tuple[datetime, str, str]] = field(default_factory=list)      # (raw wall time, source file, disposition) of non-repeat events


@dataclass
class WorkingSet:
    aggs: dict[str, Agg]
    baseline: list[Agg]                                   # population D
    eligible: int                                         # 1,699: registered-export session keys before any removal
    irregular_days: frozenset[str]
    low_days: frozenset[str]
    largest_event: tuple[str, str, int]                   # (event_id, session_key, weight)
    weather: dict[datetime, tuple[float | None, float | None]]     # obs hour (naive UTC) -> (t2m, r_1h)
    weather_available: bool


def _sum(values: list[int | None]) -> int | None:
    return None if any(v is None for v in values) else sum(values)  # type: ignore[arg-type]


def _int(text: str) -> int | None:
    return int(text) if text != "" else None


def _wall(local_text: str, offset_hours: int) -> datetime:
    return datetime.strptime(local_text, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=offset_hours)


def build_working_set(inp: MetricInputs, cfg: Config) -> WorkingSet:
    by_session: dict[str, list[dict[str, str]]] = defaultdict(list)
    for e in inp.events:
        by_session[e["session_key"]].append(e)
    aggs: dict[str, Agg] = {}
    for r in inp.session_rows:
        key = r["session_key"]
        evs = by_session[key]
        nonrepeat = [e for e in evs if e["disposition"] != "DUPLICATE_EXCLUDED"]
        aggs[key] = Agg(
            key, r["session_id"], r["population"], r["service_date"] or None, r["is_quarantined"] == "true", r["core_ready"] == "true",
            _int(r["derived_selected_meal_weight_g"]), _sum([_int(e["component_weight_g"]) for e in nonrepeat]), _sum([_int(e["component_weight_g"]) for e in evs]),
            frozenset(e["component_id_normalized"] for e in nonrepeat if e["component_id_normalized"]), frozenset(e["component_name_raw"] for e in nonrepeat),
            frozenset(e["scale_id"] for e in nonrepeat), int(r["modellable_event_count"]), _int(r["session_span_s"]), r["has_session_warn"] == "true", r["has_event_warn"] == "true",
            [(_wall(e["event_time_local"], int(e["timezone_offset_hours_applied"])), e["source_file"], e["disposition"]) for e in nonrepeat if e["event_time_local"]])
    baseline = [a for a in aggs.values() if a.population == REG and a.core_ready]
    weighted = [e for e in inp.events if e["component_weight_g"]]
    big = max(weighted, key=lambda e: (int(e["component_weight_g"]), e["event_id"]))
    volume = [v for v in inp.daily_volume if v["is_primary_population"] == "true"]
    weather: dict[datetime, tuple[float | None, float | None]] = {}
    for w in inp.weather or []:
        weather[datetime.strptime(w["obs_time_utc"], "%Y-%m-%dT%H:%M:%SZ")] = (float(w["t2m_c"]) if w["t2m_c"] else None, float(w["r_1h_mm"]) if w["r_1h_mm"] else None)
    return WorkingSet(aggs, sorted(baseline, key=lambda a: a.key), sum(1 for a in aggs.values() if a.population == REG),
                      frozenset(v["service_date"] for v in volume if v["volume_irregularity"] == "true"),
                      frozenset(v["service_date"] for v in volume if v["low_observed_volume_day"] == "true"),
                      (big["event_id"], big["session_key"], int(big["component_weight_g"])), weather, inp.weather is not None)
