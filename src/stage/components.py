"""Field normalization for staging: component names, scale identifiers, weights. Pure functions.

Component names are normalised by STRING rules only (trim, collapse whitespace, casefold). There is no alias table: names
disagree across exports in a way that mixes language variants with genuinely different dishes, so no mapping is defensible.
The raw name is always kept beside the normalised identifier.
"""
from __future__ import annotations

import re

from src.vocab import WeightParseStatus

_SCALE = re.compile(r"^(?P<kind>salaatti|lammin)(?P<pos>\d+)$")
_INT = re.compile(r"^\d+$")


def normalize_component_name(raw: str) -> str | None:
    """Trim, collapse internal whitespace, casefold. Empty input gives None (never an empty identifier)."""
    collapsed = " ".join(raw.split())
    return collapsed.casefold() if collapsed else None


def has_edge_whitespace(raw: str) -> bool:
    return raw != raw.strip()


def parse_weight(raw: str) -> tuple[int | None, WeightParseStatus]:
    """Integer grams or NULL. Zero and negative are not judged here (that is validation, WP4)."""
    text = raw.strip()
    if not text:
        return None, WeightParseStatus.EMPTY
    if _INT.match(text):
        return int(text), WeightParseStatus.OK
    return None, WeightParseStatus.NOT_INTEGER


def scale_parts(scale_id: str) -> tuple[str | None, str | None, str | None, int | None]:
    """(line, side, kind, position) from names like 'koti2-vasen-salaatti3' or 'vege2-lammin6'. Unparseable parts are None."""
    parts = scale_id.strip().split("-")
    if len(parts) == 3:
        line, side, last = parts
    elif len(parts) == 2:
        (line, last), side = parts, None
    else:
        return (parts[0] or None), None, None, None
    m = _SCALE.match(last)
    return line, side, (m.group("kind") if m else None), (int(m.group("pos")) if m else None)
