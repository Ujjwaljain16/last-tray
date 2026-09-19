"""Metrics on the real canonical model: exact approved values, numerators and denominators, populations, quarantine, weights, components,
weather, evidence table, and the contract that must match the code."""
from __future__ import annotations

import csv
import json

import pytest

from src.metrics import contracts as ct
from src.metrics.evaluate import EVIDENCE_COLUMNS, EVIDENCE_CSV, METRIC_COLUMNS, METRICS_CSV, OUT_SUBDIR, CONTRACTS_JSON, SUMMARY_JSON, REPORT_MD, judge, population_matches
from src.metrics.populations import POPULATIONS

pytestmark = pytest.mark.usefixtures("no_network")


def rows(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TestApprovedValues:
    def test_m1_median_is_499(self, real_metrics, golden):
        r = real_metrics.result.results["M1"]
        assert r.value == golden["metrics"]["M1_median_derived_selected_meal_weight_g"] == 499.0
        assert (r.n_used, r.n_population, r.n_null_excluded) == (1697, 1697, 0) and r.population == ct.D

    def test_m2_p90_is_1039_6_by_linear_interpolation(self, real_metrics, golden):
        r = real_metrics.result.results["M2"]
        assert abs(r.value - golden["metrics"]["M2_p90_derived_selected_meal_weight_g"]) <= golden["tolerances"]["M2_abs"]
        assert r.detail["method"] == "percentile_linear" and r.detail["q"] == 0.9 and r.n_used == 1697

    def test_m3_is_1697_observed_valid_registered_export_sessions(self, real_metrics, golden):
        r = real_metrics.result.results["M3"]
        assert r.value == golden["metrics"]["M3_observed_valid_sessions_registered_export"] == 1697
        assert real_metrics.rows["M3"]["metric_name"] == "Observed Valid Sessions — Registered-Export Population"

    def test_m4_median_distinct_components_is_5(self, real_metrics, golden):
        assert real_metrics.result.results["M4"].value == golden["metrics"]["M4_median_distinct_normalized_components"] == 5

    def test_m5_is_1697_over_1699_and_99_88_percent(self, real_metrics, golden):
        r, g = real_metrics.result.results["M5"], golden["metrics"]["M5_core_measurement_readiness"]
        assert (r.numerator, r.denominator) == (g["numerator"], g["denominator"]) == (1697, 1699)
        assert abs(r.value - g["percent"]) <= golden["tolerances"]["percent_abs"] and r.detail["quarantined_in_denominator"] == 2

    def test_s2_warn_free_rate_is_97_88_with_the_approved_accounting(self, real_metrics, golden):
        r, g = real_metrics.result.results["S2"], golden["supporting"]["warn_free_rate"]
        assert (r.numerator, r.denominator) == (g["numerator"], g["denominator"]) == (1663, 1699)
        assert abs(r.value - g["percent"]) <= golden["tolerances"]["percent_abs"]
        assert r.detail["with_session_level_warn"] == 34 and r.detail["not_core_ready"] == 2 and 1663 + 34 + 2 == 1699

    def test_the_event_level_variant_is_a_labelled_diagnostic_and_never_replaces_s2(self, real_metrics, golden):
        d, s = real_metrics.result.results["S2D"], real_metrics.result.results["S2"]
        w = golden["supporting"]["warn_free_reconciliation"]
        assert (d.numerator, d.denominator) == (w["no_warn_incl_event_level"], 1699) and abs(d.value - w["percent_incl_event_level"]) <= 0.005
        assert real_metrics.rows["S2"]["value_display"] == "97.88%" and real_metrics.rows["S2D"]["role"] == "diagnostic" and d.detail["event_level_only_warn"] == 3
        assert real_metrics.rows["S2"]["metric_id"] != real_metrics.rows["S2D"]["metric_id"] and s.value != d.value

    def test_every_metric_passes_its_contract(self, real_metrics):
        assert real_metrics.result.core_status == "PASSED" and real_metrics.result.summary["failed_metrics"] == []
        assert {m: r["status"] for m, r in real_metrics.rows.items()} == {"M1": "PASS", "M2": "PASS", "M3": "PASS", "M4": "PASS", "M5": "PASS", "S1": "PASS",
                                                                          "S2": "PASS", "S2D": "PASS", "W1": "BLOCKED"}

    def test_the_approved_values_in_the_contracts_equal_the_golden_values(self, golden):
        m, s = golden["metrics"], golden["supporting"]
        c = ct.CONTRACTS
        assert (c["M1"].approved_value, c["M2"].approved_value, c["M3"].approved_value, c["M4"].approved_value) == (
            m["M1_median_derived_selected_meal_weight_g"], m["M2_p90_derived_selected_meal_weight_g"], m["M3_observed_valid_sessions_registered_export"],
            m["M4_median_distinct_normalized_components"])
        assert c["M5"].approved_value == m["M5_core_measurement_readiness"]["percent"] and c["S2"].approved_value == s["warn_free_rate"]["percent"]
        assert c["S2D"].approved_value == s["warn_free_reconciliation"]["percent_incl_event_level"]
        assert c["M2"].tolerance == golden["tolerances"]["M2_abs"] and c["M5"].tolerance == golden["tolerances"]["percent_abs"]


class TestPopulations:
    def test_populations_a_to_e(self, real_metrics):
        p = real_metrics.result.summary["populations"]
        assert {v["letter"]: v["sessions"] for v in p.values()} == {"A": 3345, "B": 3341, "C": 1699, "D": 1697, "E": 1646}
        assert real_metrics.checks["MC02"].status == "PASS", "A = C + E: populations are never pooled"

    def test_every_metric_names_its_population_explicitly_in_the_contract_and_the_result(self):
        for mid, c in ct.CONTRACTS.items():
            if mid != "W1":
                assert c.population in POPULATIONS, mid
                assert c.population != ct.A and c.population != ct.E, f"{mid} must not use the all-sessions or the diagnostic population"

    def test_each_result_uses_the_contract_population(self, real_metrics):
        for mid, r in real_metrics.result.results.items():
            assert population_matches(ct.CONTRACTS[mid], r), mid

    def test_the_non_registered_population_never_enters_a_headline_metric(self, real_metrics):
        for mid in ct.HEADLINE:
            assert ct.CONTRACTS[mid].population in (ct.C, ct.D)


class TestQuarantineDuplicatesNullsAndWeights:
    def test_no_quarantined_session_contributes_and_all_stay_in_the_m5_denominator(self, real_metrics):
        assert real_metrics.checks["MC05"].status == "PASS" and real_metrics.checks["MC04"].status == "PASS"
        assert real_metrics.result.results["M5"].detail["quarantined_in_denominator"] == 2
        assert real_metrics.rows["M1"]["n_excluded_vs_eligible"] == 2

    def test_repeats_are_excluded_from_the_weights_and_scoops_stay_additive(self, real_metrics):
        assert real_metrics.checks["MC07"].status == "PASS" and real_metrics.checks["MC07"].observed == "[]"
        assert int(real_metrics.checks["MC08"].observed) >= 1, "at least one D session would differ if an exact repeat were summed"
        assert int(real_metrics.checks["MC09"].observed) > 200, "repeated same-scale weighings exist and are all summed"

    def test_null_weights_are_handled_by_contract_not_by_dataframe_behaviour(self, real_metrics):
        assert real_metrics.checks["MC06"].observed == "0"
        r = real_metrics.result.results["M1"]
        assert r.n_used + r.n_null_excluded == r.n_population

    def test_the_2097g_observation_is_preserved_and_counted(self, real_metrics):
        c = real_metrics.checks["MC10"]
        assert c.status == "PASS" and "2097 g" in c.description
        assert real_metrics.result.results["M1"].detail["max"] > 2000, "the session holding the 2,097 g event is in the population and keeps its weight"

    def test_min_and_max_are_recorded_but_are_not_headline_metrics(self, real_metrics):
        d = real_metrics.result.results["M1"].detail
        assert d["min"] < 100 and d["max"] > 2000 and not any("min" in m.lower() or "max" in m.lower() for m in real_metrics.rows)

    def test_the_independent_statistics_agree(self, real_metrics):
        assert real_metrics.checks["MC11"].status == "PASS" and real_metrics.checks["MC12"].status == "PASS"


class TestComponents:
    def test_m4_is_backed_by_the_component_table_with_no_aliasing_or_pooling(self, real_metrics):
        for cid in ("MC13", "MC14", "MC15"):
            assert real_metrics.checks[cid].status == "PASS", cid
        dist = real_metrics.result.results["M4"].detail["distribution"]
        assert sum(dist.values()) == 1697 and min(dist) >= 1


class TestWeatherAndVolumeAreContextOnly:
    def test_s1_follows_the_contract_and_reports_the_quarantine_effect(self, real_metrics):
        r = real_metrics.result.results["S1"]
        assert (r.numerator, r.denominator) == (1697, 1699) and r.detail["join_status"] == {"MATCHED": 1697, "NOT_ATTEMPTED_QUARANTINED": 2}
        assert (r.detail["r_1h_null_sessions"], r.detail["ri_10min_null_sessions"]) == (67, 25)

    def test_weather_is_never_a_causal_claim_anywhere_in_the_outputs(self, real_metrics):
        text = " ".join(str(v) for r in real_metrics.result.rows for v in r.values()) + " ".join(e["What it tells us"] for e in real_metrics.result.evidence)
        for phrase in ("caused", "because of the weather", "explains", "rain causes", "weather effect"):
            assert phrase not in text.lower()

    def test_m3_daily_counts_come_from_the_daily_volume_table_and_agree(self, real_metrics):
        assert real_metrics.checks["MC16"].status == "PASS"
        assert sum(real_metrics.result.results["M3"].detail["by_service_date"].values()) == 1697

    def test_the_six_irregular_days_remain_included_and_are_not_called_errors(self, real_metrics):
        v = next(e for e in real_metrics.result.evidence if e["Metric"].startswith("V "))
        assert "6 differ from the weekday baseline" in v["Value"] and "Demand" in v["What it does NOT tell us"] and "data errors" in v["What it does NOT tell us"]
        assert "anomal" not in v["What it tells us"].lower()


class TestWasteIsBlocked:
    def test_w1_is_an_explicit_blocked_source_gap_with_no_value(self, real_metrics):
        w = real_metrics.rows["W1"]
        assert w["status"] == "BLOCKED" and w["evidence_status"] == "BLOCKED" and w["value"] is None and w["value_display"] == "BLOCKED / SOURCE GAP"
        assert w["numerator"] is None and w["denominator"] is None and w["approved_value"] is None
        written = next(r for r in rows(real_metrics.out / OUT_SUBDIR / METRICS_CSV) if r["metric_id"] == "W1")
        assert written["value"] == "" and written["numerator"] == "" and written["approved_value"] == ""
        assert "no proxy" in w["formula"] or "no formula" in w["formula"]

    def test_no_other_metric_or_column_is_about_waste_or_consumption(self, real_metrics):
        assert real_metrics.checks["MC24"].status == "PASS"
        others = [r for m, r in real_metrics.rows.items() if m != "W1"]
        assert not [r for r in others if any(w in (r["metric_id"] + r["metric_name"]).lower() for w in ("waste", "consum", "leftover", "intake"))]
        assert not [c for c in METRIC_COLUMNS if any(w in c for w in ("waste", "consum"))]

    def test_the_outputs_never_estimate_waste_from_a_weight(self, real_metrics):
        report = (real_metrics.out / OUT_SUBDIR / REPORT_MD).read_text(encoding="utf-8")
        assert "W1 Direct Food Waste Measurement: BLOCKED / SOURCE GAP" in report and "no proxy is estimated" in report
        assert "estimated waste" not in report.lower() and "waste estimate" not in report.lower()


class TestOutputsAndEvidenceTable:
    def test_files_and_columns(self, real_metrics):
        d = real_metrics.out / OUT_SUBDIR
        assert tuple(csv.DictReader((d / METRICS_CSV).open(encoding="utf-8")).fieldnames) == METRIC_COLUMNS
        assert tuple(csv.DictReader((d / EVIDENCE_CSV).open(encoding="utf-8")).fieldnames) == EVIDENCE_COLUMNS
        assert [r["metric_id"] for r in rows(d / METRICS_CSV)] == list(ct.ORDER)

    def test_every_metric_row_carries_the_required_fields(self, real_metrics):
        for r in real_metrics.result.rows:
            for f in ("metric_id", "metric_name", "unit", "population", "grain", "status", "interpretation", "limitation") + (("source_tables",) if r["metric_id"] != "W1" else ()):
                assert r[f] not in (None, ""), (r["metric_id"], f)
        assert (real_metrics.rows["M5"]["numerator"], real_metrics.rows["M5"]["denominator"]) == (1697, 1699)
        assert real_metrics.rows["M1"]["source_snapshot_id"].startswith("flavoria-")

    def test_the_evidence_table_is_small_and_states_what_each_metric_does_not_tell(self, real_metrics):
        ev = real_metrics.result.evidence
        assert [e["Metric"].split()[0] for e in ev] == ["M1", "M2", "M3", "M4", "M5", "S1", "S2", "W1", "Q", "V"] and len(ev) <= 10
        assert all(e["What it tells us"] and e["What it does NOT tell us"] for e in ev)
        m1 = next(e for e in ev if e["Metric"].startswith("M1"))
        assert m1["Value"] == "499 g" and "left over or wasted" in m1["What it does NOT tell us"] and "intake" in m1["What it does NOT tell us"]
        m5 = next(e for e in ev if e["Metric"].startswith("M5"))
        assert m5["Value"] == "99.88% (1,697 / 1,699)" and "correct or accurate" in m5["What it does NOT tell us"]
        m3 = next(e for e in ev if e["Metric"].startswith("M3"))
        assert m3["Value"] == "1,697 sessions" and "Demand" in m3["What it does NOT tell us"]

    def test_the_evidence_records_used_and_excluded_are_measured_against_the_fixed_eligible_population(self, real_metrics):
        ev = {e["Metric"].split()[0]: e for e in real_metrics.result.evidence}
        assert (ev["M1"]["records_used"], ev["M1"]["records_excluded"]) == (1697, 2) and (ev["S2"]["records_used"], ev["S2"]["records_excluded"]) == (1663, 36)

    def test_the_summary_and_contract_files_are_complete(self, real_metrics):
        d = real_metrics.out / OUT_SUBDIR
        s = json.loads((d / SUMMARY_JSON).read_text(encoding="utf-8"))
        assert s["metrics"]["M1"]["display"] == "499 g" and s["waste"].startswith("W1 BLOCKED / SOURCE GAP") and s["semantic_chain"][-1].startswith("SOURCE GAP")
        assert s["percentile_method"].startswith("linear interpolation")
        c = json.loads((d / CONTRACTS_JSON).read_text(encoding="utf-8"))
        assert [x["metric_id"] for x in c] == list(ct.ORDER)
        needed = {"metric_id", "metric_name", "business_question", "definition", "grain", "population", "numerator", "denominator", "formula", "filters", "exclusions",
                  "quarantine_handling", "null_handling", "statistical_method", "source_tables", "lineage", "interpretation", "limitation", "approved_value", "tolerance",
                  "computed_value", "pass_fail"}
        assert all(needed <= set(x) for x in c)
        assert {x["metric_id"]: x["pass_fail"] for x in c}["M5"] == "PASS"


class TestContractsMatchCode:
    def test_the_contract_formulas_and_methods_describe_what_the_code_does(self):
        assert "MEDIAN" in ct.CONTRACTS["M1"].formula and "PERCENTILE_LINEAR" in ct.CONTRACTS["M2"].formula and "0.90" in ct.CONTRACTS["M2"].formula
        assert "linear interpolation" in ct.CONTRACTS["M2"].statistical_method and "not nearest-rank" in ct.CONTRACTS["M2"].statistical_method
        assert ct.CONTRACTS["M5"].numerator_population == ct.D and ct.CONTRACTS["M5"].population == ct.C
        assert ct.CONTRACTS["M3"].metric_name == "Observed Valid Sessions — Registered-Export Population"

    def test_every_contract_field_is_filled_for_every_computed_metric(self):
        for mid, c in ct.CONTRACTS.items():
            for f, v in c.as_dict().items():
                if f in ("approved_value", "tolerance", "numerator_population"):
                    continue
                assert v not in (None, ""), (mid, f)

    def test_the_contract_layer_contains_no_calculation(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(ct.__file__)).read_text(encoding="utf-8"))
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name not in ("as_dict",)], "contracts.py declares; it defines no calculation"
        assert "import statistics" not in Path(ct.__file__).read_text(encoding="utf-8")

    def test_the_judge_uses_the_contract_tolerance(self, real_metrics):
        assert judge(ct.CONTRACTS["M2"], real_metrics.result.results["M2"])[0] == "PASS"
