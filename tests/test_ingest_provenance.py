"""Snapshot identity and traceability: every source-derived record must lead back to a snapshot, a raw artifact, a checksum,
a source URL and retrieval metadata."""
from __future__ import annotations

import csv
import json

import pytest

from src.ingest.ingest import run_ingestion
from src.ingest.snapshot import input_fingerprint, snapshot_id, snapshot_sha256

pytestmark = pytest.mark.usefixtures("no_network")

ITEMS = [("member", "a.csv", "a" * 64, 10), ("member", "b.csv", "b" * 64, 20), ("archive", "x.tar", "c" * 64, 30)]


# ---- identity is a function of content only ----------------------------------------------------------------------------------------
class TestSnapshotIdentity:
    def test_order_independent(self):
        assert snapshot_sha256(ITEMS) == snapshot_sha256(list(reversed(ITEMS)))

    def test_any_changed_byte_gives_a_new_snapshot(self):
        changed = [("member", "a.csv", "d" * 64, 10)] + ITEMS[1:]
        assert snapshot_sha256(ITEMS) != snapshot_sha256(changed)

    def test_a_changed_size_or_name_gives_a_new_snapshot(self):
        assert snapshot_sha256(ITEMS) != snapshot_sha256([("member", "a.csv", "a" * 64, 11)] + ITEMS[1:])
        assert snapshot_sha256(ITEMS) != snapshot_sha256([("member", "z.csv", "a" * 64, 10)] + ITEMS[1:])

    def test_id_is_prefixed_and_short(self):
        sid = snapshot_id("flavoria", snapshot_sha256(ITEMS))
        assert sid.startswith("flavoria-") and len(sid) == len("flavoria-") + 12

    def test_input_fingerprint_is_order_independent_and_sensitive(self):
        assert input_fingerprint(["a", "b"]) == input_fingerprint(["b", "a"])
        assert input_fingerprint(["a", "b"]) != input_fingerprint(["a", "c"])

    def test_identity_contains_no_time(self, cfg, raw_repo, tmp_path):
        """Two runs at different moments give the same snapshot id: it is derived from bytes, never from the clock."""
        a = run_ingestion(cfg, raw_repo, tmp_path / "a")[0]
        b = run_ingestion(cfg, raw_repo, tmp_path / "b")[0]
        assert [s.source_snapshot_id for s in a.snapshots] == [s.source_snapshot_id for s in b.snapshots]

    def test_changing_the_raw_bytes_changes_the_snapshot(self, cfg, raw_repo, tmp_path):
        base = run_ingestion(cfg, raw_repo, tmp_path / "a")[0].snapshot("fmi_weather").source_snapshot_id
        p = raw_repo / "data" / "raw" / "weather" / "fmi_100949_20201012_20201018.xml"
        p.write_bytes(p.read_bytes() + b" ")
        changed = run_ingestion(cfg, raw_repo, tmp_path / "b")[0].snapshot("fmi_weather").source_snapshot_id
        assert base != changed


# ---- traceability through the manifest -------------------------------------------------------------------------------------------------
@pytest.fixture()
def outputs(cfg, raw_repo, tmp_path):
    result, _ = run_ingestion(cfg, raw_repo, tmp_path / "out")
    d = tmp_path / "out" / "ingestion"
    read = lambda n: list(csv.DictReader((d / n).open(encoding="utf-8")))
    return result, read("source_snapshot.csv"), read("raw_artifact_manifest.csv"), json.loads((d / "staging_handoff.json").read_text())


class TestTraceability:
    def test_every_artifact_row_leads_to_a_snapshot(self, outputs):
        _, snaps, arts, _ = outputs
        ids = {s["source_snapshot_id"] for s in snaps}
        assert len(ids) == 2 and all(a["source_snapshot_id"] in ids for a in arts)

    def test_every_artifact_row_carries_url_checksum_and_retrieval_metadata(self, outputs):
        _, _, arts, _ = outputs
        for a in arts:
            assert a["source_url"].startswith("https://"), a["artifact_id"]
            assert len(a["sha256"]) == 64, a["artifact_id"]
            assert a["retrieved_on"] == "2026-09-18" and a["version"]
            assert a["expected_sha256"] == a["sha256"], "verified artifacts carry the pin that was matched"

    def test_members_point_to_their_parent_archive(self, outputs):
        _, _, arts, _ = outputs
        by_id = {a["artifact_id"]: a for a in arts}
        members = [a for a in arts if a["kind"] == "member"]
        assert len(members) == 11
        for m in members:
            parent = by_id[m["parent_artifact_id"]]
            assert parent["kind"] == "archive" and parent["source_snapshot_id"] == m["source_snapshot_id"]

    def test_snapshot_rows_carry_license_and_retrieval_method(self, outputs):
        _, snaps, _, _ = outputs
        by = {s["source_name"]: s for s in snaps}
        assert by["flavoria"]["license"] == "CC-BY-4.0" and by["fmi_weather"]["license"] == "CC-BY-4.0"
        assert all(s["retrieval_method"] and s["retrieved_on"] and s["snapshot_sha256"] for s in snaps)

    def test_handoff_ties_every_member_and_chunk_to_a_snapshot(self, outputs):
        _, snaps, _, h = outputs
        ids = {s["source_snapshot_id"] for s in snaps}
        assert h["core"]["source_snapshot_id"] in ids and h["context"]["source_snapshot_id"] in ids
        assert all(m["source_snapshot_id"] == h["core"]["source_snapshot_id"] for m in h["core"]["members"])
        assert len(h["core"]["members"]) == 11 and len(h["context"]["chunks"]) == 7
        assert h["input_fingerprint"] and h["core"]["license"] == "CC-BY-4.0" and "10.5281/zenodo.5850856" in h["core"]["attribution"]

    def test_evidence_files_are_preserved_but_not_part_of_snapshot_identity(self, outputs):
        _, _, arts, _ = outputs
        ev = [a for a in arts if a["kind"] == "evidence"]
        assert len(ev) == 2 and all(a["in_snapshot_identity"] == "false" for a in ev)
        assert all(a["in_snapshot_identity"] == "true" for a in arts if a["kind"] != "evidence")

    def test_populations_and_timezone_treatment_are_recorded_per_member(self, outputs):
        _, _, _, h = outputs
        members = {m["file"]: m for m in h["core"]["members"]}
        assert sum(1 for m in members.values() if m["population"] == "registered_export") == 6
        assert sum(1 for m in members.values() if m["population"] == "non_registered_export") == 5
        shifted = [m for m in members.values() if m["timezone"]["offset_hours"] == 3]
        assert [m["file"] for m in shifted] == ["registered_2020_10_05-2020_10_18.csv"]
        t = shifted[0]["timezone"]
        assert t["normalization"] == "NORMALISED_PLUS_3H_STRONGEST_SUPPORT" and t["scope"] == "file_specific" and t["source_confirmed"] is False
        for m in members.values():
            if m is not shifted[0]:
                assert m["timezone"]["normalization"] == "SOURCE_LOCAL_ASSUMED" and m["timezone"]["offset_hours"] == 0 and m["timezone"]["scope"] == "none"
