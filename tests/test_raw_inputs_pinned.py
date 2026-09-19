"""The committed raw inputs must match the pins in config/sources.yml.

This proves the pins are right and the raw layer is intact. Ingestion performs the same verification at run time, with
failure handling; here it guards the configuration itself.
"""
from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_flavoria_archive_matches_published_and_local_checksums(cfg):
    f = cfg.sources.flavoria
    path = REPO / f.archive_path
    assert path.exists(), f"raw archive missing: {path}"
    assert path.stat().st_size == f.archive_size_bytes
    assert digest(path, "md5") == f.archive_md5            # published by Zenodo
    assert digest(path, "sha256") == f.archive_sha256      # pinned locally


def test_archive_contains_exactly_the_expected_members_with_expected_sizes_and_rows(cfg):
    f = cfg.sources.flavoria
    with tarfile.open(REPO / f.archive_path) as tf:
        found = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
    assert set(found) == {m.file for m in f.members}
    for spec in f.members:
        data = found[spec.file]
        assert len(data) == spec.bytes, spec.file
        rows = len(data.decode("utf-8-sig").splitlines()) - 1        # minus the header
        assert rows == spec.rows, spec.file
        has_col = "weighting_type" in data.decode("utf-8-sig").splitlines()[0].split(",")
        assert has_col == spec.weighting_type, spec.file


def test_committed_weather_files_match_their_pins(cfg):
    w = cfg.sources.weather
    for spec in (*w.raw_files, *w.evidence_files):
        path = REPO / "data" / "raw" / "weather" / spec.file
        assert path.exists(), f"missing raw weather file: {spec.file}"
        assert path.stat().st_size == spec.bytes, spec.file
        assert digest(path, "sha256") == spec.sha256, spec.file


def test_weather_files_cover_the_window_without_gaps_or_duplicates(cfg):
    import re
    hours = []
    for spec in cfg.sources.weather.raw_files:
        text = (REPO / "data" / "raw" / "weather" / spec.file).read_text(encoding="utf-8")
        hours += re.findall(r"<BsWfs:Time>([^<]*)</BsWfs:Time>\s*<BsWfs:ParameterName>t2m<", text)
    assert len(hours) == len(set(hours)) == cfg.sources.weather.expected_hours == 1129
    assert min(hours) == "2020-10-05T00:00:00Z" and max(hours) == "2020-11-21T00:00:00Z"
