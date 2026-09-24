"""Portioning consistency by scale: a supporting diagnostic, not a headline metric.

M1-M4 describe the typical selected meal as a whole. This asks a narrower, operational question: within the
approved measurement population (core-ready, registered-export sessions), which of the 30 physical scales show
the most inconsistent portioning - the most spread in what gets weighed there, and the highest share of B02
"unusually heavy" flags?

`scale_identifier` (`scale_id` in the canonical model) is an OBSERVED field, verbatim from the source, already
part of the schema (`docs/data_dictionary.md`) - this groups by it, it does not invent it. The "hot" / "cold"
label is a simple, disclosed derivation from the scale name (`lammin` = hot dish, `salaatti` = cold/salad),
the same convention already used elsewhere in the schema; it is not a new business definition.

This changes no metric, no threshold and no validation rule. It reads only the committed canonical tables and
writes one new file. A kitchen manager could use it to ask "is scale X reading consistently heavy" - the kind
of question the raw M1/M2 numbers cannot answer on their own.

Run: python -m src.portioning_report [--out outputs]
Writes: outputs/evidence/portioning_by_scale.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from src.fsutil import atomic_path
from src.metrics.stats import median, percentile_linear

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ("scale_id", "station_family", "kind", "events", "median_weight_g", "p90_weight_g", "heavy_flag_events_b02", "heavy_flag_rate_pct")


def _kind(scale_id: str) -> str:
    if "lammin" in scale_id:
        return "hot (lammin)"
    if "salaatti" in scale_id:
        return "cold (salaatti)"
    return "other"


def core_ready_registered_session_keys(out_dir: Path) -> set[str]:
    """The same population M1-M4 use: registered-export sessions with core_ready = true. Read, not recomputed."""
    with (out_dir / "model" / "fact_dining_session.csv").open(newline="", encoding="utf-8") as fh:
        return {r["session_key"] for r in csv.DictReader(fh) if r["population"] == "registered_export" and r["core_ready"] == "true"}


def build(out_dir: Path) -> list[dict]:
    keys = core_ready_registered_session_keys(out_dir)
    by_scale: dict[str, list[tuple[int, bool, str]]] = defaultdict(list)
    with (out_dir / "model" / "fact_weighing_event.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["session_key"] not in keys or r["disposition"] != "MODELLABLE" or not r["component_weight_g"]:
                continue
            by_scale[r["scale_id"]].append((int(r["component_weight_g"]), "B02" in r["validation_warn_rule_ids"].split(";"), r["station_family"]))

    rows = []
    for scale_id, items in sorted(by_scale.items()):
        weights = [w for w, _, _ in items]
        heavy = sum(1 for _, flagged, _ in items if flagged)
        rows.append({
            "scale_id": scale_id, "station_family": items[0][2], "kind": _kind(scale_id),
            "events": len(items), "median_weight_g": round(median(weights), 1),
            "p90_weight_g": round(percentile_linear(weights, 0.9), 1),
            "heavy_flag_events_b02": heavy, "heavy_flag_rate_pct": round(100 * heavy / len(items), 2),
        })
    return rows


def write(out_dir: Path, rows: list[dict]) -> Path:
    d = out_dir / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    target = d / "portioning_by_scale.csv"
    with atomic_path(target) as tmp, tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.portioning_report",
                                description="Per-scale portioning consistency, a supporting diagnostic over the approved measurement population.")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "outputs")
    args = p.parse_args(argv)

    rows = build(args.out)
    target = write(args.out, rows)
    ranked = sorted(rows, key=lambda r: r["heavy_flag_rate_pct"], reverse=True)[:5]
    print(f"{len(rows)} scales, {sum(r['events'] for r in rows):,} events (core-ready registered-export sessions). Wrote {target}.")
    print("Highest heavy-flag (B02) rate:")
    for r in ranked:
        print(f"  {r['scale_id']:<26}{r['kind']:<16}{r['events']:>5} events   median {r['median_weight_g']:>7} g   heavy-flag rate {r['heavy_flag_rate_pct']:>5}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
