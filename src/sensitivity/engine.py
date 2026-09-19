"""The scenario engine: a generic interpreter of the registry's `operation` declarations. It knows operations, never scenarios.

A scenario selects and re-weighs sessions from the verified working set and recomputes the metrics with the SAME statistics as the
baseline (src/metrics/stats.py). Nothing here writes to a canonical table, changes a threshold or edits configuration: thresholds are read
from `cfg.thresholds`, offsets from `cfg.timezone`, and every scenario is evaluated from scratch on the frozen baseline.

M5 and S2 are computed only for scenarios that vary who is eligible or ever quarantined (`M5`/`S2` in `metrics_recalculated`), always over
the FIXED denominator (1,699); an analytic exclusion does not redefine readiness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.config import Config
from src.metrics.stats import median, percentile_linear
from src.sensitivity.data import Agg, NON, REG, WorkingSet
from src.sensitivity.registry import ScenarioSpec

HELSINKI = ZoneInfo("Europe/Helsinki")
UTC = ZoneInfo("UTC")
OPS: dict[str, Callable[[str, Any], bool]] = {"<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b}


class ScenarioError(Exception):
    """A scenario declaration cannot be interpreted. It is refused, never approximated."""


@dataclass
class Member:
    agg: Agg
    weight: int | None
    components: int


@dataclass
class ScenarioResult:
    scenario_id: str
    sessions: int
    m1: float | None
    m2: float | None
    m3: int
    m4: float | None
    m5_numerator: int | None = None
    m5_denominator: int | None = None
    m5: float | None = None
    s2_numerator: int | None = None
    s2: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def _members(aggs: list[Agg]) -> list[Member]:
    return [Member(a, a.weight, len(a.comps_norm)) for a in aggs]


# ---- operations -----------------------------------------------------------------------------------------------------------------------------------
def _include(ws: WorkingSet, members: list[Member], op: dict[str, Any]) -> tuple[list[Member], dict[str, Any]]:
    keys = op["keys"]
    if keys == "quarantined_registered":
        keys = sorted(a.key for a in ws.aggs.values() if a.population == REG and a.quarantined)
    add = []
    for k in keys:
        a = ws.aggs[k]
        if a.population != REG:
            raise ScenarioError(f"{k}: only registered-export sessions may be added to the registered-export population")
        add.append(Member(a, a.w_nonrepeat, len(a.comps_norm)))
    return members + add, {"sessions_added": sorted(keys)}


def _exclude(members: list[Member], drop: Callable[[Member], bool]) -> tuple[list[Member], int]:
    kept = [m for m in members if not drop(m)]
    return kept, len(members) - len(kept)


def _dates(ws: WorkingSet, op: dict[str, Any]) -> Callable[[str | None], bool]:
    if "set" in op:
        chosen = {"irregular_volume_days": ws.irregular_days, "low_volume_days": ws.low_days}.get(op["set"])
        if chosen is None:
            raise ScenarioError(f"unknown date set {op['set']!r}")
        return lambda d: d in chosen
    if "before" in op:
        return lambda d: d is not None and d < op["before"]
    if "from" in op:
        return lambda d: d is not None and op["from"] <= d <= op["to"]
    raise ScenarioError(f"unsupported date selector {op}")


def apply_operation(ws: WorkingSet, cfg: Config, op: dict[str, Any], members: list[Member]) -> tuple[list[Member], dict[str, Any]]:
    kind = op["kind"]
    detail: dict[str, Any] = {}
    if kind == "baseline":
        return members, detail
    if kind == "include":
        return _include(ws, members, op)
    if kind == "exclude_session":
        target = ws.largest_event[1]
        members, n = _exclude(members, lambda m: m.agg.key == target)
        return members, {"sessions_removed": n, "session": target}
    if kind == "drop_event":
        _, key, weight = ws.largest_event
        return [Member(m.agg, (m.weight - weight) if m.agg.key == key and m.weight is not None else m.weight, m.components) for m in members], {"event_weight_removed_g": weight}
    if kind == "exclude_weight_outside":
        weights = [m.weight for m in members if m.weight is not None]
        if op["method"] == "percentile":
            lo, hi = percentile_linear(weights, op["lo"]), percentile_linear(weights, op["hi"])
        elif op["method"] == "threshold":
            rule = cfg.thresholds.rules[op["rule"]]
            lo, hi = rule.low, rule.high
        else:
            raise ScenarioError(f"unsupported bound method {op['method']!r}")
        members, n = _exclude(members, lambda m: m.weight is None or not lo <= m.weight <= hi)
        return members, {"sessions_removed": n, "lo_g": lo, "hi_g": hi}
    if kind == "exclude_where":
        value = op["value"] if "value" in op else cfg.thresholds.rules[op["value_ref"]].value
        getter = {"modellable_event_count": lambda a: a.n_modellable, "session_span_s": lambda a: a.span_s}.get(op["field"])
        if getter is None:
            raise ScenarioError(f"unsupported field {op['field']!r}")
        test = OPS[op["op"]]
        members, n = _exclude(members, lambda m: getter(m.agg) is not None and test(getter(m.agg), value))
        return members, {"sessions_removed": n}
    if kind == "exclude_where_any_warn":
        members, n = _exclude(members, lambda m: m.agg.has_session_warn or m.agg.has_event_warn)
        return members, {"sessions_removed": n}
    if kind == "exclude_dates":
        match = _dates(ws, op)
        members, n = _exclude(members, lambda m: match(m.agg.service_date))
        return members, {"sessions_removed": n}
    if kind == "m4_definition":
        pick = {"raw_names": lambda a: len(a.comps_raw), "scales": lambda a: len(a.scales), "events": lambda a: a.n_modellable}.get(op["definition"])
        if pick is None:
            raise ScenarioError(f"unsupported M4 definition {op['definition']!r}")
        return [Member(m.agg, m.weight, pick(m.agg)) for m in members], {"m4_definition": op["definition"]}
    if kind == "weight_definition":
        if op.get("duplicates") != "included":
            raise ScenarioError("only the 'duplicates included' weight definition is declared")
        return [Member(m.agg, m.agg.w_incl_repeats, m.components) for m in members], {"duplicates": "summed"}
    if kind == "population":
        if op["population"] != NON:
            raise ScenarioError("the only alternative population is the diagnostic non-registered-export one")
        return _members([a for a in ws.aggs.values() if a.population == NON and not a.quarantined and a.weight is not None]), {"population": NON}
    if kind == "pooled":
        return members + _members([a for a in ws.aggs.values() if a.population == NON and not a.quarantined and a.weight is not None]), {"pooled": True, "forbidden": True}
    if kind == "timezone_shift":
        return apply_timezone(ws, cfg, op["hours"], members)
    raise ScenarioError(f"unknown operation kind {kind!r}")


# ---- timezone: only the file-specific override files are shifted ----------------------------------------------------------------------------
def shifted_local(wall: datetime, hours: int) -> datetime:
    return wall + timedelta(hours=hours)


def t03_violators(ws: WorkingSet, cfg: Config, hours: int, members: list[Member]) -> set[str]:
    """Session keys with a non-repeat event in an override file whose shifted local hour is outside the service-hours rule T03."""
    t03 = cfg.thresholds.rules["T03"]
    files = set(cfg.timezone.overrides)
    bad = set()
    for m in members:
        for wall, source_file, _ in m.agg.events:
            if source_file in files and not t03.low <= shifted_local(wall, hours).hour < t03.high:
                bad.add(m.agg.key)
                break
    return bad


def apply_timezone(ws: WorkingSet, cfg: Config, hours: int, members: list[Member]) -> tuple[list[Member], dict[str, Any]]:
    bad = t03_violators(ws, cfg, hours, members)
    members, n = _exclude(members, lambda m: m.agg.key in bad)
    return members, {"tz_offset_hours": hours, "t03_quarantined_sessions": n, "files_shifted": sorted(cfg.timezone.overrides)}


# ---- metrics --------------------------------------------------------------------------------------------------------------------------------------------
def run_scenario(spec: ScenarioSpec, ws: WorkingSet, cfg: Config) -> ScenarioResult:
    members = _members(ws.baseline)
    members, detail = apply_operation(ws, cfg, spec.operation, members)
    weights = [m.weight for m in members if m.weight is not None]
    comps = [m.components for m in members]
    r = ScenarioResult(spec.scenario_id, len(members), median(weights), percentile_linear(weights, 0.9), len(members), median(comps), detail=detail)
    if "M5" in spec.metrics_recalculated:
        r.m5_numerator, r.m5_denominator = len(members), ws.eligible
        r.m5 = 100 * len(members) / ws.eligible
    if "S2" in spec.metrics_recalculated:
        r.s2_numerator = sum(1 for m in members if not m.agg.has_session_warn)
        r.s2 = 100 * r.s2_numerator / ws.eligible
    return r
