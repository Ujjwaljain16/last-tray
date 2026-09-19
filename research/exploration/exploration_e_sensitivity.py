"""Profile report section N: sensitivity analysis. Writes outputs/validation/sensitivity_analysis.csv.

Purpose: show that assumptions were TESTED, not selected for favourable KPI results. Every scenario recomputes
M1-M5 under an alternative assumption; the baseline is scenario S00. Diagnostic thresholds are derived from the
observed data structure; they are not claims of physical impossibility.
"""
import glob
import re

import numpy as np
import pandas as pd

from exploration_common import OUT, ROOT, UTC_FILES, exact_dup_mask

pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)
REG, NON = "registered_export", "non_registered_export"
e = pd.read_pickle(OUT / "_events.pkl")
s = pd.read_pickle(OUT / "_sessions.pkl")
e["dup"] = exact_dup_mask(e)
v = pd.read_csv(ROOT / "outputs" / "validation" / "validation_issues.csv")

TH = dict(hour_lo=9, hour_hi=15, low_volume=30)

# ---- weather from the preserved raw XML ---------------------------------------------------------
rows = []
for f in sorted(glob.glob(str(ROOT / "data/raw/weather/fmi_100949_*.xml"))):
    x = open(f, encoding="utf-8").read()
    rows += re.findall(r"<BsWfs:Time>([^<]*)</BsWfs:Time>\s*<BsWfs:ParameterName>([^<]*)</BsWfs:ParameterName>\s*<BsWfs:ParameterValue>([^<]*)<", x)
wx = pd.DataFrame(rows, columns=["t", "p", "v"])
wx["v"] = pd.to_numeric(wx.v, errors="coerce")
wx = wx.drop_duplicates(["t", "p"]).pivot(index="t", columns="p", values="v")
wx.index = pd.to_datetime(wx.index, utc=True)

# ---- warn flags at session level and event level (registered-export) ------------------------------
reg = s[s.population == REG].copy()
xo = set(s[s.crossover].session_id)
sess_warn = set(v[(v.entity_type == "session") & (v.severity == "WARN") & (v.population == REG)].entity_id.str.split("|").str[0])
ev = v[(v.entity_type == "event") & (v.severity == "WARN") & (v.population == REG)].copy()
ev[["source_file", "row"]] = ev.entity_id.str.split("#", expand=True)
ev["row"] = ev.row.astype(int)
ev = ev.merge(e[["source_file", "source_row_number", "session_id"]], left_on=["source_file", "row"],
              right_on=["source_file", "source_row_number"])
event_warn = set(ev.session_id)
reg["warn_session"] = reg.session_id.isin(sess_warn)
reg["warn_event"] = reg.session_id.isin(event_warn)
reg["warn_any"] = reg.warn_session | reg.warn_event
reg["crossover"] = reg.session_id.isin(xo)

# irregular days (registered-export regime vs weekday baseline)
day = s[~s.crossover].groupby(["service_date", "population"]).size().unstack()
wd = pd.Series(pd.to_datetime(day.index).day_name(), index=day.index)
exp = wd.map(lambda d: "high" if d in ("Monday", "Tuesday", "Wednesday") else "low")
obs = day[REG].map(lambda n: "high" if n >= TH["low_volume"] else "low")
irregular_days = set(day.index[obs != exp])
low_days = set(day.index[day[REG] < TH["low_volume"]])
nov16_20 = {pd.Timestamp(d).date() for d in pd.date_range("2020-11-16", "2020-11-20")}

ELIGIBLE = len(reg)  # 1,699: every registered-export session ID in the source, BEFORE any removal
print("eligible registered-export session IDs (fixed M5 / warn-free denominator):", ELIGIBLE)


def metrics(d, scenario_pop_label, m5_num=None, m5_den=None, m4col="distinct_component_count", wcol="derived_selected_meal_weight_g"):
    w = d[wcol]
    return dict(population_definition=scenario_pop_label, m3_observed_valid_sessions=len(d), m1_median_g=w.median(),
                m2_p90_g=w.quantile(0.9), m4_median_components=d[m4col].median(), m5_numerator=m5_num, m5_denominator=m5_den)


base = reg[(~reg.crossover)]
out = []


def add(sid, grp, desc, d, pop, m5_num, m5_den=ELIGIBLE, extra=None, **kw):
    r = dict(scenario_id=sid, group=grp, description=desc)
    r.update(metrics(d, pop, m5_num, m5_den, **kw))
    r["m5_rate_pct"] = 100 * m5_num / m5_den if m5_num is not None else np.nan
    r["warn_free_rate_pct"] = np.nan
    r.update(extra or {})
    out.append(r)


core_n = len(base)
# S00 baseline
add("S00", "baseline", "Canonical: registered-export population, crossover quarantined, duplicates excluded from sums, +3h normalisation",
    base, "registered-export, eligible 1,699", core_n,
    extra=dict(warn_free_rate_pct=100 * (~base.warn_session).sum() / ELIGIBLE,
               note="canonical warn-free = no SESSION-level WARN (B04, B07, T04, T05, I06) over the fixed 1,699; "
                    "file-level (T07) and day-level (C02) flags excluded by design"))
out[-1]["warn_free_incl_event_level_pct"] = 100 * (~base.warn_any).sum() / ELIGIBLE   # diagnostic: also counts B02/I02 event-level WARNs

# crossover
r_all = reg
add("S01", "crossover", "Include both crossover sessions (session2266, session3222) as if unquarantined",
    r_all, "registered-export incl. 2 crossover sessions", len(r_all),
    extra=dict(note="M5 would be 100% only because the quarantine is lifted; NOT a valid way to report readiness"))
add("S02", "crossover", "Include only session2266 (exact cross-export duplicate)", reg[reg.session_id != "session3222"],
    "registered-export + session2266", core_n + 1, extra=dict(note="exact duplicate: adds a second copy of the same tray pass to the population"))
add("S03", "crossover", "Include only session3222 (version conflict)", reg[reg.session_id != "session2266"],
    "registered-export + session3222", core_n + 1, extra=dict(note="registered-export version (UTC-file version, normalised +3h)"))

# 2097 g
d = base.copy()
sid = e[e.w == e.w.max()].session_id.iloc[0]
d1 = d[d.session_id != sid]
add("S04", "outlier", "Remove the 2,097 g SESSION (session2104)", d1, "registered-export minus 1 session", len(d1),
    extra=dict(note="removal is analytical only: the session stays in the canonical population"))
d2 = d.copy()
d2.loc[d2.session_id == sid, "derived_selected_meal_weight_g"] -= 2097
add("S05", "outlier", "Remove only the 2,097 g EVENT from session2104 (session kept)", d2, "registered-export, one event dropped", len(d2))
lo, hi = base.derived_selected_meal_weight_g.quantile([0.005, 0.995])
d3 = base[base.derived_selected_meal_weight_g.between(lo, hi)]
add("S06", "outlier", f"Exclude sessions outside the data percentiles P0.5-P99.5 ({lo:.0f}-{hi:.0f} g) instead of the fixed [50, 2200] g",
    d3, "registered-export within P0.5-P99.5", len(d3))
d4 = base[base.derived_selected_meal_weight_g.between(50, 2200)]
add("S07", "outlier", "Exclude sessions outside the approved [50, 2,200] g bounds (B07)", d4, "registered-export within [50, 2200] g", len(d4))
d5 = base[base.component_weighing_event_count > 1]
add("S08", "outlier", "Exclude single-event sessions (B04)", d5, "registered-export, event count > 1", len(d5))
d6 = base[base.session_span_s <= 600]
add("S09", "outlier", "Exclude sessions with span > 600 s (T05)", d6, "registered-export, span <= 600 s", len(d6))
d7 = base[~base.warn_any]
add("S10", "outlier", "Exclude every session with any WARN (session or event level)", d7, "registered-export, warn-free", len(d7))

# timezone hypotheses for the override file
ovr = base.source_file.isin(UTC_FILES)
ovr_events = e[e.source_file.isin(UTC_FILES) & ~e.dup]
t_base = base.copy()
for h in [0, 1, 2, 3, 4]:
    # events of the override file shifted by h hours; T03 (09:00 <= hour < 15:00) applied at event level
    ee = ovr_events.copy()
    ee["local"] = ee.t_naive + pd.Timedelta(hours=h)
    bad = ee[(ee.local.dt.hour < TH["hour_lo"]) | (ee.local.dt.hour >= TH["hour_hi"])]
    bad_sessions = set(bad.session_id)
    ok = base[~base.session_id.isin(bad_sessions)]
    # weather consequence relative to the +3h decision
    o = base[ovr].copy()
    loc_h = (o.first_weighing_at - pd.Timedelta(hours=3) + pd.Timedelta(hours=h))
    utc_h = loc_h.dt.tz_localize("Europe/Helsinki").dt.tz_convert("UTC").dt.ceil("h")
    utc_b = o.first_weighing_at.dt.tz_localize("Europe/Helsinki").dt.tz_convert("UTC").dt.ceil("h")
    jh, jb = wx.reindex(pd.DatetimeIndex(utc_h)), wx.reindex(pd.DatetimeIndex(utc_b))
    rain = (jh["r_1h"] > 0).sum() / max(jh["r_1h"].notna().sum(), 1) * 100
    extra = dict(weather_hour_changed_sessions=int((utc_h.values != utc_b.values).sum()),
                 mean_abs_t2m_diff_c=float(np.nanmean(np.abs(jh.t2m.values - jb.t2m.values))),
                 rainy_hour_share_pct_override_file=float(rain),
                 t03_violating_sessions=len(bad_sessions & set(base.session_id)),
                 note=("BASELINE assumption" if h == 3 else
                       ("treat file as local time: T03 (service hours) quarantines every session in the file, so M1-M5 fall; shows why T07/T03 catch the shift" if h == 0
                        else "alternative offset tested; weights unaffected")))
    add(f"TZ{h}", "timezone", f"Override file shifted by +{h}h (T03 applied at event level)", ok, f"registered-export, +{h}h", len(ok), extra=extra)

# volume diagnostics (flag-only in the pipeline; here only as tests)
d8 = base[~base.service_date.isin(irregular_days)]
add("S20", "volume", f"Exclude the {len(irregular_days)} volume-irregularity days (diagnostic test only; the flag NEVER excludes in the pipeline)", d8,
    "registered-export minus irregular days", len(d8))
d9 = base[~base.service_date.isin(nov16_20)]
add("S21", "volume", "Exclude 2020-11-16..20 (diagnostic test only)", d9, "registered-export minus Nov 16-20", len(d9))
d10 = base[~base.service_date.isin(low_days)]
add("S22", "volume", f"Exclude the {len(low_days)} low-observed-volume days (< 30 sessions) (diagnostic test only)", d10,
    "registered-export on high-volume days only", len(d10))
d11 = base[pd.to_datetime(base.service_date) >= pd.Timestamp("2020-10-19")]
add("S23", "volume", "Exclude the first two weeks (2020-10-05..16, the +3h file period and cross-export name disagreement)", d11,
    "registered-export from 2020-10-19", len(d11), extra=dict(note="period effect on M2, not a timezone effect"))

# definitions
for sid_, col, txt in [("S30", "distinct_raw_names", "M4 with raw component names"), ("S31", "distinct_scales", "M4 counted as distinct scales"),
                       ("S32", "component_weighing_event_count", "M4 counted as weighing events per session")]:
    add(sid_, "definition", txt, base, "registered-export", core_n, m4col=col)
# duplicates included in sums
dupsum = e[(e.population == REG) & ~e.session_id.isin(xo)].groupby("session_id").w.sum()
dd = base.copy()
dd["derived_selected_meal_weight_g"] = dd.session_id.map(dupsum)
add("S33", "definition", "Do NOT exclude the exact duplicate row from sums", dd, "registered-export, duplicates summed", core_n,
    extra=dict(note="I02 duplicate would double-count 67 g in session1274"))
# population contrast (diagnostic only)
non = s[(s.population == NON) & ~s.crossover]
add("S40", "population", "DIAGNOSTIC: non-registered-export population (never a KPI source)", non, "non-registered-export (diagnostic)", None, None)

sa = pd.DataFrame(out)
b = sa.loc[sa.scenario_id == "S00"].iloc[0]
sa["d_m1_g"] = sa.m1_median_g - b.m1_median_g
sa["d_m2_g"] = sa.m2_p90_g - b.m2_p90_g
sa["d_m3_sessions"] = sa.m3_observed_valid_sessions - b.m3_observed_valid_sessions
sa["d_m4"] = sa.m4_median_components - b.m4_median_components
sa["d_m5_pp"] = sa.m5_rate_pct - b.m5_rate_pct
# materiality: a diagnostic convention, not a physical claim
# Diagnostic convention (NOT a claim of practical or physical significance): visible relative to the baseline.
sa["material_change"] = ((sa.d_m1_g.abs() >= 10) | (sa.d_m2_g.abs() >= 25) | (sa.d_m4.abs() > 0)).where(sa.group != "population", np.nan)
# M5 is only meaningful where the readiness definition itself is being varied (baseline, crossover, timezone).
na_m5 = ~sa.group.isin(["baseline", "crossover", "timezone"])
for c in ["m5_numerator", "m5_denominator", "m5_rate_pct", "d_m5_pp"]:
    sa.loc[na_m5, c] = np.nan
sa.loc[na_m5 & (sa.group != "population"), "note"] = sa.loc[na_m5 & (sa.group != "population"), "note"].fillna("analytic exclusion: M5 not redefined; M3 shows the remaining sessions")
sa.loc[sa.scenario_id == "S00", "material_change"] = False
cols = ["scenario_id", "group", "description", "population_definition", "m1_median_g", "m2_p90_g", "m3_observed_valid_sessions", "m4_median_components",
        "m5_numerator", "m5_denominator", "m5_rate_pct", "warn_free_rate_pct", "warn_free_incl_event_level_pct", "d_m1_g", "d_m2_g", "d_m3_sessions", "d_m4", "d_m5_pp",
        "material_change", "t03_violating_sessions", "weather_hour_changed_sessions", "mean_abs_t2m_diff_c", "rainy_hour_share_pct_override_file", "note"]
for c in cols:
    if c not in sa:
        sa[c] = np.nan
sa = sa[cols].round(3)
sa.to_csv(ROOT / "outputs" / "validation" / "sensitivity_analysis.csv", index=False)
print(sa[["scenario_id", "group", "m1_median_g", "m2_p90_g", "m3_observed_valid_sessions", "m4_median_components", "m5_rate_pct", "d_m1_g", "d_m2_g", "material_change"]].to_string(index=False))
print()
print(sa[sa.group == "timezone"][["scenario_id", "t03_violating_sessions", "weather_hour_changed_sessions", "mean_abs_t2m_diff_c", "rainy_hour_share_pct_override_file"]].to_string(index=False))
print("\nbaseline warn-free, canonical (session-level):", round(b.warn_free_rate_pct, 3), "| incl. event-level WARNs (diagnostic):", round(out[0]["warn_free_incl_event_level_pct"], 3))
print("irregular days:", sorted(map(str, irregular_days)), "| low days:", len(low_days))
