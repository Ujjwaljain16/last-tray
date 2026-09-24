"""Independent SQL verification: the window-function percentile SQL is correct on its own, and it reproduces
the approved metrics from the committed canonical tables - a second engine, not a second opinion.
"""
from __future__ import annotations

import csv
import sqlite3
import statistics
from pathlib import Path

import pytest

from src.sql_verify import approved_metrics, build_db, main, run
from tests.static_checks import raw_access_violations

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "src" / "sql_verify.py").read_text(encoding="utf-8")


def test_module_reads_only_the_committed_canonical_tables_never_raw_or_staging():
    problems = raw_access_violations(SRC, may_touch_files=True)
    assert not problems, problems
    assert "outputs/staging" not in SRC and "outputs/validation" not in SRC and "data/raw" not in SRC


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (v REAL)")
    return conn


@pytest.mark.parametrize("values,p", [
    ([1, 2, 3, 4, 5], 0.5), ([1, 2, 3, 4, 5], 0.90), ([10], 0.5), ([10], 0.90),
    ([3, 1, 4, 1, 5, 9, 2, 6], 0.5), ([3, 1, 4, 1, 5, 9, 2, 6], 0.90), ([1, 2], 0.5), ([1, 2], 0.90),
])
def test_the_window_function_percentile_sql_matches_numpy_style_linear_interpolation(values, p):
    from src.sql_verify import _percentile_sql
    conn = _fresh_db()
    conn.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
    got = conn.execute(_percentile_sql("t", "v", "1=1", p)).fetchone()[0]
    sv = sorted(values)
    pos = (len(sv) - 1) * p
    lo, hi = int(pos), min(int(pos) + 1, len(sv) - 1)
    want = sv[lo] + (pos - lo) * (sv[hi] - sv[lo])
    assert got == pytest.approx(want)


def test_median_p50_agrees_with_the_statistics_module_on_odd_and_even_counts():
    from src.sql_verify import _percentile_sql
    for values in ([5, 1, 9, 3, 7], [5, 1, 9, 3]):
        conn = _fresh_db()
        conn.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
        got = conn.execute(_percentile_sql("t", "v", "1=1", 0.5)).fetchone()[0]
        assert got == pytest.approx(statistics.median(values))


def test_the_where_filter_is_applied_before_ranking():
    from src.sql_verify import _percentile_sql
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (v REAL, keep INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(100, 0), (1, 1), (2, 1), (3, 1)])
    got = conn.execute(_percentile_sql("t", "v", "keep = 1", 0.5)).fetchone()[0]
    assert got == pytest.approx(2.0), "the excluded row (100) must not affect the ranking or the result"


@pytest.fixture(scope="module")
def sql_result():
    conn = build_db(REPO / "outputs")
    return run(conn)


def test_sql_computed_m1_through_m5_match_the_approved_metrics_on_the_committed_outputs(sql_result):
    approved = approved_metrics(REPO / "outputs")
    assert sql_result.m1 == pytest.approx(float(approved["M1"]["value"]), abs=0)
    assert sql_result.m2 == pytest.approx(float(approved["M2"]["value"]), abs=0.05)
    assert sql_result.m3 == int(float(approved["M3"]["value"]))
    assert sql_result.m4 == pytest.approx(float(approved["M4"]["value"]), abs=0)
    assert round(sql_result.m5, 4) == pytest.approx(round(float(approved["M5"]["value"]), 4), abs=0.005)
    assert sql_result.m5_numerator == int(float(approved["M5"]["numerator"]))
    assert sql_result.m5_denominator == int(float(approved["M5"]["denominator"]))


def test_the_independent_sql_join_against_fact_weather_reproduces_the_weather_coverage_count(sql_result):
    """A real JOIN on (fmisid, obs_time_utc) against fact_weather, not the weather_matched flag the model itself wrote,
    still finds every core-ready registered-export session - proving the join key documented in the schema actually works."""
    assert sql_result.weather_join_matches == sql_result.m3


def test_main_prints_pass_and_exits_0_on_the_real_committed_outputs(capsys):
    assert main(["--out", str(REPO / "outputs")]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "FAIL" not in out and "all SQL-computed values match" in out


def test_main_fails_loudly_when_a_metric_is_tampered(tmp_path):
    """The verification must never quietly agree with a wrong number: tamper metrics.csv (not the canonical tables)
    and the SQL-computed value must disagree with it."""
    out = tmp_path / "outputs"
    (out / "model").mkdir(parents=True)
    (out / "metrics").mkdir(parents=True)
    for name in ("fact_dining_session.csv", "fact_weather.csv"):
        (out / "model" / name).write_bytes((REPO / "outputs" / "model" / name).read_bytes())
    with (REPO / "outputs" / "metrics" / "metrics.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)
    for r in rows:
        if r["metric_id"] == "M1":
            r["value"] = "1.0"
    with (out / "metrics" / "metrics.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    assert main(["--out", str(out)]) == 1


def test_the_database_is_built_only_from_the_two_named_canonical_files(tmp_path):
    """build_db must not silently pick up any other file; deleting fact_weather.csv must make it fail to build, not fall back to something else."""
    out = tmp_path / "outputs"
    (out / "model").mkdir(parents=True)
    (out / "model" / "fact_dining_session.csv").write_bytes((REPO / "outputs" / "model" / "fact_dining_session.csv").read_bytes())
    with pytest.raises(FileNotFoundError):
        build_db(out)
