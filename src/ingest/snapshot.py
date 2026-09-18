"""Source snapshot identity.

A snapshot is an immutable set of raw artifacts from one source. Its id is derived from CONTENT (sha256 and size of each
artifact), never from time, so the same bytes always give the same id and any changed byte gives a different one.
A refreshed source is therefore always a NEW snapshot, never an edit of an old one.
"""
from __future__ import annotations

from typing import Iterable

from src.ingest.hashing import sha256_of_lines


def snapshot_sha256(items: Iterable[tuple[str, str, str, int]]) -> str:
    """items: (kind, filename, sha256, size_bytes). Sorted, so file order never matters."""
    return sha256_of_lines(sorted(f"{kind}|{name}|{sha}|{size}" for kind, name, sha, size in items))


def snapshot_id(prefix: str, sha: str) -> str:
    return f"{prefix}-{sha[:12]}"


def input_fingerprint(snapshot_ids: Iterable[str]) -> str:
    """One id for the complete set of inputs a run consumed."""
    return sha256_of_lines(sorted(snapshot_ids))[:16]
