"""Shared vocabulary. One place for every enumerated value the documentation defines.

The values here mirror docs/data_dictionary.md section 9 and docs/canonical_schema.md. A test compares them with
the documentation, so the code cannot drift from the specification unnoticed.
"""
from __future__ import annotations

from enum import Enum


class Population(str, Enum):
    """Source-derived labels (from filenames). Not customer-registration status."""

    REGISTERED_EXPORT = "registered_export"
    NON_REGISTERED_EXPORT = "non_registered_export"


class Severity(str, Enum):
    INFO = "INFO"        # records a fact
    WARN = "WARN"        # kept and visible; never removes a record from the KPI population
    ERROR = "ERROR"      # breaks core_ready


class Handling(str, Enum):
    FLAG = "FLAG"                # kept, counted
    QUARANTINE = "QUARANTINE"    # kept in the model, out of the canonical population, listed
    BLOCK = "BLOCK"              # stop the affected stage
    KEEP_FIRST = "KEEP_FIRST"    # exact duplicate: first row kept, repeats excluded from sums


class Category(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    BUSINESS = "BUSINESS"
    TEMPORAL = "TEMPORAL"
    IDENTITY = "IDENTITY"
    CROSS_SOURCE = "CROSS-SOURCE"
    COMPLETENESS = "COMPLETENESS"


class QualityStatus(str, Enum):
    VALID = "VALID"
    WARN = "WARN"
    INVALID = "INVALID"


class EvidenceStatus(str, Enum):
    """Deterministic evidence statuses, not confidence scores."""

    READY = "READY"
    READY_WITH_LIMITATION = "READY_WITH_LIMITATION"
    BLOCKED = "BLOCKED"


class StageOutcome(str, Enum):
    RECOVERED = "RECOVERED"   # a fault occurred and a retry or fallback succeeded
    WARNING = "WARNING"       # output produced with a documented limitation
    FAILED = "FAILED"         # a stage could not do its job; the run stops with a message
    BLOCKED = "BLOCKED"       # one output cannot be produced because a prerequisite is unavailable


class SemanticClass(str, Enum):
    """What kind of fact a value is. UNKNOWN and SOURCE_GAP are never stored as zero."""

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"
    SOURCE_GAP = "SOURCE_GAP"


class TimezoneHandling(str, Enum):
    """How a timestamp's zone was treated. Recorded on every staged timestamp; never dropped."""

    SOURCE_LOCAL_ASSUMED = "SOURCE_LOCAL_ASSUMED"          # source states no zone; read as Europe/Helsinki local time (an assumption)
    NORMALISED_PLUS_3H_STRONGEST_SUPPORT = "NORMALISED_PLUS_3H_STRONGEST_SUPPORT"   # file-specific, evidence-backed, NOT source-confirmed
    SOURCE_UTC_STATED = "SOURCE_UTC_STATED"                # the source states UTC (FMI 'Z' timestamps)


TimezoneNormalization = TimezoneHandling    # name used by configuration and ingestion


class LocalTimeStatus(str, Enum):
    """Result of reading a wall-clock time in a zone with daylight saving. Ambiguous and nonexistent times are never guessed."""

    OK = "OK"
    AMBIGUOUS = "AMBIGUOUS"          # the local time occurs twice (clocks go back)
    NONEXISTENT = "NONEXISTENT"      # the local time never occurs (clocks go forward)
    UNPARSEABLE = "UNPARSEABLE"


class WeightParseStatus(str, Enum):
    OK = "OK"
    NOT_INTEGER = "NOT_INTEGER"
    EMPTY = "EMPTY"


class RowParseStatus(str, Enum):
    OK = "OK"
    SHORT_ROW = "SHORT_ROW"          # fewer cells than the required columns need
    EXTRA_CELLS = "EXTRA_CELLS"      # more cells than the header, or data under a blank header column


class ValueStatus(str, Enum):
    OK = "OK"
    NAN_SOURCE_NULL = "NAN_SOURCE_NULL"    # the source reports NaN: stored as NULL, never zero
    UNPARSEABLE = "UNPARSEABLE"


class ComponentCountStatus(str, Enum):
    READY_WITH_LIMITATION = "READY_WITH_LIMITATION"
    LIMITED = "LIMITED"        # cross-export component identity unstable for that session's day


def values(enum_cls: type[Enum]) -> set[str]:
    """The string values of an enum, for comparison with documentation."""
    return {m.value for m in enum_cls}
