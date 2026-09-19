"""The sensitivity analysis itself: run every registered scenario on the verified working set and assemble the evidence tables.

Order of events: (1) the baseline (S00) is recomputed and must equal the frozen approved package; (2) every scenario runs from scratch on the
same working set; (3) every scenario with an approved reference must reproduce it, otherwise the analysis FAILS with the difference
(nothing is tuned); (4) results are classified with one rule set; (5) the evidence matrix, uncertainty register and controls are built from
the computed results. The analysis reads nothing but the verified canonical tables and never writes to them.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.config import Config
from src.metrics import contracts as ct
from src.metrics.evaluate import compute_all
from src.metrics.inputs import MetricInputs
from src.sensitivity import classify as cl
from src.sensitivity.data import WorkingSet, build_working_set
from src.sensitivity.engine import ScenarioResult, run_scenario
from src.sensitivity.questions import QUESTIONS, Facts, uncertainty_rows
from src.sensitivity.registry import (APPROVED_OVERRIDE_OFFSET_HOURS, CLASSIFICATION, GUARDRAIL_IDS, REFERENCE_TOLERANCE_G, SCENARIOS, SCENARIO_BY_ID, ScenarioSpec,
                                      validate_registry)
from src.sensitivity.timezone import timezone_rows
from src.validate.reconcile import Check, eq, info

METRIC_ORDER = ("M1", "M2", "M3", "M4", "M5", "S2")
NOT_CLASSIFIED = "NOT_CLASSIFIED"
RESULT_ATTR = {"M1": "m1", "M2": "m2", "M3": "m3", "M4": "m4", "M5": "m5", "S2": "s2"}
UNITS = {"M1": "g", "M2": "g", "M3": "sessions", "M4": "components", "M5": "%", "S2": "%"}
POPULATION_LABEL = {"registered_export": "registered-export (core-ready)", "non_registered_export": "non-registered-export (diagnostic)"}


class SensitivityError(Exception):
    """The analysis cannot be trusted: the baseline moved, an approved reference no longer reproduces, or a scenario is undeclared."""


@dataclass
class Analysis:
    results: dict[str, ScenarioResult]
    metric_rows: list[dict[str, Any]]
    result_rows: list[dict[str, Any]]
    timezone: list[dict[str, Any]]
    ranges: dict[str, dict[str, Any]]
    biggest: dict[str, dict[str, Any]]
    matrix: list[dict[str, Any]]
    register: list[dict[str, Any]]
    checks: list[Check]
    reference_mismatches: list[str] = field(default_factory=list)
    baseline_problems: list[str] = field(default_factory=list)
    eligible: int = 0

    @property
    def failed(self) -> bool:
        return bool(self.baseline_problems or self.reference_mismatches or any(c.status == "FAIL" for c in self.checks))


def value_of(r: ScenarioResult, metric: str) -> float | None:
    return getattr(r, RESULT_ATTR[metric])


def defined_metrics(spec: ScenarioSpec) -> list[str]:
    return [m for m in METRIC_ORDER if m in spec.metrics_recalculated]


def is_comparable(spec: ScenarioSpec) -> bool:
    """Registered-export scenarios only: the diagnostic population contrast and the forbidden guardrail are reported but never classified or ranged."""
    return spec.scenario_id not in GUARDRAIL_IDS and spec.scenario_id != "S40"


# ---- baseline freeze and profiling reproduction --------------------------------------------------------------------------------------------------
def baseline_problems(base: ScenarioResult, inp: MetricInputs, ws: WorkingSet) -> list[str]:
    """The S00 recomputation must equal the frozen approved package AND the independent metrics computation."""
    problems = []
    c = ct.CONTRACTS
    recomputed = compute_all(inp)
    checks = (("M1", base.m1, c["M1"].approved_value, c["M1"].tolerance, recomputed["M1"].value), ("M2", base.m2, c["M2"].approved_value, c["M2"].tolerance, recomputed["M2"].value),
              ("M3", base.m3, c["M3"].approved_value, 0, recomputed["M3"].value), ("M4", base.m4, c["M4"].approved_value, 0, recomputed["M4"].value),
              ("M5", base.m5, c["M5"].approved_value, c["M5"].tolerance, recomputed["M5"].value), ("S2", base.s2, c["S2"].approved_value, c["S2"].tolerance, recomputed["S2"].value))
    for name, got, approved, tol, independent in checks:
        if abs(got - approved) > tol:
            problems.append(f"{name}: baseline {got} differs from the approved {approved} (tolerance {tol})")
        if abs(got - independent) > 1e-9:
            problems.append(f"{name}: baseline {got} differs from the metrics computation {independent}")
    if (base.m5_numerator, base.m5_denominator) != (1697, 1699) or ws.eligible != 1699:
        problems.append(f"M5 counts {base.m5_numerator}/{base.m5_denominator} differ from the approved 1697/1699")
    if base.s2_numerator != 1663:
        problems.append(f"S2 numerator {base.s2_numerator} differs from the approved 1663")
    return problems


def reference_mismatches(results: dict[str, ScenarioResult]) -> list[str]:
    out = []
    for spec in SCENARIOS:
        ref = spec.reference
        if ref is None:
            continue
        r = results[spec.scenario_id]
        bad = []
        if abs(r.m1 - ref[0]) > REFERENCE_TOLERANCE_G:
            bad.append(f"M1 {r.m1} vs {ref[0]}")
        if abs(r.m2 - ref[1]) > REFERENCE_TOLERANCE_G:
            bad.append(f"M2 {r.m2:.3f} vs {ref[1]}")
        if r.m3 != ref[2]:
            bad.append(f"M3 {r.m3} vs {ref[2]}")
        if r.m4 != ref[3]:
            bad.append(f"M4 {r.m4} vs {ref[3]}")
        if ref[4] is not None and r.m5_numerator != ref[4]:
            bad.append(f"M5 numerator {r.m5_numerator} vs {ref[4]}")
        if bad:
            out.append(f"{spec.scenario_id}: " + "; ".join(bad))
    return out


# ---- tables -------------------------------------------------------------------------------------------------------------------------------------------
def _metric_rows(results: dict[str, ScenarioResult]) -> list[dict[str, Any]]:
    base = results["S00"]
    rows = []
    for metric in METRIC_ORDER:
        for spec in SCENARIOS:
            if metric not in spec.metrics_recalculated:
                continue
            r = results[spec.scenario_id]
            b, v = value_of(base, metric), value_of(r, metric)
            absolute, relative = cl.deltas(metric, b, v)
            rows.append({"metric_id": metric, "scenario_id": spec.scenario_id, "baseline_value": round(b, 6), "scenario_value": round(v, 6), "absolute_delta": round(absolute, 6),
                         "relative_delta": round(relative, 6), "population": POPULATION_LABEL.get(spec.affected_population, spec.affected_population),
                         "interpretation": spec.interpretation, "robustness_class": cl.classify(metric, b, v) if is_comparable(spec) else NOT_CLASSIFIED})
    rows.append({"metric_id": "W1", "scenario_id": "S00", "baseline_value": None, "scenario_value": None, "absolute_delta": None, "relative_delta": None, "population": "n/a",
                 "interpretation": "BLOCKED / SOURCE GAP: no scenario can turn missing source data into observed evidence; no waste estimate, band or proxy is produced.",
                 "robustness_class": "BLOCKED"})
    return rows


def _result_rows(results: dict[str, ScenarioResult], metric_rows: list[dict[str, Any]], mism: list[str]) -> list[dict[str, Any]]:
    base = results["S00"]
    by_scenario: dict[str, list[str]] = {}
    for m in metric_rows:
        if m["robustness_class"] not in (NOT_CLASSIFIED, "BLOCKED"):
            by_scenario.setdefault(m["scenario_id"], []).append(m["robustness_class"])
    bad_ids = {x.split(":")[0] for x in mism}
    rows = []
    for spec in SCENARIOS:
        r = results[spec.scenario_id]
        row: dict[str, Any] = {"scenario_id": spec.scenario_id, "group": spec.group, "name": spec.name, "assumption_changed": spec.assumption_changed,
                               "baseline_assumption": spec.baseline_assumption, "alternative_assumption": spec.alternative_assumption, "rationale": spec.rationale,
                               "affected_tables": ";".join(spec.affected_tables), "affected_population": spec.affected_population, "metrics_recalculated": ";".join(spec.metrics_recalculated),
                               "sessions": r.sessions, "m1_g": r.m1, "m2_g": round(r.m2, 3), "m3_sessions": r.m3, "m4_components": r.m4,
                               "m5_pct": None if r.m5 is None else round(r.m5, 3), "m5_numerator": r.m5_numerator, "m5_denominator": r.m5_denominator,
                               "s2_pct": None if r.s2 is None else round(r.s2, 3)}
        for metric, key in (("M1", "m1_g"), ("M2", "m2_g"), ("M3", "m3_sessions"), ("M4", "m4_components"), ("M5", "m5_pct"), ("S2", "s2_pct")):
            b, v = value_of(base, metric), value_of(r, metric)
            if v is None:
                row[f"d_{key}"], row[f"pct_d_{key}"] = None, None
            else:
                absolute, relative = cl.deltas(metric, b, v)
                row[f"d_{key}"], row[f"pct_d_{key}"] = round(absolute, 3), round(100 * relative, 3)
        row.update({"defensible": spec.defensible, "diagnostic_only": spec.diagnostic_only, "forbidden": spec.forbidden, "interpretation": spec.interpretation,
                    "decision_impact": spec.decision_impact,
                    "worst_robustness_class": cl.worst(by_scenario[spec.scenario_id]) if spec.scenario_id in by_scenario else NOT_CLASSIFIED,
                    "reference_status": "n/a" if spec.reference is None else ("MISMATCH" if spec.scenario_id in bad_ids else "reproduced"),
                    "detail": json.dumps(r.detail, sort_keys=True)})
        rows.append(row)
    return rows


def _ranges(results: dict[str, ScenarioResult], metric_rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    ranges, biggest = {}, {}
    for metric in METRIC_ORDER:
        comparable = [(spec.scenario_id, value_of(results[spec.scenario_id], metric)) for spec in SCENARIOS if is_comparable(spec) and metric in spec.metrics_recalculated]
        defensible = [(sid, v) for sid, v in comparable if SCENARIO_BY_ID[sid].defensible]
        vals, dvals = [v for _, v in comparable], [v for _, v in defensible]
        rows = [m for m in metric_rows if m["metric_id"] == metric and m["robustness_class"] != NOT_CLASSIFIED]
        top_abs = max(rows, key=lambda m: (abs(m["absolute_delta"]), m["scenario_id"]))
        top_rel = max(rows, key=lambda m: (abs(m["relative_delta"]), m["scenario_id"]))
        ranges[metric] = {"min": round(min(vals), 6), "max": round(max(vals), 6), "scenarios": len(vals), "defensible_min": round(min(dvals), 6), "defensible_max": round(max(dvals), 6),
                          "defensible_scenarios": len(dvals), "unit": UNITS[metric], "baseline": round(value_of(results["S00"], metric), 6)}
        biggest[metric] = {"largest_absolute": {"scenario_id": top_abs["scenario_id"], "delta": top_abs["absolute_delta"], "relative": top_abs["relative_delta"]},
                           "largest_relative": {"scenario_id": top_rel["scenario_id"], "delta": top_rel["absolute_delta"], "relative": top_rel["relative_delta"]}}
    return ranges, biggest


def _matrix(facts: Facts, metric_rows: list[dict[str, Any]], all_ids: list[str]) -> list[dict[str, Any]]:
    out = []
    for q in QUESTIONS:
        ids = [s for s in all_ids if is_comparable(SCENARIO_BY_ID[s])] if q.scenarios == ("ALL",) else list(q.scenarios)
        rows = [m for m in metric_rows if m["metric_id"] in q.metrics and m["scenario_id"] in ids and m["scenario_id"] != "S00"]
        if q.rule == "blocked":
            robustness, observed, basis = q.declared_class or "BLOCKED", "not testable: " + q.basis, q.basis
        else:
            observed = "; ".join(f"{metric} {value_of(facts.results['S00'], metric):,.1f} -> {facts.ranges[metric]['min']:,.1f} to {facts.ranges[metric]['max']:,.1f}" if q.scenarios == ("ALL",) else
                                 f"{metric}: " + ", ".join(f"{m['scenario_id']} {m['absolute_delta']:+,.2f}" for m in rows if m["metric_id"] == metric)
                                 for metric in q.metrics)
            worst_row = max(rows, key=lambda m: (("STABLE", "SENSITIVE", "CONDITIONAL").index(m["robustness_class"]), abs(m["relative_delta"]))) if rows else None
            if q.rule == "worst":
                robustness = cl.worst([m["robustness_class"] for m in rows])
                basis = f"worst over {len(rows)} metric-scenario cells" + (f" (driven by {worst_row['metric_id']} in {worst_row['scenario_id']})" if worst_row and robustness != "STABLE" else "")
            else:
                robustness, basis = q.declared_class or "STABLE", q.basis
        out.append({"Question": q.question, "Baseline evidence": q.baseline_evidence(facts), "Sensitivity tested": q.sensitivity_tested, "Observed range/change": observed or "not testable",
                    "Robustness": robustness, "What can be concluded": q.can_conclude, "What cannot be concluded": q.cannot_conclude, "Next evidence needed": q.next_evidence,
                    "question_id": q.question_id, "robustness_basis": basis})
    return out


# ---- controls -------------------------------------------------------------------------------------------------------------------------------------------
def _controls(results: dict[str, ScenarioResult], ws: WorkingSet, cfg: Config, metric_rows: list[dict[str, Any]], tz: list[dict[str, Any]], bp: list[str], mism: list[str],
              before: tuple, after: tuple) -> list[Check]:
    ids = [s.scenario_id for s in SCENARIOS]
    denominators = {r.m5_denominator for r in results.values() if r.m5_denominator is not None}
    quarantined_registered = sum(a.quarantined and a.population == "registered_export" for a in ws.aggs.values())
    shifted = {f for r in results.values() for f in r.detail.get("files_shifted", [])}
    return [
        eq("SC01", "scenarios", "every registered scenario was executed exactly once", ids, sorted(results, key=ids.index), "registry"),
        eq("SC02", "baseline", "the recomputed baseline equals the frozen approved package and the independent metrics computation", [], bp, "approved baseline"),
        eq("SC03", "baseline", "every approved reference scenario reproduces (M1, M2, M3, M4, M5 numerator)", [], mism, "approved profiling sensitivity"),
        eq("SC04", "baseline", "running every scenario leaves the baseline working set untouched (fingerprint of every baseline session)", _digest(before), _digest(after), "purity"),
        eq("SC05", "timezone", "only the override file(s) in the configuration are shifted", sorted(cfg.timezone.overrides), sorted(shifted), "file-specific override"),
        eq("SC06", "timezone", "the +3h scenario reproduces the baseline exactly", (results["S00"].m1, results["S00"].m2, results["S00"].m3), (results["TZ3"].m1, results["TZ3"].m2, results["TZ3"].m3), "approved decision"),
        eq("SC07", "baseline", "M5's denominator is the fixed 1,699 in every scenario that defines M5", {1699}, denominators, "approved denominator rule"),
        eq("SC08", "baseline", "both quarantined registered-export sessions remain quarantined and eligible in the baseline", 2, quarantined_registered, "quarantine policy"),
        eq("SC09", "guardrail", "the forbidden pooled comparison is never classified", {NOT_CLASSIFIED}, {m["robustness_class"] for m in metric_rows if m["scenario_id"] in GUARDRAIL_IDS}, "population separation"),
        eq("SC10", "timezone", "the configured override offset is the approved +3h (an alternative offset is tested, never adopted)", [APPROVED_OVERRIDE_OFFSET_HOURS],
           sorted({o.offset_hours for o in cfg.timezone.overrides.values()}), "approved decision"),
        eq("SC11", "timezone", "at the baseline offset no session changes weather hour", 0, next(r["weather_hour_changed_sessions"] for r in tz if r["is_baseline"]), "identity"),
        eq("SC12", "semantics", "no output metric is about waste or consumption other than the blocked W1", [], sorted(m["metric_id"] for m in metric_rows if m["metric_id"] not in METRIC_ORDER + ("W1",)), "semantic chain"),
        info("SC13", "scenarios", "scenarios executed | of which comparable registered-export | diagnostic-only | forbidden", f"{len(results)} | {sum(is_comparable(s) for s in SCENARIOS)} | {sum(s.diagnostic_only for s in SCENARIOS)} | {sum(s.forbidden for s in SCENARIOS)}"),
    ]


def _digest(fingerprint: tuple) -> str:
    return hashlib.sha256(repr(fingerprint).encode("utf-8")).hexdigest()[:16]


def _fingerprint(ws: WorkingSet) -> tuple:
    return tuple((a.key, a.weight, a.w_nonrepeat, len(a.comps_norm), a.n_modellable, a.core_ready) for a in ws.baseline) + (ws.eligible,)


def run_analysis(inp: MetricInputs, cfg: Config) -> Analysis:
    problems = validate_registry()
    if problems:
        raise SensitivityError("the scenario registry is invalid: " + "; ".join(problems))
    ws = build_working_set(inp, cfg)
    before = _fingerprint(ws)
    results = {s.scenario_id: run_scenario(s, ws, cfg) for s in SCENARIOS}
    after = _fingerprint(ws)
    bp = baseline_problems(results["S00"], inp, ws)
    mism = reference_mismatches(results)
    tz = timezone_rows(ws, cfg)
    metric_rows = _metric_rows(results)
    ranges, biggest = _ranges(results, metric_rows)
    facts = Facts(results, ranges, tz)
    all_ids = [s.scenario_id for s in SCENARIOS]
    return Analysis(results, metric_rows, _result_rows(results, metric_rows, mism), tz, ranges, biggest, _matrix(facts, metric_rows, all_ids), uncertainty_rows(facts),
                    _controls(results, ws, cfg, metric_rows, tz, bp, mism, before, after), mism, bp, ws.eligible)
