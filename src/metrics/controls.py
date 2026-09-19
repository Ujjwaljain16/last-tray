"""Metric controls: independent cross-checks that the populations and the inputs behind the metrics are what the contracts say.

None of these changes a metric. They compare the metric layer with the canonical model tables it reads (never staging or raw files) and with
an independent implementation of the statistics from the Python standard library. Statuses: PASS, WARN, FAIL, INFO (as in WP4 and WP5).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from src.metrics import contracts as ct
from src.metrics.compute import MetricResult
from src.metrics.inputs import MetricInputs
from src.metrics.compute import P90
from src.metrics.populations import POPULATIONS, select
from src.metrics.stats import median, percentile_linear
from src.validate.reconcile import Check, eq, info

FORBIDDEN_NAME_PARTS = ("waste", "consum", "intake", "leftover")


def _events_by_session(inp: MetricInputs) -> dict[str, list[dict[str, str]]]:
    by: dict[str, list[dict[str, str]]] = defaultdict(list)
    for e in inp.events:
        by[e["session_key"]].append(e)
    return by


def population_checks(inp: MetricInputs) -> list[Check]:
    all_s = inp.sessions
    n = {name: len(select(all_s, name)) for name in POPULATIONS}
    quarantined = [s for s in all_s if s.is_quarantined]
    overlap = {s.session_key for s in select(all_s, ct.C)} & {s.session_key for s in select(all_s, ct.E)}
    modelled = {s.session_key for s in select(all_s, ct.B)}
    return [
        info("MC01", "populations", "A all observed | B non-quarantined modelled | C eligible registered-export | D core-ready registered-export | E non-registered-export",
             " | ".join(str(n[k]) for k in (ct.A, ct.B, ct.C, ct.D, ct.E))),
        eq("MC02", "populations", "populations are never pooled: A = C + E and C and E share no session key", (n[ct.A], 0), (n[ct.C] + n[ct.E], len(overlap)), "identity"),
        eq("MC03", "populations", "the quarantined session keys are exactly the sessions of A that are not in B", sorted(s.session_key for s in quarantined),
           sorted(s.session_key for s in all_s if s.session_key not in modelled), "WP4 quarantine, via the model"),
        eq("MC04", "populations", "every quarantined registered-export session stays inside the eligible population C (the M5 denominator is not shrunk)",
           sum(s.population == "registered_export" for s in quarantined), sum(s.is_quarantined for s in select(all_s, ct.C)), "approved denominator rule"),
        eq("MC05", "populations", "no quarantined session is in the measurement population D", 0, sum(s.is_quarantined for s in select(all_s, ct.D)), "quarantine policy"),
    ]


def weight_checks(inp: MetricInputs) -> list[Check]:
    d = select(inp.sessions, ct.D)
    by = _events_by_session(inp)
    wrong, with_repeats_differ, repeated_scale = [], 0, 0
    for s in d:
        evs = by[s.session_key]
        modellable = sum(int(e["component_weight_g"]) for e in evs if e["is_modellable"] == "true")
        if modellable != s.derived_selected_meal_weight_g:
            wrong.append(s.session_key)
        if sum(int(e["component_weight_g"]) for e in evs if e["disposition"] != "QUARANTINED") != s.derived_selected_meal_weight_g:
            with_repeats_differ += 1
        per_scale: dict[str, int] = defaultdict(int)
        for e in evs:
            if e["is_modellable"] == "true":
                per_scale[e["scale_id"]] += 1
        repeated_scale += any(v > 1 for v in per_scale.values())
    largest = max((e for e in inp.events if e["component_weight_g"]), key=lambda e: int(e["component_weight_g"]))
    largest_session = next(s for s in inp.sessions if s.session_key == largest["session_key"])
    kept = largest["disposition"] == "MODELLABLE" and (not largest_session.core_ready or largest_session.derived_selected_meal_weight_g is not None)
    weights = [s.derived_selected_meal_weight_g for s in d if s.derived_selected_meal_weight_g is not None]
    return [
        eq("MC06", "weights", "every session in D has a canonical weight: no NULL is dropped silently", 0, sum(s.derived_selected_meal_weight_g is None for s in d), "null handling"),
        eq("MC07", "weights", "each D session's weight equals the sum of its MODELLABLE event weights in fact_weighing_event", [], sorted(wrong), "canonical event fact"),
        info("MC08", "weights", "D sessions whose weight would differ if exact repeats were summed (proves repeats are excluded, not double counted)", with_repeats_differ),
        info("MC09", "weights", "D sessions that weighed the same scale more than once (repeats that are not exact duplicates stay additive)", repeated_scale),
        eq("MC10", "weights", f"the largest single event ({largest['component_weight_g']} g, {largest['event_id']}) is preserved and modellable; its session keeps its weight", True, kept, "2,097 g preservation"),
        eq("MC11", "weights", "the independent standard-library percentile (statistics.quantiles, inclusive) equals the linear-interpolation P90",
           round(statistics.quantiles(weights, n=10, method="inclusive")[8], 9), round(percentile_linear(weights, P90), 9), "independent method"),
        eq("MC12", "weights", "the independent standard-library median equals the median used", statistics.median(weights), median(weights), "independent method"),
    ]


def component_checks(inp: MetricInputs) -> list[Check]:
    d = {s.session_key: s for s in select(inp.sessions, ct.D)}
    by_key: dict[str, set[str]] = defaultdict(set)
    populations: set[tuple[str, str]] = set()
    for c in inp.components:
        by_key[c["session_key"]].add(c["component_id_normalized"])
        populations.add((c["session_key"], c["population"]))
    session_pop = {s.session_key: s.population for s in inp.sessions}
    return [
        eq("MC13", "components", "distinct components counted from fact_session_component equal distinct_component_count for every D session", [],
           sorted(k for k, s in d.items() if len(by_key.get(k, ())) != s.distinct_component_count), "canonical component fact"),
        eq("MC14", "components", "raw and normalised distinct component counts do not differ within any D session (Phase 2 property)", [],
           sorted(k for k, s in d.items() if s.distinct_raw_component_count != s.distinct_component_count), "approved Phase 2 finding"),
        eq("MC15", "components", "no component row is attached to a session of another population (no pooling)", 0, sum(session_pop.get(k) != p for k, p in populations), "population separation"),
    ]


def volume_and_readiness_checks(inp: MetricInputs, results: dict[str, MetricResult]) -> list[Check]:
    m3 = results["M3"]
    reg_days = {r["service_date"]: int(r["sessions"]) for r in inp.daily_volume if r["is_primary_population"] == "true"}
    m5, s2 = results["M5"], results["S2"]
    c = select(inp.sessions, ct.C)
    return [
        eq("MC16", "volume", "registered-export daily sessions in fact_daily_volume equal M3 per date and in total", m3.detail["by_service_date"], reg_days, "canonical daily volume"),
        eq("MC17", "readiness", "M5's denominator equals the registered-export session keys counted before any removal", len([s for s in inp.sessions if s.population == "registered_export"]),
           m5.denominator, "approved denominator rule"),
        eq("MC18", "readiness", "S2 accounting: warn-free + with a session-level WARN + not core-ready = eligible", s2.denominator,
           s2.numerator + s2.detail["with_session_level_warn"] + s2.detail["not_core_ready"], "approved reconciliation (1,663 + 34 + 2 = 1,699)"),
        eq("MC19", "readiness", "M3 (count of D) equals M5's numerator", m3.value, m5.numerator, "identity"),
        info("MC20", "readiness", "eligible registered-export session ids | quarantined among them", f"{len({s.session_id for s in c})} | {sum(s.is_quarantined for s in c)}"),
    ]


def weather_checks(inp: MetricInputs, results: dict[str, MetricResult]) -> list[Check]:
    if inp.weather is None:
        return [Check("MC21", "weather", "fact_weather is available", "available", f"BLOCKED: {inp.weather_error}", "FAIL", "canonical model")]
    s1 = results["S1"]
    hours = {(w["fmisid"], w["obs_time_utc"]) for w in inp.weather}
    return [
        eq("MC21", "weather", "fact_weather has one row per station and UTC hour", len(inp.weather), len(hours), "identity"),
        info("MC22", "weather", "session weather_join_status counts over the eligible population", ";".join(f"{k}={v}" for k, v in s1.detail["join_status"].items())),
        info("MC23", "weather", "sessions whose matched hour has a NULL r_1h | NULL ri_10min (never filled, never zero)", f"{s1.detail['r_1h_null_sessions']} | {s1.detail['ri_10min_null_sessions']}"),
    ]


def waste_checks(inp: MetricInputs, metric_ids: list[str]) -> list[Check]:
    columns = {c for cols in inp.manifest["tables"].values() for c in cols["columns"]}
    bad_columns = sorted(c for c in columns if any(p in c for p in FORBIDDEN_NAME_PARTS))
    other = sorted(m for m in metric_ids if m != "W1" and any(p in m.lower() for p in FORBIDDEN_NAME_PARTS))
    return [eq("MC24", "semantics", "no canonical column and no metric id is named for waste, consumption, intake or leftovers (W1 is the blocked evidence row)", [], bad_columns + other, "semantic chain")]


def all_controls(inp: MetricInputs, results: dict[str, MetricResult]) -> list[Check]:
    return (population_checks(inp) + weight_checks(inp) + component_checks(inp) + volume_and_readiness_checks(inp, results) + weather_checks(inp, results)
            + waste_checks(inp, list(ct.ORDER)))
