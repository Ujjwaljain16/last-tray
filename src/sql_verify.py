"""Independent SQL verification of the approved metrics.

The pipeline computes M1-M5 in pandas (`src/metrics/`). This module is a second, independent computation of the
same numbers, written in real SQL against a real relational database (SQLite), loaded only from the committed
canonical tables (`outputs/model/fact_dining_session.csv`, `fact_weather.csv`) - never from raw or staging data.

It exists to demonstrate, and to prove, that the approved values are not an artifact of one code path: an
unrelated query engine, given the same canonical rows, reaches the same answer. This mirrors the project's
existing pattern of independent cross-checks (the canonical model's own reconstruction of the selected weight
against validation's working value, D50) rather than adding a new production metric.

SQLite has no built-in MEDIAN or PERCENTILE function, so the linear-interpolation percentile (the same method
pandas' `quantile()` uses, R type 7) is expressed as a window-function query: rank the population, take the two
rows either side of the fractional position, and interpolate between them in SQL. No Python does the arithmetic.

Run:  python -m src.sql_verify [--out outputs]
Exit: 0 if every SQL-computed value matches outputs/metrics/metrics.csv exactly (within the same tolerances the
metric contract already declares); 1 and a printed diff otherwise. Never adjusts a value to make it agree.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

SESSION_COLUMNS = ("session_key", "session_id", "population", "core_ready", "derived_selected_meal_weight_g",
                   "distinct_component_count", "weather_matched", "weather_hour_utc", "weather_fmisid")
WEATHER_COLUMNS = ("fmisid", "obs_time_utc")


def _bool(s: str) -> int:
    return 1 if s == "true" else 0


def build_db(out_dir: Path) -> sqlite3.Connection:
    """Loads the two committed canonical CSVs into an in-memory SQLite database. Read-only inputs; nothing here writes to outputs/."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE fact_dining_session (
        session_key TEXT PRIMARY KEY, session_id TEXT, population TEXT, core_ready INTEGER,
        derived_selected_meal_weight_g INTEGER, distinct_component_count INTEGER,
        weather_matched INTEGER, weather_hour_utc TEXT, weather_fmisid TEXT)""")
    conn.execute("CREATE TABLE fact_weather (fmisid TEXT, obs_time_utc TEXT, PRIMARY KEY (fmisid, obs_time_utc))")

    with (out_dir / "model" / "fact_dining_session.csv").open(newline="", encoding="utf-8") as fh:
        rows = []
        for r in csv.DictReader(fh):
            w = r["derived_selected_meal_weight_g"]
            rows.append((r["session_key"], r["session_id"], r["population"], _bool(r["core_ready"]),
                        int(w) if w else None, int(r["distinct_component_count"]) if r["distinct_component_count"] else None,
                        _bool(r["weather_matched"]), r["weather_hour_utc"] or None, r["weather_fmisid"] or None))
    conn.executemany(f"INSERT INTO fact_dining_session VALUES ({','.join('?' * len(SESSION_COLUMNS))})", rows)

    with (out_dir / "model" / "fact_weather.csv").open(newline="", encoding="utf-8") as fh:
        wrows = [(r["fmisid"], r["obs_time_utc"]) for r in csv.DictReader(fh)]
    conn.executemany("INSERT OR IGNORE INTO fact_weather VALUES (?, ?)", wrows)

    conn.commit()
    return conn


def _percentile_sql(table: str, value_col: str, where: str, p: float) -> str:
    """A real SQL query for the linear-interpolation percentile (numpy/pandas default, R type 7).

    Ranks the filtered population with a window function, then a self-join on the ordered rows either side of
    the fractional position `(n - 1) * p` computes the interpolated value - entirely in SQL, no Python arithmetic
    on the row values themselves.
    """
    return f"""
    WITH pop AS (SELECT {value_col} AS v FROM {table} WHERE {where}),
         n   AS (SELECT COUNT(*) AS c FROM pop),
         h   AS (SELECT c, (c - 1) * {p} AS h, CAST((c - 1) * {p} AS INTEGER) AS lo_idx FROM n),
         ordered AS (SELECT v, ROW_NUMBER() OVER (ORDER BY v) - 1 AS idx FROM pop)
    SELECT lo.v + (h.h - h.lo_idx) * (hi.v - lo.v) AS result
    FROM h JOIN ordered lo ON lo.idx = h.lo_idx
           JOIN ordered hi ON hi.idx = MIN(h.lo_idx + 1, h.c - 1)
    """


REGISTERED_CORE_READY = "population = 'registered_export' AND core_ready = 1"


@dataclass
class SqlResult:
    m1: float
    m2: float
    m3: int
    m4: float
    m5_numerator: int
    m5_denominator: int
    m5: float
    weather_join_matches: int   # a real JOIN against fact_weather, independent of the weather_matched flag the model itself set


def run(conn: sqlite3.Connection) -> SqlResult:
    m1 = conn.execute(_percentile_sql("fact_dining_session", "derived_selected_meal_weight_g", REGISTERED_CORE_READY, 0.5)).fetchone()[0]
    m2 = conn.execute(_percentile_sql("fact_dining_session", "derived_selected_meal_weight_g", REGISTERED_CORE_READY, 0.90)).fetchone()[0]
    m3 = conn.execute(f"SELECT COUNT(*) FROM fact_dining_session WHERE {REGISTERED_CORE_READY}").fetchone()[0]
    m4 = conn.execute(_percentile_sql("fact_dining_session", "distinct_component_count", REGISTERED_CORE_READY, 0.5)).fetchone()[0]
    num, den = conn.execute(
        "SELECT SUM(CASE WHEN core_ready = 1 THEN 1 ELSE 0 END), COUNT(*) FROM fact_dining_session WHERE population = 'registered_export'"
    ).fetchone()
    # An explicit JOIN to fact_weather on the documented key (fmisid, hour), independent of the weather_matched
    # flag the canonical model itself set - proves the join is reproducible from the two tables alone.
    joined = conn.execute(f"""
        SELECT COUNT(*) FROM fact_dining_session s
        JOIN fact_weather w ON w.fmisid = s.weather_fmisid AND w.obs_time_utc = s.weather_hour_utc
        WHERE {REGISTERED_CORE_READY}
    """).fetchone()[0]
    return SqlResult(m1=m1, m2=m2, m3=m3, m4=m4, m5_numerator=num, m5_denominator=den, m5=100 * num / den, weather_join_matches=joined)


def approved_metrics(out_dir: Path) -> dict[str, dict[str, str]]:
    with (out_dir / "metrics" / "metrics.csv").open(newline="", encoding="utf-8") as fh:
        return {r["metric_id"]: r for r in csv.DictReader(fh)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.sql_verify",
                                description="Recompute M1-M5 and the weather join in real SQL, against the committed canonical tables only, "
                                "and check the result against outputs/metrics/metrics.csv.")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "outputs")
    args = p.parse_args(argv)

    conn = build_db(args.out)
    r = run(conn)
    approved = approved_metrics(args.out)

    checks: list[tuple[str, Any, Any, float]] = [
        ("M1", r.m1, float(approved["M1"]["value"]), 0.0),
        ("M2", r.m2, float(approved["M2"]["value"]), 0.05),
        ("M3", r.m3, int(float(approved["M3"]["value"])), 0),
        ("M4", r.m4, float(approved["M4"]["value"]), 0.0),
        ("M5", round(r.m5, 6), round(float(approved["M5"]["value"]), 6), 0.005),
        ("S1 (weather join, independent JOIN)", r.weather_join_matches, r.m3, 0),   # every core-ready session should join, same count as M3
    ]
    def fmt(v: Any) -> str:
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    print(f"{'metric':<32}{'sql':<18}{'approved':<18}status")
    ok = True
    for name, got, want, tol in checks:
        passed = abs(got - want) <= tol if tol or isinstance(got, float) else got == want
        ok = ok and passed
        print(f"{name:<32}{fmt(got):<18}{fmt(want):<18}{'PASS' if passed else 'FAIL'}")
    print(f"\n{'all SQL-computed values match the approved metrics' if ok else 'MISMATCH: see above'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
