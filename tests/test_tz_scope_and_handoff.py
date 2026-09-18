"""Rule T10 (the +3h override is file-specific and only valid where its evidence holds) and the staging handoff contract."""
from __future__ import annotations

import dataclasses
import tarfile
from pathlib import Path

import pytest

from src.config import SourcesConfig, TimezoneConfig, TimezoneOverride
from src.ingest.handoff import HandoffError, load_handoff, read_verified_member
from src.ingest.ingest import run_ingestion
from src.ingest.model import LaneOutcome
from src.ingest.tz_scope import check_override, parse_source_timestamp
from tests.helpers import REG_FILE, build_tar, read_members, retarget

pytestmark = pytest.mark.usefixtures("no_network")
OUT = "out"


def csv_with_first_events(times: list[str]) -> bytes:
    """A minimal Flavoria-shaped CSV whose FIRST event of each day is the given raw timestamp."""
    rows = ["session_id,weighing_event_time,weighting_type,scale_identifier,weight_of_a_component,component_name,tray_id,user_identification_time,,,,"]
    for i, t in enumerate(times):
        rows.append(f"session{i},{t},line,koti2-vasen-salaatti1,50,Salad,tray1,{t},")
    return ("﻿" + "\r\n".join(rows) + "\r\n").encode("utf-8")


@pytest.fixture()
def override(cfg) -> TimezoneOverride:
    return cfg.timezone.overrides[REG_FILE]


@pytest.fixture()
def t07(cfg):
    r = cfg.thresholds.rules["T07"]
    return r.low, r.high


# ---- the scope check itself ---------------------------------------------------------------------------------------------------------------
class TestOverrideScope:
    def test_the_real_file_is_in_scope(self, cfg, override, t07):
        raw = read_members(Path(__file__).resolve().parents[1] / "data/raw/flavoria/dataset_csv.tar")[REG_FILE]
        s = check_override(override, raw, *t07)
        assert s.status == "VALID" and s.first_event_date == "2020-10-05" and s.last_event_date == "2020-10-16"
        assert 7.5 < s.raw_median_first_hour < 7.6 and 10.5 < s.normalised_median_first_hour < 10.6

    def test_dates_outside_the_validated_range_are_refused(self, override, t07):
        data = csv_with_first_events(["2020.11.02 07:30:00", "2020.11.03 07:30:00"])
        s = check_override(override, data, *t07)
        assert s.status == "INVALID" and any("outside the validated range" in r for r in s.reasons)

    def test_a_file_that_no_longer_shows_the_shift_is_refused(self, override, t07):
        """If a corrected file arrives under the same name (times already local), +3h would push it to 13:xx. Refuse."""
        data = csv_with_first_events(["2020.10.05 10:30:00", "2020.10.06 10:35:00"])
        s = check_override(override, data, *t07)
        assert s.status == "INVALID"
        assert any("shift this override corrects is not visible" in r for r in s.reasons)
        assert any("outside the T07 band" in r for r in s.reasons)

    def test_a_shift_of_the_wrong_size_is_refused(self, override, t07):
        """Raw 8.9 h is inside the raw band, but +3h gives 11.9 h: the evidence supported 3h only for a 7.5 h file."""
        data = csv_with_first_events(["2020.10.05 08:54:00", "2020.10.06 08:54:00"])
        s = check_override(override, data, *t07)
        assert s.status == "INVALID" and any("outside the T07 band" in r for r in s.reasons)

    def test_unparseable_or_empty_data_is_invalid_never_valid_by_default(self, override, t07):
        assert check_override(override, csv_with_first_events(["not a time"]), *t07).status == "INVALID"
        assert check_override(override, b"", *t07).status == "INVALID"
        assert check_override(override, None, *t07).status == "INVALID"

    def test_both_source_timestamp_formats_parse(self):
        assert parse_source_timestamp("2020-10-09 11:07:07") == parse_source_timestamp("2020.10.09 11:07:07")


class TestOverrideIsFileSpecific:
    def test_exactly_one_member_receives_the_override(self, cfg, raw_repo, tmp_path):
        r, _ = run_ingestion(cfg, raw_repo, tmp_path / OUT)
        import json
        h = json.loads((tmp_path / OUT / "ingestion" / "staging_handoff.json").read_text())
        shifted = [m["file"] for m in h["core"]["members"] if m["timezone"]["offset_hours"] != 0]
        assert shifted == [REG_FILE]
        assert len(cfg.timezone.overrides) == 1 and next(iter(cfg.timezone.overrides.values())).valid_for.last_event_date.isoformat() == "2020-10-16"

    def test_out_of_scope_data_fails_the_core_lane_with_t10(self, cfg, raw_repo, tmp_path):
        """A file with the override's name but different content: ingestion must FAIL, not silently normalise it."""
        arc = raw_repo / "data/raw/flavoria/dataset_csv.tar"
        members = read_members(arc)
        members[REG_FILE] = csv_with_first_events([f"2020.10.0{d} 10:30:00" for d in range(5, 10)])
        build_tar(arc, members)
        r, _ = run_ingestion(retarget(cfg, arc, members), raw_repo, tmp_path / OUT)
        assert r.core_outcome is LaneOutcome.FAILED
        assert any(m.code == "T10" and REG_FILE in m.text for m in r.messages)
        assert r.tz_scope[0].status == "INVALID"

    def test_the_override_is_never_described_as_confirmed_or_general(self, cfg):
        o = cfg.timezone.overrides[REG_FILE]
        assert o.source_confirmed is False
        text = (Path(__file__).resolve().parents[1] / "config" / "timezone_overrides.yml").read_text(encoding="utf-8")
        assert "FILE-SPECIFIC" in text and "NOT source-confirmed" in text.replace("it is NOT source-confirmed", "NOT source-confirmed")
        for forbidden in ("UTC+3", "UTC +3", "Helsinki is"):
            assert forbidden not in text, f"config states a general timezone fact: {forbidden!r}"

    def test_config_refuses_an_override_that_is_not_file_specific(self, config_copy):
        from src.config import ConfigError, load_config
        config_copy.edit("timezone_overrides.yml", "scope: file_specific", "scope: global")
        with pytest.raises(ConfigError, match="file_specific"):
            load_config(config_copy.dir)

    def test_config_refuses_an_override_without_a_validity_scope(self, config_copy):
        from src.config import ConfigError, load_config
        config_copy.edit("timezone_overrides.yml", "    valid_for:\n", "    not_valid_for:\n")
        with pytest.raises(ConfigError, match="valid_for"):
            load_config(config_copy.dir)


# ---- the handoff contract ------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def handoff(cfg, raw_repo, tmp_path):
    run_ingestion(cfg, raw_repo, tmp_path / OUT)
    return raw_repo, load_handoff(tmp_path / OUT / "ingestion" / "staging_handoff.json")


class TestHandoff:
    def test_member_bytes_are_returned_verified(self, handoff):
        root, h = handoff
        data = read_verified_member(root, h, REG_FILE)
        assert data.startswith("﻿session_id".encode("utf-8"))

    def test_raw_changed_after_ingestion_is_caught_at_read_time(self, handoff):
        root, h = handoff
        arc = root / h["core"]["archive"]["path"]
        members = read_members(arc)
        members[REG_FILE] = members[REG_FILE].replace(b"session", b"sessioN", 1)
        build_tar(arc, members)
        with pytest.raises(HandoffError, match="no longer match the SHA-256 verified at ingestion"):
            read_verified_member(root, h, REG_FILE)

    def test_unknown_member_is_refused(self, handoff):
        root, h = handoff
        with pytest.raises(HandoffError, match="not in the handoff"):
            read_verified_member(root, h, "invented.csv")

    def test_a_failed_core_lane_hands_off_nothing(self, cfg, raw_repo, tmp_path):
        (raw_repo / "data/raw/flavoria/dataset_csv.tar").unlink()
        run_ingestion(cfg, raw_repo, tmp_path / OUT)
        h = load_handoff(tmp_path / OUT / "ingestion" / "staging_handoff.json")
        assert h["core"]["ready"] is False and h["core"]["members"] == []
        with pytest.raises(HandoffError, match="core lane is FAILED"):
            read_verified_member(raw_repo, h, REG_FILE)

    def test_missing_handoff_says_how_to_create_it(self, tmp_path):
        with pytest.raises(HandoffError, match="python -m src.pipeline.run --stages ingest"):
            load_handoff(tmp_path / "nope.json")
