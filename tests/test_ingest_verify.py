"""Ingestion verification: checksums, sizes, row counts, members, schemas. Mismatches FAIL; nothing is repaired or re-pinned."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.ingest.ingest import run_ingestion
from src.ingest.model import ArtifactStatus, LaneOutcome, SchemaStatus
from tests.helpers import REG_FILE, build_tar, read_members, retarget, rewrite_header, with_member_spec

pytestmark = pytest.mark.usefixtures("no_network")

ARCHIVE = Path("data/raw/flavoria/dataset_csv.tar")
V8 = ["session_id", "weighing_event_time", "weighting_type", "scale_identifier", "weight_of_a_component", "component_name",
      "tray_id", "user_identification_time", "", "", "", ""]


def run(cfg, root: Path, tmp_path: Path):
    return run_ingestion(cfg, root, tmp_path / "out")[0]


def artifact(result, kind: str, filename: str):
    return next(a for a in result.artifacts if a.kind == kind and a.filename == filename)


# ---- the real, committed data --------------------------------------------------------------------------------------------------
class TestRealRawData:
    def test_everything_verifies(self, cfg, raw_repo, tmp_path):
        r = run(cfg, raw_repo, tmp_path)
        assert (r.core_outcome, r.context_outcome) == (LaneOutcome.OK, LaneOutcome.OK)
        assert len(r.artifacts) == 21 and all(a.status is ArtifactStatus.VERIFIED for a in r.artifacts)
        kinds = {}
        for a in r.artifacts:
            kinds[a.kind] = kinds.get(a.kind, 0) + 1
        assert kinds == {"archive": 1, "member": 11, "weather_chunk": 7, "evidence": 2}

    def test_row_counts_reproduce_the_golden_total(self, cfg, raw_repo, tmp_path, golden):
        r = run(cfg, raw_repo, tmp_path)
        assert sum(a.row_count for a in r.artifacts if a.kind == "member") == golden["counts"]["raw_event_rows"]

    def test_schema_variants_are_recognised(self, cfg, raw_repo, tmp_path):
        r = run(cfg, raw_repo, tmp_path)
        by_variant: dict[str, int] = {}
        for s in r.schemas:
            assert s.status is SchemaStatus.KNOWN_VARIANT
            by_variant[s.variant] = by_variant.get(s.variant, 0) + 1
        assert by_variant == {"V8_with_weighting_type": 4, "V7_without_weighting_type": 7}

    def test_weather_completeness(self, cfg, raw_repo, tmp_path, golden):
        r = run(cfg, raw_repo, tmp_path)
        assert sum(c.hours for c in r.weather_chunks) >= golden["counts"]["weather_hours"] - 6   # chunks are disjoint: 6 x 168 + 121
        assert all(c.number_returned == c.elements for c in r.weather_chunks)
        assert all(c.content_sha256 == c.expected_content_sha256 for c in r.weather_chunks)


# ---- core lane: Flavoria problems FAIL, and never repair anything ------------------------------------------------------------------
class TestCoreFailures:
    def test_missing_archive_fails_and_names_the_explicit_retrieval_command(self, cfg, raw_repo, tmp_path):
        (raw_repo / ARCHIVE).unlink()
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        a = artifact(r, "archive", "dataset_csv.tar")
        assert a.status is ArtifactStatus.MISSING
        assert "python -m src.pipeline.fetch --source flavoria" in a.message
        assert not (raw_repo / ARCHIVE).exists(), "a normal run must never download or recreate a missing source"

    def test_size_mismatch_fails(self, cfg, raw_repo, tmp_path):
        p = raw_repo / ARCHIVE
        p.write_bytes(p.read_bytes() + b"\0" * 512)
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "archive", "dataset_csv.tar").status is ArtifactStatus.SIZE_MISMATCH

    def test_same_size_but_different_bytes_fails_on_checksum(self, cfg, raw_repo, tmp_path):
        p = raw_repo / ARCHIVE
        data = bytearray(p.read_bytes())
        data[100_000] ^= 0xFF
        p.write_bytes(bytes(data))
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "archive", "dataset_csv.tar").status is ArtifactStatus.CHECKSUM_MISMATCH
        assert all(a.status is ArtifactStatus.NOT_CHECKED for a in r.artifacts if a.kind == "member"), "members of an unverified archive are not trusted"

    def test_corrupt_archive_fails_before_any_dependent_output_is_trusted(self, cfg, raw_repo, tmp_path):
        garbage = raw_repo / ARCHIVE
        garbage.write_bytes(b"this is not a tar archive " * 2000)
        r = run(retarget(cfg, garbage, {}, sync_members=False), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "archive", "dataset_csv.tar").status is ArtifactStatus.CORRUPT
        handoff = (tmp_path / "out" / "ingestion" / "staging_handoff.json").read_text()
        assert '"ready": false' in handoff and '"members": []' in handoff

    def test_missing_member_fails(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        members.pop(REG_FILE)
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "archive", "dataset_csv.tar").status is ArtifactStatus.MEMBER_SET_MISMATCH

    def test_unexpected_extra_member_fails(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        members["surprise.csv"] = b"a,b\n1,2\n"
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "archive", "dataset_csv.tar").status is ArtifactStatus.MEMBER_SET_MISMATCH

    def test_path_traversal_member_is_refused_not_read(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        build_tar(raw_repo / ARCHIVE, members, extra_names={"../evil.csv": b"x,y\n1,2\n"})
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        a = artifact(r, "archive", "dataset_csv.tar")
        assert a.status is ArtifactStatus.UNEXPECTED_CONTENT and "unsafe" in a.message
        assert not (raw_repo / "evil.csv").exists() and not (tmp_path / "evil.csv").exists()

    def test_member_bytes_changed_fails_on_member_checksum(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        data = bytearray(members[REG_FILE])
        i = data.index(b"session", 200) + 7          # change one digit inside an id: same size, different content
        data[i] = ord("9") if data[i] != ord("9") else ord("8")
        members[REG_FILE] = bytes(data)
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members, sync_members=False), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "member", REG_FILE).status is ArtifactStatus.CHECKSUM_MISMATCH

    def test_row_count_mismatch_fails(self, cfg, raw_repo, tmp_path):
        bad = with_member_spec(cfg, REG_FILE, rows=1932)
        r = run(bad, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "member", REG_FILE).status is ArtifactStatus.ROW_COUNT_MISMATCH

    def test_missing_required_column_fails_with_s02(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        members[REG_FILE] = rewrite_header(members[REG_FILE], [c for c in V8 if c != "tray_id"])
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "member", REG_FILE).status is ArtifactStatus.SCHEMA_MISSING_REQUIRED
        assert any(m.code == "S02" and "tray_id" in m.text for m in r.messages)

    def test_a_renamed_required_column_is_missing_not_drift(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        members[REG_FILE] = rewrite_header(members[REG_FILE], [("scale_id" if c == "scale_identifier" else c) for c in V8])
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert artifact(r, "member", REG_FILE).status is ArtifactStatus.SCHEMA_MISSING_REQUIRED


# ---- schema drift is a WARNING, not a failure ------------------------------------------------------------------------------------
class TestSchemaDrift:
    def test_an_extra_column_is_a_warning_and_processing_continues(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        members[REG_FILE] = rewrite_header(members[REG_FILE], V8[:8] + ["new_field", "", "", ""])
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.WARNING
        s = next(s for s in r.schemas if s.filename == REG_FILE)
        assert s.status is SchemaStatus.DRIFT and s.unexpected == ("new_field",)
        assert any(m.code == "S08" for m in r.messages)
        assert artifact(r, "member", REG_FILE).status is ArtifactStatus.VERIFIED

    def test_reordered_columns_are_drift_because_staging_reads_by_name(self, cfg, raw_repo, tmp_path):
        members = read_members(raw_repo / ARCHIVE)
        reordered = V8[:2] + ["scale_identifier", "weighting_type"] + V8[4:]
        members[REG_FILE] = rewrite_header(members[REG_FILE], reordered)
        build_tar(raw_repo / ARCHIVE, members)
        r = run(retarget(cfg, raw_repo / ARCHIVE, members), raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.WARNING
        assert next(s for s in r.schemas if s.filename == REG_FILE).status is SchemaStatus.DRIFT


# ---- context lane: weather problems BLOCK weather only ----------------------------------------------------------------------------
CHUNK = "fmi_100949_20201012_20201018.xml"


def weather_path(root: Path, name: str = CHUNK) -> Path:
    return root / "data" / "raw" / "weather" / name


class TestWeatherFailuresNeverBlockCore:
    def test_missing_chunk_blocks_weather_only(self, cfg, raw_repo, tmp_path):
        weather_path(raw_repo).unlink()
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.OK and r.context_outcome is LaneOutcome.BLOCKED
        a = artifact(r, "weather_chunk", CHUNK)
        assert a.status is ArtifactStatus.MISSING and "python -m src.pipeline.fetch --source weather" in a.message
        assert not weather_path(raw_repo).exists(), "a normal run must never download"

    def test_whole_weather_directory_missing_still_leaves_core_ready(self, cfg, raw_repo, tmp_path):
        for p in (raw_repo / "data" / "raw" / "weather").glob("*.xml"):
            p.unlink()
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.OK and r.context_outcome is LaneOutcome.BLOCKED
        handoff = (tmp_path / "out" / "ingestion" / "staging_handoff.json").read_text()
        assert '"source": "flavoria"' in handoff
        import json
        h = json.loads(handoff)
        assert h["core"]["ready"] is True and h["context"]["ready"] is False and h["context"]["chunks"] == []

    def test_checksum_mismatch_blocks_weather(self, cfg, raw_repo, tmp_path):
        p = weather_path(raw_repo)
        p.write_bytes(p.read_bytes().replace(b"<BsWfs:ParameterValue>", b"<BsWfs:ParameterValue>", 1)[:-1] + b" ")
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.OK and r.context_outcome is LaneOutcome.BLOCKED
        assert artifact(r, "weather_chunk", CHUNK).status in (ArtifactStatus.SIZE_MISMATCH, ArtifactStatus.CHECKSUM_MISMATCH)

    @pytest.mark.parametrize("payload, expected", [
        (b"<not-xml", ArtifactStatus.MALFORMED),
        (b'<?xml version="1.0"?><ExceptionReport xmlns="http://www.opengis.net/ows/1.1"><Exception><ExceptionText>Too long time interval requested!</ExceptionText></Exception></ExceptionReport>', ArtifactStatus.MALFORMED),
        (b'<?xml version="1.0"?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberReturned="5"/>', ArtifactStatus.INCOMPLETE),
    ])
    def test_unusable_or_incomplete_responses_are_rejected(self, cfg, raw_repo, tmp_path, payload, expected):
        import dataclasses
        from src.config import RawFileSpec, SourcesConfig
        p = weather_path(raw_repo)
        p.write_bytes(payload)
        w = cfg.sources.weather
        specs = tuple(dataclasses.replace(s, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()) if s.file == CHUNK else s for s in w.raw_files)
        bad = dataclasses.replace(cfg, sources=SourcesConfig(cfg.sources.flavoria, dataclasses.replace(w, raw_files=specs), cfg.sources.gaps))
        r = run(bad, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.OK and r.context_outcome is LaneOutcome.BLOCKED
        a = artifact(r, "weather_chunk", CHUNK)
        assert a.status is expected
        if "Too long" in payload.decode(errors="ignore"):
            assert "Too long time interval" in a.message      # FMI's own reason is preserved

    def test_tampered_evidence_file_is_reported_without_blocking_weather(self, cfg, raw_repo, tmp_path):
        p = weather_path(raw_repo, "stations.xml")
        p.write_bytes(p.read_bytes() + b" ")
        r = run(cfg, raw_repo, tmp_path)
        assert r.context_outcome is LaneOutcome.WARNING and r.core_outcome is LaneOutcome.OK
        assert artifact(r, "evidence", "stations.xml").status is not ArtifactStatus.VERIFIED


# ---- pins and raw files are never modified by verification -------------------------------------------------------------------------
class TestNothingIsRepaired:
    def test_a_failing_run_leaves_raw_and_pins_untouched(self, cfg, raw_repo, tmp_path, repo):
        p = raw_repo / ARCHIVE
        p.write_bytes(p.read_bytes() + b"\0" * 64)
        before_raw = hashlib.sha256(p.read_bytes()).hexdigest()
        pins_before = hashlib.sha256((repo / "config" / "sources.yml").read_bytes()).hexdigest()
        r = run(cfg, raw_repo, tmp_path)
        assert r.core_outcome is LaneOutcome.FAILED
        assert hashlib.sha256(p.read_bytes()).hexdigest() == before_raw, "verification must not repair or replace a raw file"
        assert hashlib.sha256((repo / "config" / "sources.yml").read_bytes()).hexdigest() == pins_before, "pins must never be updated by a run"
        assert r.raw_unchanged is True
