"""Timestamp handling: canonical UTC, DST semantics, and the file-specific override with its two gates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.stage.timestamps import (StagingError, TimezoneTreatment, iso_local, iso_utc, local_to_utc, parse_source_timestamp,
                                  stage_timestamp, treatment_for)
from src.vocab import LocalTimeStatus, TimezoneHandling

ZONE = "Europe/Helsinki"
REG = "registered_2020_10_05-2020_10_18.csv"
LOCAL = TimezoneTreatment(TimezoneHandling.SOURCE_LOCAL_ASSUMED, 0, ZONE, "assumption", "none")
SHIFT = TimezoneTreatment(TimezoneHandling.NORMALISED_PLUS_3H_STRONGEST_SUPPORT, 3, ZONE, "cross-export temporal alignment", "file_specific")
HANDOFF_LOCAL = {"normalization": "SOURCE_LOCAL_ASSUMED", "offset_hours": 0, "scope": "none", "source_confirmed": False}
HANDOFF_SHIFT = {"normalization": "NORMALISED_PLUS_3H_STRONGEST_SUPPORT", "offset_hours": 3, "scope": "file_specific", "source_confirmed": False}


def dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


# ---- parsing ---------------------------------------------------------------------------------------------------------------------------
class TestParsing:
    def test_both_source_formats(self):
        assert parse_source_timestamp("2020-10-09 11:07:07") == (dt("2020-10-09 11:07:07"), "dash")
        assert parse_source_timestamp("2020.10.16 07:47:02") == (dt("2020-10-16 07:47:02"), "dot")

    @pytest.mark.parametrize("bad", ["", "not a time", "2020-10-09", "2020-10-09 11:07", "2020-10-09 11:07:07.5", "09/10/2020 11:07:07", "2020-13-01 00:00:00"])
    def test_anything_else_is_unparseable_not_guessed(self, bad):
        assert parse_source_timestamp(bad) == (None, None)

    def test_surrounding_whitespace_is_tolerated_but_the_raw_text_is_kept_verbatim(self):
        staged = stage_timestamp(" 2020-10-09 11:07:07 ", LOCAL)
        assert staged.raw == " 2020-10-09 11:07:07 " and staged.status is LocalTimeStatus.OK

    def test_unparseable_staged_timestamp_keeps_raw_and_has_no_canonical_value(self):
        s = stage_timestamp("garbage", LOCAL)
        assert (s.raw, s.local, s.utc, s.status) == ("garbage", None, None, LocalTimeStatus.UNPARSEABLE)


# ---- canonical UTC and the 2020 clock change -------------------------------------------------------------------------------------------------
class TestCanonicalUtc:
    def test_summer_time_is_three_hours_ahead_of_utc(self):
        utc, status = local_to_utc(dt("2020-10-05 10:00:00"), ZONE)
        assert (iso_utc(utc), status) == ("2020-10-05T07:00:00Z", LocalTimeStatus.OK)

    def test_winter_time_is_two_hours_ahead_of_utc(self):
        utc, status = local_to_utc(dt("2020-10-26 10:00:00"), ZONE)
        assert (iso_utc(utc), status) == ("2020-10-26T08:00:00Z", LocalTimeStatus.OK)

    def test_the_same_wall_time_maps_to_different_utc_offsets_across_the_transition(self):
        """This is why SOURCE_LOCAL_ASSUMED must use zoneinfo and never a fixed +3h."""
        before, _ = local_to_utc(dt("2020-10-23 11:00:00"), ZONE)
        after, _ = local_to_utc(dt("2020-10-26 11:00:00"), ZONE)
        assert before.hour == 8 and after.hour == 9

    @pytest.mark.parametrize("wall, expected", [("2020-10-25 02:59:59", "2020-10-24T23:59:59Z"), ("2020-10-25 04:00:00", "2020-10-25T02:00:00Z")])
    def test_times_either_side_of_the_repeated_hour_convert_normally(self, wall, expected):
        utc, status = local_to_utc(dt(wall), ZONE)
        assert (iso_utc(utc), status) == (expected, LocalTimeStatus.OK)

    @pytest.mark.parametrize("wall", ["2020-10-25 03:00:00", "2020-10-25 03:30:00", "2020-10-25 03:59:59"])
    def test_the_repeated_hour_is_ambiguous_and_never_guessed(self, wall):
        utc, status = local_to_utc(dt(wall), ZONE)
        assert utc is None and status is LocalTimeStatus.AMBIGUOUS

    @pytest.mark.parametrize("wall", ["2020-03-29 03:00:00", "2020-03-29 03:30:00", "2020-03-29 03:59:59"])
    def test_the_skipped_hour_is_nonexistent_and_never_guessed(self, wall):
        utc, status = local_to_utc(dt(wall), ZONE)
        assert utc is None and status is LocalTimeStatus.NONEXISTENT

    def test_iso_helpers(self):
        assert iso_local(dt("2020-10-05 10:00:00")) == "2020-10-05T10:00:00" and iso_local(None) is None and iso_utc(None) is None


# ---- the file-specific override -----------------------------------------------------------------------------------------------------------------
class TestOverrideNormalization:
    def test_raw_text_is_preserved_and_the_local_time_is_shifted(self):
        s = stage_timestamp("2020.10.16 07:47:02", SHIFT)
        assert s.raw == "2020.10.16 07:47:02" and iso_local(s.local) == "2020-10-16T10:47:02"

    def test_within_scope_the_canonical_utc_equals_the_raw_time_read_as_utc(self):
        """The hypothesis is that this file is UTC. Inside its validated date range the shifted local time converts back to it."""
        d = dt("2020-10-05 07:00:00")
        for _ in range(0, 12 * 24 * 4):                       # every 15 minutes across the validated dates
            s = stage_timestamp(d.strftime("%Y.%m.%d %H:%M:%S"), SHIFT)
            assert s.utc.replace(tzinfo=None) == d and s.status is LocalTimeStatus.OK
            d += timedelta(minutes=15)
            if d > dt("2020-10-16 23:59:59"):
                break

    def test_outside_scope_the_equivalence_breaks_which_is_why_the_scope_check_exists(self):
        """After the clock change the same +3h would NOT reproduce the raw time as UTC: a general 'Helsinki = UTC+3' would be wrong."""
        s = stage_timestamp("2020.11.02 07:30:00", SHIFT)
        assert s.utc.replace(tzinfo=None) != dt("2020-11-02 07:30:00")

    def test_a_shifted_time_landing_in_the_repeated_hour_is_ambiguous_not_guessed(self):
        s = stage_timestamp("2020.10.25 00:30:00", SHIFT)          # +3h -> 03:30 on the repeated hour
        assert s.utc is None and s.status is LocalTimeStatus.AMBIGUOUS


class TestTreatmentGates:
    def test_a_normal_file_is_source_local_assumed(self, cfg):
        t = treatment_for(cfg, "registered_2020-11-02_2020-11-08.csv", HANDOFF_LOCAL)
        assert (t.handling, t.offset_hours, t.scope, t.zone) == (TimezoneHandling.SOURCE_LOCAL_ASSUMED, 0, "none", ZONE)
        assert "assumption" in t.reason

    def test_the_configured_file_gets_the_override_with_a_stated_reason(self, cfg):
        t = treatment_for(cfg, REG, HANDOFF_SHIFT)
        assert (t.handling, t.offset_hours, t.scope) == (TimezoneHandling.NORMALISED_PLUS_3H_STRONGEST_SUPPORT, 3, "file_specific")
        assert t.reason.startswith("cross-export temporal alignment") and "not source-confirmed" in t.reason

    @pytest.mark.parametrize("other", ["registered_2020-10-19_2020-10-25.csv", "non_registered_2020-10-05_2020-10-18.csv", "registered_2020_10_05-2020_10_18.CSV",
                                       "x" + REG, REG + ".bak", "registered_2020-10-05_2020-10-18.csv"])
    def test_a_handoff_that_shifts_any_other_file_is_refused(self, cfg, other):
        """Gate 1: the configuration must name the exact filename. A forged or mistaken handoff cannot widen the override."""
        with pytest.raises(StagingError, match="configuration has none for that file"):
            treatment_for(cfg, other, HANDOFF_SHIFT)

    def test_a_handoff_that_fails_to_shift_the_configured_file_is_refused(self, cfg):
        """Gate 2: config and handoff must agree in both directions."""
        with pytest.raises(StagingError, match="disagrees with the configured override"):
            treatment_for(cfg, REG, HANDOFF_LOCAL)

    @pytest.mark.parametrize("change", [{"offset_hours": 2}, {"offset_hours": 4}, {"scope": "global"}, {"source_confirmed": True},
                                        {"normalization": "SOURCE_LOCAL_ASSUMED"}])
    def test_any_deviation_in_the_handoffs_treatment_is_refused(self, cfg, change):
        with pytest.raises(StagingError, match="disagrees with the configured override"):
            treatment_for(cfg, REG, {**HANDOFF_SHIFT, **change})

    def test_partial_handoff_claims_on_other_files_are_refused_too(self, cfg):
        for bad in ({"offset_hours": 3}, {"normalization": "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"}, {"scope": "file_specific"}):
            with pytest.raises(StagingError):
                treatment_for(cfg, "registered_2020-11-02_2020-11-08.csv", {**HANDOFF_LOCAL, **bad})

    def test_only_one_configured_override_exists(self, cfg):
        assert list(cfg.timezone.overrides) == [REG]
