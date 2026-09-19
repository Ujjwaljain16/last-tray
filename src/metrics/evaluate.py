"""Metric orchestration and PRESENTATION: canonical tables in, metric rows, contracts, controls, evidence table and report out. Offline.

Three separate layers: compute.py calculates, contracts.py declares meaning and limits, and this module joins them, judges each result
against the approved value and tolerance, and writes the files. A metric that misses its tolerance is reported FAILED with the exact
difference; nothing is recalibrated. Reads only the canonical model tables (never staging or raw files).

Not here: sensitivity analysis, thresholds, population redefinition, a dashboard, a waste estimate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.fsutil import atomic_write_text
from src.ingest.hashing import digest_file
from src.ingest.manifest import write_csv, write_json
from src.metrics import compute, contracts as ct
from src.metrics.controls import all_controls
from src.metrics.inputs import MetricInputError, MetricInputs, load_metric_inputs
from src.metrics.populations import POPULATIONS
from src.validate.reconcile import Check

OUT_SUBDIR = "metrics"
METRICS_CSV = "metrics.csv"
EVIDENCE_CSV = "metric_evidence.csv"
SUMMARY_JSON = "metric_summary.json"
CONTRACTS_JSON = "metric_contracts.json"
REPORT_MD = "metrics_report.md"
CONTROLS_CSV = "metric_controls.csv"
DETERMINISTIC_FILES = (METRICS_CSV, EVIDENCE_CSV, SUMMARY_JSON, CONTRACTS_JSON, REPORT_MD, CONTROLS_CSV)

# The approved numerators and the FIXED denominators of the ratio metrics (docs/metric_contract.md). Changing a denominator changes the meaning.
APPROVED_COUNTS = {"M5": (1697, 1699), "S1": (1697, 1699), "S2": (1663, 1699), "S2D": (1660, 1699)}

METRIC_COLUMNS = ("metric_id", "metric_name", "role", "value", "value_display", "unit", "population", "population_definition", "grain", "numerator", "denominator",
                  "n_used", "n_excluded_vs_eligible", "formula", "source_tables", "source_snapshot_id", "approved_value", "tolerance", "status", "evidence_status",
                  "interpretation", "limitation")
EVIDENCE_COLUMNS = ("Metric", "Value", "Population", "Grain", "What it tells us", "What it does NOT tell us", "records_used", "records_excluded", "evidence_status")
CONTROL_COLUMNS = ("check_id", "area", "description", "expected", "observed", "status", "basis")

NEGATIONS = ("not ", "no ", "never", "cannot", "neither", "without")


class MetricContractError(Exception):
    """The metric layer was asked to do something its contracts forbid (implicit population, waste proxy, changed denominator...)."""


@dataclass
class MetricsResult:
    core_status: str = "PASSED"            # PASSED | FAILED | BLOCKED
    weather_status: str = "PASSED"         # PASSED | BLOCKED
    error: str | None = None
    results: dict[str, compute.MetricResult] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    contracts_out: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)


# ---- judging a result against its contract ----------------------------------------------------------------------------------------------------
def population_matches(contract: ct.MetricContract, r: compute.MetricResult) -> bool:
    if contract.metric_id == "M5":
        return r.population == contract.numerator_population and r.detail.get("denominator_population") == contract.population
    return r.population == contract.population


def judge(contract: ct.MetricContract, r: compute.MetricResult) -> tuple[str, list[str]]:
    """PASS or FAIL against the approved value, tolerance, population and (for ratios) the approved counts."""
    problems: list[str] = []
    if not population_matches(contract, r):
        problems.append(f"population {r.population!r} is not the contract's")
    if contract.approved_value is None or r.value is None:
        return "FAIL", ["no value to judge"] + problems
    if abs(r.value - contract.approved_value) > contract.tolerance:
        problems.append(f"value {r.value:.6f} differs from the approved {contract.approved_value} by {abs(r.value - contract.approved_value):.6f} (tolerance {contract.tolerance})")
    if contract.metric_id in APPROVED_COUNTS and (r.numerator, r.denominator) != APPROVED_COUNTS[contract.metric_id]:
        problems.append(f"counts {r.numerator}/{r.denominator} differ from the approved {APPROVED_COUNTS[contract.metric_id][0]}/{APPROVED_COUNTS[contract.metric_id][1]}")
    return ("FAIL" if problems else "PASS"), problems


def assert_no_waste_metric(rows: list[dict[str, Any]]) -> None:
    """Invariant: the only waste-related row is W1, it is BLOCKED and it has no value. Any other waste, consumption or leftover row is refused."""
    for r in rows:
        name = f"{r.get('metric_id', '')} {r.get('metric_name', '')}".lower()
        related = any(w in name for w in ("waste", "consum", "leftover", "intake"))
        if r.get("metric_id") == "W1":
            if r.get("status") != "BLOCKED" or r.get("value") not in (None, ""):
                raise MetricContractError("W1 must be BLOCKED with no value: no waste figure may be produced")
        elif related:
            raise MetricContractError(f"{r.get('metric_id')}: a waste, consumption or leftover metric is not permitted (SOURCE GAP)")


# ---- computation driver -------------------------------------------------------------------------------------------------------------------------
def compute_all(inp: MetricInputs) -> dict[str, compute.MetricResult]:
    """Every metric on the population its contract names."""
    c = ct.CONTRACTS
    s = inp.sessions
    res = {
        "M1": compute.m1_median_selected_weight(s, c["M1"].population),
        "M2": compute.m2_p90_selected_weight(s, c["M2"].population),
        "M3": compute.m3_observed_valid_sessions(s, c["M3"].population),
        "M4": compute.m4_median_distinct_components(s, c["M4"].population),
        "M5": compute.m5_core_readiness(s, c["M5"].numerator_population, c["M5"].population),
        "S2": compute.s2_warn_free_rate(s, c["S2"].population),
        "S2D": compute.s2_warn_free_rate(s, c["S2D"].population, include_event_level=True),
    }
    if inp.weather is not None:
        res["S1"] = compute.s1_weather_coverage(s, c["S1"].population)
    return res


# ---- presentation ---------------------------------------------------------------------------------------------------------------------------------
def _display(metric_id: str, r: compute.MetricResult | None) -> str:
    if r is None or r.value is None:
        return "BLOCKED / SOURCE GAP" if metric_id == "W1" else "BLOCKED"
    if metric_id == "M1":
        return f"{r.value:,.0f} g" if float(r.value).is_integer() else f"{r.value:,.1f} g"
    if metric_id == "M2":
        return f"{r.value:,.1f} g"
    if metric_id == "M3":
        return f"{r.value:,} sessions"
    if metric_id == "M4":
        return f"{r.value:g} components"
    return f"{r.value:.2f}%"


def _value(r: compute.MetricResult | None) -> Any:
    if r is None or r.value is None:
        return None
    return r.value if isinstance(r.value, int) else round(float(r.value), 6)


def build_rows(inp: MetricInputs, results: dict[str, compute.MetricResult], verdicts: dict[str, tuple[str, list[str]]], eligible: int) -> list[dict[str, Any]]:
    rows = []
    for mid in ct.ORDER:
        c = ct.CONTRACTS[mid]
        r = results.get(mid)
        status = "BLOCKED" if mid == "W1" or (r is None) else verdicts[mid][0]
        pop = c.population if mid != "W1" else "n/a"
        rows.append({
            "metric_id": mid, "metric_name": c.metric_name, "role": c.role, "value": _value(r), "value_display": _display(mid, r), "unit": c.unit,
            "population": pop, "population_definition": POPULATIONS[pop].definition if pop in POPULATIONS else c.population_rationale, "grain": c.grain,
            "numerator": r.numerator if r else None, "denominator": r.denominator if r else None, "n_used": r.n_used if r else None,
            "n_excluded_vs_eligible": (eligible - r.n_used) if r else None, "formula": c.formula, "source_tables": ";".join(c.source_tables),
            "source_snapshot_id": inp.snapshot_id if c.source_tables else None, "approved_value": c.approved_value, "tolerance": c.tolerance, "status": status,
            "evidence_status": c.evidence_status if status != "BLOCKED" or mid == "W1" else "BLOCKED", "interpretation": c.interpretation, "limitation": c.limitation,
        })
    return rows


def build_evidence(inp: MetricInputs, results: dict[str, compute.MetricResult], eligible: int) -> list[dict[str, Any]]:
    def line(mid: str, shown: str | None = None) -> dict[str, Any]:
        c, r = ct.CONTRACTS[mid], results.get(mid)
        value = shown or (_display(mid, r) + (f" ({r.numerator:,} / {r.denominator:,})" if r and r.numerator is not None else ""))
        return {"Metric": f"{mid} {c.metric_name}", "Value": value, "Population": (POPULATIONS[c.population].name if mid != "W1" else "n/a"),
                "Grain": c.grain, "What it tells us": c.tells_us, "What it does NOT tell us": c.does_not_tell_us, "records_used": r.n_used if r else None,
                "records_excluded": (eligible - r.n_used) if r else None, "evidence_status": c.evidence_status if (r or mid == "W1") else "BLOCKED"}

    rows = [line(m) for m in ("M1", "M2", "M3", "M4", "M5", "S1", "S2")]
    rows.append(line("W1"))
    quarantined = [s for s in inp.sessions if s.is_quarantined]
    days = [r for r in inp.daily_volume if r["is_primary_population"] == "true"]
    rows.append({"Metric": "Q Quarantined session keys", "Value": f"{len(quarantined)} keys ({len({s.session_id for s in quarantined})} session ids)",
                 "Population": POPULATIONS[ct.A].name, "Grain": "one session key",
                 "What it tells us": "Session ids present in both exports are kept in every table, listed, and excluded from the KPIs; neither version is preferred.",
                 "What it does NOT tell us": "That either version is correct, or that the remaining sessions are free of problems.", "records_used": len(quarantined),
                 "records_excluded": None, "evidence_status": "READY_WITH_LIMITATION"})
    rows.append({"Metric": "V Observed volume regime flags (flag only)",
                 "Value": f"{len(days)} service days; {sum(r['low_observed_volume_day'] == 'true' for r in days)} low-volume; {sum(r['volume_irregularity'] == 'true' for r in days)} differ from the weekday baseline",
                 "Population": POPULATIONS[ct.D].name, "Grain": "one service date x population",
                 "What it tells us": "On some days the observed volume regime differs from that weekday's baseline regime; every such day stays included.",
                 "What it does NOT tell us": "Demand, or that those days are data errors; the cause is unresolved.", "records_used": len(days), "records_excluded": 0,
                 "evidence_status": "READY_WITH_LIMITATION"})
    return rows


def contracts_with_results(results: dict[str, compute.MetricResult], verdicts: dict[str, tuple[str, list[str]]]) -> list[dict[str, Any]]:
    out = []
    for mid in ct.ORDER:
        d = ct.CONTRACTS[mid].as_dict()
        r = results.get(mid)
        d.update({"computed_value": _value(r), "computed_numerator": r.numerator if r else None, "computed_denominator": r.denominator if r else None,
                  "n_used": r.n_used if r else None, "n_null_excluded": r.n_null_excluded if r else None, "computed_detail": _plain(r.detail) if r else None,
                  "pass_fail": "BLOCKED" if mid == "W1" or r is None else verdicts[mid][0], "problems": verdicts[mid][1] if mid in verdicts else []})
        out.append(d)
    return out


def _plain(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    return x


def _report(res: MetricsResult, inp: MetricInputs) -> str:
    rows = {r["metric_id"]: r for r in res.rows}
    md = ["# Metrics report", "",
          "Generated by `python -m src.pipeline.run --stages metrics` from the canonical model. Every number below is an observation or a derived value; "
          "none is a measure of consumption or food waste.", "",
          "**Semantic chain.** OBSERVED component weighing events -> DERIVED selected meal weight -> UNKNOWN actual consumed quantity -> SOURCE GAP actual food waste.", "",
          "## Evidence table", "", "| " + " | ".join(EVIDENCE_COLUMNS[:6]) + " |", "|" + "---|" * 6]
    md += ["| " + " | ".join(str(e[c]).replace("|", "/") for c in EVIDENCE_COLUMNS[:6]) + " |" for e in res.evidence]
    md += ["", "## Metric results", "", "| Metric | Value | Approved | Tolerance | Status | Population |", "|---|---|---|---|---|---|"]
    for mid in ct.ORDER:
        r = rows[mid]
        md.append(f"| {mid} {r['metric_name']} | {r['value_display']} | {r['approved_value'] if r['approved_value'] is not None else 'n/a'} | "
                  f"{r['tolerance'] if r['tolerance'] is not None else 'n/a'} | {r['status']} | {r['population']} |")
    md += ["", "## Populations", "", "| | Population | Definition | Sessions |", "|---|---|---|---:|"]
    for p in POPULATIONS.values():
        md.append(f"| {p.letter} | `{p.name}` | {p.definition} | {sum(1 for s in inp.sessions if p.member(s)):,} |")
    m5 = res.results.get("M5")
    md += ["", "## Why M5 and S2 differ", "",
           f"M5 counts core-ready sessions ({m5.numerator:,} of {m5.denominator:,}); the two missing sessions are the quarantined crossover sessions. "
           "S2 also excludes sessions that carry a session-level warning (B04, B07, T04, T05, I06), which stay in every KPI. "
           "A warning is a diagnostic flag, not a failure, so S2 is lower than M5 without any session being removed. Neither is a measure of accuracy.", "",
           "## W1 Direct Food Waste Measurement: BLOCKED / SOURCE GAP", "",
           "The Flavoria system documents lunch-line waste measurement keyed on tray, but the public data available to this project does not contain those records. "
           "No direct waste metric is computed. The derived selected meal weight is not waste, and no proxy is estimated from weight, components, duration, weather or anything else.", "",
           "## Controls", "", f"{sum(c.status == 'PASS' for c in res.checks)} pass, {sum(c.status == 'FAIL' for c in res.checks)} fail, {sum(c.status == 'INFO' for c in res.checks)} info. See `metric_controls.csv`.", ""]
    return "\n".join(md)


def _has_banned_affirmative(text: str, banned: tuple[str, ...]) -> list[str]:
    hits = []
    for sentence in text.replace("\n", " ").split(". "):
        low = sentence.lower()
        if any(n in low for n in NEGATIONS):
            continue
        hits += [b for b in banned if b in low]
    return hits


# ---- the stage ------------------------------------------------------------------------------------------------------------------------------------
def run_metrics(cfg: Config, out_dir: Path) -> MetricsResult:
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    res = MetricsResult()
    try:
        inp = load_metric_inputs(out_dir)
    except MetricInputError as exc:
        res.core_status, res.weather_status, res.error = "BLOCKED", "BLOCKED", str(exc)
        for n in DETERMINISTIC_FILES:                         # a stale metric must never look current
            (d / n).unlink(missing_ok=True)
        return res

    gap = cfg.sources.gaps.get("waste")
    if gap is not None and gap.status != "BLOCKED":
        raise MetricContractError(f"config lists the waste source as {gap.status}: W1 must stay BLOCKED until an actual public waste dataset is found and reviewed")
    res.results = compute_all(inp)
    eligible = len([s for s in inp.sessions if s.population == "registered_export"])
    verdicts = {mid: judge(ct.CONTRACTS[mid], r) for mid, r in res.results.items()}
    res.checks = all_controls(inp, res.results)
    res.rows = build_rows(inp, res.results, verdicts, eligible)
    assert_no_waste_metric(res.rows)
    res.evidence = build_evidence(inp, res.results, eligible)
    res.contracts_out = contracts_with_results(res.results, verdicts)
    res.weather_status = "PASSED" if inp.weather is not None else "BLOCKED"
    failed = sorted(m for m, (v, _) in verdicts.items() if v == "FAIL")
    control_failed = [c.check_id for c in res.checks if c.status == "FAIL" and c.area != "weather"]
    res.core_status = "FAILED" if failed or control_failed else "PASSED"

    res.summary = {
        "stage": "metrics", "core_status": res.core_status, "weather_status": res.weather_status, "source_snapshot_id": inp.snapshot_id,
        "model_manifest_inputs": inp.manifest["inputs"], "metrics": {r["metric_id"]: {"value": r["value"], "display": r["value_display"], "status": r["status"], "population": r["population"],
                                                                                     "numerator": r["numerator"], "denominator": r["denominator"]} for r in res.rows},
        "populations": {p.name: {"letter": p.letter, "sessions": sum(1 for s in inp.sessions if p.member(s))} for p in POPULATIONS.values()},
        "failed_metrics": failed, "problems": {m: p for m, (v, p) in sorted(verdicts.items()) if p},
        "controls": {"checks": len(res.checks), "pass": sum(c.status == "PASS" for c in res.checks), "fail": sum(c.status == "FAIL" for c in res.checks),
                     "info": sum(c.status == "INFO" for c in res.checks), "failed_checks": [c.check_id for c in res.checks if c.status == "FAIL"]},
        "supporting_detail": {"M3_by_service_date": res.results["M3"].detail["by_service_date"], "M4_distribution": {str(k): v for k, v in res.results["M4"].detail["distribution"].items()},
                              "M1_min_max": [res.results["M1"].detail["min"], res.results["M1"].detail["max"]], "S1_join_status": res.results["S1"].detail["join_status"] if "S1" in res.results else None},
        "semantic_chain": ["OBSERVED component weighing events", "DERIVED selected meal weight", "UNKNOWN actual consumed quantity", "SOURCE GAP actual food waste"],
        "waste": "W1 BLOCKED / SOURCE GAP: no direct waste records are available; nothing is estimated from any weight or other proxy",
        "percentile_method": "linear interpolation at position (n - 1) * q (numpy/pandas default, R type 7)",
    }

    write_csv(d / METRICS_CSV, res.rows, list(METRIC_COLUMNS))
    write_csv(d / EVIDENCE_CSV, res.evidence, list(EVIDENCE_COLUMNS))
    write_csv(d / CONTROLS_CSV, [c.row() for c in res.checks], list(CONTROL_COLUMNS))
    write_json(d / CONTRACTS_JSON, res.contracts_out)
    write_json(d / SUMMARY_JSON, res.summary)
    atomic_write_text(d / REPORT_MD, _report(res, inp))
    res.hashes = {n: digest_file(d / n).sha256 for n in DETERMINISTIC_FILES}
    return res
