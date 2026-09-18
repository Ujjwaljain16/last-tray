"""Streaming digests. Raw files are only ever opened for reading ("rb")."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CHUNK = 1 << 20


@dataclass(frozen=True)
class Digests:
    size: int
    md5: str      # published by Zenodo for the Flavoria archive; kept beside sha256 for cross-checking
    sha256: str   # the pin that governs verification


def digest_bytes(data: bytes) -> Digests:
    return Digests(len(data), hashlib.md5(data).hexdigest(), hashlib.sha256(data).hexdigest())


def digest_file(path: Path) -> Digests:
    md5, sha, size = hashlib.md5(), hashlib.sha256(), 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            md5.update(chunk)
            sha.update(chunk)
            size += len(chunk)
    return Digests(size, md5.hexdigest(), sha.hexdigest())


def sha256_of_lines(lines: Iterable[str]) -> str:
    """Order-sensitive digest of text lines (callers sort first so the result is order independent)."""
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
