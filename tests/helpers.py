"""Test helpers for ingestion tests: build modified archives and matching pins without touching real raw data."""
from __future__ import annotations

import csv
import dataclasses
import io
import tarfile
from pathlib import Path

from src.config import Config, FlavoriaSource, MemberSpec, SourcesConfig
from src.ingest.hashing import digest_bytes

REG_FILE = "registered_2020_10_05-2020_10_18.csv"


def read_members(archive: Path) -> dict[str, bytes]:
    with tarfile.open(archive) as tf:
        return {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}


def build_tar(path: Path, members: dict[str, bytes], extra_names: dict[str, bytes] | None = None) -> None:
    """Write a tar. `extra_names` lets a test add members with hostile names (path traversal)."""
    with tarfile.open(path, "w") as tf:
        for name, data in {**members, **(extra_names or {})}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def csv_rows(data: bytes) -> int:
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig")))
    next(reader, None)
    return sum(1 for r in reader if any(c.strip() for c in r))


def retarget(cfg: Config, archive: Path, members: dict[str, bytes], *, sync_members: bool = True) -> Config:
    """A config whose ARCHIVE pins match `archive`, and (optionally) whose MEMBER pins match `members`.

    Tests use this to isolate one failure mode at a time: the archive is internally consistent, so only the property under
    test differs from the pins.
    """
    f = cfg.sources.flavoria
    d = digest_bytes(archive.read_bytes())
    specs = []
    for m in f.members:
        if sync_members and m.file in members:
            md = digest_bytes(members[m.file])
            specs.append(dataclasses.replace(m, bytes=md.size, sha256=md.sha256, rows=csv_rows(members[m.file])))
        else:
            specs.append(m)
    new_f: FlavoriaSource = dataclasses.replace(f, archive_size_bytes=d.size, archive_md5=d.md5, archive_sha256=d.sha256, members=tuple(specs))
    return dataclasses.replace(cfg, sources=SourcesConfig(flavoria=new_f, weather=cfg.sources.weather, gaps=cfg.sources.gaps))


def with_member_spec(cfg: Config, filename: str, **changes) -> Config:
    f = cfg.sources.flavoria
    specs = tuple(dataclasses.replace(m, **changes) if m.file == filename else m for m in f.members)
    return dataclasses.replace(cfg, sources=SourcesConfig(flavoria=dataclasses.replace(f, members=specs), weather=cfg.sources.weather, gaps=cfg.sources.gaps))


def rewrite_header(data: bytes, new_columns: list[str]) -> bytes:
    text = data.decode("utf-8-sig")
    first, _, rest = text.partition("\r\n")
    header = ",".join(new_columns)
    return ("﻿" + header + "\r\n" + rest).encode("utf-8")
