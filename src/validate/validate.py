"""Validation orchestration (WP4): verified staging tables in, findings, quarantine and reconciliation out. Offline.

Reads ONLY the staging tables (through src.validate.load, which verifies them against what staging recorded). It never opens
data/raw. It deletes nothing: quarantine is a list plus a flag, every staged row keeps a disposition, and the derived tables here
are validation evidence, not the canonical model or any metric (WP5-WP6).

Semantic chain, unchanged: OBSERVED component weighing events -> DERIVED selected meal weight -> UNKNOWN consumed quantity ->
SOURCE GAP for actual food waste. Nothing in validation infers consumption or waste from any weight.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.ingest.hashing import digest_file
from src.ingest.manifest import write_csv, write_json
from src.validate import reconcile as rc
from src.validate import rules_events as re_, rules_files as rf, rules_sessions as rs, rules_volume as rv, rules_weather as rw
from src.validate.load import StagedInputs, StagingInputError, load_staging
from src.validate.model import ISSUE_COLUMNS, Issue, build_catalogue, finalise
from src.validate.sessions import SessionProfile, build_profiles, find_repeats

OUT_SUBDIR = "validation"
ISSUES_CSV = "validation_issues.csv"
BY_RULE_CSV = "validation_summary_by_rule.csv"
SUMMARY_JSON = "validation_summary.json"
RECON_CSV = "reconciliation_summary.csv"
QUARANTINE_CSV = "quarantine_manifest.csv"
SESSION_STATUS_CSV = "session_validation_status.csv"
EVENT_STATUS_CSV = "event_validation_status.csv"
DAYS_CSV = "service_day_volume.csv"
COMPLETENESS_CSV = "field_completeness.csv"
DETERMINISTIC_FILES = (ISSUES_CSV, BY_RULE_CSV, SUMMARY_JSON, RECON_CSV, QUARANTINE_CSV, SESSION_STATUS_CSV, EVENT_STATUS_CSV, DAYS_CSV, COMPLETENESS_CSV)

SESSION_LEVEL_WARN_RULES = ("B04", "B07", "T04", "T05", "I06")      # the canonical warn-free definition (docs/validation_rules.md)
EVENT_LEVEL_WARN_RULES = ("B02", "I02")                             # counted only in the diagnostic event-level variant
QUARANTINE_COLUMNS = ("quarantine_entity_type", "entity_id", "session_key", "session_id", "population", "source_snapshot_id", "source_file",
                      "source_row_lineage", "quarantine_rule_ids", "handling_note")
SESSION_COLUMNS = ("session_key", "session_id", "population", "source_files", "events_staged", "events_counted", "exact_repeats_excluded", "first_weighing_local",
                   "service_date", "span_s", "rule_weight_sum_g", "distinct_identification_values", "tray_count", "in_both_populations", "quarantined",
                   "quarantine_rule_ids", "error_rule_ids", "warn_rule_ids", "info_rule_ids", "session_level_warn", "event_level_warn",
                   "low_observed_volume_day", "volume_irregularity_day")
EVENT_STATUS_COLUMNS = ("event_id", "session_key", "population", "source_file", "source_row_number", "disposition", "error_rule_ids", "warn_rule_ids", "info_rule_ids")
DAY_COLUMNS = ("population", "service_date", "weekday", "sessions", "observed_regime", "expected_regime", "low_observed_volume_day", "volume_irregularity_day", "source_files")

WEATHER_RULES = ("X01", "X03", "X07", "X08")      # findings that block the weather lane only, never the core lane
HANDLING_NOTE = "kept in staging and every validation table; excluded from the primary population; nothing is deleted"


@dataclass
class ValidationResult:
    core_status: str = "PASSED"            # PASSED | PASSED_WITH_QUARANTINE | BLOCKED
    weather_status: str = "PASSED"         # PASSED | PASSED_WITH_WARNINGS | BLOCKED
    run_id: str = ""
    issues: list[dict[str, Any]] = field(default_factory=list)
    checks: list[rc.Check] = field(default_factory=list)
    quarantined_keys: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def _run_id(inp: StagedInputs, catalogue: dict) -> str:
    basis = {"input_fingerprint": inp.summary.get("input_fingerprint"), "tables": inp.table_sha256,
             "rules": {k: [v.severity.value, v.handling.value] for k, v in sorted(catalogue.items())}}
    return "val-" + hashlib.sha256(json.dumps(basis, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def collect_core_issues(inp: StagedInputs, cfg: Config, profiles: dict[str, SessionProfile], repeats: dict[str, str]) -> tuple[list[Issue], set[str]]:
    """All core-lane findings. The quarantine set is decided here from ERROR-level rules that quarantine (I01, I04 and the event-level ones)."""
    rules = cfg.thresholds.rules
    primary = cfg.populations.primary.code.value
    ev = inp.events
    issues = (re_.check_structure(ev) + re_.check_weights(ev, repeats, rules) + re_.check_time_window(ev, cfg, rules) + re_.check_repeats(ev, repeats)
              + rf.check_files(ev, cfg) + rf.check_override_scope(ev, cfg) + rs.check_crossover(profiles) + rs.check_identity(profiles)
              + rs.check_cross_export(profiles) + rs.check_component_identity_across_exports(ev))
    cat = build_catalogue(cfg)
    quarantined = {i.session_key for i in issues if i.session_key and cat[i.rule_id].handling.value == "QUARANTINE"}
    issues += rs.check_session_metrics(profiles, rules, primary) + rs.check_repeated_scales(profiles, quarantined)
    return issues, quarantined


def _rules_by_key(rows: list[dict[str, Any]], profiles: dict[str, SessionProfile]) -> dict[str, dict[str, set[str]]]:
    """session_key -> severity -> rule ids. Event issues attach through their session_key; session_id-level issues (I06) to both keys."""
    ids_to_keys: dict[str, list[str]] = defaultdict(list)
    for k, p in profiles.items():
        ids_to_keys[p.session_id].append(k)
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        keys = ids_to_keys.get(r["entity_id"], []) if r["entity_type"] == "session_id" else [r["session_key"]] if r["session_key"] else []
        for k in keys:
            out[k][r["severity"]].add(r["rule_id"])
    return out


def _session_rows(profiles: dict[str, SessionProfile], rules: dict[str, dict[str, set[str]]], quarantined: set[str], repeats: dict[str, str],
                  both: set[str], days: list[rv.ServiceDay]) -> list[dict[str, Any]]:
    day_flags = {(d.population, d.service_date.isoformat()): d for d in days}
    rows = []
    for k, p in profiles.items():
        sev = rules.get(k, {})
        d = day_flags.get((p.population, p.service_date or ""))
        rows.append({
            "session_key": k, "session_id": p.session_id, "population": p.population, "source_files": ";".join(p.source_files),
            "events_staged": len(p.events), "events_counted": len(p.counted), "exact_repeats_excluded": sum(1 for e in p.events if e.event_id in repeats),
            "first_weighing_local": p.first_local.isoformat() if p.first_local else "", "service_date": p.service_date or "",
            "span_s": "" if p.span_s is None else f"{p.span_s:g}", "rule_weight_sum_g": "" if p.rule_weight_sum_g is None else p.rule_weight_sum_g,
            "distinct_identification_values": len(p.identification_values), "tray_count": len([t for t in p.tray_ids if t]),
            "in_both_populations": p.session_id in both, "quarantined": k in quarantined,
            "quarantine_rule_ids": ";".join(sorted(_quarantine_rules(sev, quarantined, k))),
            "error_rule_ids": ";".join(sorted(sev.get("ERROR", ()))), "warn_rule_ids": ";".join(sorted(sev.get("WARN", ()))),
            "info_rule_ids": ";".join(sorted(sev.get("INFO", ()))),
            "session_level_warn": bool(sev.get("WARN", set()) & set(SESSION_LEVEL_WARN_RULES)),
            "event_level_warn": bool(sev.get("WARN", set()) & set(EVENT_LEVEL_WARN_RULES)),
            "low_observed_volume_day": bool(d and d.low_observed_volume), "volume_irregularity_day": bool(d and d.volume_irregularity),
        })
    return rows


def _quarantine_rules(sev: dict[str, set[str]], quarantined: set[str], key: str) -> set[str]:
    return set(sev.get("ERROR", ())) if key in quarantined else set()


def _quarantine_manifest(issues: list[dict[str, Any]], profiles: dict[str, SessionProfile], quarantined: set[str]) -> list[dict[str, Any]]:
    reasons: dict[str, set[str]] = defaultdict(set)
    for r in issues:
        if r["quarantine"] and r["session_key"]:
            reasons[r["session_key"]].add(r["rule_id"])
    rows: list[dict[str, Any]] = []
    for k in sorted(quarantined):
        p = profiles[k]
        rule_ids = ";".join(sorted(reasons[k]))
        rows.append({"quarantine_entity_type": "session_key", "entity_id": k, "session_key": k, "session_id": p.session_id, "population": p.population,
                     "source_snapshot_id": p.events[0].source_snapshot_id, "source_file": ";".join(p.source_files), "source_row_lineage": p.lineage,
                     "quarantine_rule_ids": rule_ids, "handling_note": HANDLING_NOTE})
        for e in p.events:
            rows.append({"quarantine_entity_type": "event", "entity_id": e.event_id, "session_key": k, "session_id": p.session_id, "population": p.population,
                         "source_snapshot_id": e.source_snapshot_id, "source_file": e.source_file, "source_row_lineage": e.event_id,
                         "quarantine_rule_ids": rule_ids, "handling_note": HANDLING_NOTE})
    return rows


def _event_rows(inp: StagedInputs, issues: list[dict[str, Any]], disp: dict[str, str]) -> list[dict[str, Any]]:
    by_event: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in issues:
        if r["event_id"]:
            by_event[r["event_id"]][r["severity"]].add(r["rule_id"])
    return [{"event_id": e.event_id, "session_key": e.session_key, "population": e.population, "source_file": e.source_file, "source_row_number": e.source_row_number,
             "disposition": disp.get(e.event_id, "MISSING_DISPOSITION"), "error_rule_ids": ";".join(sorted(by_event[e.event_id].get("ERROR", ()))),
             "warn_rule_ids": ";".join(sorted(by_event[e.event_id].get("WARN", ()))), "info_rule_ids": ";".join(sorted(by_event[e.event_id].get("INFO", ())))}
            for e in inp.events]


def _by_rule(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[(r["rule_id"], r["category"], r["severity"], r["population"] or "n/a")].append(r)
    return [{"rule_id": k[0], "category": k[1], "severity": k[2], "population": k[3], "issues": len(v), "entities": len({x["entity_id"] for x in v}),
             "quarantine": any(x["quarantine"] for x in v)} for k, v in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][3], kv[0][2]))]


def _summarise(res: ValidationResult, inp: StagedInputs, cfg: Config, profiles: dict[str, SessionProfile], repeats: dict[str, str], disp: dict[str, str],
               session_rows: list[dict[str, Any]], days: list[rv.ServiceDay], both: list[str]) -> dict[str, Any]:
    primary = cfg.populations.primary.code.value
    eligible = [r for r in session_rows if r["population"] == primary]
    live = [r for r in eligible if not r["quarantined"]]
    sev = Counter(r["severity"] for r in res.issues)
    quarantined_events = [e for e, d in disp.items() if d == rc.DISPOSITION_QUARANTINED]
    warn_ids = sorted(r["session_id"] for r in live if r["event_level_warn"] and not r["session_level_warn"])
    return {
        "stage": "validation", "run_id": res.run_id, "core_status": res.core_status, "weather_status": res.weather_status,
        "input_fingerprint": inp.summary.get("input_fingerprint"), "source_snapshot_ids": inp.summary.get("source_snapshot_ids"),
        "staging_table_sha256": inp.table_sha256, "thresholds_approved_on": str(cfg.thresholds.approved_on),
        "thresholds_statement": cfg.thresholds.statement.strip(),
        "issues": {"total": len(res.issues), "by_severity": {s: sev.get(s, 0) for s in ("ERROR", "WARN", "INFO")},
                   "by_rule": {r["rule_id"]: sum(1 for x in res.issues if x["rule_id"] == r["rule_id"]) for r in sorted(res.issues, key=lambda x: x["rule_id"])},
                   "by_handling": dict(sorted(Counter(r["handling"] for r in res.issues).items()))},
        "quarantine": {"session_keys": len(res.quarantined_keys), "session_ids": sorted({profiles[k].session_id for k in res.quarantined_keys}),
                       "keys": res.quarantined_keys, "events": len(quarantined_events), "rules": sorted({r["rule_id"] for r in res.issues if r["quarantine"]}),
                       "note": HANDLING_NOTE},
        "reconciliation": {"checks": len(res.checks), "pass": sum(c.status == "PASS" for c in res.checks), "warn": sum(c.status == "WARN" for c in res.checks), "fail": sum(c.status == "FAIL" for c in res.checks),
                           "info": sum(c.status == "INFO" for c in res.checks), "failed_checks": [c.check_id for c in res.checks if c.status == "FAIL"]},
        "events": {"staged": len(inp.events), "by_population": dict(sorted(Counter(e.population for e in inp.events).items())), "dispositions": dict(sorted(Counter(disp.values()).items())),
                   "exact_repeats": len(repeats)},
        "sessions": {"session_ids": len({p.session_id for p in profiles.values()}), "session_keys": len(profiles), "session_ids_in_both_populations": both,
                     "by_population": dict(sorted(Counter(p.population for p in profiles.values()).items()))},
        "session_level_warn_accounting": {
            "note": "validation-level reconciliation only; the metric (warn-free rate) is computed in the metric layer (WP6)",
            "eligible_primary_session_keys": len(eligible), "quarantined": len(eligible) - len(live),
            "with_session_level_warn": sum(r["session_level_warn"] for r in live), "no_session_level_warn": sum(not r["session_level_warn"] for r in live),
            "event_level_only_warn_session_ids": warn_ids, "session_level_warn_rules": list(SESSION_LEVEL_WARN_RULES), "event_level_warn_rules": list(EVENT_LEVEL_WARN_RULES)},
        "volume": {"primary_service_days": sum(1 for d in days if d.population == primary),
                   "low_observed_volume_days": sum(1 for d in days if d.population == primary and d.low_observed_volume),
                   "volume_irregularity_days": [d.service_date.isoformat() for d in days if d.population == primary and d.volume_irregularity],
                   "note": "flag only: no day is excluded; M3 is Observed Valid Sessions — Registered-Export Population, not demand"},
        "weather": {"status": res.weather_status, "error": inp.weather_error},
        "semantic_chain": ["OBSERVED component weighing events", "DERIVED selected meal weight", "UNKNOWN actual consumed quantity", "SOURCE GAP actual food waste"],
        "source_gaps": {"waste": "BLOCKED: no source of measured food waste exists in the retrieved data; nothing is inferred from any weight (rule X06)"},
    }


def run_validation(cfg: Config, out_dir: Path) -> ValidationResult:
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    res = ValidationResult()
    try:
        inp = load_staging(out_dir)
    except StagingInputError as exc:
        res.core_status, res.weather_status, res.error = "BLOCKED", "BLOCKED", str(exc)
        for name in DETERMINISTIC_FILES:                         # a stale finding must never look current
            (d / name).unlink(missing_ok=True)
        return res

    catalogue = build_catalogue(cfg)
    res.run_id = _run_id(inp, catalogue)
    repeats = find_repeats(inp.events)
    profiles = build_profiles(inp.events, repeats)
    both = rs.session_ids_in_both_populations(profiles)
    core_issues, quarantined = collect_core_issues(inp, cfg, profiles, repeats)
    dst_issues, dst_checked = rf.check_dst_round_trip(inp.events)
    days = rv.service_days(profiles, quarantined, cfg)
    disp = rc.disposition(inp.events, repeats, quarantined)

    weather_issues = rw.check_weather(inp.weather, cfg) if inp.weather is not None else []
    x07 = sum(1 for i in weather_issues if i.rule_id == "X07")
    checks = (rc.event_checks(inp, cfg, disp) + rc.session_checks(inp, cfg, profiles, both, quarantined) + rc.structure_checks(inp.events)
              + rc.name_checks(profiles, inp.events) + rc.timezone_checks(inp.events, cfg, sum(1 for i in core_issues if i.rule_id == "T10"), dst_checked, len(dst_issues))
              + rc.duplicate_checks(inp, repeats, profiles, quarantined) + rc.weather_checks(inp.weather, inp.weather_error, cfg, x07))
    checks += _baseline_check(days, cfg) + _volume_info(days, cfg)
    all_issues = core_issues + dst_issues + rv.check_volume(days, cfg) + rv.check_coverage(days, cfg) + weather_issues
    if next((c for c in checks if c.check_id == "E05" and c.status == "FAIL"), None):
        all_issues.append(Issue("C04", "population", "events", "POPULATION", "events were lost or double-counted between staging and validation", "see reconciliation E05", "events_in = modelled + duplicates_excluded + quarantined"))

    res.issues = finalise(all_issues, catalogue, res.run_id)
    res.checks = checks
    res.quarantined_keys = sorted(quarantined)
    core_blocked = any(r["handling"] == "BLOCK" and r["rule_id"] not in WEATHER_RULES for r in res.issues) or any(c.status == "FAIL" and c.area != "weather" for c in checks)
    weather_blocked = inp.weather is None or any(r["rule_id"] in WEATHER_RULES and r["handling"] == "BLOCK" for r in res.issues) or any(c.status == "FAIL" and c.area == "weather" for c in checks)
    res.core_status = "BLOCKED" if core_blocked else "PASSED_WITH_QUARANTINE" if quarantined else "PASSED"
    res.weather_status = "BLOCKED" if weather_blocked else "PASSED_WITH_WARNINGS" if any(r["rule_id"] in ("X01", "X08") for r in res.issues) else "PASSED"

    rules_by_key = _rules_by_key(res.issues, profiles)
    session_rows = _session_rows(profiles, rules_by_key, quarantined, repeats, set(both), days)
    res.summary = _summarise(res, inp, cfg, profiles, repeats, disp, session_rows, days, both)
    _write(d, res, inp, session_rows, _quarantine_manifest(res.issues, profiles, quarantined), _event_rows(inp, res.issues, disp), days)
    return res


def _baseline_check(days: list[rv.ServiceDay], cfg: Config) -> list[rc.Check]:
    primary = cfg.populations.primary.code.value
    derived = rv.derive_baseline_regimes(days, cfg, primary)
    configured = {k: v for k, v in cfg.thresholds.volume.expected_regime_by_weekday.items()}
    return [rc.eq("V01", "volume", "the weekday regimes derived from the baseline weeks equal the configured expected regimes", configured, derived, "config/thresholds.yml volume")]


def _volume_info(days: list[rv.ServiceDay], cfg: Config) -> list[rc.Check]:
    primary = cfg.populations.primary.code.value
    prim = [d for d in days if d.population == primary]
    return [rc.info("V02", "volume", "primary-population service days | low observed volume days | volume irregularity days (flag only; never excluded)",
                     f"{len(prim)} | {sum(d.low_observed_volume for d in prim)} | {sum(d.volume_irregularity for d in prim)}")]


def _write(d: Path, res: ValidationResult, inp: StagedInputs, session_rows: list, manifest: list, event_rows: list, days: list[rv.ServiceDay]) -> None:
    write_csv(d / ISSUES_CSV, res.issues, list(ISSUE_COLUMNS))
    write_csv(d / BY_RULE_CSV, _by_rule(res.issues), ["rule_id", "category", "severity", "population", "issues", "entities", "quarantine"])
    write_csv(d / RECON_CSV, [c.row() for c in res.checks], list(rc.CHECK_COLUMNS))
    write_csv(d / QUARANTINE_CSV, manifest, list(QUARANTINE_COLUMNS))
    write_csv(d / SESSION_STATUS_CSV, session_rows, list(SESSION_COLUMNS))
    write_csv(d / EVENT_STATUS_CSV, event_rows, list(EVENT_STATUS_COLUMNS))
    write_csv(d / DAYS_CSV, [{"population": x.population, "service_date": x.service_date.isoformat(), "weekday": x.weekday, "sessions": x.sessions,
                              "observed_regime": x.observed_regime, "expected_regime": x.expected_regime or "", "low_observed_volume_day": x.low_observed_volume,
                              "volume_irregularity_day": x.volume_irregularity, "source_files": ";".join(x.source_files)} for x in days], list(DAY_COLUMNS))
    write_csv(d / COMPLETENESS_CSV, rc.field_completeness(inp.events), list(rc.COMPLETENESS_COLUMNS))
    write_json(d / SUMMARY_JSON, res.summary)
    res.hashes = {n: digest_file(d / n).sha256 for n in DETERMINISTIC_FILES}
