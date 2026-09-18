"""GOLDEN METRIC VALUES. Floating-point results, asserted with the published tolerances in golden_values.yml.

A percentage such as 97.88 is a rounded publication of a quotient (1663 / 1699). Whether the computer stores it as
97.88000000000001 is not a business rule, so these tests use tolerances and never exact float equality. Structural facts
(counts, partitions, reconciliations) are asserted exactly, in integers, in test_golden_invariants.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

G = Path(__file__).resolve().parent / "golden"


@pytest.fixture(scope="module")
def sens() -> pd.DataFrame:
    return pd.read_csv(G / "phase2_sensitivity_analysis.csv").set_index("scenario_id")


def pct(numerator: int, denominator: int) -> float:
    return 100.0 * numerator / denominator


# ---- the locked KPI values ----------------------------------------------------------------------------------------------------------------
def test_kpi_values(golden):
    m, tol = golden["metrics"], golden["tolerances"]
    assert m["M1_median_derived_selected_meal_weight_g"] == pytest.approx(499.0, abs=tol["M2_abs"])
    assert m["M2_p90_derived_selected_meal_weight_g"] == pytest.approx(1039.6, abs=tol["M2_abs"])
    assert m["M3_observed_valid_sessions_registered_export"] == 1697          # a count, exact by nature
    assert m["M4_median_distinct_normalized_components"] == pytest.approx(5.0)


def test_m5_percent_is_the_published_rounding_of_its_fraction(golden):
    m5, tol = golden["metrics"]["M5_core_measurement_readiness"], golden["tolerances"]
    assert pct(m5["numerator"], m5["denominator"]) == pytest.approx(m5["percent"], abs=tol["percent_abs"]) == pytest.approx(99.88, abs=tol["percent_abs"])
    assert m5["percent"] < 100.0


def test_canonical_warn_free_percent(golden):
    w, tol = golden["supporting"]["warn_free_rate"], golden["tolerances"]
    assert pct(w["numerator"], w["denominator"]) == pytest.approx(97.88, abs=tol["percent_abs"])
    assert w["percent"] == pytest.approx(97.88, abs=tol["percent_abs"])


def test_event_level_variant_is_a_different_figure_and_does_not_replace_the_canonical_one(golden):
    r, w, tol = golden["supporting"]["warn_free_reconciliation"], golden["supporting"]["warn_free_rate"], golden["tolerances"]
    assert pct(r["no_warn_incl_event_level"], r["eligible"]) == pytest.approx(97.70, abs=tol["percent_abs"])
    assert w["percent"] == pytest.approx(97.88, abs=tol["percent_abs"])
    assert w["percent"] - r["percent_incl_event_level"] == pytest.approx(0.18, abs=0.01)


# ---- sensitivity fixture: values ------------------------------------------------------------------------------------------------------------
def test_sensitivity_baseline_row_equals_the_headline_kpis(golden, sens):
    b, tol = sens.loc["S00"], golden["tolerances"]
    assert b.m1_median_g == pytest.approx(499.0, abs=tol["M2_abs"])
    assert b.m2_p90_g == pytest.approx(1039.6, abs=tol["M2_abs"])
    assert b.m4_median_components == pytest.approx(5.0)
    assert b.m5_rate_pct == pytest.approx(99.88, abs=tol["percent_abs"] * 2)
    assert b.warn_free_rate_pct == pytest.approx(97.88, abs=tol["percent_abs"] * 2)                 # canonical, session-level
    assert b.warn_free_incl_event_level_pct == pytest.approx(97.70, abs=tol["percent_abs"] * 2)     # diagnostic variant


def test_kpi_sensitivity_findings(golden, sens):
    s, tol = golden["sensitivity"], golden["tolerances"]
    kpi = sens[sens.group != "population"]
    lo, hi = s["baseline_m1_range_g"]
    assert kpi.m1_median_g.between(lo - tol["delta_g_abs"], hi + tol["delta_g_abs"]).all()
    assert sens.loc["TZ0", "m5_rate_pct"] == pytest.approx(s["tz0_no_shift"]["m5_percent"], abs=tol["percent_abs"] * 2)
    assert sens.loc["TZ0", "d_m2_g"] == pytest.approx(s["tz0_no_shift"]["m2_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["TZ1", "m5_rate_pct"] == pytest.approx(s["tz1_plus_1h"]["m5_percent"], abs=tol["percent_abs"] * 2)
    assert sens.loc["S01", "d_m2_g"] == pytest.approx(s["crossover_inclusion"]["m2_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["S01", "d_m1_g"] == pytest.approx(s["crossover_inclusion"]["m1_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["S04", "d_m2_g"] == pytest.approx(s["removal_2097g_session"]["m2_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["S04", "d_m1_g"] == pytest.approx(s["removal_2097g_session"]["m1_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["S23", "d_m2_g"] == pytest.approx(s["first_two_weeks_excluded"]["m2_delta_g"], abs=tol["delta_g_abs"])
    assert sens.loc["S20", "d_m2_g"] == pytest.approx(s["irregular_days_excluded"]["m2_delta_g"], abs=tol["delta_g_abs"])


def test_the_kpis_do_not_select_the_timezone(sens):
    """+2h, +3h and +4h are indistinguishable on every KPI. Cross-export evidence, not the KPI, selects +3h."""
    cols = ["m1_median_g", "m2_p90_g", "m3_observed_valid_sessions", "m4_median_components", "m5_rate_pct"]
    base = sens.loc["TZ3", cols].astype(float)
    for tz in ("TZ2", "TZ4", "S00"):
        assert sens.loc[tz, cols].astype(float).to_numpy() == pytest.approx(base.to_numpy(), abs=1e-9)


def test_lifting_the_quarantine_reaches_100_percent_only_by_construction(sens):
    assert sens.loc["S01", "m5_rate_pct"] == pytest.approx(100.0) and sens.loc["S00", "m5_rate_pct"] < 100.0


def test_m2_is_the_sensitive_metric_and_m1_is_not(sens):
    kpi = sens[sens.group != "population"]
    assert kpi.m1_median_g.max() - kpi.m1_median_g.min() < 13.0 < kpi.m2_p90_g.max() - kpi.m2_p90_g.min()
