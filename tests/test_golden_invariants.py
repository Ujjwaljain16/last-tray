"""GOLDEN STRUCTURE. Counts, partitions and reconciliations: integers, asserted EXACTLY.

Nothing here involves a floating-point number. If one of these fails, a business fact changed (a population, a partition, a
reconciliation), never a representation detail. Metric values, which are floating point, are in test_golden_metrics.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

G = Path(__file__).resolve().parent / "golden"


@pytest.fixture(scope="module")
def issues() -> pd.DataFrame:
    return pd.read_csv(G / "reference_validation_issues.csv")


@pytest.fixture(scope="module")
def summary() -> pd.DataFrame:
    return pd.read_csv(G / "reference_validation_summary_by_rule.csv")


@pytest.fixture(scope="module")
def sens() -> pd.DataFrame:
    return pd.read_csv(G / "reference_sensitivity_analysis.csv").set_index("scenario_id")


# ---- source counts: the raw layer -------------------------------------------------------------------------------------------------
def test_raw_layer_counts_agree_with_the_pins(cfg, golden):
    c = golden["counts"]
    f = cfg.sources.flavoria
    assert sum(m.rows for m in f.members) == f.expected_total_rows == c["raw_event_rows"] == 12284
    assert len(f.members) == c["raw_files"] == 11 and f.expected_session_ids == c["session_ids"] == 3343
    assert cfg.sources.weather.expected_hours == c["weather_hours"] == 1129


# ---- populations and the fixed denominator -----------------------------------------------------------------------------------------
def test_eligible_population_is_canonical_plus_quarantined(golden):
    c = golden["counts"]
    assert c["eligible_registered_export_session_ids"] == 1699
    assert c["canonical_sessions"] == 1697
    assert c["quarantined_crossover_sessions"] == 2
    assert c["canonical_sessions"] + c["quarantined_crossover_sessions"] == c["eligible_registered_export_session_ids"]


def test_the_two_crossover_sessions_are_named(golden):
    assert golden["counts"]["crossover_session_ids"] == ["session2266", "session3222"]
    assert len(golden["counts"]["crossover_session_ids"]) == golden["counts"]["quarantined_crossover_sessions"]


def test_session_population_rows_add_up(golden):
    c = golden["counts"]
    non_registered_rows = c["non_registered_export_sessions_excluding_crossover"] + c["quarantined_crossover_sessions"]
    assert c["eligible_registered_export_session_ids"] + non_registered_rows == c["session_population_rows"] == 3345
    assert c["session_population_rows"] - c["quarantined_crossover_sessions"] == c["session_ids"]


def test_m5_uses_the_fixed_eligible_denominator(golden):
    m5 = golden["metrics"]["M5_core_measurement_readiness"]
    assert m5["denominator"] == golden["counts"]["eligible_registered_export_session_ids"]
    assert m5["numerator"] == golden["counts"]["canonical_sessions"]
    assert m5["numerator"] < m5["denominator"]


def test_shrinking_the_denominator_would_make_readiness_total_which_is_the_mistake_to_avoid(golden):
    """Integer identity: numerator == denominator - quarantined means 'removed the problem records from the denominator'."""
    m5 = golden["metrics"]["M5_core_measurement_readiness"]
    assert m5["numerator"] == m5["denominator"] - golden["counts"]["quarantined_crossover_sessions"]


# ---- warn-free: partition and reconciliation ----------------------------------------------------------------------------------------
def test_warn_free_partition_covers_every_eligible_session_exactly_once(golden):
    r = golden["supporting"]["warn_free_reconciliation"]
    assert r["eligible"] == r["no_session_level_warn"] + r["with_session_level_warn"] + r["quarantined_crossover"]
    assert r["eligible"] == golden["counts"]["eligible_registered_export_session_ids"]
    assert r["quarantined_crossover"] == golden["counts"]["quarantined_crossover_sessions"]


def test_canonical_warn_free_numerator_is_the_session_level_bucket(golden):
    w, r = golden["supporting"]["warn_free_rate"], golden["supporting"]["warn_free_reconciliation"]
    assert (w["numerator"], w["denominator"]) == (1663, 1699) == (r["no_session_level_warn"], r["eligible"])
    assert "session-level" in w["definition"]


def test_event_level_variant_removes_exactly_the_event_only_sessions(golden):
    r = golden["supporting"]["warn_free_reconciliation"]
    assert r["event_level_only_warn_sessions"] == ["session320", "session1116", "session1274"]
    assert r["no_warn_incl_event_level"] == r["no_session_level_warn"] - len(r["event_level_only_warn_sessions"]) == 1660


def test_volume_and_coverage_counts(golden):
    s = golden["supporting"]
    assert len(s["volume_irregularity_days"]) == 6 and s["low_observed_volume_days"] == 16
    assert (s["service_days_registered_export"], s["service_days_non_registered_export"]) == (35, 30)


# ---- validation issues: nothing deleted ------------------------------------------------------------------------------------------------
def test_validation_issue_fixture_matches_the_counts(golden, issues, summary):
    assert len(issues) == golden["validation"]["total_issues"] == 1278
    assert int(summary.issues.sum()) == 1278
    assert int((issues.severity == "ERROR").sum()) == golden["validation"]["errors"] == 4
    assert set(issues[issues.severity == "ERROR"].rule_id) == {"I01"}


def test_no_issue_deleted_a_record(issues):
    """Every issue is a FLAG, KEEP_FIRST or QUARANTINE row. Handling never says drop or delete."""
    assert not issues.handling.str.contains("drop|delete|remove", case=False).any()


# ---- sensitivity fixture: structure ------------------------------------------------------------------------------------------------------
def test_sensitivity_has_the_25_expected_scenarios(golden, sens):
    assert len(sens) == golden["sensitivity"]["scenarios"] == 25
    assert {"S00", "S01", "S02", "S03", "S04", "S05", "TZ0", "TZ1", "TZ2", "TZ3", "TZ4", "S20", "S21", "S22", "S23", "S30", "S31", "S32", "S33", "S40"} <= set(sens.index)


def test_sensitivity_baseline_session_counts(sens):
    b = sens.loc["S00"]
    assert (int(b.m3_observed_valid_sessions), int(b.m5_numerator), int(b.m5_denominator)) == (1697, 1697, 1699)
    assert int(sens.loc["S01", "m3_observed_valid_sessions"]) == 1699 and int(sens.loc["S01", "m5_numerator"]) == 1699


def test_timezone_scenarios_quarantine_the_expected_session_counts(golden, sens):
    assert int(sens.loc["TZ0", "t03_violating_sessions"]) == golden["sensitivity"]["tz0_no_shift"]["sessions_failing_t03"] == 303
    assert int(sens.loc["TZ1", "t03_violating_sessions"]) == golden["sensitivity"]["tz1_plus_1h"]["sessions_failing_t03"] == 103
    assert [int(sens.loc[f"TZ{h}", "t03_violating_sessions"]) for h in (2, 3, 4)] == [0, 0, 0]
    assert int(sens.loc["TZ0", "m3_observed_valid_sessions"]) == 1697 - 303
    assert [int(sens.loc[f"TZ{h}", "weather_hour_changed_sessions"]) for h in (0, 1, 2, 3, 4)] == [385, 385, 385, 0, 385]


def test_volume_scenarios_are_tests_only(sens):
    """S20-S22 exclude days to measure the effect; the pipeline's volume flags never exclude (invariant I-6)."""
    for sid in ("S20", "S21", "S22"):
        assert "test only" in sens.loc[sid, "description"]


def test_m4_is_five_wherever_it_is_a_kpi(sens):
    kpi = sens[sens.group != "population"]
    assert (kpi.m4_median_components == 5).all() and int(sens.loc["S40", "m4_median_components"]) == 2


def test_population_profile_fixture_counts(golden):
    prof = pd.read_csv(G / "reference_population_profile.csv", index_col=0)
    assert int(prof.loc["sessions", "registered_export"]) == golden["counts"]["canonical_sessions"]
    assert int(prof.loc["sessions", "non_registered_export"]) == golden["counts"]["non_registered_export_sessions_excluding_crossover"]
    assert int(prof.loc["events", "registered_export"]) + int(prof.loc["events", "non_registered_export"]) == 8360 + 3900
