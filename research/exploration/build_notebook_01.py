"""Builds notebooks/01_source_exploration.ipynb with real outputs embedded (no jupyter needed). HISTORICAL EVIDENCE tooling.

Each code cell is executed here, its stdout (and any matplotlib figure) is stored as the cell output.
Run after the reference_*.py scripts:  python research/exploration/build_notebook_01.py
"""
import base64
import contextlib
import io
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parents[2] / "notebooks"  # the notebook lives in notebooks/; its cells use ../outputs/ paths
os.chdir(HERE)

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)})


ns = {}


def code(text):
    text = text.strip("\n")
    figs = []
    orig_show = plt.show

    def fake_show(*a, **k):
        buf = io.BytesIO()
        plt.gcf().savefig(buf, format="png", dpi=110, bbox_inches="tight")
        figs.append(base64.b64encode(buf.getvalue()).decode())
        plt.close("all")

    plt.show = fake_show
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(text, "<cell>", "exec"), ns)
    plt.show = orig_show
    outputs = []
    if out.getvalue():
        outputs.append({"output_type": "stream", "name": "stdout", "text": out.getvalue().splitlines(True)})
    for f in figs:
        outputs.append({"output_type": "display_data", "metadata": {}, "data": {"image/png": f, "text/plain": ["<Figure>"]}})
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": len([c for c in cells if c["cell_type"] == "code"]) + 1,
                  "source": text.splitlines(True), "outputs": outputs})


md("""
# 01. Source exploration: what did the archive actually contain?

We did not begin with a clean session table. We began with **12,284 component-level weighing events** in 11 CSV files and had to establish what a session meant, keep two populations apart, investigate a timezone discrepancy, cope with schema drift and unstable component names, and decide what the evidence could legitimately support.

**Labels.** "registered-export population" and "non-registered-export population" are **inherited from source filenames**. The public documentation reviewed for this project does not define them, so they are population labels only, not customer-registration status.

Every table below is loaded from `outputs/exploration/` (written by the exploration scripts `reference_*.py`). Nothing here is cleaned or modified; nothing is dropped.
""")
code("""
import pandas as pd
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)
P = "../outputs/exploration/"
schema = pd.read_csv(P + "schema_drift_by_file.csv")
pop = pd.read_csv(P + "population_profile.csv", index_col=0)
tz = pd.read_csv(P + "timezone_validation_by_file.csv")
scan = pd.read_csv(P + "timezone_offset_scan.csv")
cross = pd.read_csv(P + "crossover_session_event_comparison.csv")
m4 = pd.read_csv(P + "m4_definition_sensitivity.csv")
day = pd.read_csv(P + "daily_volume_by_population.csv")
comp = pd.read_csv(P + "registered_export_daily_composition.csv")
kpi = pd.read_csv(P + "kpi_sensitivity_preview.csv")
issues = pd.read_csv("../outputs/validation/validation_issues.csv")
print("events in the archive: 12,284 | files:", len(schema), "| session IDs: 3,343")
""")
md("""
## 1. Schema drift
Seven of eleven files have no `weighting_type` column, two timestamp formats appear (decided per **column**, because one file mixes them), and file order is not chronological. Pipeline consequence: parse by header name, sort by parsed time, never trust row order.
""")
code("""
print(schema[["file", "rows", "columns_named", "has_weighting_type", "ts_format_weighing", "ts_format_identification"]].to_string(index=False))
""")
md("""
## 2. The two populations behave differently
Crossover sessions are excluded from both columns. A 4 g tenth percentile is not a plausible plate, so the non-registered-export population is a diagnostic, not a KPI source. Note also the daily volume row: 2 to 107 sessions per day in one export, 36 to 75 in the other.
""")
code("""
print(pop.drop(columns="note").round(2).to_string())
""")
md("""
## 3. Timezone: evidence, not assumption
One file's first weighing of the day is at 07:30, against 10:30 in every other file. We scanned offsets from -6 h to +6 h. **+3 h is the strongest-supported normalisation decision based on cross-export consistency evidence; the source metadata does not explicitly confirm the timezone.**
""")
code("""
print(scan.round(3).T.to_string(header=False))
print()
print(tz[["file", "median_first_event_hour_raw", "median_first_event_hour_after_rule", "T07_suspect_raw", "T07_suspect_after_rule"]].to_string(index=False))
""")
md("""
## 4. The two crossover sessions
`session2266` is an exact duplicate across exports (0 s apart). `session3222` differs by exactly 10,800 s and 2 of 6 component names differ. Both are quarantined until the source owner says which record is authoritative.
""")
code("""
print(cross[["session_id", "scale_id", "weight_g", "name_registered_export", "name_non_registered_export", "dt_s(non_reg - reg)"]].to_string(index=False))
""")
md("""
## 5. Component names: what is stable, and what is not
Within a session the count of distinct components is the same under every identity definition (median 5). Across exports the names disagree in one window only, so we do **not** build an alias table.
""")
code("""
print(m4.to_string(index=False))
agree = pd.read_csv(P + "component_name_cross_export_agreement.csv")
print()
print(agree.groupby("day_in_override_file").agg(scale_days=("jaccard", "size"), identical=("identical", "mean"), disjoint=("disjoint", "mean")).round(3).rename(index={True: "2020-10-05..16", False: "all other days"}))
""")
md("""
## 6. Daily volume: registered-export volume is bimodal by weekday
Nov 16-20 is retained and flagged, not excluded and not called a data error: six days break the weekday pattern (Nov 2, 6, 16, 17, 18, 20), and the sessions on those days look ordinary.
""")
code("""
import numpy as np
import matplotlib.pyplot as plt
piv = day.pivot(index="service_date", columns="population", values="sessions")
wd = pd.to_datetime(piv.index).day_name()
fig, ax = plt.subplots(figsize=(11, 3.6))
x = np.arange(len(piv))
ax.bar(x - 0.2, piv["registered_export"].fillna(0), 0.4, label="registered-export population", color="#1d4ed8")
ax.bar(x + 0.2, piv["non_registered_export"].fillna(0), 0.4, label="non-registered-export population", color="#9ca3af")
irregular = ["2020-11-02", "2020-11-06", "2020-11-16", "2020-11-17", "2020-11-18", "2020-11-20"]
for i, d in enumerate(piv.index):
    if d in irregular:
        ax.annotate("!", (i - 0.2, piv["registered_export"].loc[d] + 1.5), ha="center", fontsize=11, fontweight="bold", color="#b91c1c")
ax.set_xticks(x); ax.set_xticklabels([f"{d[5:]}\\n{w[:2]}" for d, w in zip(piv.index, wd)], fontsize=6)
ax.set_ylabel("sessions per day"); ax.legend(frameon=False, fontsize=8); ax.set_title("Sessions per service day by population (crossover excluded; ! = volume irregularity)")
plt.tight_layout(); plt.show()
""")
code("""
print(comp.loc[comp["day"] >= "2020-11-09", ["day", "sessions", "events_per_session", "single_event_pct", "hot_pct", "median_weight"]].to_string(index=False))
""")
md("""
## 7. Findings expressed as validation issues
1,278 issues, no rows deleted. ERROR = identity conflicts only.
""")
code("""
print(issues.groupby(["rule_id", "severity", "population"]).size().unstack(fill_value=0).to_string())
""")
md("""
## 8. KPI sensitivity **preview** (not final evidence)
M1 stays within 499-505 g and M4 is 5 in every scenario. M2 is the sensitive one. The pipeline will compute the real KPIs.
""")
code("""
print(kpi[["scenario", "sessions", "M1_median_g", "M2_p90_g", "M4_median_components"]].to_string(index=False))
""")
md("""
## What comes next
Thresholds are documented in `docs/validation_rules.md`; the decisions taken from these findings are in `docs/decision_log.md`.
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
(HERE / "01_source_exploration.ipynb").write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("notebook cells:", len(cells))
