"""Sensitivity analysis on the real canonical model: the frozen baseline, the reproduction of every approved Phase 2 scenario, ranges,
robustness classes, the evidence matrix and uncertainty register, and the semantic guardrails."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.metrics.evaluate import _has_banned_affirmative
from src.sensitivity import classify as cl
from src.sensitivity.evidence import NOT_CLASSIFIED, METRIC_ORDER
from src.sensitivity.figures import FIGURES
from src.sensitivity.registry import CLASSIFICATION, GUARDRAIL_IDS, SCENARIOS, SCENARIO_BY_ID
from src.sensitivity.report import BEGIN, END, render_block
from src.sensitivity.stage import (CONTROLS_CSV, FIGURE_DIR, MATRIX_COLUMNS, MATRIX_CSV, METRIC_COLUMNS, METRIC_CSV, OUT_SUBDIR, REGISTER_COLUMNS, REGISTER_CSV,
                                   REGISTRY_JSON, RESULTS_CSV, SUMMARY_JSON, TZ_CSV)

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden" / "phase2_sensitivity_analysis.csv"
pytestmark = pytest.mark.usefixtures("no_network")


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(text: str) -> float | None:
    return None if text == "" else float(text)


class TestFrozenBaseline:
    def test_the_baseline_is_the_approved_package_unchanged(self, real_sensitivity, golden):
        b = real_sensitivity.results["S00"]
        m = golden["metrics"]
        assert (b.m1, b.m3, b.m4) == (m["M1_median_derived_selected_meal_weight_g"], m["M3_observed_valid_sessions_registered_export"], m["M4_median_distinct_normalized_components"])
        assert abs(b.m2 - m["M2_p90_derived_selected_meal_weight_g"]) <= golden["tolerances"]["M2_abs"]
        assert (b.m5_numerator, b.m5_denominator) == (1697, 1699) and abs(b.m5 - 99.88) <= 0.005 and (b.s2_numerator, abs(b.s2 - 97.88) <= 0.005) == (1663, True)

    def test_the_analysis_passes_all_controls_and_reports_no_problem(self, real_sensitivity):
        a = real_sensitivity.analysis
        assert real_sensitivity.result.core_status == "PASSED" and not a.failed and a.baseline_problems == [] and a.phase2_mismatches == []
        assert [c.status for c in a.checks if c.check_id != "SC13"] == ["PASS"] * 12 and a.checks[-1].status == "INFO"

    def test_w1_stays_blocked_and_no_scenario_recomputes_it(self, real_sensitivity):
        w1 = [r for r in rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV) if r["metric_id"] == "W1"]
        assert len(w1) == 1 and w1[0]["robustness_class"] == "BLOCKED" and w1[0]["scenario_value"] == "" and "no waste estimate" in w1[0]["interpretation"]
        assert real_sensitivity.result.summary["baseline"]["W1"] == "BLOCKED / SOURCE GAP"


class TestPhase2Reproduction:
    def test_every_approved_phase2_scenario_is_reproduced(self, real_sensitivity):
        golden = {r["scenario_id"]: r for r in rows(GOLDEN)}
        assert len(golden) == 25
        for sid, g in golden.items():
            r = real_sensitivity.results[sid]
            assert abs(r.m1 - float(g["m1_median_g"])) <= 0.05, sid
            assert abs(r.m2 - float(g["m2_p90_g"])) <= 0.05, sid
            assert (r.m3, r.m4) == (int(float(g["m3_observed_valid_sessions"])), float(g["m4_median_components"])), sid
            if num(g["m5_numerator"]) is not None:
                assert (r.m5_numerator, r.m5_denominator) == (int(float(g["m5_numerator"])), 1699), sid
                assert abs(r.m5 - float(g["m5_rate_pct"])) <= 0.005, sid

    def test_the_registry_references_equal_the_frozen_phase2_file(self):
        golden = {r["scenario_id"]: r for r in rows(GOLDEN)}
        for s in SCENARIOS:
            if s.phase2 is None:
                continue
            g = golden[s.scenario_id]
            assert (s.phase2[0], s.phase2[1], s.phase2[2], s.phase2[3]) == (float(g["m1_median_g"]), float(g["m2_p90_g"]), int(float(g["m3_observed_valid_sessions"])), float(g["m4_median_components"]))
            assert s.phase2[4] == (None if num(g["m5_numerator"]) is None else int(float(g["m5_numerator"])))

    def test_the_headline_phase2_findings_still_hold(self, real_sensitivity):
        r = real_sensitivity.results
        d = lambda sid, k: getattr(r[sid], k) - getattr(r["S00"], k)
        assert abs(d("S23", "m2") + 62.6) <= 0.05 and abs(d("TZ0", "m2") + 50.5) <= 0.05 and abs(d("S20", "m2") - 26.4) <= 0.05
        assert abs(d("S04", "m2") + 1.6) <= 0.05 and abs(d("S05", "m2") + 1.6) <= 0.05
        assert max(abs(d(s, "m2")) for s in ("S01", "S02", "S03")) <= 3.0 + 0.05 and max(abs(d(s, "m1")) for s in ("S01", "S02", "S03")) <= 0.5
        assert r["TZ0"].detail["t03_quarantined_sessions"] == 303 and abs(r["TZ0"].m5 - 82.05) <= 0.005 and r["S01"].m5 == 100.0
        assert (r["TZ2"].m1, r["TZ2"].m2, r["TZ2"].m3) == (r["TZ3"].m1, r["TZ3"].m2, r["TZ3"].m3) == (r["TZ4"].m1, r["TZ4"].m2, r["TZ4"].m3) == (r["S00"].m1, r["S00"].m2, r["S00"].m3)
        assert all(x.m4 == 5.0 for k, x in r.items() if k not in ("S40", "G01"))

    def test_ranges_match_the_approved_evidence(self, real_sensitivity):
        rg = real_sensitivity.analysis.ranges
        assert (rg["M1"]["min"], rg["M1"]["max"]) == (493.0, 505.0) and (rg["M4"]["min"], rg["M4"]["max"]) == (5.0, 5.0)
        assert abs(rg["M2"]["min"] - 977.0) <= 0.05 and abs(rg["M2"]["max"] - 1066.0) <= 0.05


class TestRegistryAndExecutionAgree:
    def test_every_declared_scenario_was_executed_exactly_once(self, real_sensitivity):
        ids = [s.scenario_id for s in SCENARIOS]
        assert list(real_sensitivity.results) == ids and len(set(ids)) == 26
        for name, key in ((RESULTS_CSV, "scenario_id"),):
            assert [r[key] for r in rows(real_sensitivity.out / OUT_SUBDIR / name)] == ids
        registry = json.loads((real_sensitivity.out / OUT_SUBDIR / REGISTRY_JSON).read_text(encoding="utf-8"))
        assert [r["scenario_id"] for r in registry] == ids

    def test_each_registry_entry_declares_everything_the_brief_requires(self):
        needed = {"scenario_id", "name", "assumption_changed", "baseline_assumption", "alternative_assumption", "rationale", "affected_tables", "affected_population",
                  "metrics_recalculated", "interpretation", "decision_impact", "defensible", "diagnostic_only"}
        for s in SCENARIOS:
            d = s.as_dict()
            assert needed <= set(d) and all(d[k] not in (None, "", []) for k in needed - {"defensible", "diagnostic_only"}), s.scenario_id

    def test_results_carry_deltas_and_percentage_deltas(self, real_sensitivity):
        by = {r["scenario_id"]: r for r in rows(real_sensitivity.out / OUT_SUBDIR / RESULTS_CSV)}
        assert float(by["S23"]["d_m2_g"]) == pytest.approx(-62.6, abs=0.05) and float(by["S23"]["pct_d_m2_g"]) == pytest.approx(-6.02, abs=0.01)
        assert by["S00"]["d_m1_g"] == "0.0" and by["S30"]["m1_g"] == "499.0"
        assert by["G01"]["forbidden"] == "true" and by["S00"]["phase2_reference"] == "reproduced" and by["G01"]["phase2_reference"] == "n/a"


class TestTimezoneIsFileSpecific:
    def test_only_the_named_file_is_shifted_and_the_baseline_offset_is_unchanged(self, real_sensitivity, cfg):
        assert real_sensitivity.analysis.checks[4].check_id == "SC05" and real_sensitivity.analysis.checks[4].status == "PASS"
        shifted = {f for r in real_sensitivity.results.values() for f in r.detail.get("files_shifted", [])}
        assert shifted == {"registered_2020_10_05-2020_10_18.csv"} == set(cfg.timezone.overrides)

    def test_timezone_evidence_table(self, real_sensitivity):
        tz = {int(r["offset_hours"]): r for r in rows(real_sensitivity.out / OUT_SUBDIR / TZ_CSV)}
        assert [int(tz[h]["t03_quarantined_sessions"]) for h in range(5)] == [303, 103, 0, 0, 0] and all(tz[h]["sessions_in_shifted_file"] == "385" for h in tz)
        assert [tz[h]["inside_t07_band"] for h in range(5)] == ["false", "false", "false", "true", "false"], "only +3h lands the file inside the other exports' band"
        assert [int(tz[h]["weather_hour_changed_sessions"]) for h in range(5)] == [385, 385, 385, 0, 385]
        assert [float(tz[h]["mean_abs_t2m_diff_c"]) for h in (0, 1, 2, 4)] == [1.231, 0.873, 0.529, 0.467] and float(tz[3]["gap_to_other_files_h"]) < 0.05

    def test_the_baseline_offset_reproduces_the_baseline_exactly(self, real_sensitivity):
        b, t = real_sensitivity.results["S00"], real_sensitivity.results["TZ3"]
        assert (b.m1, b.m2, b.m3, b.m4, b.m5_numerator, b.s2_numerator) == (t.m1, t.m2, t.m3, t.m4, t.m5_numerator, t.s2_numerator)

    def test_the_kpis_cannot_choose_between_2_3_and_4_hours_but_the_time_of_day_can(self, real_sensitivity):
        a = real_sensitivity.analysis
        same = {(a.results[s].m1, a.results[s].m2, a.results[s].m3, a.results[s].m4) for s in ("TZ2", "TZ3", "TZ4")}
        assert len(same) == 1
        assert [t["inside_t07_band"] for t in a.timezone].count(True) == 1 and a.timezone[3]["inside_t07_band"]


class TestRobustnessClassification:
    def test_thresholds_are_declared_and_used_consistently(self, real_sensitivity):
        assert set(CLASSIFICATION) == {"M1", "M2", "M3", "M4", "M5", "S2"}
        assert real_sensitivity.result.summary["classification_thresholds"]["M2"]["stable_below"] == 25.0
        for m in rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV):
            if m["metric_id"] == "W1" or m["robustness_class"] == NOT_CLASSIFIED:
                continue
            assert m["robustness_class"] == cl.classify(m["metric_id"], float(m["baseline_value"]), float(m["scenario_value"])), (m["metric_id"], m["scenario_id"])

    def test_boundaries(self):
        assert cl.classify("M2", 1000, 1024.9) == "STABLE" and cl.classify("M2", 1000, 1025) == "SENSITIVE" and cl.classify("M2", 1000, 1074.9) == "SENSITIVE" and cl.classify("M2", 1000, 1075) == "CONDITIONAL"
        assert cl.classify("M4", 5, 5) == "STABLE" and cl.classify("M4", 5, 6) == "SENSITIVE" and cl.classify("M4", 5, 7) == "CONDITIONAL"
        assert cl.classify("M3", 1000, 1049) == "STABLE" and cl.classify("M3", 1000, 950) == "SENSITIVE" and cl.classify("M3", 1000, 800) == "CONDITIONAL"
        assert cl.classify("M5", 99.88, 99.5) == "STABLE" and cl.classify("M5", 99.88, 93.82) == "CONDITIONAL" and cl.classify("M1", 499, None) == "BLOCKED"

    def test_a_number_that_moves_a_little_is_not_automatically_stable(self):
        assert cl.classify("M1", 499, 509) == "SENSITIVE", "a 2% move on M1 is beyond the approved materiality convention"

    def test_worst_class_ordering(self):
        assert cl.worst(["STABLE", "SENSITIVE", "STABLE"]) == "SENSITIVE" and cl.worst(["STABLE", "CONDITIONAL"]) == "CONDITIONAL" and cl.worst([]) == "BLOCKED"

    def test_metric_classes_on_the_real_scenarios(self, real_sensitivity):
        by = {(m["metric_id"], m["scenario_id"]): m["robustness_class"] for m in rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV)}
        assert {by[("M1", s)] for s in ("S01", "S06", "S10", "S20", "S22", "S23", "TZ0", "TZ1")} == {"STABLE"} and {c for (m, s), c in by.items() if m == "M4" and c != NOT_CLASSIFIED} == {"STABLE"}
        assert by[("M2", "S23")] == "SENSITIVE" and by[("M2", "TZ0")] == "SENSITIVE" and by[("M2", "S20")] == "SENSITIVE" and by[("M2", "S04")] == "STABLE"
        assert by[("M5", "TZ0")] == "CONDITIONAL" and by[("M5", "TZ1")] == "CONDITIONAL" and by[("M5", "S01")] == "STABLE" and by[("M5", "TZ3")] == "STABLE"

    def test_the_forbidden_and_diagnostic_population_scenarios_are_never_classified_or_ranged(self, real_sensitivity):
        for m in rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV):
            if m["scenario_id"] in GUARDRAIL_IDS or m["scenario_id"] == "S40":
                assert m["robustness_class"] == NOT_CLASSIFIED
        rg = real_sensitivity.analysis.ranges["M1"]
        assert rg["min"] > 400, "the pooled (413 g) and non-registered (192 g) figures are excluded from the range"

    def test_the_guardrail_shows_the_population_confounding_risk(self, real_sensitivity):
        g, b = real_sensitivity.results["G01"], real_sensitivity.results["S00"]
        assert SCENARIO_BY_ID["G01"].forbidden and not SCENARIO_BY_ID["G01"].defensible
        assert g.m1 < b.m1 - 50 and g.m3 == 3341, "pooling adds the other export's sessions and moves the median by far more than any legitimate scenario"


class TestEvidenceMatrixAndRegister:
    def test_the_matrix_columns_and_the_six_headline_conclusion_tests(self, real_sensitivity):
        m = rows(real_sensitivity.out / OUT_SUBDIR / MATRIX_CSV)
        assert tuple(m[0]) == MATRIX_COLUMNS and len(m) == 13
        by = {r["Question"]: r for r in m}
        assert by[next(q for q in by if q.startswith("Can a selected-meal-weight distribution"))]["Robustness"] == "STABLE"
        assert by[next(q for q in by if q.startswith("Is the median derived"))]["Robustness"] == "STABLE"
        assert by[next(q for q in by if q.startswith("Does the component-count"))]["Robustness"] == "STABLE"
        assert by[next(q for q in by if q.startswith("How stable is the upper end"))]["Robustness"] == "SENSITIVE"
        assert by[next(q for q in by if q.startswith("Is the registered-export valid-session count"))]["Robustness"] == "CONDITIONAL"
        assert by[next(q for q in by if q.startswith("Can actual consumption"))]["Robustness"] == "BLOCKED" and by[next(q for q in by if q.startswith("Can food waste"))]["Robustness"] == "BLOCKED"
        assert all(r[c] for r in m for c in MATRIX_COLUMNS)

    def test_the_quoted_magnitudes_in_the_conclusions_match_the_computed_results(self, real_sensitivity):
        r, a = real_sensitivity.results, real_sensitivity.analysis
        d = lambda s, k: abs(getattr(r[s], k) - getattr(r["S00"], k))
        assert 55 <= max(d(s, "m2") for s in r if s not in ("S40", "G01")) <= 65, "Q3 quotes about 60 g"
        assert max(d(s, "m2") for s in ("S01", "S02", "S03")) <= 3.1 and 25 <= d("S20", "m2") <= 27 and 61 <= d("S23", "m2") <= 64 and 1.5 <= d("S04", "m2") <= 1.7 and 24 <= d("S10", "m2") <= 25

    def test_blocked_conclusions_produce_no_estimate(self, real_sensitivity):
        m = rows(real_sensitivity.out / OUT_SUBDIR / MATRIX_CSV)
        blocked = [r for r in m if r["Robustness"] == "BLOCKED"]
        assert len(blocked) == 2
        for r in blocked:
            assert r["Observed range/change"].startswith("not testable") and r["Sensitivity tested"].startswith("None: ")
        waste = next(r for r in blocked if r["Question"].startswith("Can food waste"))
        assert "waste band" in waste["What cannot be concluded"] and "Per-tray waste weight" in waste["Next evidence needed"]

    def test_the_uncertainty_register_covers_the_required_topics(self, real_sensitivity):
        reg = rows(real_sensitivity.out / OUT_SUBDIR / REGISTER_CSV)
        assert tuple(reg[0]) == REGISTER_COLUMNS and len(reg) == 10
        text = " ".join(r["assumption"].lower() for r in reg)
        for topic in ("timezone", "population", "crossover", "component", "volume", "meal weight", "food-waste", "weather"):
            assert topic in text, topic
        assert all(r[c] for r in reg for c in REGISTER_COLUMNS) and {r["impact_level"] for r in reg} <= {"HIGH", "MEDIUM", "LOW", "BLOCKING"}
        blocking = [r for r in reg if r["impact_level"] == "BLOCKING"]
        assert {r["uncertainty_id"] for r in blocking} == {"U06", "U07"} and all("Not testable" in r["sensitivity_result"] for r in blocking)

    def test_register_sensitivity_numbers_come_from_the_results(self, real_sensitivity):
        reg = {r["uncertainty_id"]: r for r in rows(real_sensitivity.out / OUT_SUBDIR / REGISTER_CSV)}
        assert "303 sessions (M5 82.05%)" in reg["U01"]["sensitivity_result"] and "103 (M5 93.82%)" in reg["U01"]["sensitivity_result"]
        assert "252 sessions" in reg["U05"]["sensitivity_result"] and "+26.4 g" in reg["U05"]["sensitivity_result"]
        assert "M5 to 100.0%" in reg["U03"]["sensitivity_result"] and "-62.6 g" in reg["U09"]["sensitivity_result"]


class TestMetricSensitivityTable:
    def test_columns_order_and_content(self, real_sensitivity):
        m = rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV)
        assert tuple(m[0]) == METRIC_COLUMNS
        order = [(METRIC_ORDER.index(r["metric_id"]) if r["metric_id"] in METRIC_ORDER else 99, [s.scenario_id for s in SCENARIOS].index(r["scenario_id"])) for r in m]
        assert order == sorted(order), "stable ordering: metric, then registry order"
        assert m[0]["metric_id"] == "M1" and m[0]["scenario_id"] == "S00" and m[0]["absolute_delta"] == "0.0" and m[0]["robustness_class"] == "STABLE"
        m5 = next(r for r in m if r["metric_id"] == "M5" and r["scenario_id"] == "TZ0")
        assert float(m5["absolute_delta"]) == pytest.approx(-17.83402, abs=1e-4) and float(m5["relative_delta"]) == pytest.approx(-0.17855, abs=1e-4)

    def test_m5_and_s2_are_only_defined_where_eligibility_is_varied(self, real_sensitivity):
        m5 = {r["scenario_id"] for r in rows(real_sensitivity.out / OUT_SUBDIR / METRIC_CSV) if r["metric_id"] == "M5"}
        assert m5 == {"S00", "S01", "S02", "S03", "TZ0", "TZ1", "TZ2", "TZ3", "TZ4"}
        assert all(r.m5_denominator == 1699 for r in real_sensitivity.results.values() if r.m5_denominator is not None)

    def test_s2_and_m5_are_not_collapsed(self, real_sensitivity):
        b = real_sensitivity.results["S00"]
        assert b.m5 != b.s2 and abs(b.m5 - b.s2 - 2.0) < 0.01, "M5 99.88% and S2 97.88% stay separate"
        assert real_sensitivity.results["S01"].s2 != real_sensitivity.results["S01"].m5


class TestSemanticsAndOutputs:
    def test_no_output_names_or_estimates_waste_consumption_or_demand(self, real_sensitivity):
        d = real_sensitivity.out / OUT_SUBDIR
        for name in (RESULTS_CSV, METRIC_CSV, MATRIX_CSV, REGISTER_CSV, TZ_CSV, CONTROLS_CSV):
            header = next(csv.reader((d / name).open(encoding="utf-8")))
            assert not [h for h in header if any(w in h.lower() for w in ("waste", "consum", "leftover", "intake"))], name
        ids = {r["metric_id"] for r in rows(d / METRIC_CSV)}
        assert ids == {"M1", "M2", "M3", "M4", "M5", "S2", "W1"}
        text = " ".join(str(v) for r in rows(d / MATRIX_CSV) + rows(d / REGISTER_CSV) for k, v in r.items() if k != "What cannot be concluded")     # that column is the list of things NOT claimed
        banned = ("customers", "diners", "visits", "transactions", "savings", "food waste estimate", "potential waste", "waste band", "waste proxy is")
        assert _has_banned_affirmative(text, banned) == []

    def test_the_summary_records_the_conclusion_classes(self, real_sensitivity):
        s = real_sensitivity.result.summary
        assert s["baseline"]["frozen"] is True and s["scenarios"]["registered"] == 26 and s["scenarios"]["phase2_reproduced"] == 25
        assert s["conclusion_classes"] == {"BLOCKED": 2, "CONDITIONAL": 2, "SENSITIVE": 3, "STABLE": 6}
        assert s["questions"]["Q11"] == "CONDITIONAL" and s["questions"]["Q12"] == "BLOCKED" and "not alternative truths" in s["note"]

    def test_four_figures_are_written(self, real_sensitivity):
        for name in FIGURES:
            data = (real_sensitivity.out / OUT_SUBDIR / FIGURE_DIR / name).read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 30_000, name

    def test_the_documentation_block_is_exactly_what_the_analysis_renders(self, real_sensitivity):
        doc = (REPO / "docs" / "sensitivity_analysis.md").read_text(encoding="utf-8")
        assert render_block(real_sensitivity.analysis) in doc, "regenerate docs/sensitivity_analysis.md (scratch patch script) after changing the analysis"
        assert doc.count(BEGIN) == 1 and doc.count(END) == 1
        for section in ("## 1. Baseline definition", "## 2. Scenario methodology", "## 3. Scenario table", "## 4. Headline metric ranges", "## 5. Stable conclusions",
                        "## 6. Sensitive conclusions", "## 7. Conditional conclusions", "## 8. Blocked conclusions", "## 9. Uncertainty register summary", "## 10. Evidence gaps",
                        "## 11. Recommended next instrumentation and data"):
            assert section in doc, section
