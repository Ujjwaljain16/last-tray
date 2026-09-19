"""Atomic output writing. Every deterministic artifact is written to a temporary file in the SAME directory and then moved into place with
os.replace, so a failure at any point leaves either the previous complete file or nothing: never a truncated file that looks valid.

Temporary names start with a dot and contain '.tmp-' so they are ignored by git and easy to spot; a failed write removes its own temporary file.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

TMP_MARK = ".tmp-"


def _tmp_name(path: Path) -> Path:
    return path.with_name(f".{path.name}{TMP_MARK}{os.getpid()}")


@contextmanager
def atomic_path(path: Path) -> Iterator[Path]:
    """Yield a temporary path beside `path`; on clean exit it replaces `path`, on error it is deleted and `path` is untouched."""
    path = Path(path)
    tmp = _tmp_name(path)
    try:
        yield tmp
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    with atomic_path(path) as tmp:
        tmp.write_text(text, encoding="utf-8", newline="\n")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    with atomic_path(path) as tmp:
        tmp.write_bytes(data)


def leftover_temporaries(root: Path) -> list[Path]:
    """Temporary files an interrupted write could have left behind (there must be none after any run)."""
    return sorted(p for p in Path(root).rglob("*") if p.is_file() and TMP_MARK in p.name)
