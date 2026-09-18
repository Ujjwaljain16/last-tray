"""Event-level rules (S04-S08, B01-B03, T01-T03, I02). One issue per offending staged row; the row itself is never touched.

Thresholds come from config/thresholds.yml. They are DIAGNOSTIC: they describe this dataset's observed structure and are not
claims of physical impossibility. Rules read staged values only.
"""
from __future__ import annotations

import operator
from datetime import date

from src.config import Config, Rule
from src.validate.load import Ev
from src.validate.model import BASIS_EVENT, BASIS_ROWS, Issue

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
REQUIRED_TEXT_FIELDS = (("session_id", lambda e: e.session_id), ("tray_id", lambda e: e.tray_id),
                        ("scale_id", lambda e: e.scale_id), ("component_name", lambda e: e.component_name_raw))


def _issue(rule_id: str, e: Ev, description: str, observed: str, expected: str, basis: str = BASIS_EVENT, lineage: str = "") -> Issue:
    return Issue(rule_id, "event", e.event_id, basis, description, observed, expected, session_key=e.session_key, event_id=e.event_id,
                 population=e.population, source_snapshot_id=e.source_snapshot_id, source_file=e.source_file,
                 source_row_lineage=lineage or e.event_id)


def check_structure(events: list[Ev]) -> list[Issue]:
    """S04 hidden data under an unnamed column, S05 empty required value, S06 weight not an integer, S07 timestamp not usable, S08 row does not fit the header."""
    out: list[Issue] = []
    for e in events:
        if '"blank_header_columns"' in e.unmapped_cells:
            out.append(_issue("S04", e, "a value sits under an unnamed column (kept in staging.unmapped_cells)", e.unmapped_cells, "unnamed columns are empty"))
        if e.row_parse_status != "OK" or '"extra_columns"' in e.unmapped_cells or '"beyond_header"' in e.unmapped_cells:
            out.append(_issue("S08", e, "the row does not fit the declared columns; nothing was repaired", f"row_parse_status={e.row_parse_status}; {e.unmapped_cells}".rstrip("; "), "row_parse_status=OK and no undeclared columns"))
        empty = [name for name, get in REQUIRED_TEXT_FIELDS if not get(e).strip()]
        if empty:
            out.append(_issue("S05", e, "a required value is empty", ",".join(empty), "all required values present"))
        if e.weight_parse_status != "OK":
            out.append(_issue("S06", e, "weight_of_a_component is not an integer", f"{e.weight_parse_status}: {e.weight_raw!r}", "an integer number of grams"))
        for label, status, raw in (("weighing_event_time", e.event_time_status, e.event_time_raw), ("user_identification_time", e.identification_time_status, e.identification_time_raw)):
            if status != "OK":
                out.append(_issue("S07", e, f"{label} cannot be placed on the timeline", f"{status}: {raw!r}", "a parseable, unambiguous local time"))
    return out


def check_weights(events: list[Ev], repeats: dict[str, str], rules: dict[str, Rule]) -> list[Issue]:
    """B01 weight not positive; B02 large; B03 trace (excluding repeats and non-positive weights, which B01 already reports)."""
    b02, b03 = rules["B02"], rules["B03"]
    out: list[Issue] = []
    for e in events:
        w = e.weight_g
        if w is None:
            continue
        if w <= 0:
            out.append(_issue("B01", e, "component weight is not positive", str(w), "> 0 g"))
            continue
        if _OPS[b02.operator](w, b02.value):
            out.append(_issue("B02", e, f"event weight {w} g on {e.scale_id} (diagnostic threshold, not a physical limit)", f"{w} g", f"below {b02.value:g} g"))
        if e.event_id not in repeats and _OPS[b03.operator](w, b03.value):
            out.append(_issue("B03", e, f"trace weight {w} g", f"{w} g", f"above {b03.value:g} g"))
    return out


def check_time_window(events: list[Ev], cfg: Config, rules: dict[str, Rule]) -> list[Issue]:
    """T01 inside the study window, T02 on a weekday, T03 inside service hours (local time after the timezone rule)."""
    t03 = rules["T03"]
    lo, hi = cfg.sources.flavoria.window_start, cfg.sources.flavoria.window_end
    out: list[Issue] = []
    for e in events:
        t = e.event_time_local
        if t is None:
            continue
        d: date = t.date()
        if not lo <= d <= hi:
            out.append(_issue("T01", e, "event date is outside the study window", d.isoformat(), f"{lo}..{hi}"))
        if d.weekday() >= 5:
            out.append(_issue("T02", e, "event on a weekend", f"{d} ({d.strftime('%A')})", "Monday-Friday"))
        if not t03.low <= t.hour < t03.high:
            out.append(_issue("T03", e, f"event at {t.isoformat()} is outside service hours after the timezone rule", f"hour {t.hour}", f"{t03.low:g} <= hour < {t03.high:g}"))
    return out


def check_repeats(events: list[Ev], repeats: dict[str, str]) -> list[Issue]:
    """I02: an exact repeat of an earlier row of the same file. Keep first; the repeat is excluded from sums (never deleted)."""
    by_id = {e.event_id: e for e in events}
    return [_issue("I02", by_id[rid], f"exact duplicate of {first} (every source cell equal)", f"repeats {first}", "no exact duplicate rows",
                   BASIS_ROWS, f"{rid};{first}") for rid, first in sorted(repeats.items())]
