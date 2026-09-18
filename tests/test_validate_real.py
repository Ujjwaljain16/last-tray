"""Validation on the real committed data, checked against the golden expectations and the Phase 2 evidence.

Structural expectations are integers and are asserted exactly. Where WP4 differs from the Phase 2 exploration, the difference is
named in DOCUMENTED_DIFFERENCES and asserted too, so a difference can never hide inside a tolerance.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from src.validate.validate import EVENT_STATUS_CSV, QUARANTINE_CSV, SESSION_STATUS_CSV

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "golden"
pytestmark = pytest.mark.usefixtures("no_network")

# WP4 vs the Phase 2 exploration run (docs/validation_rules.md, "Differences from Phase 2"). Everything else must match exactly.
NEW_IN_WP4 = {"C01", "I07", "X03"}          # documented in the specification, never emitted by the exploration run
C02_GRANULARITY = {"C02a"}                 # Phase 2 wrote ONE population-level C02 INFO issue; WP4 writes one INFO per low-volume day (16)


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def phase2_by_rule() -> Counter:
    c: Counter = Counter()
    for r in rows(GOLDEN / "phase2_validation_summary_by_rule.csv"):
        rule = "C02b" if r["rule_id"] == "C02" and r["severity"] == "WARN" else "C02a" if r["rule_id"] == "C02" else r["rule_id"]
        c[(rule, r["severity"], r["population"])] += int(r["issues"])
    return c


class TestEventAndSessionReconciliation:
    def test_event_counts_equal_the_golden_values(self, real_validation, golden):
        s = real_validation.result.summary
        assert s["events"]["staged"] == golden["counts"]["raw_event_rows"] == 12284
        assert s["events"]["by_population"] == golden["staging"]["events_by_population"] == {"non_registered_export": 3912, "registered_export": 8372}

    def test_session_counts_and_why_ids_and_keys_differ(self, real_validation, golden):
        s = real_validation.result.summary["sessions"]
        assert (s["session_ids"], s["session_keys"]) == (3343, 3345)
        assert s["session_ids_in_both_populations"] == golden["counts"]["crossover_session_ids"] == ["session2266", "session3222"]
        assert s["session_keys"] == s["session_ids"] + len(s["session_ids_in_both_populations"]), "the two extra keys are exactly the two crossover ids"

    def test_no_reconciliation_check_fails(self, real_validation):
        assert real_validation.result.summary["reconciliation"]["fail"] == 0
        assert real_validation.result.core_status == "PASSED_WITH_QUARANTINE" and real_validation.result.weather_status == "PASSED"

    def test_every_pinned_file_total_reconciles(self, real_validation):
        per_file = [c for cid, c in real_validation.checks.items() if cid.startswith("E03:")]
        assert len(per_file) == 11 and all(c.status == "PASS" and c.expected == c.observed for c in per_file)
        assert sum(int(c.observed) for c in per_file) == 12284

    def test_event_partition_is_complete_and_nothing_is_lost(self, real_validation):
        d = real_validation.result.summary["events"]["dispositions"]
        assert d == {"DUPLICATE_EXCLUDED": 2, "MODELLABLE": 12260, "QUARANTINED": 22}
        assert sum(d.values()) == 12284 and real_validation.checks["E05"].status == "PASS"


class TestCrossoverQuarantine:
    def test_exactly_the_two_crossover_sessions_are_quarantined_in_both_populations(self, real_validation, golden):
        q = real_validation.result.summary["quarantine"]
        assert q["session_ids"] == ["session2266", "session3222"] and q["session_keys"] == 4
        assert q["keys"] == [f"{sid}|{pop}" for sid in ("session2266", "session3222") for pop in ("non_registered_export", "registered_export")]
        assert q["rules"] == ["I01"]

    def test_the_four_findings_are_the_only_errors_and_they_quarantine(self, real_validation):
        errors = [i for i in real_validation.issues if i["severity"] == "ERROR"]
        assert len(errors) == 4 and {i["rule_id"] for i in errors} == {"I01"}
        assert all(i["quarantine"] is True and i["handling"] == "QUARANTINE" for i in errors)

    def test_quarantine_keeps_every_source_row_and_lists_them(self, real_validation, real_staging):
        manifest = rows(real_validation.out / "validation" / QUARANTINE_CSV)
        keys = [r for r in manifest if r["quarantine_entity_type"] == "session_key"]
        events = [r for r in manifest if r["quarantine_entity_type"] == "event"]
        staged = [e for e in real_staging.events.itertuples() if e.session_id in ("session2266", "session3222")]
        assert len(keys) == 4 and len(events) == len(staged) == 22
        assert {r["entity_id"] for r in events} == {e.event_id for e in staged}, "every quarantined row is still in staging and named in the manifest"
        assert all(r["quarantine_rule_ids"] == "I01" and "nothing is deleted" in r["handling_note"] for r in manifest)

    def test_cross_export_behaviour_is_reported_not_merged(self, real_validation):
        i06 = {i["entity_id"]: i for i in real_validation.issues if i["rule_id"] == "I06"}
        assert i06["session2266"]["severity"] == "INFO" and "identical" in i06["session2266"]["description"]
        assert i06["session3222"]["severity"] == "WARN" and "component-name conflicts: 2 of 6" in i06["session3222"]["observed_value"]
        assert "10800" in i06["session3222"]["observed_value"], "the raw wall-clock offset that supports the file-specific +3h decision is visible"

    def test_the_quarantined_sessions_are_still_present_in_the_session_table(self, real_validation):
        status = {r["session_key"]: r for r in rows(real_validation.out / "validation" / SESSION_STATUS_CSV)}
        assert len(status) == 3345
        for k in ("session2266|registered_export", "session3222|non_registered_export"):
            assert status[k]["quarantined"] == "true" and status[k]["quarantine_rule_ids"] == "I01" and status[k]["in_both_populations"] == "true"


class TestApprovedThresholds:
    def test_b02_flags_the_six_large_events_and_names_the_2097g_one_without_removing_it(self, real_validation, real_staging):
        b02 = [i for i in real_validation.issues if i["rule_id"] == "B02"]
        assert len(b02) == 6 == real_staging.events.component_weight_g.astype(int).ge(1500).sum()
        biggest = max(b02, key=lambda i: int(i["observed_value"].split()[0]))
        assert biggest["observed_value"] == "2097 g" and biggest["severity"] == "WARN" and biggest["quarantine"] is False
        staged = real_staging.events[real_staging.events.event_id == biggest["event_id"]].iloc[0]
        assert staged.weight_raw == "2097" and staged.component_weight_g == "2097", "raw and normalised weight are both preserved"
        assert "not a physical limit" in biggest["description"]
        disp = {r["event_id"]: r["disposition"] for r in rows(real_validation.out / "validation" / EVENT_STATUS_CSV)}
        assert disp[biggest["event_id"]] == "MODELLABLE"

    def test_b07_session_weight_range_registered_and_non_registered(self, real_validation):
        b07 = [i for i in real_validation.issues if i["rule_id"] == "B07"]
        reg = [i for i in b07 if i["population"] == "registered_export"]
        assert (len(reg), len(b07) - len(reg)) == (15, 470)
        weights = [int(i["observed_value"].split()[0]) for i in reg]
        assert (sum(w < 50 for w in weights), sum(w > 2200 for w in weights)) == (7, 8)
        assert all(i["severity"] == "WARN" and not i["quarantine"] and "not automatically invalid" in i["description"] for i in b07)

    def test_t05_span_over_600s_registered(self, real_validation):
        t05 = [i for i in real_validation.issues if i["rule_id"] == "T05"]
        assert len(t05) == 7 and all(i["population"] == "registered_export" and int(i["observed_value"].split()[0]) > 600 for i in t05)
        assert real_validation.result.summary["issues"]["by_rule"]["T05"] == 7, "Phase 2 correction: 8 -> 7 after sessions are keyed by population"

    def test_b04_seventeen_single_event_sessions_all_kept_and_match_phase2(self, real_validation):
        b04 = {i["session_key"]: i for i in real_validation.issues if i["rule_id"] == "B04"}
        phase2 = {f"{r['session_id']}|{r['population']}" for r in rows(REPO / "outputs" / "phase2" / "single_event_registered_export_sessions.csv")}
        assert len(b04) == 17 and set(b04) == phase2
        assert all(not i["quarantine"] and "not automatically invalid" in i["description"] for i in b04.values())
        over_100 = sum(int(i["observed_value"].split(";")[1].split()[0]) > 100 for i in b04.values())
        assert 0 <= over_100 <= 17, "classification by 100 g is descriptive only: it adds no meaning"

    def test_c02_low_volume_and_the_six_irregular_days(self, real_validation, golden):
        s = real_validation.result.summary["volume"]
        assert s["volume_irregularity_days"] == [str(d) for d in golden["supporting"]["volume_irregularity_days"]]
        assert s["low_observed_volume_days"] == golden["supporting"]["low_observed_volume_days"] == 16
        assert s["primary_service_days"] == 35 and real_validation.checks["V01"].status == "PASS"
        c02b = [i for i in real_validation.issues if i["rule_id"] == "C02b"]
        assert len(c02b) == 6 and all(i["severity"] == "WARN" and not i["quarantine"] and "NOT a data error" in i["description"] for i in c02b)

    def test_irregular_days_are_not_excluded_from_anything(self, real_validation):
        status = rows(real_validation.out / "validation" / SESSION_STATUS_CSV)
        flagged = [r for r in status if r["volume_irregularity_day"] == "true"]
        assert flagged and all(r["population"] == "registered_export" and r["quarantined"] == "false" for r in flagged), "flagged days keep their sessions"
        assert not any(r["volume_irregularity_day"] == "true" for r in status if r["population"] != "registered_export")

    def test_single_event_and_trace_findings_are_diagnostic_severities(self, real_validation):
        sev = {i["rule_id"]: i["severity"] for i in real_validation.issues}
        assert (sev["B02"], sev["B04"], sev["B05"], sev["B07"], sev["T05"], sev["C02a"], sev["C02b"]) == ("WARN", "WARN", "INFO", "WARN", "WARN", "INFO", "WARN")


class TestIdentificationDuplicatesAndNames:
    def test_no_session_key_has_more_than_one_identification_value(self, real_validation):
        assert real_validation.checks["S06"].status == "PASS" and real_validation.checks["S06"].observed == "0"
        assert not [i for i in real_validation.issues if i["rule_id"] == "T06"]
        assert all(r["distinct_identification_values"] == "1" for r in rows(real_validation.out / "validation" / SESSION_STATUS_CSV))

    def test_the_old_count_of_two_is_a_pooling_artefact(self, real_validation):
        assert real_validation.checks["S07"].observed == "2 | 2", "pooled by session_id alone the two crossover ids look like multiple identifications"

    def test_exact_duplicates_are_two_and_repeated_same_scale_weighings_are_not_duplicates(self, real_validation):
        assert len([i for i in real_validation.issues if i["rule_id"] == "I02"]) == 2
        b05 = [i for i in real_validation.issues if i["rule_id"] == "B05"]
        assert len(b05) == 222 and all(i["severity"] == "INFO" and "additive scoops" in i["description"] for i in b05)
        assert not [i for i in real_validation.issues if i["rule_id"] == "B06"], "B06 is retired and must not return"
        assert real_validation.checks["D03"].observed == "7 | 2 | 5", "natural-key duplicates: 2 within a population, 5 across the two exports"

    def test_repeats_are_excluded_from_sums_but_never_deleted(self, real_validation, real_staging):
        status = {r["session_key"]: r for r in rows(real_validation.out / "validation" / SESSION_STATUS_CSV)}
        repeated = [r for r in status.values() if r["exact_repeats_excluded"] != "0"]
        assert len(repeated) == 2 and all(int(r["events_staged"]) == int(r["events_counted"]) + int(r["exact_repeats_excluded"]) for r in repeated)
        assert len(real_staging.events) == 12284

    def test_component_names_raw_vs_normalised_do_not_differ_within_a_session(self, real_validation):
        assert real_validation.checks["N01"].status == "PASS"
        assert real_validation.checks["N02"].observed == "246 | 245", "one string-level variant exists across the data (a casing difference), never inside a session"


class TestPhase2Comparison:
    def test_every_rule_count_matches_the_phase2_fixture_except_the_documented_differences(self, real_validation):
        actual: Counter = Counter()
        for i in real_validation.issues:
            actual[(i["rule_id"], i["severity"], i["population"] or "n/a")] += 1
        expected = phase2_by_rule()
        comparable_actual = Counter({k: v for k, v in actual.items() if k[0] not in NEW_IN_WP4 | C02_GRANULARITY})
        comparable_expected = Counter({k: v for k, v in expected.items() if k[0] not in C02_GRANULARITY})
        assert comparable_actual == comparable_expected

    def test_the_documented_differences_are_exactly_these(self, real_validation):
        by_rule = real_validation.result.summary["issues"]["by_rule"]
        assert by_rule["C02a"] == 16, "one INFO per low-volume day (Phase 2 wrote one population-level issue)"
        assert by_rule["I07"] == 86 and by_rule["X03"] == 3 and by_rule["C01"] == 1

    def test_severity_totals(self, real_validation):
        s = real_validation.result.summary["issues"]
        assert s["by_severity"] == {"ERROR": 4, "WARN": 530, "INFO": 849} and s["total"] == 1383
        assert s["by_handling"] == {"FLAG": 1377, "KEEP_FIRST": 2, "QUARANTINE": 4}

    def test_session_level_warn_accounting_reproduces_the_golden_reconciliation(self, real_validation, golden):
        a = real_validation.result.summary["session_level_warn_accounting"]
        w = golden["supporting"]["warn_free_reconciliation"]
        assert (a["eligible_primary_session_keys"], a["quarantined"], a["with_session_level_warn"], a["no_session_level_warn"]) == (
            w["eligible"], w["quarantined_crossover"], w["with_session_level_warn"], w["no_session_level_warn"])
        assert a["eligible_primary_session_keys"] == a["quarantined"] + a["with_session_level_warn"] + a["no_session_level_warn"]
        assert a["event_level_only_warn_session_ids"] == sorted(w["event_level_only_warn_sessions"])

    def test_cross_export_component_evidence_matches_phase2(self, real_validation):
        results_b = json.loads((REPO / "outputs" / "phase2" / "results_b.json").read_text(encoding="utf-8"))["names"]
        assert results_b["cross_export_disjoint"] == 86 == real_validation.result.summary["issues"]["by_rule"]["I07"]


class TestTimezoneAndWeather:
    def test_the_override_labels_are_confined_to_the_one_named_file(self, real_validation, real_staging):
        assert not [i for i in real_validation.issues if i["rule_id"] == "T10"]
        assert real_validation.checks["Z01"].status == "PASS" and real_validation.checks["Z02"].status == "PASS"
        shifted = real_staging.events[real_staging.events.timezone_handling == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"]
        assert set(shifted.source_file) == {"registered_2020_10_05-2020_10_18.csv"} and len(shifted) == 1931
        t07 = [i for i in real_validation.issues if i["rule_id"] == "T07"]
        assert len(t07) == 1 and t07[0]["entity_id"] == "registered_2020_10_05-2020_10_18.csv" and "not source-confirmed" in t07[0]["description"]
        assert "7.54" in t07[0]["observed_value"] and "10.54" in t07[0]["observed_value"]

    def test_dst_round_trips_for_every_timestamp(self, real_validation):
        assert real_validation.checks["Z05"].status == "PASS" and "24568" in real_validation.checks["Z05"].description
        assert not [i for i in real_validation.issues if i["rule_id"] == "X04"]

    def test_weather_structure_grain_coverage_and_missingness(self, real_validation):
        c = real_validation.checks
        assert [c[k].status for k in ("K01", "K02", "K03")] == ["PASS", "PASS", "PASS"]
        assert (c["K01"].observed, c["K02"].observed) == ("4516", "1129")
        assert c["K04"].observed == "NAN_SOURCE_NULL=3;OK=4513" and c["K05"].observed.startswith("FMISID 100949")
        x03 = [i for i in real_validation.issues if i["rule_id"] == "X03"]
        assert len(x03) == 3 and all(i["severity"] == "INFO" and "never zero" in i["description"] for i in x03)
        assert not [i for i in real_validation.issues if i["rule_id"] in ("X01", "X07", "X08")]


class TestCompletenessAndSemantics:
    def test_not_applicable_is_kept_apart_from_missing(self, real_validation):
        comp = {r["field"]: r for r in rows(real_validation.out / "validation" / "field_completeness.csv")}
        wt = comp["weighting_type"]
        assert (wt["not_applicable_rows"], wt["empty_rows"]) == ("6990", "0"), "absent column in 7 files is schema drift, not missing data"
        assert all(comp[f]["empty_rows"] == "0" and comp[f]["malformed_rows"] == "0" for f in comp if f != "weighting_type")

    def test_waste_is_reported_as_a_source_gap_and_never_inferred(self, real_validation):
        s = real_validation.result.summary
        assert s["source_gaps"]["waste"].startswith("BLOCKED")
        assert s["semantic_chain"] == ["OBSERVED component weighing events", "DERIVED selected meal weight", "UNKNOWN actual consumed quantity", "SOURCE GAP actual food waste"]
        text = json.dumps(s).lower() + "".join(i["description"].lower() + i["business_consequence"].lower() for i in real_validation.issues)
        for banned in ("customers", "diners", "consumed weight", "food waste weight", "registered diners", "registered customers"):
            assert banned not in text

    def test_thresholds_are_described_as_diagnostic_not_physical(self, real_validation):
        assert "not claims of physical impossibility" in real_validation.result.summary["thresholds_statement"]
        assert real_validation.result.summary["volume"]["note"].endswith("not demand")
        assert "Observed Valid Sessions — Registered-Export Population" in real_validation.result.summary["volume"]["note"]
