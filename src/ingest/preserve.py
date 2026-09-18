"""Raw preservation: prove that a run left data/raw exactly as it found it.

Raw inputs are immutable. The pipeline reads them ("rb") and never writes into them. This module records the state of the
whole raw tree (every file: size, modification time, SHA-256) before and after a run so the claim is checked, not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.ingest.hashing import digest_file


@dataclass(frozen=True)
class RawState:
    files: dict[str, tuple[int, int, str]]    # relative posix path -> (size, mtime_ns, sha256)

    def diff(self, other: "RawState") -> list[str]:
        """Human-readable differences (empty when identical)."""
        out = []
        for path in sorted(set(self.files) | set(other.files)):
            a, b = self.files.get(path), other.files.get(path)
            if a is None:
                out.append(f"{path}: appeared during the run")
            elif b is None:
                out.append(f"{path}: disappeared during the run")
            elif a != b:
                out.append(f"{path}: changed during the run")
        return out


def capture(raw_root: Path) -> RawState:
    files: dict[str, tuple[int, int, str]] = {}
    if raw_root.is_dir():
        for p in sorted(raw_root.rglob("*")):
            if p.is_file():
                st = p.stat()
                files[p.relative_to(raw_root).as_posix()] = (st.st_size, st.st_mtime_ns, digest_file(p).sha256)
    return RawState(files)


def assert_outputs_outside_raw(out_dir: Path, raw_root: Path) -> None:
    """Outputs must never be written inside the raw tree."""
    out, raw = out_dir.resolve(), raw_root.resolve()
    if out == raw or raw in out.parents:
        raise ValueError(f"output directory {out} is inside the immutable raw tree {raw}")
