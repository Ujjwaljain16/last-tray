"""Ingestion data model. Every record carries its source_snapshot_id so any downstream value can be traced to a
snapshot, a raw artifact, a checksum, a source URL and retrieval metadata.

Grains (one row =):
    Snapshot          one immutable, checksum-identified set of raw artifacts from ONE source
    Artifact          one raw file (or one member of a raw archive) inside a snapshot
    SchemaFingerprint one CSV header, classified against the known schema variants
    WeatherChunk      one FMI response file, with its completeness evidence
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ArtifactStatus(str, Enum):
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
    CORRUPT = "CORRUPT"
    MEMBER_SET_MISMATCH = "MEMBER_SET_MISMATCH"
    UNEXPECTED_CONTENT = "UNEXPECTED_CONTENT"
    SCHEMA_MISSING_REQUIRED = "SCHEMA_MISSING_REQUIRED"
    MALFORMED = "MALFORMED"
    INCOMPLETE = "INCOMPLETE"
    NOT_CHECKED = "NOT_CHECKED"


class Lane(str, Enum):
    CORE = "core"          # Flavoria weighing events: without them there is nothing to measure
    CONTEXT = "context"    # weather: enrichment only; never blocks core outputs


class LaneOutcome(str, Enum):
    OK = "OK"
    WARNING = "WARNING"    # output possible with a documented limitation
    FAILED = "FAILED"      # core lane could not be trusted: the run stops
    BLOCKED = "BLOCKED"    # context lane: weather-dependent outputs are blocked, core continues


class SchemaStatus(str, Enum):
    KNOWN_VARIANT = "KNOWN_VARIANT"
    DRIFT = "DRIFT"                        # all required columns present, header differs from every known variant (S08)
    MISSING_REQUIRED = "MISSING_REQUIRED"  # a required column is absent (S02)


class Level(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Message:
    level: Level
    code: str
    text: str


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    source_snapshot_id: str | None
    source_name: str
    lane: Lane
    kind: str                    # archive | member | weather_chunk | evidence
    filename: str
    path: str                    # repo-relative, posix
    parent_artifact_id: str | None
    source_url: str
    retrieved_on: str
    version: str
    in_snapshot_identity: bool
    size_bytes: int | None
    md5: str | None
    sha256: str | None
    expected_size_bytes: int | None
    expected_sha256: str | None
    row_count: int | None
    expected_rows: int | None
    status: ArtifactStatus
    message: str = ""


@dataclass(frozen=True)
class Snapshot:
    source_snapshot_id: str | None
    source_name: str
    lane: Lane
    source_url: str
    version: str
    license: str
    retrieved_on: str
    retrieval_method: str
    artifact_count: int
    snapshot_sha256: str | None
    status: str                  # VERIFIED | FAILED | MISSING


@dataclass(frozen=True)
class SchemaFingerprint:
    artifact_id: str
    filename: str
    fingerprint: str
    variant: str | None
    status: SchemaStatus
    named_columns: int
    blank_columns: int
    missing_required: tuple[str, ...]
    unexpected: tuple[str, ...]
    message: str = ""


@dataclass(frozen=True)
class WeatherChunk:
    artifact_id: str
    filename: str
    elements: int | None
    number_returned: int | None
    hours: int | None
    parameters: tuple[str, ...]
    null_values: int | None
    content_sha256: str | None
    expected_content_sha256: str | None
    status: ArtifactStatus
    message: str = ""


@dataclass(frozen=True)
class TzScope:
    """Rule T10: a file-specific normalization is valid only for its file, date range and observed shift."""

    filename: str
    status: str                  # VALID | INVALID
    first_event_date: str | None
    last_event_date: str | None
    raw_median_first_hour: float | None
    normalised_median_first_hour: float | None
    reasons: tuple[str, ...]


@dataclass
class IngestionResult:
    snapshots: list[Snapshot] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    schemas: list[SchemaFingerprint] = field(default_factory=list)
    weather_chunks: list[WeatherChunk] = field(default_factory=list)
    tz_scope: list[TzScope] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    core_outcome: LaneOutcome = LaneOutcome.OK
    context_outcome: LaneOutcome = LaneOutcome.OK
    input_fingerprint: str | None = None
    raw_unchanged: bool | None = None
    steps: list[tuple[str, str]] = field(default_factory=list)   # (step, status), in execution order

    def snapshot(self, source_name: str) -> Snapshot | None:
        return next((s for s in self.snapshots if s.source_name == source_name), None)
