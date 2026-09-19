"""Canonical model behaviour on hand-built staged events: each semantic rule in isolation."""
from __future__ import annotations

from datetime import datetime

import pytest

from src.model import control, schema
from src.model.events import build_events, quality_of
from src.model.sessions import build_components, build_sessions, selected_meal_weight
from src.model.volume import build_daily_volume
from src.model.weather import WeatherModelError, build_weather, ceil_hour, join_sessions
from tests.model_helpers import make_event, model_inputs, wx
from tests.validate_helpers import NON, REG


def build(events, cfg, **kw):
    inp = model_inputs(events, **kw)
    ev = build_events(inp)
    return inp, ev, build_sessions(ev, inp, cfg)


class TestSelectedMealWeight:
    def test_repeated_same_scale_weighings_are_additive(self, cfg):
        evs = [make_event(row=1, weight=40, local="2020-10-09T11:00:00"), make_event(row=2, weight=55, local="2020-10-09T11:00:20"),
               make_event(row=3, weight=10, scale="koti2-vasen-salaatti2", local="2020-10-09T11:00:30")]
        _, _, (s,) = build(evs, cfg)
        assert s["derived_selected_meal_weight_g"] == 105 and s["modellable_event_count"] == 3

    def test_an_exact_duplicate_is_not_double_counted_but_stays_a_row(self, cfg):
        evs = [make_event(row=1, weight=40, raw_hash="h"), make_event(row=2, weight=40, raw_hash="h"), make_event(row=3, weight=10, scale="koti2-vasen-salaatti2")]
        inp, ev, (s,) = build(evs, cfg)
        assert s["derived_selected_meal_weight_g"] == 50 and (s["event_count"], s["modellable_event_count"], s["duplicate_excluded_event_count"]) == (3, 2, 1)
        assert [e["disposition"] for e in ev] == ["MODELLABLE", "DUPLICATE_EXCLUDED", "MODELLABLE"] and [e["is_exact_duplicate"] for e in ev] == [False, True, False]

    def test_an_invalid_weight_gives_null_never_zero(self, cfg):
        evs = [make_event(row=1, weight=40), make_event(row=2, weight=None, weight_raw="12.5", weight_parse_status="NOT_INTEGER", scale="koti2-vasen-salaatti2")]
        _, ev, (s,) = build(evs, cfg)
        assert s["derived_selected_meal_weight_g"] is None and s["core_ready"] is False
        assert ev[1]["weight_raw"] == "12.5" and ev[1]["component_weight_g"] is None and ev[1]["weight_status"] == "NOT_INTEGER"

    def test_no_modellable_event_means_null_not_zero(self):
        assert selected_meal_weight([]) is None

    def test_a_quarantined_session_keeps_its_rows_but_has_no_selected_weight(self, cfg):
        evs = [make_event(session_id="x", weight=70, row=1, file="r.csv"), make_event(session_id="x", weight=30, scale="koti2-vasen-salaatti2", row=2, file="r.csv")]
        inp, ev, (s,) = build(evs, cfg, quarantine=["x|registered_export"])
        assert s["derived_selected_meal_weight_g"] is None and s["is_quarantined"] and s["quarantined_event_count"] == 2 and s["modellable_event_count"] == 0
        assert s["core_ready"] is False and s["first_weighing_utc"] is not None, "traceable in time"
        assert [e["disposition"] for e in ev] == ["QUARANTINED"] * 2 and [e["component_weight_g"] for e in ev] == [70, 30], "observed weights are kept on the rows"
        assert [e["quarantine_rule_ids"] for e in ev] == ["I01", "I01"] and all(e["quality_status"] == "INVALID" for e in ev)

    def test_the_large_weight_stays_modellable(self, cfg):
        _, ev, (s,) = build([make_event(row=1, weight=2097)], cfg, warns={"s1|registered_export": "B07"})
        assert ev[0]["is_modellable"] and s["derived_selected_meal_weight_g"] == 2097 and s["core_ready"] is True


class TestSessionKeysAndPopulations:
    def test_the_same_id_in_two_populations_is_two_sessions_never_merged(self, cfg):
        evs = [make_event(session_id="s", population=REG, weight=10, file="r.csv", row=1), make_event(session_id="s", population=NON, weight=99, file="n.csv", row=1)]
        _, _, sessions = build(evs, cfg, quarantine=["s|registered_export", "s|non_registered_export"])
        assert [s["session_key"] for s in sessions] == ["s|non_registered_export", "s|registered_export"]
        assert all(s["identity_conflict"] for s in sessions) and {s["population"] for s in sessions} == {REG, NON}

    def test_core_ready_needs_primary_population_no_error_and_a_valid_weight(self, cfg):
        evs = [make_event(session_id="a", population=REG, row=1, file="r.csv"), make_event(session_id="b", population=NON, row=1, file="n.csv"),
               make_event(session_id="c", population=REG, row=2, file="r.csv")]
        _, _, sessions = build(evs, cfg, errors={"c|registered_export": "B01"})
        ready = {s["session_key"]: s["core_ready"] for s in sessions}
        assert ready == {"a|registered_export": True, "b|non_registered_export": False, "c|registered_export": False}

    def test_a_quarantined_key_is_never_core_ready_even_if_dispositions_disagree(self, cfg):
        inp = model_inputs([make_event(row=1)], quarantine=["s1|registered_export"], errors={"s1|registered_export": ""})
        inp.event_status["f.csv#1"]["disposition"] = "MODELLABLE"           # an inconsistent forgery: the key is quarantined but the event is not
        (s,) = build_sessions(build_events(inp), inp, cfg)
        assert s["is_quarantined"] and s["core_ready"] is False, "the quarantine decision is authoritative"

    def test_warn_findings_never_remove_core_readiness(self, cfg):
        _, _, (s,) = build([make_event(row=1)], cfg, warns={"s1|registered_export": "B04;B07"}, session_warn=["s1|registered_export"])
        assert s["core_ready"] is True and s["has_session_warn"] is True and s["quality_status"] == "WARN" and s["max_validation_severity"] == "WARN"

    def test_session_fields_are_deterministic_regardless_of_event_order(self, cfg):
        evs = [make_event(row=i, weight=10 * i, scale=f"koti2-vasen-salaatti{i}", local=f"2020-10-09T11:00:{i:02d}") for i in (1, 2, 3)]
        a = build(evs, cfg)[2]
        b = build(list(reversed(evs)), cfg)[2]
        assert a == b, "row order in staging must not change a session"

    def test_first_last_span_and_service_date(self, cfg):
        evs = [make_event(row=1, local="2020-10-09T11:00:05"), make_event(row=2, scale="koti2-vasen-salaatti2", local="2020-10-09T11:01:20")]
        _, _, (s,) = build(evs, cfg)
        assert (s["first_weighing_local"], s["last_weighing_utc"], s["session_span_s"], s["service_date"]) == ("2020-10-09T11:00:05", "2020-10-09T08:01:20Z", 75, "2020-10-09")
        assert s["session_duration_minutes"] == 1.25


class TestComponents:
    def test_normalisation_merges_spelling_only_and_never_different_dishes(self, cfg):
        evs = [make_event(row=1, name="Salad ", scale="koti2-vasen-salaatti1"), make_event(row=2, name="  salad", scale="koti2-vasen-salaatti2"),
               make_event(row=3, name="Salad bar", scale="koti2-vasen-salaatti3"), make_event(row=4, name="Kaalisalaatti", scale="koti2-vasen-salaatti4")]
        inp, ev, (s,) = build(evs, cfg)
        comps = build_components(ev)
        assert [c["component_id_normalized"] for c in comps] == ["kaalisalaatti", "salad", "salad bar"], "no alias table, no fuzzy matching"
        salad = next(c for c in comps if c["component_id_normalized"] == "salad")
        assert salad["component_name_raw_variants"] == "  salad|Salad " and salad["component_weighing_event_count"] == 2 and salad["derived_component_weight_g"] == 200
        assert s["distinct_component_count"] == 3 and s["distinct_raw_component_count"] == 4, "here raw differs from normalised: the control would report it"

    def test_component_rows_come_from_modellable_events_only(self, cfg):
        evs = [make_event(session_id="q", row=1, name="a"), make_event(session_id="ok", row=2, name="b")]
        inp, ev, _ = build(evs, cfg, quarantine=["q|registered_export"])
        assert [c["session_key"] for c in build_components(ev)] == ["ok|registered_export"]

    def test_limited_status_follows_rule_i07_scale_days(self, cfg):
        evs = [make_event(row=1, scale="koti2-vasen-salaatti1", local="2020-10-09T11:00:00"), make_event(session_id="o", row=2, scale="koti2-vasen-salaatti1", local="2020-10-12T11:00:00")]
        issues = [{"rule_id": "I07", "entity_id": "koti2-vasen-salaatti1|2020-10-09"}]
        _, _, sessions = build(evs, cfg, issues=issues)
        assert {s["session_id"]: s["distinct_component_count_status"] for s in sessions} == {"s1": "LIMITED", "o": "READY_WITH_LIMITATION"}


class TestEventFactPreservation:
    def test_raw_local_utc_and_timezone_provenance_are_kept(self, cfg):
        e = make_event(row=1, local="2020-10-09T11:00:00", handling="NORMALISED_PLUS_3H_STRONGEST_SUPPORT", offset_h=3, file="registered_2020_10_05-2020_10_18.csv",
                       event_time_raw="2020.10.09 08:00:00", timezone_transformation_reason="cross-export temporal alignment")
        (row,) = build_events(model_inputs([e]))
        assert row["event_time_raw"] == "2020.10.09 08:00:00" and row["event_time_local"] == "2020-10-09T11:00:00" and row["event_time_utc"] == "2020-10-09T08:00:00Z"
        assert row["timezone_handling"] == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT" and row["timezone_offset_hours_applied"] == 3
        assert row["timezone_transformation_reason"] == "cross-export temporal alignment"

    def test_event_columns_equal_the_declared_schema(self):
        (row,) = build_events(model_inputs([make_event(row=1)]))
        assert tuple(row) == schema.EVENT.column_names

    def test_quality_status_rules(self):
        assert quality_of("", "", "MODELLABLE") == "VALID" and quality_of("", "B02", "MODELLABLE") == "WARN"
        assert quality_of("B01", "", "MODELLABLE") == "INVALID" and quality_of("", "", "QUARANTINED") == "INVALID"


class TestWeatherJoin:
    def test_ceil_to_the_next_full_utc_hour_and_an_exact_hour_keeps_itself(self):
        assert ceil_hour(datetime(2020, 10, 9, 8, 0, 1)) == datetime(2020, 10, 9, 9)
        assert ceil_hour(datetime(2020, 10, 9, 8, 59, 59)) == datetime(2020, 10, 9, 9)
        assert ceil_hour(datetime(2020, 10, 9, 9, 0, 0)) == datetime(2020, 10, 9, 9)

    def weather(self, cfg, hours, **kw):
        rows = [wx(h, p) for h in hours for p in cfg.sources.weather.request["parameters"]]
        return build_weather(model_inputs([make_event(row=1)], weather=rows), cfg)

    def test_a_session_joins_the_hour_ending_after_its_first_weighing(self, cfg):
        _, _, sessions = build([make_event(row=1, local="2020-10-09T11:20:00")], cfg)          # 08:20 UTC -> 09:00 UTC
        join_sessions(sessions, self.weather(cfg, ["2020-10-09T08:00:00Z", "2020-10-09T09:00:00Z"]))
        (s,) = sessions
        assert s["weather_hour_utc"] == "2020-10-09T09:00:00Z" and s["weather_matched"] and s["weather_join_status"] == "MATCHED" and s["weather_fmisid"] == 100949

    def test_the_join_is_dst_correct_after_the_clock_change(self, cfg):
        # 2020-10-26 is after the change: 11:20 local = 09:20 UTC, so the join hour is 10:00 UTC
        e = make_event(row=1, local="2020-10-26T11:20:00")
        object.__setattr__(e, "event_time_utc", datetime(2020, 10, 26, 9, 20, tzinfo=e.event_time_utc.tzinfo))
        inp = model_inputs([e])
        sessions = build_sessions(build_events(inp), inp, cfg)
        join_sessions(sessions, self.weather(cfg, ["2020-10-26T09:00:00Z", "2020-10-26T10:00:00Z"]))
        assert sessions[0]["weather_hour_utc"] == "2020-10-26T10:00:00Z" and sessions[0]["weather_matched"]

    def test_a_missing_hour_is_unmatched_and_the_session_stays_valid(self, cfg):
        _, _, sessions = build([make_event(row=1, local="2020-10-09T11:20:00")], cfg)
        join_sessions(sessions, self.weather(cfg, ["2020-10-09T15:00:00Z"]))
        s = sessions[0]
        assert s["weather_join_status"] == "UNMATCHED_NO_OBSERVATION" and not s["weather_matched"] and s["core_ready"] is True, "weather never enters readiness"

    def test_quarantined_sessions_are_not_joined(self, cfg):
        _, _, sessions = build([make_event(session_id="q", row=1)], cfg, quarantine=["q|registered_export"])
        join_sessions(sessions, self.weather(cfg, ["2020-10-09T09:00:00Z"]))
        assert sessions[0]["weather_join_status"] == "NOT_ATTEMPTED_QUARANTINED" and sessions[0]["weather_hour_utc"] is None

    def test_blocked_weather_marks_sessions_without_inventing_values(self, cfg):
        _, _, sessions = build([make_event(row=1, local="2020-10-09T11:20:00")], cfg)
        join_sessions(sessions, None, "weather blocked")
        assert sessions[0]["weather_join_status"] == "WEATHER_BLOCKED" and not sessions[0]["weather_matched"] and sessions[0]["weather_r_1h_null"] is None

    def test_nan_stays_null_with_status_never_zero_and_never_backfilled(self, cfg):
        params = cfg.sources.weather.request["parameters"]
        rows = [wx("2020-10-09T09:00:00Z", p, status="NAN_SOURCE_NULL" if p == "r_1h" else "OK") for p in params]
        (w,) = build_weather(model_inputs([make_event(row=1)], weather=rows), cfg)
        assert w["r_1h_mm"] is None and w["r_1h_status"] == "NAN_SOURCE_NULL" and w["t2m_c"] == "10.5" and w["is_null_any"] is True
        _, _, sessions = build([make_event(row=1, local="2020-10-09T11:20:00")], cfg)
        join_sessions(sessions, [w])
        assert sessions[0]["weather_r_1h_null"] is True and sessions[0]["weather_ri_10min_null"] is False

    def test_a_missing_parameter_becomes_a_MISSING_status(self, cfg):
        rows = [wx("2020-10-09T09:00:00Z", "t2m")]
        (w,) = build_weather(model_inputs([make_event(row=1)], weather=rows), cfg)
        assert w["ws_10min_status"] == "MISSING" and w["ws_10min_ms"] is None and w["is_null_any"] is True

    def test_a_duplicate_station_hour_parameter_blocks_weather(self, cfg):
        rows = [wx("2020-10-09T09:00:00Z", "t2m"), wx("2020-10-09T09:00:00Z", "t2m", value="11")]
        with pytest.raises(WeatherModelError, match="duplicate station-hour-parameter"):
            build_weather(model_inputs([make_event(row=1)], weather=rows), cfg)

    def test_an_unrequested_parameter_blocks_weather(self, cfg):
        with pytest.raises(WeatherModelError, match="unrequested"):
            build_weather(model_inputs([make_event(row=1)], weather=[wx("2020-10-09T09:00:00Z", "humidity")]), cfg)

    def test_unavailable_weather_raises_a_weather_only_error(self, cfg):
        with pytest.raises(WeatherModelError):
            build_weather(model_inputs([make_event(row=1)], weather=None), cfg)


class TestDailyVolume:
    def sessions_on(self, cfg, day, n, population=REG, quarantine=()):
        evs = [make_event(session_id=f"{day}-{i}", population=population, local=f"{day}T11:{i % 60:02d}:00", row=i + 1, file=f"{population}.csv") for i in range(n)]
        _, _, sessions = build(evs, cfg, quarantine=quarantine)
        return sessions

    def test_low_volume_boundary_and_flag_only_semantics(self, cfg):
        rows = build_daily_volume(self.sessions_on(cfg, "2020-10-05", 29) + self.sessions_on(cfg, "2020-10-06", 30), cfg)
        assert [(r["sessions"], r["low_observed_volume_day"]) for r in rows] == [(29, True), (30, False)]

    def test_irregularity_is_observed_vs_weekday_baseline_and_nothing_is_excluded(self, cfg):
        rows = build_daily_volume(self.sessions_on(cfg, "2020-11-02", 20), cfg)      # a Monday: baseline regime high
        assert rows[0]["volume_irregularity"] is True and rows[0]["sessions"] == 20 and rows[0]["expected_regime"] == "high"

    def test_non_primary_days_carry_no_flags_and_populations_are_not_pooled(self, cfg):
        rows = build_daily_volume(self.sessions_on(cfg, "2020-11-02", 3, population=NON) + self.sessions_on(cfg, "2020-11-02", 40), cfg)
        by_pop = {r["population"]: r for r in rows}
        assert by_pop[NON]["sessions"] == 3 and by_pop[REG]["sessions"] == 40
        assert not by_pop[NON]["low_observed_volume_day"] and not by_pop[NON]["volume_irregularity"] and by_pop[NON]["expected_regime"] is None

    def test_quarantined_sessions_are_counted_apart_from_observed_valid_sessions(self, cfg):
        sessions = self.sessions_on(cfg, "2020-10-05", 5, quarantine=["2020-10-05-0|registered_export"])
        (row,) = build_daily_volume(sessions, cfg)
        assert (row["sessions"], row["quarantined_sessions"], row["events"]) == (4, 1, 4)


class TestControlDetectsDisagreement:
    def test_a_wp4_weight_that_differs_is_reported_by_session(self, cfg):
        evs = [make_event(row=1, weight=40), make_event(row=2, weight=10, scale="koti2-vasen-salaatti2")]
        inp, ev, sessions = build(evs, cfg)
        inp.session_status["s1|registered_export"]["rule_weight_sum_g"] = "999"
        rows = control.session_control_rows(sessions, inp)
        assert rows[0]["weight_control"] == "MISMATCH" and rows[0]["canonical_weight_g"] == 50 and rows[0]["validation_rule_weight_sum_g"] == 999

    def test_a_quarantined_session_with_a_canonical_weight_would_be_a_mismatch(self, cfg):
        inp, ev, sessions = build([make_event(row=1)], cfg, quarantine=["s1|registered_export"])
        sessions[0]["derived_selected_meal_weight_g"] = 100
        assert control.session_control_rows(sessions, inp)[0]["weight_control"] == "MISMATCH"
