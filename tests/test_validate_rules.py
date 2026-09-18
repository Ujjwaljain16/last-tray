"""Each rule at its exact boundary, on hand-built staged events. No file access: rules are pure functions of staged rows."""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from src.validate import rules_events as re_, rules_files as rf, rules_sessions as rs, rules_volume as rv
from src.validate.model import ISSUE_COLUMNS, Issue, build_catalogue, finalise, issue_id
from src.validate.sessions import build_profiles, find_repeats
from src.vocab import Handling, Severity
from tests.validate_helpers import NON, REG, make_event, profiles_of


def rules_of(issues):
    return sorted(i.rule_id for i in issues)


# ---- event weights --------------------------------------------------------------------------------------------------------------------------
class TestEventWeightThresholds:
    def test_b02_is_inclusive_at_1500(self, cfg):
        evs = [make_event(weight=1499, row=1), make_event(weight=1500, row=2), make_event(weight=2097, row=3)]
        out = re_.check_weights(evs, {}, cfg.thresholds.rules)
        assert [i.event_id for i in out if i.rule_id == "B02"] == ["f.csv#2", "f.csv#3"]

    def test_b03_trace_is_inclusive_at_3_and_ignores_repeats(self, cfg):
        evs = [make_event(weight=3, row=1), make_event(weight=4, row=2), make_event(weight=2, row=3, raw_hash="x"), make_event(weight=2, row=4, raw_hash="x")]
        repeats = find_repeats(evs)
        assert [i.event_id for i in re_.check_weights(evs, repeats, cfg.thresholds.rules) if i.rule_id == "B03"] == ["f.csv#1", "f.csv#3"]

    def test_b01_zero_and_negative_weights_are_errors_not_trace(self, cfg):
        out = re_.check_weights([make_event(weight=0, row=1), make_event(weight=-5, row=2)], {}, cfg.thresholds.rules)
        assert rules_of(out) == ["B01", "B01"]

    def test_an_unparseable_weight_is_not_silently_treated_as_zero(self, cfg):
        e = make_event(weight=None, row=1, weight_raw="12.5", weight_parse_status="NOT_INTEGER")
        assert rules_of(re_.check_weights([e], {}, cfg.thresholds.rules)) == []
        assert rules_of(re_.check_structure([e])) == ["S06"]


# ---- structure ------------------------------------------------------------------------------------------------------------------------------
class TestStructuralRules:
    def test_empty_required_values_are_errors(self):
        out = re_.check_structure([make_event(tray="  ", row=1), make_event(scale="", row=2), make_event(name="", row=3, component_id_normalized="")])
        assert rules_of(out) == ["S05", "S05", "S05"]
        assert [i.observed_value for i in out] == ["tray_id", "scale_id", "component_name"]

    def test_unusable_timestamps_are_errors_per_column(self):
        e = make_event(row=1, event_time_status="UNPARSEABLE", event_time_local=None, event_time_utc=None, identification_time_status="AMBIGUOUS")
        out = re_.check_structure([e])
        assert rules_of(out) == ["S07", "S07"] and "weighing_event_time" in out[0].description and "user_identification_time" in out[1].description

    def test_schema_drift_and_hidden_cells_are_warned_never_repaired(self):
        e = make_event(row=1, row_parse_status="EXTRA_CELLS", unmapped_cells='{"blank_header_columns": {"8": "hidden"}}')
        assert rules_of(re_.check_structure([e])) == ["S04", "S08"]
        assert rules_of(re_.check_structure([make_event(row=2, row_parse_status="SHORT_ROW")])) == ["S08"]

    def test_a_clean_row_has_no_structural_finding(self):
        assert re_.check_structure([make_event(row=1)]) == []


# ---- time -----------------------------------------------------------------------------------------------------------------------------------
class TestTimeRules:
    def test_t03_service_hours_are_9_inclusive_to_15_exclusive(self, cfg):
        cases = {"2020-10-09T08:59:59": True, "2020-10-09T09:00:00": False, "2020-10-09T14:59:59": False, "2020-10-09T15:00:00": True}
        for i, (t, flagged) in enumerate(cases.items()):
            out = re_.check_time_window([make_event(local=t, row=i + 1)], cfg, cfg.thresholds.rules)
            assert ("T03" in rules_of(out)) is flagged, t

    def test_t01_window_edges(self, cfg):
        for day, flagged in {"2020-10-02": True, "2020-10-05": False, "2020-11-20": False, "2020-11-23": True}.items():
            out = re_.check_time_window([make_event(local=f"{day}T11:00:00", row=1)], cfg, cfg.thresholds.rules)
            assert ("T01" in rules_of(out)) is flagged, day

    def test_t02_weekend_event(self, cfg):
        assert "T02" in rules_of(re_.check_time_window([make_event(local="2020-10-10T11:00:00", row=1)], cfg, cfg.thresholds.rules))   # a Saturday

    def test_an_unplaceable_event_gets_no_time_rule_but_does_get_s07(self, cfg):
        e = make_event(row=1, event_time_status="UNPARSEABLE", event_time_local=None, event_time_utc=None)
        assert re_.check_time_window([e], cfg, cfg.thresholds.rules) == []


# ---- duplicates -----------------------------------------------------------------------------------------------------------------------------
class TestRepeatsVersusScoops:
    def test_an_identical_row_in_the_same_file_is_a_repeat_keep_first(self):
        a, b = make_event(row=1, raw_hash="same"), make_event(row=2, raw_hash="same")
        assert find_repeats([a, b]) == {"f.csv#2": "f.csv#1"}
        (issue,) = re_.check_repeats([a, b], find_repeats([a, b]))
        assert issue.rule_id == "I02" and issue.source_row_lineage == "f.csv#2;f.csv#1"

    def test_the_same_row_in_two_different_files_is_not_a_repeat(self):
        assert find_repeats([make_event(row=1, file="a.csv", raw_hash="same"), make_event(row=1, file="b.csv", raw_hash="same")]) == {}

    def test_same_scale_weighed_twice_with_different_weights_is_an_additive_scoop_not_a_duplicate(self):
        evs = [make_event(row=1, weight=40, local="2020-10-09T11:00:00"), make_event(row=2, weight=55, local="2020-10-09T11:00:20")]
        profiles, repeats = profiles_of(evs)
        assert repeats == {} and profiles["s1|registered_export"].rule_weight_sum_g == 95
        (issue,) = rs.check_repeated_scales(profiles, set())
        assert issue.rule_id == "B05" and "additive scoops" in issue.description

    def test_a_repeat_is_left_out_of_the_sum_but_stays_a_staged_row(self):
        evs = [make_event(row=1, weight=40, raw_hash="h"), make_event(row=2, weight=40, raw_hash="h"), make_event(row=3, weight=10, scale="koti2-vasen-salaatti2")]
        p = profiles_of(evs)[0]["s1|registered_export"]
        assert (len(p.events), len(p.counted), p.rule_weight_sum_g) == (3, 2, 50)


# ---- session rules --------------------------------------------------------------------------------------------------------------------------
def session(weight_a=100, weight_b=100, span_s=20, session_id="s1", population=REG, ident_offset_s=60, **kw):
    """Two weighings `span_s` apart; the session has ONE identification instant, `ident_offset_s` after the last weighing."""
    last = f"2020-10-09T11:{span_s // 60:02d}:{span_s % 60:02d}"
    from datetime import datetime, timedelta
    row_a, row_b = kw.pop("row_a", 1), kw.pop("row_b", 2)
    ident = (datetime.strptime(last, "%Y-%m-%dT%H:%M:%S") + timedelta(seconds=ident_offset_s)).strftime("%Y-%m-%dT%H:%M:%S")
    a = make_event(session_id=session_id, population=population, weight=weight_a, local="2020-10-09T11:00:00", row=row_a, scale="koti2-vasen-salaatti1", ident_at=ident, **kw)
    b = make_event(session_id=session_id, population=population, weight=weight_b, local=last, row=row_b, scale="koti2-vasen-salaatti2", ident_at=ident, **kw)
    return [a, b]


class TestSessionRules:
    def test_b07_range_is_inclusive_50_to_2200(self, cfg):
        for total, flagged in {49: True, 50: False, 2200: False, 2201: True}.items():
            profiles, _ = profiles_of(session(total - 10, 10))
            out = rs.check_session_metrics(profiles, cfg.thresholds.rules, REG)
            assert ("B07" in rules_of(out)) is flagged, total

    def test_t05_span_is_flagged_only_above_600_seconds(self, cfg):
        for span, flagged in {600: False, 601: True}.items():
            profiles, _ = profiles_of(session(span_s=span))
            assert ("T05" in rules_of(rs.check_session_metrics(profiles, cfg.thresholds.rules, REG))) is flagged, span

    def test_t04_identification_before_the_last_weighing(self, cfg):
        profiles, _ = profiles_of(session(span_s=30, ident_offset_s=-5))
        assert "T04" in rules_of(rs.check_session_metrics(profiles, cfg.thresholds.rules, REG))

    def test_b04_single_event_sessions_only_in_the_primary_population_and_are_not_errors(self, cfg):
        for pop, flagged in {REG: True, NON: False}.items():
            profiles, _ = profiles_of([make_event(population=pop, row=1)])
            out = rs.check_session_metrics(profiles, cfg.thresholds.rules, REG)
            assert ("B04" in rules_of(out)) is flagged
        assert build_catalogue(cfg)["B04"].severity is Severity.WARN and not build_catalogue(cfg)["B04"].handling is Handling.QUARANTINE

    def test_a_session_with_an_invalid_weight_gets_no_range_finding_instead_of_a_wrong_one(self, cfg):
        evs = session() + [make_event(weight=None, weight_raw="x", weight_parse_status="NOT_INTEGER", row=9, scale="koti2-vasen-salaatti3")]
        p = profiles_of(evs)[0]["s1|registered_export"]
        assert p.rule_weight_sum_g is None and "B07" not in rules_of(rs.check_session_metrics({p.session_key: p}, cfg.thresholds.rules, REG))

    def test_i04_two_trays_in_one_session_key_is_an_error(self):
        evs = [make_event(tray="t1", row=1), make_event(tray="t2", row=2, scale="koti2-vasen-salaatti2")]
        profiles, _ = profiles_of(evs)
        assert rules_of(rs.check_identity(profiles)) == ["I04"]

    def test_t06_two_identification_instants_in_one_session_key(self):
        evs = [make_event(row=1, ident_offset_s=60), make_event(row=2, scale="koti2-vasen-salaatti2", ident_offset_s=90)]
        assert rules_of(rs.check_identity(profiles_of(evs)[0])) == ["T06"]

    def test_the_same_identification_repeated_is_one_value(self):
        assert rs.check_identity(profiles_of(session())[0]) == []


# ---- populations and crossover --------------------------------------------------------------------------------------------------------------
class TestPopulationsAndCrossover:
    def test_the_same_session_id_in_two_populations_is_two_keys_never_merged(self):
        evs = session(session_id="sX", population=REG, row_a=1, row_b=2, file="r.csv") + session(session_id="sX", population=NON, row_a=1, row_b=2, file="n.csv")
        profiles, _ = profiles_of(evs)
        assert sorted(profiles) == ["sX|non_registered_export", "sX|registered_export"]
        assert all(len(p.events) == 2 for p in profiles.values())

    def test_i01_flags_both_versions_as_quarantine_errors(self, cfg):
        evs = session(session_id="sX", population=REG, file="r.csv") + session(session_id="sX", population=NON, file="n.csv") + session(session_id="sY", file="r.csv", row_a=8, row_b=9)
        profiles, _ = profiles_of(evs)
        issues = rs.check_crossover(profiles)
        assert sorted(i.session_key for i in issues) == ["sX|non_registered_export", "sX|registered_export"]
        rows = finalise(issues, build_catalogue(cfg), "run")
        assert all(r["severity"] == "ERROR" and r["quarantine"] is True for r in rows)

    def test_identical_versions_are_info_disagreeing_versions_are_warn(self):
        same = session(session_id="a", population=REG, file="r.csv") + session(session_id="a", population=NON, file="n.csv")
        assert [i.severity for i in rs.check_cross_export(profiles_of(same)[0])] == ["INFO"]
        other = session(session_id="b", population=REG, file="r.csv") + session(session_id="b", population=NON, file="n.csv", name="different dish")
        (issue,) = rs.check_cross_export(profiles_of(other)[0])
        assert issue.severity == "" and "disagree" in issue.description and "name conflicts: 2 of 2" in issue.observed_value

    def test_component_identity_i07_uses_normalised_strings_only(self):
        evs = [make_event(population=REG, name="Salad ", row=1, file="r.csv"), make_event(population=NON, name="salad", row=1, file="n.csv", session_id="z")]
        assert rs.check_component_identity_across_exports(evs) == [], "trim and casefold make these the same normalised string"
        evs = [make_event(population=REG, name="Potatoes", row=1, file="r.csv"), make_event(population=NON, name="Peruna", row=1, file="n.csv", session_id="z")]
        (issue,) = rs.check_component_identity_across_exports(evs)
        assert issue.rule_id == "I07" and issue.population == "both"


# ---- timezone -------------------------------------------------------------------------------------------------------------------------------
class TestTimezoneRules:
    SUSPECT = "registered_2020_10_05-2020_10_18.csv"

    def shifted(self, row, hour=10, **kw):
        return make_event(row=row, file=self.SUSPECT, local=f"2020-10-0{5 + row % 4}T{hour}:30:00", handling="NORMALISED_PLUS_3H_STRONGEST_SUPPORT", offset_h=3, **kw)

    def test_the_override_on_its_own_file_is_clean(self, cfg):
        evs = [self.shifted(1), self.shifted(2), self.shifted(3)]
        assert rf.check_override_scope(evs, cfg) == []

    def test_an_override_label_on_any_other_file_is_a_t10_error_that_blocks(self, cfg):
        leaked = make_event(row=1, file="registered_2020-10-19_2020-10-25.csv", handling="NORMALISED_PLUS_3H_STRONGEST_SUPPORT", offset_h=3)
        (issue,) = rf.check_override_scope([leaked], cfg)
        assert issue.rule_id == "T10" and issue.source_file == "registered_2020-10-19_2020-10-25.csv"
        (row,) = finalise([issue], build_catalogue(cfg), "run")
        assert row["severity"] == "ERROR" and row["handling"] == "BLOCK" and row["quarantine"] is False

    def test_the_named_file_losing_its_label_is_also_caught(self, cfg):
        unlabelled = make_event(row=1, file=self.SUSPECT)
        found = rf.check_override_scope([unlabelled], cfg)
        assert {i.entity_type for i in found} == {"event", "file"} and set(rules_of(found)) == {"T10"}, "the missing label AND the unshifted raw median are both reported"

    def test_dates_outside_the_validated_range_are_caught(self, cfg):
        late = make_event(row=1, file=self.SUSPECT, local="2020-10-20T11:30:00", handling="NORMALISED_PLUS_3H_STRONGEST_SUPPORT", offset_h=3)
        assert "T10" in rules_of(rf.check_override_scope([late], cfg))

    def test_t07_flags_a_file_whose_median_first_event_hour_is_outside_the_band(self, cfg):
        early = [make_event(row=i, file="r.csv", local=f"2020-10-0{i}T07:30:00") for i in (5, 6, 7)]
        (issue,) = [i for i in rf.check_files(early, cfg) if i.rule_id == "T07"]
        assert "NO normalization was applied" in issue.description
        ok = [make_event(row=i, file="r.csv", local=f"2020-10-0{i}T10:30:00") for i in (5, 6, 7)]
        assert not [i for i in rf.check_files(ok, cfg) if i.rule_id == "T07"]

    def test_the_shifted_file_is_reported_with_provenance_wording(self, cfg):
        evs = [self.shifted(i, hour=10) for i in (1, 2, 3)]      # treated hour 10.5; raw wall time 7.5
        (issue,) = [i for i in rf.check_files(evs, cfg) if i.rule_id == "T07"]
        assert "strongest-supported, not source-confirmed" in issue.description

    def test_a_round_trip_break_is_caught(self):
        from datetime import datetime, timedelta
        e = make_event(row=1)
        broken = dataclasses.replace(e, event_time_utc=e.event_time_utc + timedelta(hours=1))
        issues, checked = rf.check_dst_round_trip([e, broken])
        assert checked == 4 and rules_of(issues) == ["X04"]

    def test_s03_and_t08_are_file_level_info(self, cfg):
        evs = [make_event(row=1, file="a.csv", local="2020-10-09T10:30:00", weighing_type="", identification_time_source_format="dot")]
        assert rules_of(rf.check_files(evs, cfg)) == ["S03", "T08"]


# ---- volume ---------------------------------------------------------------------------------------------------------------------------------
def day_sessions(day: str, n: int, population=REG):
    evs = []
    for i in range(n):
        evs.append(make_event(session_id=f"{day}-{i}", population=population, local=f"{day}T11:{i % 60:02d}:00", row=len(evs) + 1, file="f.csv", tray=f"t{i}"))
    return evs


class TestVolumeRules:
    def days(self, cfg, spec: dict[str, int], quarantined=frozenset()):
        evs = [e for d, n in spec.items() for e in day_sessions(d, n)]
        return rv.service_days(build_profiles(evs, {}), set(quarantined), cfg)

    def test_c02a_low_volume_boundary_at_30_sessions(self, cfg):
        days = self.days(cfg, {"2020-10-05": 29, "2020-10-06": 30})
        assert [d.low_observed_volume for d in days] == [True, False]

    def test_c02b_irregularity_compares_observed_regime_with_the_weekday_baseline(self, cfg):
        # 2020-11-02 is a Monday (baseline regime: high); 2020-11-05 a Thursday (baseline regime: low)
        days = self.days(cfg, {"2020-11-02": 20, "2020-11-05": 40, "2020-11-03": 45, "2020-11-06": 5})
        flags = {d.service_date.isoformat(): d.volume_irregularity for d in days}
        assert flags == {"2020-11-02": True, "2020-11-03": False, "2020-11-05": True, "2020-11-06": False}

    def test_volume_findings_never_quarantine_or_exclude(self, cfg):
        days = self.days(cfg, {"2020-11-02": 20})
        issues = rv.check_volume(days, cfg)
        rows = finalise(issues, build_catalogue(cfg), "run")
        assert {r["rule_id"] for r in rows} == {"C02a", "C02b"} and not any(r["quarantine"] for r in rows)
        assert all("NOT a data error" in r["description"] for r in rows if r["rule_id"] == "C02b")
        assert [d.sessions for d in days] == [20], "the day keeps all its sessions"

    def test_quarantined_sessions_do_not_count_as_observed_valid_sessions(self, cfg):
        evs = day_sessions("2020-10-05", 5)
        days = rv.service_days(build_profiles(evs, {}), {"s-not-there"}, cfg)
        assert days[0].sessions == 5
        days = rv.service_days(build_profiles(evs, {}), {evs[0].session_key}, cfg)
        assert days[0].sessions == 4

    def test_only_the_primary_population_carries_volume_flags(self, cfg):
        evs = day_sessions("2020-11-02", 3, population=NON)
        (d,) = rv.service_days(build_profiles(evs, {}), set(), cfg)
        assert not d.low_observed_volume and not d.volume_irregularity and d.expected_regime is None

    def test_baseline_regimes_are_derived_from_the_baseline_weeks_and_equal_the_configuration(self, cfg):
        spec = {"2020-10-05": 50, "2020-10-06": 50, "2020-10-07": 50, "2020-10-08": 5, "2020-10-09": 5}
        derived = rv.derive_baseline_regimes(self.days(cfg, spec), cfg, REG)
        assert derived == cfg.thresholds.volume.expected_regime_by_weekday

    def test_c01_and_c03_report_missing_weekdays_and_weeks(self, cfg):
        days = self.days(cfg, {"2020-10-05": 40})
        issues = rv.check_coverage(days, cfg)
        assert "C01" in rules_of(issues) and rules_of(issues).count("C03") == 6, "seven weeks in the window, one present"


# ---- schema, severity and quarantine behaviour ---------------------------------------------------------------------------------------------------
class TestIssueSchemaAndSeverityBehaviour:
    def test_the_issue_schema_is_stable_and_every_field_has_one_meaning(self):
        assert ISSUE_COLUMNS == ("validation_issue_id", "run_id", "rule_id", "category", "severity", "handling", "quarantine", "entity_type", "entity_id",
                                 "session_key", "event_id", "population", "source_snapshot_id", "source_file", "lineage_basis", "source_row_lineage",
                                 "observed_value", "expected_condition", "description", "business_consequence")

    def test_ids_are_content_derived_and_stable(self):
        assert issue_id("B02", "event", "f#1") == issue_id("B02", "event", "f#1") != issue_id("B02", "event", "f#2")

    def test_finalise_refuses_a_duplicate_finding_and_an_unknown_rule(self, cfg):
        cat = build_catalogue(cfg)
        one = Issue("B02", "event", "f#1", "EVENT_ROW", "x")
        with pytest.raises(ValueError, match="not unique"):
            finalise([one, one], cat, "run")
        with pytest.raises(ValueError, match="unknown rule"):
            finalise([Issue("Z99", "event", "f#1", "EVENT_ROW", "x")], cat, "run")

    def test_severity_and_handling_follow_the_configuration_not_the_code(self, cfg):
        stricter = dataclasses.replace(cfg.thresholds.rules["B02"], severity=Severity.ERROR, handling=Handling.QUARANTINE)
        cfg2 = dataclasses.replace(cfg, thresholds=dataclasses.replace(cfg.thresholds, rules={**cfg.thresholds.rules, "B02": stricter}))
        (row,) = finalise([Issue("B02", "event", "f#1", "EVENT_ROW", "x")], build_catalogue(cfg2), "run")
        assert (row["severity"], row["handling"], row["quarantine"]) == ("ERROR", "QUARANTINE", True)
        (base,) = finalise([Issue("B02", "event", "f#1", "EVENT_ROW", "x")], build_catalogue(cfg), "run")
        assert (base["severity"], base["handling"], base["quarantine"]) == ("WARN", "FLAG", False)

    def test_only_error_rules_that_quarantine_ever_quarantine(self, cfg):
        cat = build_catalogue(cfg)
        for rid, spec in cat.items():
            if spec.handling is Handling.QUARANTINE:
                assert spec.severity is Severity.ERROR, rid
            if spec.severity is not Severity.ERROR:
                assert spec.handling in (Handling.FLAG, Handling.KEEP_FIRST), rid
        assert {r for r, s in cat.items() if s.handling is Handling.QUARANTINE} == {"S05", "S06", "S07", "B01", "T01", "T03", "I01", "I04"}
        assert "B06" not in cat, "retired rule"

    def test_an_event_level_error_quarantines_its_session_key_and_keeps_every_row(self, cfg):
        from src.validate.validate import collect_core_issues
        from src.validate.load import StagedInputs
        evs = session(session_id="bad") + [make_event(session_id="bad", weight=0, row=5, scale="koti2-vasen-salaatti3")] + session(session_id="ok", row_a=11, row_b=12)
        profiles, repeats = profiles_of(evs)
        inp = StagedInputs({}, evs, [], None, None, {})
        issues, quarantined = collect_core_issues(inp, cfg, profiles, repeats)
        assert quarantined == {"bad|registered_export"} and len(profiles["bad|registered_export"].events) == 3

    def test_severity_never_implies_deletion_unless_quarantine_says_so(self, cfg):
        rows = finalise([Issue("B02", "event", "f#1", "EVENT_ROW", "x"), Issue("I02", "event", "f#2", "EVENT_ROW", "x"), Issue("T10", "file", "f", "SOURCE_FILE", "x")],
                        build_catalogue(cfg), "run")
        assert {r["rule_id"]: r["quarantine"] for r in rows} == {"B02": False, "I02": False, "T10": False}
