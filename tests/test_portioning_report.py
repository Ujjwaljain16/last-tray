"""Portioning-by-scale is a diagnostic, not a metric: it must reuse the approved population and the approved
statistics, changing neither, and it must not silently invent a scale grouping the schema doesn't already have.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.portioning_report import _kind, build, core_ready_registered_session_keys, main
from tests.static_checks import raw_access_violations

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "src" / "portioning_report.py").read_text(encoding="utf-8")


def test_module_reads_only_the_committed_canonical_tables():
    problems = raw_access_violations(SRC, may_touch_files=True)
    assert not problems, problems
    assert "outputs/staging" not in SRC and "data/raw" not in SRC


def test_kind_is_derived_from_the_real_scale_naming_convention_already_in_the_schema():
    assert _kind("koti2-vasen-lammin5") == "hot (lammin)"
    assert _kind("vege2-salaatti3") == "cold (salaatti)"
    assert _kind("something-else") == "other"


@pytest.fixture(scope="module")
def rows():
    return build(REPO / "outputs")


def test_uses_exactly_the_m1_through_m4_population_no_more_no_less(rows):
    """Total events grouped by scale must equal the MODELLABLE events of core-ready registered-export sessions -
    the same population M1-M4 report over - not staging's full count and not the raw archive's row count."""
    keys = core_ready_registered_session_keys(REPO / "outputs")
    assert len(keys) == 1697   # the approved M3/M5 numerator; if this drifts, the diagnostic's population drifted too

    with (REPO / "outputs" / "model" / "fact_weighing_event.csv").open(newline="", encoding="utf-8") as fh:
        expected = sum(1 for r in csv.DictReader(fh) if r["session_key"] in keys and r["disposition"] == "MODELLABLE" and r["component_weight_g"])
    assert sum(r["events"] for r in rows) == expected


def test_covers_at_most_the_thirty_documented_scales_and_every_row_has_a_real_event_count(rows):
    assert 1 <= len(rows) <= 30
    scale_ids = [r["scale_id"] for r in rows]
    assert len(scale_ids) == len(set(scale_ids)), "one row per scale, never duplicated"
    for r in rows:
        assert r["events"] > 0
        assert 0 <= r["heavy_flag_events_b02"] <= r["events"]
        assert r["heavy_flag_rate_pct"] == pytest.approx(100 * r["heavy_flag_events_b02"] / r["events"], abs=0.01)


def test_the_median_and_p90_use_the_same_statistics_module_the_approved_metrics_use():
    from src.metrics.stats import median, percentile_linear
    from src.portioning_report import build as _build
    weights_by_scale: dict[str, list[int]] = {}
    keys = core_ready_registered_session_keys(REPO / "outputs")
    with (REPO / "outputs" / "model" / "fact_weighing_event.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["session_key"] in keys and r["disposition"] == "MODELLABLE" and r["component_weight_g"]:
                weights_by_scale.setdefault(r["scale_id"], []).append(int(r["component_weight_g"]))
    rows = {r["scale_id"]: r for r in _build(REPO / "outputs")}
    for scale_id, weights in weights_by_scale.items():
        assert rows[scale_id]["median_weight_g"] == pytest.approx(round(median(weights), 1))
        assert rows[scale_id]["p90_weight_g"] == pytest.approx(round(percentile_linear(weights, 0.9), 1))


def test_the_total_heavy_flag_count_matches_the_known_registered_export_b02_count(rows):
    """Cross-check against the independently known figure: 3 registered-export B02 warnings (validation_issues.csv)."""
    assert sum(r["heavy_flag_events_b02"] for r in rows) == 3


def test_main_writes_the_output_file_and_reports_the_same_totals(tmp_path, capsys):
    out = tmp_path / "outputs"
    for sub, name in (("model", "fact_dining_session.csv"), ("model", "fact_weighing_event.csv")):
        (out / sub).mkdir(parents=True, exist_ok=True)
        (out / sub / name).write_bytes((REPO / "outputs" / sub / name).read_bytes())
    assert main(["--out", str(out)]) == 0
    target = out / "evidence" / "portioning_by_scale.csv"
    assert target.is_file()
    with target.open(newline="", encoding="utf-8") as fh:
        written = list(csv.DictReader(fh))
    assert len(written) == 30
    assert sum(int(r["events"]) for r in written) == 8360
