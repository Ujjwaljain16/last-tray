"""Validation findings: the stable issue schema and the rule catalogue.

Three ideas are kept apart on purpose:
  severity  ERROR / WARN / INFO      how serious the finding is for measurement integrity
  handling  FLAG / QUARANTINE / BLOCK / KEEP_FIRST   what the pipeline does about it
  quarantine (bool)                  True only when handling is QUARANTINE: the entity is kept in every table, listed in the
                                     quarantine manifest and excluded from the primary population. Nothing is ever deleted.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from src.config import Config
from src.vocab import Category, Handling, Severity

ISSUE_COLUMNS = (
    "validation_issue_id", "run_id", "rule_id", "category", "severity", "handling", "quarantine",
    "entity_type", "entity_id", "session_key", "event_id", "population", "source_snapshot_id", "source_file",
    "lineage_basis", "source_row_lineage", "observed_value", "expected_condition", "description", "business_consequence",
)

# What a reviewer follows from an issue back to the staged rows.
BASIS_EVENT = "EVENT_ROW"                  # event_id is the staged row (file#row)
BASIS_SESSION = "SESSION_EVENT_ROWS"       # source_row_lineage lists every event row of the session key
BASIS_ROWS = "EVENT_ROW_SET"               # source_row_lineage lists the related rows (e.g. a repeat and the row it repeats)
BASIS_FILE = "SOURCE_FILE"                 # the whole staged file
BASIS_DAY = "SERVICE_DAY"                  # the sessions of that service_date in session_validation_status.csv
BASIS_ABSENT = "ABSENT_SOURCE"             # expected data is missing; there is no row to point at
BASIS_WEATHER = "WEATHER_OBSERVATION"      # observation_id (file#element) in stg_weather_observation.csv
BASIS_POPULATION = "POPULATION"


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    category: Category
    severity: Severity
    handling: Handling
    consequence: str


@dataclass(frozen=True)
class Issue:
    rule_id: str
    entity_type: str
    entity_id: str
    lineage_basis: str
    description: str
    observed_value: str = ""
    expected_condition: str = ""
    session_key: str = ""
    event_id: str = ""
    population: str = ""
    source_snapshot_id: str = ""
    source_file: str = ""
    source_row_lineage: str = ""
    severity: str = ""                     # only when one rule legitimately has two severities (I06: identical versions are INFO)


def _spec(rule_id: str, category: Category, severity: Severity, handling: Handling, consequence: str) -> RuleSpec:
    return RuleSpec(rule_id, category, severity, handling, consequence)


S, B, T, I, X, C = (Category.STRUCTURAL, Category.BUSINESS, Category.TEMPORAL, Category.IDENTITY, Category.CROSS_SOURCE, Category.COMPLETENESS)
E, W, N = Severity.ERROR, Severity.WARN, Severity.INFO
F, Q, K, D = Handling.FLAG, Handling.QUARANTINE, Handling.BLOCK, Handling.KEEP_FIRST

# Severity and handling for the rules below come from docs/validation_rules.md. Rules whose thresholds live in config/thresholds.yml
# take severity and handling from there (see build_catalogue), so configuration cannot drift from what the code does.
_FIXED = [
    _spec("S03", S, N, F, "none: the only value ever seen is 'line'"),
    _spec("S04", S, W, F, "hidden data under an unnamed column would otherwise be lost"),
    _spec("S05", S, E, Q, "the event cannot be attributed to a session, tray, scale or component"),
    _spec("S06", S, E, Q, "the derived session weight would be wrong"),
    _spec("S07", S, E, Q, "the event cannot be placed in time"),
    _spec("S08", S, W, F, "schema drift: the row does not fit the declared columns"),
    _spec("B01", B, E, Q, "a non-positive weight cannot be a selected component"),
    _spec("B02", B, W, F, "may be a tray or plate artefact or a genuine bulk portion; kept in sums"),
    _spec("B03", B, N, F, "may be scale noise or a garnish; kept"),
    _spec("B04", B, W, F, "may be a single-item lunch or a partial capture; kept"),
    _spec("B05", B, N, F, "repeat scoops are additive; the derived weight includes them"),
    _spec("B07", B, W, F, "extreme sessions influence the upper percentile; kept"),
    _spec("T01", T, E, Q, "outside the study window"),
    _spec("T02", T, W, F, "an event on a day the restaurant is not expected to serve"),
    _spec("T03", T, E, Q, "a clock problem: the event cannot be trusted to sit in service hours"),
    _spec("T04", T, W, F, "the workflow order assumption is violated; kept"),
    _spec("T05", T, W, F, "may merge two tray passes; kept"),
    _spec("T06", T, W, F, "the session boundary would be uncertain"),
    _spec("T07", T, W, F, "a silent clock shift would corrupt time-of-day analysis and the weather join"),
    _spec("T08", T, N, F, "the timestamp parser must be per column"),
    _spec("T10", T, E, K, "a normalization applied outside the evidence that supports it would silently corrupt time"),
    _spec("I01", I, E, Q, "two versions of one tray pass exist and no source has authority: both are quarantined"),
    _spec("I02", I, W, D, "the repeated row would double-count grams: the first row is kept, the repeat is excluded from sums"),
    _spec("I04", I, E, Q, "the session cannot be attributed to one tray"),
    _spec("I06", I, W, F, "the two exports disagree about the same tray pass"),
    _spec("I07", I, N, F, "component identity is unstable across exports for that scale and day: component-level comparison is limited"),
    _spec("X01", X, W, F, "weather context is incomplete for some hours"),
    _spec("X03", X, N, F, "the value is NULL, never zero; precipitation comparisons exclude that hour"),
    _spec("X04", X, E, K, "a wrong hour would be joined to weather"),
    _spec("X07", X, E, K, "the weather table does not have the expected station-hour-parameter grain: weather outputs are blocked"),
    _spec("X08", X, W, F, "a weather hour lacks a requested parameter"),
    _spec("C01", C, W, F, "volume comparisons are not like-for-like"),
    _spec("C02a", C, N, F, "volume is not like-for-like across days"),
    _spec("C02b", C, W, F, "the observed volume regime differs from the weekday's baseline regime; NOT a data error, never excluded; M3 is not a demand indicator"),
    _spec("C03", C, W, F, "diagnostic coverage for that population and week is incomplete"),
    _spec("C04", C, E, K, "events were lost or double-counted between staging and validation"),
]
RULE_ORDER = {s.rule_id: i for i, s in enumerate(_FIXED)}


def build_catalogue(cfg: Config) -> dict[str, RuleSpec]:
    """The rule catalogue with severity and handling taken from config/thresholds.yml wherever the rule is configured there."""
    catalogue = {s.rule_id: s for s in _FIXED}
    for rid, rule in cfg.thresholds.rules.items():
        if rid in catalogue:
            base = catalogue[rid]
            catalogue[rid] = RuleSpec(rid, base.category, rule.severity, rule.handling, base.consequence)
    return catalogue


def issue_id(rule_id: str, entity_type: str, entity_id: str) -> str:
    """Content-derived and stable: the same finding on the same entity always has the same id."""
    return "vi-" + hashlib.sha256(f"{rule_id}|{entity_type}|{entity_id}".encode("utf-8")).hexdigest()[:12]


def finalise(issues: list[Issue], catalogue: dict[str, RuleSpec], run_id: str) -> list[dict[str, Any]]:
    """Issues to rows with the full stable schema, sorted deterministically. Refuses duplicate ids and unknown rules."""
    rows: list[dict[str, Any]] = []
    for i in issues:
        spec = catalogue.get(i.rule_id)
        if spec is None:
            raise ValueError(f"issue for unknown rule {i.rule_id!r}")
        rows.append({
            "validation_issue_id": issue_id(i.rule_id, i.entity_type, i.entity_id), "run_id": run_id, "rule_id": i.rule_id,
            "category": spec.category.value, "severity": i.severity or spec.severity.value, "handling": spec.handling.value,
            "quarantine": spec.handling is Handling.QUARANTINE,
            "entity_type": i.entity_type, "entity_id": i.entity_id, "session_key": i.session_key, "event_id": i.event_id,
            "population": i.population, "source_snapshot_id": i.source_snapshot_id, "source_file": i.source_file,
            "lineage_basis": i.lineage_basis, "source_row_lineage": i.source_row_lineage, "observed_value": i.observed_value,
            "expected_condition": i.expected_condition, "description": i.description, "business_consequence": spec.consequence,
        })
    rows.sort(key=lambda r: (RULE_ORDER[r["rule_id"]], r["population"], r["entity_id"], r["event_id"]))
    ids = [r["validation_issue_id"] for r in rows]
    if len(set(ids)) != len(ids):
        dup = sorted({x for x in ids if ids.count(x) > 1})[:3]
        raise ValueError(f"validation_issue_id is not unique (rule, entity type, entity id must identify one finding): {dup}")
    return rows
