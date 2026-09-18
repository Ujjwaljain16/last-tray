"""Control checks: does the independently reconstructed canonical model agree with staging and with WP4?

WP4's `rule_weight_sum_g` (and its span, counts and day table) are validation WORKING values. Here they are used only as a control:
the canonical values are computed from the canonical event rows and compared. A difference is never patched. It is reported by
session and blocks the model (the core lane), because two independent computations of the same figure must agree.

Statuses as in WP4 reconciliation: PASS, WARN, FAIL, INFO.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from src.config import Config
from src.model.inputs import ModelInputs
from src.validate.reconcile import Check, eq, info

SESSION_CONTROL_COLUMNS = ("session_key", "population", "is_quarantined", "canonical_weight_g", "wp4_rule_weight_sum_g", "weight_control",
                           "canonical_span_s", "wp4_span_s", "span_control", "event_count_control", "canonical_first_weighing_local",
                           "wp4_first_weighing_local", "first_weighing_control")
CONTROL_COLUMNS = ("check_id", "area", "description", "expected", "observed", "status", "basis")


def _num(text: str) -> int | None:
    return int(float(text)) if text != "" else None


def session_control_rows(sessions: list[dict[str, Any]], inp: ModelInputs) -> list[dict[str, Any]]:
    rows = []
    for s in sessions:
        w4 = inp.session_status[s["session_key"]]
        wp4_weight, wp4_span = _num(w4["rule_weight_sum_g"]), _num(w4["span_s"])
        if s["is_quarantined"]:
            weight_control = "EXCLUDED_QUARANTINED" if s["derived_selected_meal_weight_g"] is None else "MISMATCH"
        else:
            weight_control = "MATCH" if s["derived_selected_meal_weight_g"] == wp4_weight else "MISMATCH"
        span_control = "MATCH" if s["session_span_s"] == wp4_span else "MISMATCH"
        counts_ok = (s["event_count"] == int(w4["events_staged"]) and s["duplicate_excluded_event_count"] == int(w4["exact_repeats_excluded"])
                     and (s["is_quarantined"] or s["modellable_event_count"] == int(w4["events_counted"])))
        rows.append({"session_key": s["session_key"], "population": s["population"], "is_quarantined": s["is_quarantined"],
                     "canonical_weight_g": s["derived_selected_meal_weight_g"], "wp4_rule_weight_sum_g": wp4_weight, "weight_control": weight_control,
                     "canonical_span_s": s["session_span_s"], "wp4_span_s": wp4_span, "span_control": span_control,
                     "event_count_control": "MATCH" if counts_ok else "MISMATCH", "canonical_first_weighing_local": s["first_weighing_local"],
                     "wp4_first_weighing_local": w4["first_weighing_local"] or None,
                     "first_weighing_control": "MATCH" if s["first_weighing_local"] == (w4["first_weighing_local"] or None) else "MISMATCH"})
    return rows


def control_checks(events: list[dict[str, Any]], sessions: list[dict[str, Any]], components: list[dict[str, Any]], weather: list[dict[str, Any]] | None,
                   volume: list[dict[str, Any]], control_rows: list[dict[str, Any]], inp: ModelInputs, cfg: Config) -> list[Check]:
    f, s4 = cfg.sources.flavoria, inp.validation_summary
    disp = dict(sorted(Counter(e["disposition"] for e in events).items()))
    ids = {s["session_id"] for s in sessions}
    both = sorted(i for i in ids if sum(1 for s in sessions if s["session_id"] == i) > 1)
    primary_rows = [s for s in sessions if s["is_primary_population"]]
    mism = lambda col: sorted(r["session_key"] for r in control_rows if r[col] == "MISMATCH")
    weight_pairs = [r for r in control_rows if r["weight_control"] == "MATCH"]
    checks = [
        eq("M01", "events", "fact_weighing_event rows equal the staged events and the pinned total", f.expected_total_rows, len(events), "pin + staging"),
        eq("M02", "events", "canonical event ids equal the staged event ids in staging order", True, [e.event_id for e in inp.staged.events] == [e["event_id"] for e in events], "staging"),
        eq("M03", "events", "events by population equal WP4", s4["events"]["by_population"], dict(sorted(Counter(e["population"] for e in events).items())), "WP4 summary"),
        eq("M04", "events", "dispositions equal WP4 (nothing dropped: modellable + duplicate-excluded + quarantined = staged)", s4["events"]["dispositions"], disp, "WP4 summary"),
        eq("M05", "sessions", "session keys equal WP4 and the sum of session event counts equals the event total", (s4["sessions"]["session_keys"], len(events)),
           (len(sessions), sum(s["event_count"] for s in sessions)), "WP4 summary"),
        eq("M06", "sessions", "distinct session ids equal the pinned count", f.expected_session_ids, len(ids), "pin: config/sources.yml"),
        eq("M07", "sessions", "session ids present in both populations equal WP4 (the crossover ids; keys are never merged)", s4["sessions"]["session_ids_in_both_populations"], both, "WP4 summary"),
        eq("M08", "sessions", "quarantined session keys equal the WP4 quarantine", sorted(inp.quarantined_keys), sorted(s["session_key"] for s in sessions if s["is_quarantined"]), "WP4 quarantine manifest"),
        eq("M09", "sessions", "every event of a quarantined key is QUARANTINED and no other event is", 0,
           sum((e["disposition"] == "QUARANTINED") != (e["session_key"] in inp.quarantined_keys) for e in events), "WP4 quarantine manifest"),
        eq("M10", "control", "sessions whose canonical selected-meal weight differs from WP4 rule_weight_sum_g (quarantined excluded by design)", [], mism("weight_control"), "independent reconstruction"),
        info("M11", "control", "sessions with a MATCHING independent weight | quarantined sessions with no canonical weight", f"{len(weight_pairs)} | {sum(r['weight_control'] == 'EXCLUDED_QUARANTINED' for r in control_rows)}"),
        eq("M12", "control", "sessions whose canonical span differs from WP4", [], mism("span_control"), "independent reconstruction"),
        eq("M13", "control", "sessions whose event, modellable or repeat counts differ from WP4", [], mism("event_count_control"), "independent reconstruction"),
        eq("M14", "control", "sessions whose first weighing differs from WP4", [], mism("first_weighing_control"), "independent reconstruction"),
        eq("M15", "components", "sessions where distinct raw and normalised component counts differ (Phase 2 property)", [],
           sorted(s["session_key"] for s in sessions if s["distinct_raw_component_count"] != s["distinct_component_count"]), "approved Phase 2 finding"),
        eq("M16", "components", "session_component rows equal the sum of the sessions' distinct component counts", sum(s["distinct_component_count"] or 0 for s in sessions), len(components), "identity"),
        eq("M17", "timezone", "events carrying the file-specific override equal WP4 and sit only in the configured file(s)", 0,
           sum(1 for e in events if e["timezone_handling"] != "SOURCE_LOCAL_ASSUMED" and e["source_file"] not in cfg.timezone.overrides), "approved decision"),
        info("M18", "timezone", "events by timezone_handling", ";".join(f"{k}={v}" for k, v in sorted(Counter(e["timezone_handling"] for e in events).items()))),
        info("M19", "readiness", "core_ready sessions | eligible primary-population sessions (fields prepared for M5; the metric itself is WP6)",
             f"{sum(s['core_ready'] for s in sessions)} | {len(primary_rows)}"),
        eq("M20", "readiness", "core_ready sessions are never quarantined and never carry an ERROR finding", 0,
           sum(s["core_ready"] and (s["is_quarantined"] or s["validation_error_rule_ids"] is not None) for s in sessions), "approved readiness contract"),
    ]
    prim_days = {(v["service_date"]): v for v in inp.service_days if v["population"] == cfg.populations.primary.code.value}
    canon_days = {v["service_date"]: v for v in volume if v["is_primary_population"]}
    same_days = (sorted(prim_days) == sorted(canon_days) and all(
        int(prim_days[d]["sessions"]) == canon_days[d]["sessions"] and (prim_days[d]["low_observed_volume_day"] == "true") == canon_days[d]["low_observed_volume_day"]
        and (prim_days[d]["volume_irregularity_day"] == "true") == canon_days[d]["volume_irregularity"] for d in canon_days))
    checks.append(eq("M21", "volume", "registered-export daily sessions and both flags equal the WP4 day table", True, same_days, "WP4 service_day_volume"))
    if weather is None:
        checks.append(Check("M22", "weather", "fact_weather is available", "available", f"BLOCKED: {inp.staged.weather_error}", "FAIL", "validation"))
    else:
        matched = Counter(s["weather_join_status"] for s in sessions)
        core = [s for s in sessions if s["core_ready"]]
        checks += [
            info("M22", "weather", "fact_weather hours (grain: one station x UTC hour)", len(weather)),
            eq("M23", "weather", "no duplicate (station, hour) in fact_weather", len(weather), len({(w["fmisid"], w["obs_time_utc"]) for w in weather}), "identity"),
            info("M24", "weather", "session weather_join_status counts", ";".join(f"{k}={v}" for k, v in sorted(matched.items()))),
            info("M25", "weather", "core_ready registered-export sessions matched | eligible (approved Phase 2: 1,697 of 1,697)",
                 f"{sum(s['weather_matched'] for s in core)} | {len(core)}"),
            info("M26", "weather", "core_ready sessions whose matched hour has NULL r_1h | NULL ri_10min", f"{sum(bool(s['weather_r_1h_null']) for s in core)} | {sum(bool(s['weather_ri_10min_null']) for s in core)}"),
        ]
    return checks
