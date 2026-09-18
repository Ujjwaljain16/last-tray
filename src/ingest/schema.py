"""Schema fingerprints. A fingerprint identifies a CSV header exactly; classification says whether it is a known variant.

Missing required column -> S02 (the file cannot be used). Anything else that differs from a known variant -> S08 drift
(a warning: staging reads by column NAME, so extra or reordered columns do not corrupt the data).
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

from src.ingest.model import SchemaFingerprint, SchemaStatus

SEP = "\x1f"   # unit separator: cannot occur in a header name


def fingerprint(columns: Iterable[str]) -> str:
    return hashlib.sha256(SEP.join(columns).encode("utf-8")).hexdigest()


def classify(artifact_id: str, filename: str, columns: list[str], required: Iterable[str],
             variants: Mapping[str, tuple[str, ...]]) -> SchemaFingerprint:
    fp = fingerprint(columns)
    named = [c for c in columns if c.strip()]
    blank = len(columns) - len(named)
    missing = tuple(c for c in required if c not in named)
    known_named = {c for v in variants.values() for c in v if c.strip()}
    unexpected = tuple(c for c in named if c not in known_named)

    if missing:
        return SchemaFingerprint(artifact_id, filename, fp, None, SchemaStatus.MISSING_REQUIRED, len(named), blank, missing, unexpected,
                                 f"required column(s) missing: {', '.join(missing)} (S02)")
    for name, cols in variants.items():
        if fingerprint(cols) == fp:
            return SchemaFingerprint(artifact_id, filename, fp, name, SchemaStatus.KNOWN_VARIANT, len(named), blank, (), (), "")
    reason = (f"unexpected column(s): {', '.join(unexpected)}" if unexpected
              else "same columns as a known variant but a different order or blank-column layout")
    return SchemaFingerprint(artifact_id, filename, fp, None, SchemaStatus.DRIFT, len(named), blank, (), unexpected,
                             f"header matches no known variant: {reason} (S08)")
