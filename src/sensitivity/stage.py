"""Sensitivity stage (WP7): verified canonical tables in, evidence artifacts out. Offline; writes only under outputs/evidence/.

Blocked on missing or altered canonical inputs (stale outputs removed). FAILED if the baseline moved or an approved Phase 2 reference no
longer reproduces (the artifacts are still written so the difference is visible; nothing is tuned).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import Config
from src.ingest.hashing import digest_file
from src.ingest.manifest import write_csv, write_json
from src.metrics.inputs import MetricInputError, load_metric_inputs
from src.sensitivity.evidence import Analysis, run_analysis
from src.sensitivity.figures import FIGURES, write_figures
from src.sensitivity.registry import CLASSIFICATION, GUARDRAIL_IDS, SCENARIOS

OUT_SUBDIR = "evidence"
REGISTRY_JSON, REGISTRY_CSV = "scenario_registry.json", "scenario_registry.csv"
RESULTS_CSV, METRIC_CSV, TZ_CSV = "sensitivity_results.csv", "metric_sensitivity.csv", "timezone_evidence.csv"
MATRIX_CSV, REGISTER_CSV = "evidence_matrix.csv", "uncertainty_register.csv"
SUMMARY_JSON, CONTROLS_CSV = "sensitivity_summary.json", "sensitivity_controls.csv"
FIGURE_DIR = "figures"
DETERMINISTIC_FILES = (REGISTRY_JSON, REGISTRY_CSV, RESULTS_CSV, METRIC_CSV, TZ_CSV, MATRIX_CSV, REGISTER_CSV, SUMMARY_JSON, CONTROLS_CSV, *[f"{FIGURE_DIR}/{f}" for f in FIGURES])

METRIC_COLUMNS = ("metric_id", "scenario_id", "baseline_value", "scenario_value", "absolute_delta", "relative_delta", "population", "interpretation", "robustness_class")
MATRIX_COLUMNS = ("Question", "Baseline evidence", "Sensitivity tested", "Observed range/change", "Robustness", "What can be concluded", "What cannot be concluded", "Next evidence needed")
REGISTER_COLUMNS = ("uncertainty_id", "assumption", "why_it_matters", "current_evidence", "sensitivity_result", "impact_level", "affected_metrics", "current_disposition", "evidence_that_would_resolve")
CONTROL_COLUMNS = ("check_id", "area", "description", "expected", "observed", "status", "basis")
REGISTRY_CSV_COLUMNS = ("scenario_id", "group", "name", "assumption_changed", "baseline_assumption", "alternative_assumption", "rationale", "affected_tables", "affected_population",
                        "metrics_recalculated", "operation", "interpretation", "decision_impact", "defensible", "diagnostic_only", "forbidden")
TZ_COLUMNS = ("offset_hours", "is_baseline", "sessions_in_shifted_file", "t03_quarantined_sessions", "median_first_event_hour", "other_registered_files_median_hour", "gap_to_other_files_h",
              "inside_t07_band", "weather_hour_changed_sessions", "mean_abs_t2m_diff_c", "rainy_hour_share_pct")


@dataclass
class SensitivityResult:
    core_status: str = "PASSED"            # PASSED | FAILED | BLOCKED
    error: str | None = None
    analysis: Analysis | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)


def _remove(d: Path) -> None:
    for n in DETERMINISTIC_FILES:
        (d / n).unlink(missing_ok=True)


def _summary(a: Analysis, status: str) -> dict[str, Any]:
    base = a.results["S00"]
    classes: dict[str, int] = {}
    for r in a.matrix:
        classes[r["Robustness"]] = classes.get(r["Robustness"], 0) + 1
    return {
        "stage": "sensitivity", "core_status": status,
        "baseline": {"M1": base.m1, "M2": round(base.m2, 6), "M3": base.m3, "M4": base.m4, "M5": round(base.m5, 6), "M5_numerator": base.m5_numerator, "M5_denominator": base.m5_denominator,
                     "S2": round(base.s2, 6), "S2_numerator": base.s2_numerator, "W1": "BLOCKED / SOURCE GAP", "frozen": True},
        "scenarios": {"registered": len(SCENARIOS), "guardrail": list(GUARDRAIL_IDS), "diagnostic_only": sum(s.diagnostic_only for s in SCENARIOS),
                      "defensible": sum(s.defensible for s in SCENARIOS), "phase2_reproduced": sum(s.phase2 is not None for s in SCENARIOS) - len(a.phase2_mismatches)},
        "phase2_mismatches": a.phase2_mismatches, "baseline_problems": a.baseline_problems,
        "ranges": a.ranges, "biggest_changes": a.biggest, "classification_thresholds": CLASSIFICATION, "conclusion_classes": dict(sorted(classes.items())),
        "questions": {r["question_id"]: r["Robustness"] for r in a.matrix},
        "controls": {"checks": len(a.checks), "pass": sum(c.status == "PASS" for c in a.checks), "fail": sum(c.status == "FAIL" for c in a.checks), "info": sum(c.status == "INFO" for c in a.checks),
                     "failed_checks": [c.check_id for c in a.checks if c.status == "FAIL"]},
        "timezone": a.timezone, "eligible_denominator": a.eligible,
        "semantic_chain": ["OBSERVED component weighing events", "DERIVED selected meal weight", "UNKNOWN actual consumed quantity", "SOURCE GAP actual food waste"],
        "waste": "W1 BLOCKED / SOURCE GAP: no scenario produces a waste estimate, band or proxy",
        "note": "Scenarios are sensitivity tests, not alternative truths. The baseline is the approved interpretation and is never overwritten.",
    }


def run_sensitivity(cfg: Config, out_dir: Path) -> SensitivityResult:
    d = out_dir / OUT_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    res = SensitivityResult()
    try:
        inp = load_metric_inputs(out_dir)
    except MetricInputError as exc:
        res.core_status, res.error = "BLOCKED", str(exc)
        _remove(d)                                              # a stale sensitivity finding must never look current
        return res
    a = run_analysis(inp, cfg)
    res.analysis = a
    res.core_status = "FAILED" if a.failed else "PASSED"
    res.summary = _summary(a, res.core_status)

    write_json(d / REGISTRY_JSON, [s.as_dict() for s in SCENARIOS])
    write_csv(d / REGISTRY_CSV, [{**s.as_dict(), "affected_tables": ";".join(s.affected_tables), "metrics_recalculated": ";".join(s.metrics_recalculated),
                                  "operation": json.dumps(s.operation, sort_keys=True)} for s in SCENARIOS], list(REGISTRY_CSV_COLUMNS))
    write_csv(d / RESULTS_CSV, a.result_rows, list(a.result_rows[0]))
    write_csv(d / METRIC_CSV, a.metric_rows, list(METRIC_COLUMNS))
    write_csv(d / TZ_CSV, a.timezone, list(TZ_COLUMNS))
    write_csv(d / MATRIX_CSV, a.matrix, list(MATRIX_COLUMNS))
    write_csv(d / REGISTER_CSV, a.register, list(REGISTER_COLUMNS))
    write_csv(d / CONTROLS_CSV, [c.row() for c in a.checks], list(CONTROL_COLUMNS))
    write_json(d / SUMMARY_JSON, res.summary)
    write_figures(a, d / FIGURE_DIR)
    res.hashes = {n: digest_file(d / n).sha256 for n in DETERMINISTIC_FILES}
    return res
