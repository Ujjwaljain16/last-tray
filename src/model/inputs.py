"""Inputs of the canonical model: verified staging tables plus verified validation outputs. Nothing else.

The model never opens data/raw. It trusts a validation file only after (1) the file matches the SHA-256 the validation summary recorded,
(2) the validation summary says it was computed on exactly these staging tables, and (3) the files agree with each other and with
staging. Any failure stops the model: a canonical table built on unverified evidence would be worse than no table.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ingest.hashing import digest_file
from src.validate.load import StagedInputs, StagingInputError, load_staging
from src.validate.validate import (COMPLETENESS_CSV, DAYS_CSV, EVENT_STATUS_CSV, ISSUES_CSV, OUT_SUBDIR as VALIDATION_SUBDIR, QUARANTINE_CSV, RECON_CSV,
                                   SESSION_STATUS_CSV, SUMMARY_JSON as VALIDATION_SUMMARY)

DISPOSITIONS = ("MODELLABLE", "DUPLICATE_EXCLUDED", "QUARANTINED")
VERIFIED_FILES = (ISSUES_CSV, RECON_CSV, QUARANTINE_CSV, SESSION_STATUS_CSV, EVENT_STATUS_CSV, DAYS_CSV, COMPLETENESS_CSV, "validation_summary_by_rule.csv")


class ModelInputError(Exception):
    """A staging or validation input is missing, altered, or inconsistent. The model must not be built."""


@dataclass
class ModelInputs:
    staged: StagedInputs
    validation_summary: dict[str, Any]
    event_status: dict[str, dict[str, str]]       # event_id -> validation row
    session_status: dict[str, dict[str, str]]     # session_key -> validation row
    quarantined_keys: list[str]
    issues: list[dict[str, str]]
    service_days: list[dict[str, str]]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_model_inputs(out_dir: Path) -> ModelInputs:
    try:
        staged = load_staging(out_dir)
    except StagingInputError as exc:
        raise ModelInputError(f"staging is not usable: {exc}") from exc
    v = out_dir / VALIDATION_SUBDIR
    summary_path = v / VALIDATION_SUMMARY
    if not summary_path.is_file():
        raise ModelInputError(f"{VALIDATION_SUMMARY} is missing: validation has not run (python -m src.pipeline.run --stages validate)")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelInputError(f"{VALIDATION_SUMMARY} is not valid JSON: {exc}") from exc
    if summary.get("core_status") not in ("PASSED", "PASSED_WITH_QUARANTINE"):
        raise ModelInputError(f"validation reports the core lane as {summary.get('core_status')}: the model must not be built on it")
    if summary.get("staging_table_sha256") != staged.table_sha256:
        raise ModelInputError("validation was computed on different staging tables than the ones present (checksums differ): rerun validation")
    recorded = summary.get("output_sha256", {})
    for name in VERIFIED_FILES:
        p = v / name
        if not p.is_file():
            raise ModelInputError(f"{name} is missing from the validation outputs")
        if name not in recorded:
            raise ModelInputError(f"{VALIDATION_SUMMARY} records no SHA-256 for {name}")
        if digest_file(p).sha256 != recorded[name]:
            raise ModelInputError(f"{name} does not match the SHA-256 recorded by validation: it was altered or is stale")

    event_rows = _rows(v / EVENT_STATUS_CSV)
    if [r["event_id"] for r in event_rows] != [e.event_id for e in staged.events]:
        raise ModelInputError("event_validation_status does not list exactly the staged events, in staging order")
    bad = sorted({r["disposition"] for r in event_rows} - set(DISPOSITIONS))
    if bad:
        raise ModelInputError(f"event_validation_status has unknown dispositions: {bad}")
    session_rows = _rows(v / SESSION_STATUS_CSV)
    manifest_keys = sorted(r["entity_id"] for r in _rows(v / QUARANTINE_CSV) if r["quarantine_entity_type"] == "session_key")
    if manifest_keys != sorted(summary["quarantine"]["keys"]):
        raise ModelInputError("the quarantine manifest and the validation summary disagree about which session keys are quarantined")
    return ModelInputs(staged, summary, {r["event_id"]: r for r in event_rows}, {r["session_key"]: r for r in session_rows}, manifest_keys,
                       _rows(v / ISSUES_CSV), _rows(v / DAYS_CSV))
