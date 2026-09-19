"""The scenario engine and the registry validator on hand-built sessions, plus the NEGATIVE tests: every attempt to overwrite the baseline,
adopt an alternative timezone, unquarantine the crossover sessions, exclude the irregular days from the baseline, change M5's denominator,
introduce a waste proxy or pool the populations must be caught."""
from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from src.sensitivity import engine, evidence
from src.sensitivity.engine import ScenarioError, apply_operation, run_scenario
from src.sensitivity.registry import SCENARIOS, SCENARIO_BY_ID, ScenarioSpec, validate_registry
from tests.sensitivity_helpers import NON, OVERRIDE_FILE, REG, agg, working_set

pytestmark = pytest.mark.usefixtures("no_network")


def spec(op: dict, metrics=("M1", "M2", "M3", "M4"), sid="T99", **kw) -> ScenarioSpec:
    base = dict(scenario_id=sid, group="test", name="t", assumption_changed="a", baseline_assumption="b", alternative_assumption="c", rationale="r", affected_tables=("fact_dining_session",),
                affected_population=REG, metrics_recalculated=metrics, operation=op, interpretation="i", decision_impact="none", defensible=True, diagnostic_only=True)
    base.update(kw)
    return ScenarioSpec(**base)


def ws5():
    return working_set([agg(weight=w, day=d) for w, d in ((100, "2020-10-05"), (200, "2020-10-06"), (300, "2020-10-19"), (400, "2020-10-20"), (500, "2020-10-21"))], irregular=["2020-10-20"], low=["2020-10-05"])


class TestOperations:
    def test_baseline_changes_nothing(self, cfg):
        r = run_scenario(spec({"kind": "baseline"}, metrics=("M1", "M2", "M3", "M4", "M5", "S2")), ws5(), cfg)
        assert (r.m1, r.m3, r.m4, r.m5_numerator, r.m5_denominator, r.s2_numerator) == (300.0, 5, 5.0, 5, 5, 5)

    def test_exclude_dates_by_set_range_and_before(self, cfg):
        ws = ws5()
        assert run_scenario(spec({"kind": "exclude_dates", "set": "irregular_volume_days"}), ws, cfg).m3 == 4
        assert run_scenario(spec({"kind": "exclude_dates", "set": "low_volume_days"}), ws, cfg).m3 == 4
        assert run_scenario(spec({"kind": "exclude_dates", "from": "2020-10-19", "to": "2020-10-20"}), ws, cfg).m3 == 3
        r = run_scenario(spec({"kind": "exclude_dates", "before": "2020-10-19"}), ws, cfg)
        assert r.m3 == 3 and r.m1 == 400.0

    def test_exclude_where_uses_the_configured_threshold(self, cfg):
        ws = working_set([agg(span_s=600), agg(span_s=601), agg(span_s=10)])
        assert run_scenario(spec({"kind": "exclude_where", "field": "session_span_s", "op": ">", "value_ref": "T05"}), ws, cfg).m3 == 2, "T05 is 600 s: 601 is left out, 600 is not"

    def test_weight_bounds_fixed_and_percentile(self, cfg):
        ws = working_set([agg(weight=w) for w in (49, 50, 1000, 2200, 2201)])
        assert run_scenario(spec({"kind": "exclude_weight_outside", "method": "threshold", "rule": "B07"}), ws, cfg).m3 == 3
        r = run_scenario(spec({"kind": "exclude_weight_outside", "method": "percentile", "lo": 0.25, "hi": 0.75}), ws, cfg)
        assert r.detail["lo_g"] == 50 and r.detail["hi_g"] == 2200 and r.m3 == 3

    def test_any_warn_and_single_event_exclusions(self, cfg):
        ws = working_set([agg(), agg(session_warn=True), agg(event_warn=True), agg(n_modellable=1)])
        assert run_scenario(spec({"kind": "exclude_where_any_warn"}), ws, cfg).m3 == 2
        assert run_scenario(spec({"kind": "exclude_where", "field": "modellable_event_count", "op": "<=", "value": 1}), ws, cfg).m3 == 3

    def test_the_largest_event_can_be_dropped_from_its_session_or_the_session_removed(self, cfg):
        ws = working_set([agg(weight=2600, key="big|registered_export"), agg(weight=500)], largest=("f#1", "big|registered_export", 2097))
        drop = run_scenario(spec({"kind": "drop_event", "selector": "largest_event"}), ws, cfg)
        assert drop.m3 == 2 and drop.m1 == (503 + 500) / 2 and drop.detail["event_weight_removed_g"] == 2097
        gone = run_scenario(spec({"kind": "exclude_session", "selector": "largest_event_session"}), ws, cfg)
        assert gone.m3 == 1 and gone.m1 == 500.0

    def test_inclusion_adds_the_quarantined_registered_sessions_only_as_a_what_if(self, cfg):
        q = agg(weight=None, quarantined=True, w_nonrepeat=900, key="x|registered_export", comps=4)
        ws = working_set([agg(weight=100), agg(weight=200), q])
        r = run_scenario(spec({"kind": "include", "keys": "quarantined_registered"}, metrics=("M1", "M2", "M3", "M4", "M5")), ws, cfg)
        assert r.m3 == 3 and r.m1 == 200.0 and r.m5_numerator == 3 and r.m5_denominator == 3
        base = run_scenario(spec({"kind": "baseline"}, metrics=("M5",)), ws, cfg)
        assert base.m5_numerator == 2 and base.m5_denominator == 3, "the quarantined session stays in the denominator of the baseline"

    def test_inclusion_of_a_non_registered_session_is_refused(self, cfg):
        ws = working_set([agg(), agg(population=NON, quarantined=True, key="y|non_registered_export")])
        with pytest.raises(ScenarioError, match="only registered-export"):
            apply_operation(ws, cfg, {"kind": "include", "keys": ["y|non_registered_export"]}, [])

    def test_m4_definitions_and_duplicate_summing(self, cfg):
        ws = working_set([agg(comps=5, raw_comps=6, scales=3, n_modellable=7, w_incl_repeats=560, weight=500)])
        assert [run_scenario(spec({"kind": "m4_definition", "definition": d}, metrics=("M4",)), ws, cfg).m4 for d in ("raw_names", "scales", "events")] == [6.0, 3.0, 7.0]
        assert run_scenario(spec({"kind": "weight_definition", "duplicates": "included"}), ws, cfg).m1 == 560.0

    def test_the_diagnostic_population_uses_only_non_quarantined_non_registered_sessions(self, cfg):
        ws = working_set([agg(weight=500), agg(weight=100, population=NON), agg(weight=300, population=NON), agg(weight=None, population=NON, quarantined=True)])
        r = run_scenario(spec({"kind": "population", "population": NON}), ws, cfg)
        assert r.m3 == 2 and r.m1 == 200.0

    def test_unknown_or_unsupported_declarations_are_refused_not_approximated(self, cfg):
        for op in ({"kind": "teleport"}, {"kind": "exclude_dates", "set": "nope"}, {"kind": "m4_definition", "definition": "vibes"}, {"kind": "weight_definition", "duplicates": "ignored"},
                   {"kind": "population", "population": REG}, {"kind": "exclude_where", "field": "colour", "op": ">", "value": 1}, {"kind": "exclude_weight_outside", "method": "guess"}):
            with pytest.raises(ScenarioError):
                apply_operation(ws5(), cfg, op, engine._members(ws5().baseline))

    def test_running_a_scenario_never_mutates_the_working_set(self, cfg):
        ws = ws5()
        before = [(a.key, a.weight, a.core_ready) for a in ws.baseline]
        for op in ({"kind": "exclude_where_any_warn"}, {"kind": "drop_event", "selector": "largest_event"}, {"kind": "timezone_shift", "hours": 0}, {"kind": "pooled"}):
            run_scenario(spec(op), ws, cfg)
        assert [(a.key, a.weight, a.core_ready) for a in ws.baseline] == before


class TestTimezoneOperation:
    def sessions(self):
        early = [(datetime(2020, 10, 9, 5, 59, 59), OVERRIDE_FILE, "MODELLABLE")]        # raw 05:59:59: +3h -> 08:59:59 (before service hours)
        ok = [(datetime(2020, 10, 9, 6, 0, 0), OVERRIDE_FILE, "MODELLABLE")]             # raw 06:00:00: +3h -> 09:00:00 (inside)
        other = [(datetime(2020, 10, 9, 5, 0, 0), "registered_2020-10-19_2020-10-25.csv", "MODELLABLE")]     # another file: never shifted, never quarantined by an offset
        return working_set([agg(key="early|registered_export", events=early), agg(key="ok|registered_export", events=ok), agg(key="other|registered_export", events=other)])

    def test_t03_boundaries_under_the_baseline_offset(self, cfg):
        ws = self.sessions()
        assert run_scenario(spec({"kind": "timezone_shift", "hours": 3}), ws, cfg).detail["t03_quarantined_sessions"] == 1
        assert run_scenario(spec({"kind": "timezone_shift", "hours": 4}), ws, cfg).detail["t03_quarantined_sessions"] == 0

    def test_only_the_override_file_is_shifted(self, cfg):
        ws = self.sessions()
        for h in (0, 1, 2, 3, 4):
            r = run_scenario(spec({"kind": "timezone_shift", "hours": h}), ws, cfg)
            assert "other|registered_export" not in r.detail.get("sessions_removed", []) and r.detail["files_shifted"] == [OVERRIDE_FILE]
        r0 = run_scenario(spec({"kind": "timezone_shift", "hours": 0}), ws, cfg)
        assert r0.m3 == 1, "with no shift both override-file sessions leave service hours; the session in another file is never shifted or quarantined by an offset"


class TestRegistryValidation:
    def test_the_real_registry_is_valid(self):
        assert validate_registry() == []

    def bad(self, sid, **kw):
        specs = tuple(dataclasses.replace(x, **kw) if x.scenario_id == sid else x for x in SCENARIOS)
        return validate_registry(specs)

    def test_a_pooling_scenario_must_be_a_forbidden_comparison(self):
        assert any("forbidden comparison" in p for p in self.bad("G01", forbidden=False))
        assert any("forbidden comparison" in p for p in self.bad("G01", defensible=True))

    def test_an_exclusion_can_never_be_a_production_rule(self):
        assert any("diagnostic" in p for p in self.bad("S20", diagnostic_only=False))
        assert any("diagnostic" in p for p in self.bad("S10", diagnostic_only=False))

    def test_including_quarantined_sessions_is_a_what_if_only(self):
        assert any("quarantine is never weakened" in p for p in self.bad("S01", defensible=True))
        assert any("quarantine is never weakened" in p for p in self.bad("S01", diagnostic_only=False))

    def test_the_baseline_must_change_nothing_and_be_unique(self):
        assert any("exactly one scenario, S00" in p for p in self.bad("S00", operation={"kind": "exclude_dates", "set": "irregular_volume_days"}))
        dup = tuple(dataclasses.replace(x, scenario_id="S00b", operation={"kind": "baseline"}) if x.scenario_id == "S01" else x for x in SCENARIOS)
        assert any("exactly one scenario, S00" in p for p in validate_registry(dup))

    def test_a_waste_or_consumption_metric_cannot_be_declared(self):
        for name in ("W2", "WASTE", "CONSUMED_G"):
            assert any("no waste, consumption or proxy metric" in p for p in self.bad("S04", metrics_recalculated=("M1", name)))

    def test_timezone_scenarios_are_bounded_whole_hours_and_ids_unique(self):
        assert any("0-4 whole hours" in p for p in self.bad("TZ2", operation={"kind": "timezone_shift", "hours": 5}))
        assert any("0-4 whole hours" in p for p in self.bad("TZ2", operation={"kind": "timezone_shift", "hours": 2.5}))
        assert any("not unique" in p for p in validate_registry(SCENARIOS + (SCENARIOS[1],)))

    def test_a_diagnostic_population_cannot_become_defensible(self):
        assert any("diagnostic contrast" in p for p in self.bad("S40", defensible=True))


class TestNegativeAttempts:
    """Each block tries to break the frozen baseline the way a tempted analyst might. Every attempt must be caught."""

    @pytest.fixture()
    def inp(self, real_model):
        from src.metrics.inputs import load_metric_inputs
        return load_metric_inputs(real_model.out)

    def test_overwriting_the_baseline_metric_values_is_detected(self, inp, cfg, monkeypatch):
        real = evidence.run_scenario

        def tampered(s, ws, c):
            r = real(s, ws, c)
            if s.scenario_id == "S00":
                r.m1 += 5
            return r

        monkeypatch.setattr(evidence, "run_scenario", tampered)
        a = evidence.run_analysis(inp, cfg)
        assert a.failed and any("M1: baseline 504.0 differs from the approved 499.0" in p for p in a.baseline_problems)

    def test_making_2h_the_production_timezone_is_refused_at_configuration_and_again_by_the_analysis(self, inp, cfg, config_copy):
        from src.config import ConfigError, load_config
        config_copy.edit("timezone_overrides.yml", "offset_hours: 3", "offset_hours: 2")
        with pytest.raises(ConfigError, match="offset_hours must be 3"):
            load_config(config_copy.dir)
        # defence in depth: even a Config object built around the loader carries +2h, the analysis refuses to treat it as the baseline
        override = next(iter(cfg.timezone.overrides.values()))
        cfg2 = dataclasses.replace(cfg, timezone=dataclasses.replace(cfg.timezone, overrides={override.filename: dataclasses.replace(override, offset_hours=2)}))
        a = evidence.run_analysis(inp, cfg2)
        sc = next(c for c in a.checks if c.description.startswith("the configured override offset"))
        assert sc.status == "FAIL" and a.failed, "an alternative offset is tested, never adopted"

    def test_unquarantining_the_crossover_sessions_in_the_baseline_is_detected(self, inp, cfg, monkeypatch):
        real = evidence.build_working_set

        def unquarantine(i, c):
            ws = real(i, c)
            for a in ws.aggs.values():
                if a.quarantined and a.population == "registered_export":
                    a.quarantined, a.core_ready, a.weight = False, True, a.w_nonrepeat
            ws.baseline = sorted([a for a in ws.aggs.values() if a.population == "registered_export" and a.core_ready], key=lambda a: a.key)
            return ws

        monkeypatch.setattr(evidence, "build_working_set", unquarantine)
        a = evidence.run_analysis(inp, cfg)
        assert a.failed and any("M3: baseline 1699" in p for p in a.baseline_problems) and any("M5" in p for p in a.baseline_problems)

    def test_excluding_the_irregular_days_from_the_baseline_is_refused(self, inp, cfg, monkeypatch):
        tampered = tuple(dataclasses.replace(s, operation={"kind": "exclude_dates", "set": "irregular_volume_days"}) if s.scenario_id == "S00" else s for s in SCENARIOS)
        assert validate_registry(tampered)
        monkeypatch.setattr(evidence, "validate_registry", lambda: validate_registry(tampered))
        with pytest.raises(evidence.SensitivityError, match="registry is invalid"):
            evidence.run_analysis(inp, cfg)

    def test_changing_the_m5_denominator_is_detected(self, inp, cfg, monkeypatch):
        real = evidence.build_working_set

        def shrink(i, c):
            ws = real(i, c)
            ws.eligible = 1697
            return ws

        monkeypatch.setattr(evidence, "build_working_set", shrink)
        a = evidence.run_analysis(inp, cfg)
        assert a.failed and any("M5 counts 1697/1697 differ from the approved 1697/1699" in p for p in a.baseline_problems)
        assert next(c for c in a.checks if c.description.startswith("M5's denominator")).status == "FAIL"

    def test_introducing_a_waste_proxy_is_refused(self, inp, cfg, monkeypatch):
        proxy = dataclasses.replace(SCENARIO_BY_ID["S04"], scenario_id="S99", metrics_recalculated=("M1", "WASTE_PROXY_G"))
        assert any("no waste, consumption or proxy metric" in p for p in validate_registry(SCENARIOS + (proxy,)))
        monkeypatch.setattr(evidence, "validate_registry", lambda: validate_registry(SCENARIOS + (proxy,)))
        with pytest.raises(evidence.SensitivityError):
            evidence.run_analysis(inp, cfg)

    def test_pooling_the_populations_as_a_candidate_is_refused(self, inp, cfg, monkeypatch):
        pooled = dataclasses.replace(SCENARIO_BY_ID["G01"], forbidden=False, defensible=True)
        monkeypatch.setattr(evidence, "validate_registry", lambda: validate_registry(tuple(pooled if s.scenario_id == "G01" else s for s in SCENARIOS)))
        with pytest.raises(evidence.SensitivityError, match="forbidden comparison"):
            evidence.run_analysis(inp, cfg)

    def test_a_core_ready_session_silently_disappearing_fails_the_baseline(self, inp, cfg, monkeypatch):
        real = evidence.build_working_set

        def forge(i, c):
            ws = real(i, c)
            ws.baseline = ws.baseline[1:]
            return ws

        monkeypatch.setattr(evidence, "build_working_set", forge)
        a = evidence.run_analysis(inp, cfg)
        assert a.failed and any("M3: baseline 1696" in p for p in a.baseline_problems)


class TestReproductionGateCanFail:
    def test_a_reference_that_no_longer_reproduces_is_reported_not_tuned(self, monkeypatch):
        r = {s.scenario_id: engine.ScenarioResult(s.scenario_id, 1, 1.0, 1.0, 1, 5.0, 1, 1) for s in SCENARIOS}
        r["S23"] = engine.ScenarioResult("S23", 1, 505.0, 977.0, 1312, 5.0)
        wrong = tuple(dataclasses.replace(s, phase2=(505.0, 990.0, 1312, 5.0, None, None)) if s.scenario_id == "S23" else dataclasses.replace(s, phase2=None) for s in SCENARIOS)
        monkeypatch.setattr(evidence, "SCENARIOS", wrong)
        problems = evidence.phase2_mismatches(r)
        assert problems == ["S23: M2 977.000 vs 990.0"]

    def test_a_matching_reference_reports_nothing(self, monkeypatch):
        r = {"S23": engine.ScenarioResult("S23", 1, 505.0, 977.0, 1312, 5.0)}
        ok = tuple(dataclasses.replace(s, phase2=(505.0, 977.02, 1312, 5.0, None, None)) if s.scenario_id == "S23" else dataclasses.replace(s, phase2=None) for s in SCENARIOS)
        monkeypatch.setattr(evidence, "SCENARIOS", ok)
        assert evidence.phase2_mismatches(r) == []


class TestServiceHoursUpperBound:
    def test_15_00_local_is_outside_service_hours_and_14_59_59_is_inside(self, cfg):
        late = [(datetime(2020, 10, 9, 12, 0, 0), OVERRIDE_FILE, "MODELLABLE")]          # raw 12:00:00 + 3h = 15:00:00 (T03: hour < 15)
        edge = [(datetime(2020, 10, 9, 11, 59, 59), OVERRIDE_FILE, "MODELLABLE")]        # raw 11:59:59 + 3h = 14:59:59 (inside)
        ws = working_set([agg(key="late|registered_export", events=late), agg(key="edge|registered_export", events=edge)])
        r = run_scenario(spec({"kind": "timezone_shift", "hours": 3}), ws, cfg)
        assert r.detail["t03_quarantined_sessions"] == 1 and r.m3 == 1


class TestBaselineIsRecomputedIndependently:
    def test_a_small_disagreement_with_the_wp6_computation_is_reported_even_inside_the_approved_tolerance(self, real_model, cfg, monkeypatch):
        from src.metrics.evaluate import compute_all as real_compute
        from src.metrics.inputs import load_metric_inputs
        inp = load_metric_inputs(real_model.out)

        def nudged(i):
            res = real_compute(i)
            res["M2"] = dataclasses.replace(res["M2"], value=res["M2"].value + 0.03)      # within the approved 0.05 g tolerance
            return res

        monkeypatch.setattr(evidence, "compute_all", nudged)
        problems = evidence.run_analysis(inp, cfg).baseline_problems
        assert problems and all("differs from the WP6 computation" in p for p in problems) and not any("approved 1039.6" in p for p in problems)
