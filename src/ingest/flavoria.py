"""Flavoria archive: observe, then verify against the pins in config/sources.yml.

observe_archive() does the reading (read-only). verify_flavoria() compares what was observed with what was pinned and
produces the manifest records. Mismatches are FAILED. Nothing here downloads anything, and nothing here updates a pin.
"""
from __future__ import annotations

import csv
import io
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from src.config import Config
from src.ingest.hashing import Digests, digest_bytes, digest_file
from src.ingest.model import (Artifact, ArtifactStatus, Lane, LaneOutcome, Level, Message, SchemaFingerprint,
                              SchemaStatus, Snapshot)
from src.ingest.schema import classify
from src.ingest.snapshot import snapshot_id, snapshot_sha256

MAX_MEMBER_BYTES = 50 * 1024 * 1024   # a member larger than this is not one of ours
SOURCE = "flavoria"
FETCH_HINT = "python -m src.pipeline.fetch --source flavoria"


@dataclass
class ObservedMember:
    name: str
    digests: Digests
    rows: int
    columns: list[str]
    decode_error: str | None = None


@dataclass
class ObservedArchive:
    path: Path
    exists: bool
    digests: Digests | None = None
    corrupt: str | None = None
    members: dict[str, ObservedMember] = field(default_factory=dict)
    unsafe: list[str] = field(default_factory=list)      # members we refused to read (path tricks, links, oversize)
    member_bytes: dict[str, bytes] = field(default_factory=dict)


def _count_rows(text: str) -> tuple[list[str], int]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    return header, sum(1 for rec in reader if any(cell.strip() for cell in rec))


def observe_archive(path: Path) -> ObservedArchive:
    obs = ObservedArchive(path=path, exists=path.is_file())
    if not obs.exists:
        return obs
    obs.digests = digest_file(path)
    try:
        with tarfile.open(path) as tf:
            for m in tf.getmembers():
                p = PurePosixPath(m.name)
                if not m.isfile() or p.name != m.name or ".." in p.parts or "\\" in m.name or m.size > MAX_MEMBER_BYTES:
                    obs.unsafe.append(m.name)
                    continue
                data = tf.extractfile(m).read()
                d = digest_bytes(data)
                try:
                    header, rows = _count_rows(data.decode("utf-8-sig"))
                    obs.members[m.name] = ObservedMember(m.name, d, rows, header)
                except UnicodeDecodeError as exc:
                    obs.members[m.name] = ObservedMember(m.name, d, 0, [], decode_error=str(exc))
                obs.member_bytes[m.name] = data
    except (tarfile.TarError, EOFError, OSError) as exc:
        obs.corrupt = f"{type(exc).__name__}: {exc}"
        obs.members.clear()
        obs.member_bytes.clear()
    return obs


def _aid(sid: str | None, *parts: str) -> str:
    return "/".join([sid or "UNSNAPSHOTTED", *parts])


def verify_flavoria(cfg: Config, repo_root: Path) -> "FlavoriaOutcome":
    f = cfg.sources.flavoria
    obs = observe_archive(repo_root / f.archive_path)
    version = f"v{f.version} (DOI {f.doi})"
    messages: list[Message] = []
    artifacts: list[Artifact] = []
    schemas: list[SchemaFingerprint] = []
    retrieved = str(f.archive_retrieved_on)
    arc_rel = Path(f.archive_path).as_posix()

    def snapshot_record(sid, sha, count, status):
        return Snapshot(sid, SOURCE, Lane.CORE, f.record_url, version, f.license, retrieved, f.archive_retrieval_method, count, sha, status)

    # -- discovery: is the archive there? -------------------------------------------------------------------------
    if not obs.exists:
        msg = f"raw archive missing: {arc_rel}. Normal runs never download. Retrieve it explicitly: {FETCH_HINT}"
        messages.append(Message(Level.ERROR, "S01", msg))
        art = Artifact(_aid(None, f.archive_filename), None, SOURCE, Lane.CORE, "archive", f.archive_filename, arc_rel, None, f.archive_url,
                       retrieved, version, True, None, None, None, f.archive_size_bytes, f.archive_sha256, None, f.expected_total_rows,
                       ArtifactStatus.MISSING, msg)
        return FlavoriaOutcome(snapshot_record(None, None, 0, "MISSING"), [art], [], messages, {}, LaneOutcome.FAILED)

    # -- identity from what is actually there ------------------------------------------------------------------------
    d = obs.digests
    identity_items = [("archive", f.archive_filename, d.sha256, d.size)]
    if not obs.corrupt:
        identity_items += [("member", n, m.digests.sha256, m.digests.size) for n, m in obs.members.items()]
    sha = snapshot_sha256(identity_items)
    sid = snapshot_id("flavoria", sha)

    # -- checksum verification: archive ---------------------------------------------------------------------------------
    status, note = ArtifactStatus.VERIFIED, ""
    if d.size != f.archive_size_bytes:
        status, note = ArtifactStatus.SIZE_MISMATCH, f"size {d.size} != pinned {f.archive_size_bytes}"
    elif d.md5 != f.archive_md5:
        status, note = ArtifactStatus.CHECKSUM_MISMATCH, f"MD5 {d.md5} != published {f.archive_md5}"
    elif d.sha256 != f.archive_sha256:
        status, note = ArtifactStatus.CHECKSUM_MISMATCH, f"SHA-256 {d.sha256} != pinned {f.archive_sha256}"
    elif obs.corrupt:
        status, note = ArtifactStatus.CORRUPT, f"archive cannot be read: {obs.corrupt}"
    elif obs.unsafe:
        status, note = ArtifactStatus.UNEXPECTED_CONTENT, f"refused to read unsafe or oversized member(s): {sorted(obs.unsafe)}"
    expected_names = {m.file for m in f.members}
    if status is ArtifactStatus.VERIFIED and set(obs.members) != expected_names:
        missing, extra = sorted(expected_names - set(obs.members)), sorted(set(obs.members) - expected_names)
        status, note = ArtifactStatus.MEMBER_SET_MISMATCH, f"missing members {missing}; unexpected members {extra}"
    if status is not ArtifactStatus.VERIFIED:
        messages.append(Message(Level.ERROR, "S01", f"{f.archive_filename}: {status.value}: {note}. The pin is NOT updated and the raw file is untouched; a refreshed source needs an explicit retrieval and a new snapshot"))

    arc_id = _aid(sid, f.archive_filename)
    artifacts.append(Artifact(arc_id, sid, SOURCE, Lane.CORE, "archive", f.archive_filename, arc_rel, None, f.archive_url, retrieved, version,
                              True, d.size, d.md5, d.sha256, f.archive_size_bytes, f.archive_sha256, None, f.expected_total_rows, status, note))

    # -- checksum verification and schema fingerprints: members ------------------------------------------------------------------
    archive_ok = status is ArtifactStatus.VERIFIED
    for spec in f.members:
        om = obs.members.get(spec.file)
        mid = _aid(sid, f"{f.archive_filename}::{spec.file}")
        if not archive_ok:                 # members of an unverified archive are never trusted, even if they could be read
            artifacts.append(Artifact(mid, sid, SOURCE, Lane.CORE, "member", spec.file, arc_rel, arc_id, f.archive_url, retrieved, version, True,
                                      None, None, None, spec.bytes, spec.sha256, None, spec.rows, ArtifactStatus.NOT_CHECKED, "archive not verified"))
            continue
        if om is None:
            artifacts.append(Artifact(mid, sid, SOURCE, Lane.CORE, "member", spec.file, arc_rel, arc_id, f.archive_url, retrieved, version, True,
                                      None, None, None, spec.bytes, spec.sha256, None, spec.rows, ArtifactStatus.MISSING, "member not in archive"))
            continue
        ms, mn = ArtifactStatus.VERIFIED, ""
        if om.decode_error:
            ms, mn = ArtifactStatus.UNEXPECTED_CONTENT, f"not UTF-8: {om.decode_error}"
        elif om.digests.size != spec.bytes:
            ms, mn = ArtifactStatus.SIZE_MISMATCH, f"size {om.digests.size} != pinned {spec.bytes}"
        elif om.digests.sha256 != spec.sha256:
            ms, mn = ArtifactStatus.CHECKSUM_MISMATCH, f"SHA-256 {om.digests.sha256} != pinned {spec.sha256}"
        elif om.rows != spec.rows:
            ms, mn = ArtifactStatus.ROW_COUNT_MISMATCH, f"{om.rows} rows != pinned {spec.rows}"
        sc = classify(mid, spec.file, om.columns, f.required_columns, f.schema_variants)
        schemas.append(sc)
        if sc.status is SchemaStatus.MISSING_REQUIRED and ms is ArtifactStatus.VERIFIED:
            ms, mn = ArtifactStatus.SCHEMA_MISSING_REQUIRED, sc.message
        if sc.status is SchemaStatus.DRIFT:
            messages.append(Message(Level.WARN, "S08", f"{spec.file}: {sc.message}"))
        if ms is not ArtifactStatus.VERIFIED:
            messages.append(Message(Level.ERROR, "S01" if ms is not ArtifactStatus.SCHEMA_MISSING_REQUIRED else "S02", f"{spec.file}: {ms.value}: {mn}"))
        artifacts.append(Artifact(mid, sid, SOURCE, Lane.CORE, "member", spec.file, arc_rel, arc_id, f.archive_url, retrieved, version, True,
                                  om.digests.size, om.digests.md5, om.digests.sha256, spec.bytes, spec.sha256, om.rows, spec.rows, ms, mn))

    ok = all(a.status is ArtifactStatus.VERIFIED for a in artifacts)
    outcome = LaneOutcome.FAILED
    if ok:
        outcome = LaneOutcome.WARNING if any(s.status is SchemaStatus.DRIFT for s in schemas) else LaneOutcome.OK
    return FlavoriaOutcome(snapshot_record(sid, sha, len(identity_items), "VERIFIED" if ok else "FAILED"), artifacts, schemas, messages,
                           obs.member_bytes if ok else {}, outcome)


@dataclass
class FlavoriaOutcome:
    snapshot: Snapshot
    artifacts: list[Artifact]
    schemas: list[SchemaFingerprint]
    messages: list[Message]
    member_bytes: dict[str, bytes]        # populated only when the whole archive verified
    outcome: LaneOutcome
