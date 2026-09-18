"""The verified-reader interface: the ONLY sanctioned way for a downstream stage to read raw source bytes.

Staging never trusts a path and never opens data/raw itself. It asks a VerifiedReader for a member (or a weather chunk) by
name and receives bytes that have been re-checked against the SHA-256 recorded at ingestion, so a raw file that changed
between ingestion and staging is caught, not consumed. A failed verification raises HandoffError, and the staging path for
that source stops.
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any

from src.ingest.hashing import digest_bytes


class HandoffError(Exception):
    """The handoff is not ready, or the raw bytes no longer match what ingestion verified."""


def load_handoff(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise HandoffError(f"no staging handoff at {path}. Run ingestion first: python -m src.pipeline.run --stages ingest")
    return json.loads(path.read_text(encoding="utf-8"))


class VerifiedReader:
    """Reads raw source bytes and verifies each read against the SHA-256 recorded during ingestion."""

    def __init__(self, repo_root: Path, handoff: dict[str, Any]):
        self._root = repo_root
        self._handoff = handoff

    @property
    def handoff(self) -> dict[str, Any]:
        return self._handoff

    def member(self, filename: str) -> bytes:
        """Bytes of one Flavoria archive member, verified against the ingestion SHA-256."""
        core = self._handoff["core"]
        if not core["ready"]:
            raise HandoffError(f"core lane is {core['outcome']}: staging must not read raw data")
        member = next((m for m in core["members"] if m["file"] == filename), None)
        if member is None:
            raise HandoffError(f"{filename!r} is not in the handoff")
        try:
            with tarfile.open(self._root / core["archive"]["path"]) as tf:
                data = tf.extractfile(filename).read()
        except (tarfile.TarError, KeyError, OSError, EOFError) as exc:
            raise HandoffError(f"{filename}: cannot be read from the raw archive ({type(exc).__name__}: {exc})") from exc
        if digest_bytes(data).sha256 != member["sha256"]:
            raise HandoffError(f"{filename}: bytes no longer match the SHA-256 verified at ingestion (snapshot {member['source_snapshot_id']})")
        return data

    def weather_chunk(self, filename: str) -> bytes:
        """Bytes of one FMI response file, verified against the ingestion SHA-256."""
        ctx = self._handoff["context"]
        if not ctx["ready"]:
            raise HandoffError(f"context lane is {ctx['outcome']}: staging must not read raw weather data")
        chunk = next((c for c in ctx["chunks"] if c["file"] == filename), None)
        if chunk is None:
            raise HandoffError(f"weather chunk {filename!r} is not in the handoff")
        try:
            data = (self._root / chunk["path"]).read_bytes()
        except OSError as exc:
            raise HandoffError(f"{filename}: cannot be read ({type(exc).__name__}: {exc})") from exc
        if digest_bytes(data).sha256 != chunk["sha256"]:
            raise HandoffError(f"{filename}: bytes no longer match the SHA-256 verified at ingestion (snapshot {ctx['source_snapshot_id']})")
        return data


def read_verified_member(repo_root: Path, handoff: dict[str, Any], filename: str) -> bytes:
    """Convenience wrapper kept for callers that need a single member."""
    return VerifiedReader(repo_root, handoff).member(filename)
