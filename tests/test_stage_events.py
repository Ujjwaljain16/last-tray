"""Event staging on small synthetic files: every row kept, raw preserved, drift handled by name, populations never merged."""
from __future__ import annotations

import json

import pytest

from src.stage.events import EVENT_COLUMNS, MemberMeta, stage_member
from src.stage.timestamps import StagingError, TimezoneTreatment
from src.vocab import TimezoneHandling

ZONE = "Europe/Helsinki"
LOCAL = TimezoneTreatment(TimezoneHandling.SOURCE_LOCAL_ASSUMED, 0, ZONE, "assumption", "none")
SHIFT = TimezoneTreatment(TimezoneHandling.NORMALISED_PLUS_3H_STRONGEST_SUPPORT, 3, ZONE, "cross-export temporal alignment", "file_specific")
V8 = "session_id,weighing_event_time,weighting_type,scale_identifier,weight_of_a_component,component_name,tray_id,user_identification_time,,,,"
V7 = "session_id,weighing_event_time,scale_identifier,weight_of_a_component,component_name,tray_id,user_identification_time,,,,"


def csv_bytes(header: str, rows: list[str]) -> bytes:
    return ("﻿" + "\r\n".join([header, *rows]) + "\r\n").encode("utf-8")


def meta(rows: int, population="registered_export", file="f.csv") -> MemberMeta:
    tz = {"normalization": "SOURCE_LOCAL_ASSUMED", "offset_hours": 0, "scope": "none", "source_confirmed": False}
    return MemberMeta(file, f"snap/{file}", "snap-1", population, "V8_with_weighting_type", "fp", rows, "0" * 64, tz)


ROW = "session1,2020-10-09 11:07:07,line,koti2-vasen-salaatti3,49,Kurkku-mandariini ,tray473,2020-10-09 11:08:15"


# ---- nothing is dropped, nothing is judged --------------------------------------------------------------------------------------------------
class TestEveryRowIsKeptAsFound:
    def test_odd_rows_are_staged_not_filtered(self, cfg):
        rows = [
            "s1,2020-10-09 11:00:00,line,koti2-vasen-salaatti1,0,Salad,tray1,2020-10-09 11:01:00",          # zero weight
            "s2,2020-10-09 11:00:00,line,koti2-vasen-salaatti1,2097,Stew,tray2,2020-10-09 11:01:00",       # huge weight
            "s3,2020-10-09 11:00:00,line,koti2-vasen-salaatti1,12.5,Salad,tray3,2020-10-09 11:01:00",      # not an integer
            "s4,not a time,line,koti2-vasen-salaatti1,50,Salad,tray4,also not a time",                     # unparseable timestamps
            "s5,2020-10-09 11:00:00,line,koti2-vasen-salaatti1,50,Salad,tray5,2020-10-09 11:01:00",
            "s5,2020-10-09 11:00:00,line,koti2-vasen-salaatti1,50,Salad,tray5,2020-10-09 11:01:00",        # exact duplicate row
        ]
        ev = stage_member(csv_bytes(V8, rows), meta(6), cfg, LOCAL)
        assert len(ev) == 6, "staging must not filter or deduplicate"
        assert [e.component_weight_g for e in ev] == [0, 2097, None, 50, 50, 50]
        assert ev[2].weight_raw == "12.5" and ev[2].weight_parse_status == "NOT_INTEGER"
        assert ev[3].event_time_status == "UNPARSEABLE" and ev[3].event_time_canonical_utc is None and ev[3].event_time_raw == "not a time"
        assert ev[4].raw_row_sha256 == ev[5].raw_row_sha256 and ev[4].event_id != ev[5].event_id

    def test_blank_lines_are_skipped_and_do_not_consume_row_numbers(self, cfg):
        ev = stage_member(csv_bytes(V8, [ROW, "", ROW.replace("session1", "session2"), " , , ", ROW.replace("session1", "session3")]), meta(3), cfg, LOCAL)
        assert [e.source_row_number for e in ev] == [1, 2, 3] and [e.session_id for e in ev] == ["session1", "session2", "session3"]

    def test_raw_values_are_preserved_verbatim_beside_the_normalised_ones(self, cfg):
        e = stage_member(csv_bytes(V8, [ROW]), meta(1), cfg, LOCAL)[0]
        assert e.component_name_raw == "Kurkku-mandariini " and e.component_id_normalized == "kurkku-mandariini"
        assert e.component_name_had_edge_whitespace is True
        assert e.event_time_raw == "2020-10-09 11:07:07" and e.weight_raw == "49" and e.component_weight_g == 49

    def test_lineage_is_carried_on_every_row(self, cfg):
        ev = stage_member(csv_bytes(V8, [ROW, ROW]), meta(2, file="a.csv"), cfg, LOCAL)
        assert {(e.source_snapshot_id, e.raw_artifact_id, e.source_file) for e in ev} == {("snap-1", "snap/a.csv", "a.csv")}
        assert [e.event_id for e in ev] == ["a.csv#1", "a.csv#2"]


# ---- populations are never merged --------------------------------------------------------------------------------------------------------------
class TestPopulationPreservation:
    def test_the_same_session_id_in_two_populations_gives_two_keys(self, cfg):
        a = stage_member(csv_bytes(V8, [ROW]), meta(1, "registered_export", "r.csv"), cfg, LOCAL)[0]
        b = stage_member(csv_bytes(V8, [ROW]), meta(1, "non_registered_export", "n.csv"), cfg, LOCAL)[0]
        assert a.session_id == b.session_id == "session1"
        assert a.session_key == "session1|registered_export" and b.session_key == "session1|non_registered_export" and a.session_key != b.session_key
        assert (a.population, b.population) == ("registered_export", "non_registered_export")


# ---- schema drift is handled by column NAME -------------------------------------------------------------------------------------------------------
class TestSchemaDrift:
    def test_a_file_without_weighting_type_stages_with_null(self, cfg):
        row = "session1,2020-10-09 11:07:07,koti2-vasen-salaatti3,49,Salad,tray473,2020-10-09 11:08:15"
        e = stage_member(csv_bytes(V7, [row]), meta(1), cfg, LOCAL)[0]
        assert e.weighing_type is None and e.component_weight_g == 49 and e.scale_id == "koti2-vasen-salaatti3"

    def test_the_source_spelling_weighting_type_is_read(self, cfg):
        assert stage_member(csv_bytes(V8, [ROW]), meta(1), cfg, LOCAL)[0].weighing_type == "line"

    def test_reordered_columns_give_identical_staged_values(self, cfg):
        reordered = "tray_id,user_identification_time,session_id,weight_of_a_component,component_name,weighting_type,scale_identifier,weighing_event_time,,,,"
        row = "tray473,2020-10-09 11:08:15,session1,49,Kurkku-mandariini ,line,koti2-vasen-salaatti3,2020-10-09 11:07:07"
        a = stage_member(csv_bytes(V8, [ROW]), meta(1), cfg, LOCAL)[0]
        b = stage_member(csv_bytes(reordered, [row]), meta(1), cfg, LOCAL)[0]
        skip = {"raw_row_sha256"}                            # the raw cell order legitimately differs
        assert {k: v for k, v in a.__dict__.items() if k not in skip} == {k: v for k, v in b.__dict__.items() if k not in skip}

    def test_an_extra_column_is_preserved_not_dropped(self, cfg):
        header = V8.replace("user_identification_time,", "user_identification_time,new_field,")
        row = ROW + ",surprise"
        e = stage_member(csv_bytes(header, [row]), meta(1), cfg, LOCAL)[0]
        assert json.loads(e.unmapped_cells) == {"extra_columns": {"new_field": "surprise"}}

    def test_a_missing_required_column_stops_staging_of_that_member(self, cfg):
        with pytest.raises(StagingError, match="required column"):
            stage_member(csv_bytes(V8.replace("tray_id,", ""), [ROW]), meta(1), cfg, LOCAL)

    def test_a_duplicate_column_name_is_refused_not_silently_overwritten(self, cfg):
        with pytest.raises(StagingError, match="duplicate column"):
            stage_member(csv_bytes(V8.replace("tray_id", "session_id"), [ROW]), meta(1), cfg, LOCAL)


# ---- ragged rows are flagged, never repaired ---------------------------------------------------------------------------------------------------------
class TestRaggedRows:
    def test_a_short_row_is_staged_with_status_and_empty_values(self, cfg):
        e = stage_member(csv_bytes(V8, ["session1,2020-10-09 11:07:07,line,koti2-vasen-salaatti3,49"]), meta(1), cfg, LOCAL)[0]
        assert e.row_parse_status == "SHORT_ROW" and e.component_name_raw == "" and e.component_id_normalized is None and e.tray_id == ""

    def test_cells_beyond_the_header_or_under_a_blank_header_are_preserved(self, cfg):
        e = stage_member(csv_bytes(V8, [ROW + ",,,,,leftover"]), meta(1), cfg, LOCAL)[0]
        assert e.row_parse_status == "EXTRA_CELLS" and "leftover" in json.loads(e.unmapped_cells)["beyond_header"]
        e2 = stage_member(csv_bytes(V8, [ROW + ",hidden,,,"]), meta(1), cfg, LOCAL)[0]
        assert e2.row_parse_status == "EXTRA_CELLS" and json.loads(e2.unmapped_cells)["blank_header_columns"] == {"8": "hidden"}


# ---- timestamps and reconciliation ---------------------------------------------------------------------------------------------------------------------
class TestTimestampsOnRows:
    def test_dst_aware_canonical_utc_for_source_local_rows(self, cfg):
        rows = [ROW, ROW.replace("2020-10-09 11:07:07", "2020-10-26 11:07:07").replace("2020-10-09 11:08:15", "2020-10-26 11:08:15")]
        a, b = stage_member(csv_bytes(V8, rows), meta(2), cfg, LOCAL)
        assert a.event_time_canonical_utc == "2020-10-09T08:07:07Z" and b.event_time_canonical_utc == "2020-10-26T09:07:07Z"

    def test_override_rows_are_labelled_and_never_lose_their_raw_text(self, cfg):
        e = stage_member(csv_bytes(V8, [ROW.replace("2020-10-09 11:07:07", "2020.10.09 08:07:07")]), meta(1), cfg, SHIFT)[0]
        assert e.event_time_raw == "2020.10.09 08:07:07" and e.event_time_local == "2020-10-09T11:07:07"
        assert e.timezone_handling == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT" and e.timezone_offset_hours_applied == 3
        assert e.timezone_transformation_reason.startswith("cross-export temporal alignment")

    def test_each_time_column_is_staged_independently(self, cfg):
        row = ROW.replace("2020-10-09 11:08:15", "2020.10.09 11:08:15")            # only the identification column uses the dotted format
        e = stage_member(csv_bytes(V8, [row]), meta(1), cfg, LOCAL)[0]
        assert (e.event_time_source_format, e.identification_time_source_format) == ("dash", "dot")

    def test_a_row_count_that_disagrees_with_ingestion_stops_staging(self, cfg):
        with pytest.raises(StagingError, match="staged 1 rows but ingestion verified 2"):
            stage_member(csv_bytes(V8, [ROW]), meta(2), cfg, LOCAL)

    def test_non_utf8_bytes_stop_staging(self, cfg):
        with pytest.raises(StagingError, match="not UTF-8"):
            stage_member(b"\xff\xfe\x00bad", meta(0), cfg, LOCAL)

    def test_column_order_of_the_staging_table_is_stable(self):
        assert EVENT_COLUMNS[:3] == ("event_id", "source_snapshot_id", "raw_artifact_id")
        assert {"event_time_raw", "event_time_canonical_utc", "timezone_handling", "timezone_transformation_reason", "session_key"} <= set(EVENT_COLUMNS)
