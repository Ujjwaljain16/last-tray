"""The code vocabulary must equal the documented vocabulary. Documentation is the specification."""
from __future__ import annotations

import re
from pathlib import Path

from src.vocab import (ComponentCountStatus, EvidenceStatus, Handling, Population, QualityStatus, SemanticClass,
                       Severity, StageOutcome, TimezoneNormalization, values)

DOCS = Path(__file__).resolve().parents[1] / "docs"

# field name in docs/data_dictionary.md section 9  ->  enum in src/vocab.py
DOCUMENTED = {
    "population": Population,
    "timezone_normalization": TimezoneNormalization,
    "quality_status": QualityStatus,
    "distinct_component_count_status": ComponentCountStatus,
    "severity": Severity,
    "handling": Handling,
    "evidence status": EvidenceStatus,
    "pipeline outcome": StageOutcome,
}


def documented_enumerations() -> dict[str, set[str]]:
    text = (DOCS / "data_dictionary.md").read_text(encoding="utf-8")
    section = text[text.index("## 9. Enumerations"):]
    out: dict[str, set[str]] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and not set(cells[0]) <= {"-"} and cells[0] not in {"Field", ""}:
            out[cells[0].strip("`")] = set(re.findall(r"`([^`]+)`", cells[1])) or {v.strip() for v in cells[1].split(",")}
    return out


def test_every_documented_enumeration_matches_the_code():
    doc = documented_enumerations()
    assert set(doc) == set(DOCUMENTED), f"documented fields differ: {set(doc) ^ set(DOCUMENTED)}"
    for field, enum_cls in DOCUMENTED.items():
        assert values(enum_cls) == doc[field], f"{field}: code {sorted(values(enum_cls))} != docs {sorted(doc[field])}"


def test_semantic_layers_are_exactly_the_four_locked_classes():
    assert values(SemanticClass) == {"OBSERVED", "DERIVED", "UNKNOWN", "SOURCE_GAP"}


def test_population_codes_are_source_derived_labels():
    assert values(Population) == {"registered_export", "non_registered_export"}


def test_severity_ladder():
    assert [s.value for s in Severity] == ["INFO", "WARN", "ERROR"]
