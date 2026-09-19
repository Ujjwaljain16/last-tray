"""Metric behaviour on hand-built sessions: statistics, populations, each metric at its boundaries, and the NEGATIVE tests that deliberately try
to break the contracts (pooled populations, a changed M5 denominator, dropping the quarantined sessions, swapping the S2 figure, a waste
proxy, raw-file access). Every negative test must be caught."""
from __future__ import annotations

import statistics

import pytest

from src.metrics import compute, contracts as ct
from src.metrics.evaluate import MetricContractError, assert_no_waste_metric, judge, population_matches
from src.metrics.populations import POPULATIONS, PopulationError, select
from src.metrics.stats import StatsError, median, percentile_linear
from tests.metrics_helpers import NON, REG, session
from tests.static_checks import raw_access_violations


# ---- statistics ---------------------------------------------------------------------------------------------------------------------------------
class TestStatistics:
    def test_median_odd_even_and_float(self):
        assert median([3, 1, 2]) == 2.0 and median([4, 1, 3, 2]) == 2.5 and isinstance(median([1, 2, 3]), float)

    def test_percentile_is_linear_interpolation_not_nearest_rank(self):
        data = list(range(1, 12))                                                # 1..11, position (11-1)*0.9 = 9 -> exactly 10
        assert percentile_linear(data, 0.9) == 10.0
        assert percentile_linear([10, 20], 0.9) == 19.0, "interpolates between order statistics; nearest-rank would give 20"
        assert percentile_linear([1, 2, 3, 4], 0.5) == 2.5

    def test_percentile_matches_the_standard_library_and_pandas_on_random_data(self):
        import random
        import pandas as pd
        rng = random.Random(7)
        for _ in range(20):
            data = [rng.randint(0, 3000) for _ in range(rng.randint(2, 200))]
            assert percentile_linear(data, 0.9) == pytest.approx(statistics.quantiles(data, n=10, method="inclusive")[8])
            assert percentile_linear(data, 0.9) == pytest.approx(float(pd.Series(data).quantile(0.9)))

    def test_an_empty_population_raises_it_never_reports_zero(self):
        for f in (lambda: median([]), lambda: percentile_linear([], 0.9)):
            with pytest.raises(StatsError, match="never reported as 0"):
                f()

    def test_a_percentile_outside_0_1_is_refused(self):
        with pytest.raises(StatsError):
            percentile_linear([1, 2], 1.5)


# ---- populations ------------------------------------------------------------------------------------------------------------------------------
class TestPopulations:
    SAMPLE = [session(), session(), session(quarantined=True, session_id="q"), session(population=NON), session(population=NON, quarantined=True, session_id="q")]

    def test_the_five_named_populations(self):
        assert [len(select(self.SAMPLE, n)) for n in (ct.A, ct.B, ct.C, ct.D, ct.E)] == [5, 3, 3, 2, 2]

    def test_an_unknown_or_implicit_population_is_refused(self):
        with pytest.raises(PopulationError, match="must name one of"):
            select(self.SAMPLE, "everything")
        with pytest.raises(TypeError):
            compute.m1_median_selected_weight(self.SAMPLE)                      # no default: the population must be chosen explicitly

    def test_registered_and_non_registered_are_never_pooled_in_d(self):
        assert {s.population for s in select(self.SAMPLE, ct.D)} == {REG} and {s.population for s in select(self.SAMPLE, ct.E)} == {NON}

    def test_quarantined_sessions_stay_in_c_but_never_in_d(self):
        assert sum(s.is_quarantined for s in select(self.SAMPLE, ct.C)) == 1 and not any(s.is_quarantined for s in select(self.SAMPLE, ct.D))


# ---- each metric --------------------------------------------------------------------------------------------------------------------------------
class TestMetrics:
    def test_m1_and_m2_use_only_population_d_and_exclude_null_weights_explicitly(self):
        ss = [session(weight=w) for w in (100, 200, 300, 400, 500)] + [session(quarantined=True, session_id="q"), session(population=NON, weight=99999)]
        m1 = compute.m1_median_selected_weight(ss, ct.D)
        assert m1.value == 300.0 and (m1.n_used, m1.n_population, m1.n_null_excluded) == (5, 5, 0)
        m2 = compute.m2_p90_selected_weight(ss, ct.D)
        assert m2.value == 460.0 and m2.detail["method"] == "percentile_linear"
        with_null = ss + [session(weight=None, core_ready=True)]
        r = compute.m1_median_selected_weight(with_null, ct.D)
        assert r.n_null_excluded == 1 and r.n_used == 5 and r.value == 300.0, "a NULL weight is excluded and counted, never read as 0"

    def test_m3_counts_core_ready_registered_sessions_and_groups_by_service_date(self):
        ss = [session(service_date="2020-10-12"), session(service_date="2020-10-12"), session(service_date="2020-10-13"), session(quarantined=True, session_id="q"),
              session(population=NON)]
        r = compute.m3_observed_valid_sessions(ss, ct.D)
        assert r.value == 3 and r.detail["by_service_date"] == {"2020-10-12": 2, "2020-10-13": 1}

    def test_m4_median_of_distinct_components(self):
        ss = [session(components=c) for c in (3, 5, 5, 7, 9)]
        r = compute.m4_median_distinct_components(ss, ct.D)
        assert r.value == 5.0 and r.detail["distribution"] == {3: 1, 5: 2, 7: 1, 9: 1}

    def test_m5_keeps_quarantined_sessions_in_the_denominator(self):
        ss = [session() for _ in range(8)] + [session(quarantined=True, session_id="q1"), session(quarantined=True, session_id="q2"), session(population=NON)]
        r = compute.m5_core_readiness(ss, ct.D, ct.C)
        assert (r.numerator, r.denominator) == (8, 10) and r.value == 80.0 and r.detail["quarantined_in_denominator"] == 2

    def test_s2_counts_only_session_level_warnings_and_s2d_adds_event_level(self):
        ss = [session(), session(), session(session_warn=True), session(event_warn=True), session(quarantined=True, session_id="q")]
        s2 = compute.s2_warn_free_rate(ss, ct.C)
        assert (s2.numerator, s2.denominator) == (3, 5) and s2.detail["with_session_level_warn"] == 1 and s2.detail["not_core_ready"] == 1
        s2d = compute.s2_warn_free_rate(ss, ct.C, include_event_level=True)
        assert s2d.metric_id == "S2D" and s2d.numerator == 2 and s2d.detail["event_level_only_warn"] == 1

    def test_s1_counts_matched_over_the_eligible_population(self):
        ss = [session(), session(weather=False), session(quarantined=True, session_id="q")]
        r = compute.s1_weather_coverage(ss, ct.C)
        assert (r.numerator, r.denominator) == (1, 3) and r.detail["join_status"] == {"MATCHED": 1, "NOT_ATTEMPTED_QUARANTINED": 1, "UNMATCHED_NO_OBSERVATION": 1}


# ---- the judge -----------------------------------------------------------------------------------------------------------------------------------------
def good_sessions():
    return [session(weight=w) for w in range(1, 11)]


class TestJudge:
    def test_a_value_inside_the_tolerance_passes_and_outside_fails(self):
        c = ct.CONTRACTS["M2"]
        base = compute.MetricResult("M2", ct.D, 1039.6)
        assert judge(c, base)[0] == "PASS" and judge(c, compute.MetricResult("M2", ct.D, 1039.64))[0] == "PASS"
        verdict, problems = judge(c, compute.MetricResult("M2", ct.D, 1039.7))
        assert verdict == "FAIL" and "differs from the approved" in problems[0]

    def test_percent_metrics_are_judged_on_value_and_on_the_fixed_counts(self):
        c = ct.CONTRACTS["M5"]
        ok = compute.MetricResult("M5", ct.D, 100 * 1697 / 1699, 1697, 1699, detail={"denominator_population": ct.C})
        assert judge(c, ok)[0] == "PASS"
        assert judge(c, compute.MetricResult("M5", ct.D, 100 * 1697 / 1699, 1697, 1700, detail={"denominator_population": ct.C}))[0] == "FAIL"


# ---- NEGATIVE tests: each deliberate violation must be caught --------------------------------------------------------------------------------
class TestNegativeAttempts:
    @pytest.fixture()
    def world(self):
        ss = [session(weight=400 + i) for i in range(60)] + [session(population=NON, weight=90 + i) for i in range(20)] + [session(quarantined=True, session_id="q1"),
                                                                                                                              session(quarantined=True, session_id="q2")]
        return ss

    def test_pooling_the_populations_changes_the_value_and_fails_the_contract(self, world):
        right = compute.m1_median_selected_weight(world, ct.D)
        pooled = compute.m1_median_selected_weight(world, ct.B)                # B pools registered and non-registered sessions
        assert pooled.value != right.value
        assert not population_matches(ct.CONTRACTS["M1"], pooled), "the contract names population D, not the pooled one"
        assert "population" in judge(ct.CONTRACTS["M1"], pooled)[1][0]

    def test_pooling_into_the_headline_metric_fails_even_when_the_value_is_close(self, world):
        wrong_pop = compute.m3_observed_valid_sessions(world, ct.A)
        assert judge(ct.CONTRACTS["M3"], wrong_pop)[0] == "FAIL"

    def test_a_changed_m5_denominator_is_rejected(self, world):
        shrunk = compute.m5_core_readiness(world, ct.D, ct.D)                  # denominator taken AFTER removal: 100% by construction
        assert shrunk.value == 100.0
        verdict, problems = judge(ct.CONTRACTS["M5"], shrunk)
        assert verdict == "FAIL" and any("population" in p for p in problems) and any("counts" in p for p in problems)

    def test_removing_the_quarantined_sessions_from_eligibility_is_rejected(self, world):
        without = [s for s in world if not s.is_quarantined]
        r = compute.m5_core_readiness(without, ct.D, ct.C)
        assert r.denominator == 60 and r.value == 100.0 and r.detail["quarantined_in_denominator"] == 0
        assert judge(ct.CONTRACTS["M5"], r)[0] == "FAIL", "the fixed approved counts catch a shrunk eligible population"

    def test_replacing_the_approved_s2_figure_with_another_support_value_is_rejected(self, world):
        variant = compute.s2_warn_free_rate(world, ct.C, include_event_level=True)
        assert judge(ct.CONTRACTS["S2"], variant)[0] == "FAIL"
        renamed = compute.MetricResult("S2", ct.C, 97.70, 1660, 1699)           # relabelling the diagnostic variant as S2
        v, problems = judge(ct.CONTRACTS["S2"], renamed)
        assert v == "FAIL" and any("differs from the approved 97.88" in p for p in problems)

    @pytest.mark.parametrize("row", [
        {"metric_id": "W2", "metric_name": "Estimated food waste", "status": "PASS", "value": 12.0},
        {"metric_id": "M6", "metric_name": "Consumed weight", "status": "PASS", "value": 300},
        {"metric_id": "M7", "metric_name": "Leftover ratio", "status": "PASS", "value": 0.1},
        {"metric_id": "W1", "metric_name": "Direct Food Waste Measurement", "status": "PASS", "value": None},
        {"metric_id": "W1", "metric_name": "Direct Food Waste Measurement", "status": "BLOCKED", "value": 0},
        {"metric_id": "W1", "metric_name": "Direct Food Waste Measurement", "status": "BLOCKED", "value": 37.5},
    ])
    def test_a_waste_proxy_or_a_non_blocked_w1_is_refused(self, row):
        with pytest.raises(MetricContractError):
            assert_no_waste_metric([row])

    def test_the_real_w1_row_is_accepted(self):
        assert_no_waste_metric([{"metric_id": "W1", "metric_name": "Direct Food Waste Measurement", "status": "BLOCKED", "value": None}])

    def test_the_waste_source_gap_cannot_be_flipped_in_configuration(self, config_copy):
        from src.config import ConfigError, load_config
        config_copy.edit("sources.yml", "    status: BLOCKED\n    evidence: 'Documentation sample", "    status: NOT_RETRIEVABLE\n    evidence: 'Documentation sample")
        with pytest.raises(ConfigError, match="waste source must be present and BLOCKED"):
            load_config(config_copy.dir)

    BAD_SOURCES = {
        "opens a raw file": "from pathlib import Path\nx = Path('data/raw/flavoria/dataset_csv.tar').read_bytes()\n",
        "uses tarfile": "import tarfile\nt = tarfile.open('x.tar')\n",
        "imports the verified reader": "from src.ingest.handoff import VerifiedReader\n",
        "imports the staging builder": "from src.stage.stage import run_staging\n",
        "imports the staging event module": "import src.stage.events\n",
        "downloads": "import requests\nrequests.get('http://example.org')\n",
        "opens any file (outside the two I/O modules)": "with open('x.csv') as f:\n    f.read()\n",
    }

    @pytest.mark.parametrize("label", sorted(BAD_SOURCES))
    def test_accidental_raw_file_access_is_detected(self, label):
        assert raw_access_violations(self.BAD_SOURCES[label]), f"the checker must flag: {label}"

    def test_clean_source_passes_the_checker(self):
        assert raw_access_violations("from src.metrics.compute import m1_median_selected_weight\nx = 1 + 1\n") == []
