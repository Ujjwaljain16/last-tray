"""Profile report sections A-D: schema drift, column profile, population profile, timestamp/timezone validation."""
import json

import numpy as np
import pandas as pd

from exploration_common import OUT, UTC_FILES, load_raw, parse, sessions, crossover_ids, exact_dup_mask, q

OUT.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
ev, meta = load_raw()
e = parse(ev)
R = {}  # key numbers for the report

# ---- A. schema drift ---------------------------------------------------------------------------
sd = meta.copy()
sd["ts_format_weighing"] = [",".join(sorted(e[e.source_file == f].ts_format.unique())) for f in sd.file]
sd["ts_format_identification"] = [",".join(sorted(e[e.source_file == f].user_identification_time
                                  .str.replace(r"\d", "9", regex=True).unique())) for f in sd.file]
sd["first_event"] = [e[e.source_file == f].t_naive.min() for f in sd.file]
sd["last_event"] = [e[e.source_file == f].t_naive.max() for f in sd.file]
sd["sessions"] = [e[e.source_file == f].session_id.nunique() for f in sd.file]
sd["exact_dup_rows"] = [int(exact_dup_mask(e)[e.source_file == f].sum()) for f in sd.file]
sd["fname_pattern"] = sd.file.str.replace(r"\d", "9", regex=True)
sd.drop(columns=["header"]).to_csv(OUT / "schema_drift_by_file.csv", index=False)
print("== A. schema drift ==")
print(sd[["file", "rows", "columns_named", "columns_blank", "blank_cells_nonempty", "has_weighting_type",
          "ts_format_weighing", "ts_format_identification", "bom", "crlf"]].to_string(index=False))
print("distinct headers:", sd.header.nunique(), "| files without weighting_type:", int((~sd.has_weighting_type).sum()),
      "| weighting_type values:", e.weighting_type.dropna().unique().tolist())
print("filename patterns:", sd.fname_pattern.unique().tolist())
print("column ORDER identical in files that have it?",
      sd[sd.has_weighting_type].header.nunique() == 1, "| in files without it?", sd[~sd.has_weighting_type].header.nunique() == 1)
R["schema"] = {"files": len(sd), "distinct_headers": int(sd.header.nunique()),
               "files_without_weighting_type": int((~sd.has_weighting_type).sum()),
               "rows_without_weighting_type": int(sd[~sd.has_weighting_type].rows.sum()),
               "blank_cells_nonempty_total": int(sd.blank_cells_nonempty.sum())}

# ---- B. column profile (tidy) ---------------------------------------------------------------------
rows = []
for scope, d in [("all", e)] + [(p, e[e.population == p]) for p in sorted(e.population.unique())]:
    for c in ["session_id", "weighing_event_time", "weighting_type", "scale_identifier", "weight_of_a_component",
              "component_name", "tray_id", "user_identification_time"]:
        s = d[c]
        empty = int(s.isna().sum() + (s == "").sum())
        rows.append((scope, c, "rows", len(d)))
        rows.append((scope, c, "null_or_empty", empty))
        rows.append((scope, c, "null_pct", round(100 * empty / len(d), 3)))
        rows.append((scope, c, "distinct", int(s.nunique())))
    w = d.w
    for k, v in q(w).items():
        rows.append((scope, "weight_of_a_component", k, round(v, 2)))
    rows.append((scope, "weight_of_a_component", "nonnumeric", int(w.isna().sum())))
    rows.append((scope, "weight_of_a_component", "le_0", int((w <= 0).sum())))
    rows.append((scope, "weighing_event_time", "min", str(d.t_naive.min())))
    rows.append((scope, "weighing_event_time", "max", str(d.t_naive.max())))
    rows.append((scope, "component_name", "with_edge_whitespace", int((d.component_name != d.component_name.str.strip()).sum())))
pd.DataFrame(rows, columns=["scope", "column", "metric", "value"]).to_csv(
    OUT.parent / "validation" / "profile_summary.csv", index=False)
print("\n== B. profile_summary.csv written:", len(rows), "rows")

# ---- C. population profile ------------------------------------------------------------------------
s = sessions(e)
xo = crossover_ids(e)
print("\n== C. population profile ==")
print("crossover ids:", sorted(xo))
core = s[~s.crossover]
def prof(d):
    return pd.Series({
        "sessions": len(d), "events": int(d.component_weighing_event_count.sum()),
        "events_per_session_mean": d.component_weighing_event_count.mean(),
        "events_per_session_median": d.component_weighing_event_count.median(),
        "single_event_sessions": int((d.component_weighing_event_count == 1).sum()),
        "single_event_pct": 100 * (d.component_weighing_event_count == 1).mean(),
        "with_hot_scale_pct": 100 * d.has_hot.mean(),
        "weight_p10": d.derived_selected_meal_weight_g.quantile(.1), "weight_median": d.derived_selected_meal_weight_g.median(),
        "weight_p90": d.derived_selected_meal_weight_g.quantile(.9), "weight_max": d.derived_selected_meal_weight_g.max(),
        "under_50g_pct": 100 * (d.derived_selected_meal_weight_g < 50).mean(),
        "distinct_components_median": d.distinct_component_count.median(),
        "span_s_median": d.session_span_s.median(), "span_s_p99": d.session_span_s.quantile(.99),
        "service_days": d.service_date.nunique(), "trays": d.tray_id.nunique(),
    })
pp = core.groupby("population").apply(prof, include_groups=False).T
pp["note"] = "crossover sessions excluded from both"
print(pp.round(2))
pp.round(3).to_csv(OUT / "population_profile.csv")
# same statistics including the crossover sessions once per population, for comparability with the initial review
print("initial-review-comparable (crossover included) sessions per pop:", s.groupby("population").size().to_dict())
R["population"] = pp.round(3).drop(columns="note").to_dict()

# ---- D. timestamp / timezone validation ------------------------------------------------------------
print("\n== D. timestamp / timezone ==")
def first_event_hour(d):
    g = d.groupby(d.t_naive.dt.date).t_naive.min()
    return (g.dt.hour + g.dt.minute / 60)
tz_rows = []
for f, d in e.groupby("source_file"):
    fh = first_event_hour(d)
    fh_local = first_event_hour(d.assign(t_naive=d.t))
    tz_rows.append({"file": f, "days": fh.size, "median_first_event_hour_raw": round(fh.median(), 2),
                    "median_first_event_hour_after_rule": round(fh_local.median(), 2),
                    "events_before_10h_raw": int((d.t_naive.dt.hour < 10).sum()),
                    "events_before_10h_after_rule": int((d.t.dt.hour < 10).sum()),
                    "latest_event_raw": str(d.t_naive.dt.time.max()),
                    "T07_suspect_raw": not (10.0 <= fh.median() < 11.0),
                    "T07_suspect_after_rule": not (10.0 <= fh_local.median() < 11.0),
                    "override_registered": f in UTC_FILES})
tz = pd.DataFrame(tz_rows)
tz.to_csv(OUT / "timezone_validation_by_file.csv", index=False)
print(tz.to_string(index=False))

dot = e[e.source_file.isin(UTC_FILES)]
ref = e[(e.population == "registered_export") & ~e.source_file.isin(UTC_FILES)]
def hour_dist(d, off):
    return (d.t_naive + pd.Timedelta(hours=off)).dt.hour.value_counts(normalize=True)
def l1(p, r):
    i = p.index.union(r.index)
    return float((p.reindex(i, fill_value=0) - r.reindex(i, fill_value=0)).abs().sum())
scan = [(off, round(l1(hour_dist(dot, off), ref.t.dt.hour.value_counts(normalize=True)), 3)) for off in range(-6, 7)]
scan = pd.DataFrame(scan, columns=["offset_h", "L1_distance_to_other_registered_export_files"])
scan.to_csv(OUT / "timezone_offset_scan.csv", index=False)
print(scan.T.to_string(header=False))
best = scan.loc[scan.iloc[:, 1].idxmin()]
print("best offset:", best.tolist())
# sessions seen in both exports: exact offset per event
both = e[e.session_id.isin(xo)]
cmp_ = []
for sid in sorted(xo):
    a = both[(both.session_id == sid) & (both.population == "registered_export")].sort_values("t_naive")
    b = both[(both.session_id == sid) & (both.population == "non_registered_export")].sort_values("t_naive")
    for (_, ra), (_, rb) in zip(a.iterrows(), b.iterrows()):
        cmp_.append({"session_id": sid, "scale": ra.scale_identifier == rb.scale_identifier, "weight_equal": ra.w == rb.w,
                     "name_equal_exact": ra.component_name == rb.component_name,
                     "name_equal_casefold": ra.name_norm == rb.name_norm,
                     "name_registered_export": ra.component_name, "name_non_registered_export": rb.component_name,
                     "dt_s(non_reg - reg)": (rb.t_naive - ra.t_naive).total_seconds(),
                     "scale_id": ra.scale_identifier, "weight_g": ra.w})
cmp_ = pd.DataFrame(cmp_)
cmp_.to_csv(OUT / "crossover_session_event_comparison.csv", index=False)
print("\ncrossover event-by-event:")
print(cmp_.to_string(index=False))
# tray overlap test, offset 0 vs +3h (weak test, reported as such)
st = s[~s.crossover]
def overlaps(off):
    d = st[st.source_file.isin(UTC_FILES)].copy()
    d["a"] = d.first_weighing_at - (pd.Timedelta(hours=3) if off == 0 else pd.Timedelta(0))
    d["b"] = d.identified_at - (pd.Timedelta(hours=3) if off == 0 else pd.Timedelta(0))
    o = st[~st.source_file.isin(UTC_FILES)]
    m = d.merge(o, on="tray_id", suffixes=("_d", "_o"))
    return int(((m.a <= m.identified_at_o) & (m.first_weighing_at_o <= m.b)).sum()), len(m)
R["tz"] = {"scan_best_offset": int(best.iloc[0]), "L1_at_0": float(scan[scan.offset_h == 0].iloc[0, 1]),
           "L1_at_3": float(scan[scan.offset_h == 3].iloc[0, 1]),
           "crossover_events_compared": len(cmp_),
           "crossover_offsets_s": sorted(set(cmp_["dt_s(non_reg - reg)"].tolist()))}
json.dump(R, open(OUT / "results_a.json", "w"), indent=1, default=str)
e.to_pickle(OUT / "_events.pkl")
s.to_pickle(OUT / "_sessions.pkl")
print("\nsaved.")
