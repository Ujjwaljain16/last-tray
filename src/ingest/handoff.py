"""Reading the staging handoff (used by staging in WP3).

Staging never trusts a path. It asks for a member by name and receives bytes that have been re-verified against the
SHA-256 recorded at ingestion, so a raw file that changed between ingestion and staging is caught, not consumed.
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


def read_verified_member(repo_root: Path, handoff: dict[str, Any], filename: str) -> bytes:
    core = handoff["core"]
    if not core["ready"]:
        raise HandoffError(f"core lane is {core['outcome']}: staging must not read raw data")
    member = next((m for m in core["members"] if m["file"] == filename), None)
    if member is None:
        raise HandoffError(f"{filename!r} is not in the handoff")
    archive = repo_root / core["archive"]["path"]
    with tarfile.open(archive) as tf:
        data = tf.extractfile(filename).read()
    if digest_bytes(data).sha256 != member["sha256"]:
        raise HandoffError(f"{filename}: bytes no longer match the SHA-256 verified at ingestion (snapshot {member['source_snapshot_id']})")
    return data
