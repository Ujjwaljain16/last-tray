"""Profile report sections E-J: session diagnostics, component-name stability, span checks, daily volume,
Nov 16-20, the 2,097 g event, the single-event registered-export sessions."""
import json
from itertools import combinations

import numpy as np
import pandas as pd

from exploration_common import OUT, UTC_FILES, exact_dup_mask

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)
e = pd.read_pickle(OUT / "_events.pkl")
s = pd.read_pickle(OUT / "_sessions.pkl")
e["dup"] = exact_dup_mask(e)
xo = set(s[s.crossover].session_id)
ed = e[~e.dup]
REG, NON = "registered_export", "non_registered_export"
sr = s[(s.population == REG) & ~s.crossover]      # primary candidate sessions
sn = s[(s.population == NON) & ~s.crossover]
R = {}

# ---- E. session reconstruction diagnostics -------------------------------------------------------
print("== E. session reconstruction ==")
print("sessions total (session_id, population):", len(s), "| distinct session_id:", s.session_id.nunique())
print("sessions with >1 tray:", int((s.n_trays > 1).sum()), "| with >1 identification value:", int((s.n_identified_values > 1).sum()),
      "| spanning >1 file:", int((s.n_files > 1).sum()))
print("exact duplicate event rows:", int(e.dup.sum()), e[e.dup][["session_id", "source_file", "scale_identifier", "w"]].to_string(index=False))
for lab, d in [("registered-export", sr), ("non-registered-export", sn)]:
    print(f"\n[{lab}] n={len(d)}")
    print(" events/session:", d.component_weighing_event_count.value_counts().sort_index().to_dict())
    print(" median distinct_component_count (normalised name):", d.distinct_component_count.median(),
          "| raw name:", d.distinct_raw_names.median(), "| distinct scales:", d.distinct_scales.median(),
          "| events:", d.component_weighing_event_count.median())
    print(" sessions where norm-name count != event count:", int((d.distinct_component_count != d.component_weighing_event_count).sum()),
          "| != scale count:", int((d.distinct_component_count != d.distinct_scales).sum()),
          "| raw != norm:", int((d.distinct_raw_names != d.distinct_component_count).sum()))
m4 = pd.DataFrame({
    "definition": ["distinct normalised names (chosen)", "distinct raw names", "distinct scales", "weighing events"],
    "registered_median": [sr.distinct_component_count.median(), sr.distinct_raw_names.median(), sr.distinct_scales.median(), sr.component_weighing_event_count.median()],
    "registered_mean": [sr.distinct_component_count.mean(), sr.distinct_raw_names.mean(), sr.distinct_scales.mean(), sr.component_weighing_event_count.mean()],
    "sessions_differing_from_chosen": [0, int((sr.distinct_raw_names != sr.distinct_component_count).sum()),
                                       int((sr.distinct_scales != sr.distinct_component_count).sum()),
                                       int((sr.component_weighing_event_count != sr.distinct_component_count).sum())],
}).round(3)
m4["pct_sessions_differing"] = (100 * m4.sessions_differing_from_chosen / len(sr)).round(2)
print("\nM4 sensitivity to the identity definition (registered-export):"); print(m4.to_string(index=False))
m4.to_csv(OUT / "m4_definition_sensitivity.csv", index=False)

# repeated scale within session (B05/B06)
ed_core = ed[~ed.session_id.isin(xo)].sort_values(["population", "session_id", "t"])
rep = ed_core[ed_core.duplicated(["population", "session_id", "scale_identifier"], keep=False)].copy()
rep["gap_s"] = rep.groupby(["population", "session_id", "scale_identifier"]).t.diff().dt.total_seconds()
rep["prev_w"] = rep.groupby(["population", "session_id", "scale_identifier"]).w.shift()
rep["same_name_as_prev"] = rep.name_norm == rep.groupby(["population", "session_id", "scale_identifier"]).name_norm.shift()
rp = rep.dropna(subset=["gap_s"])
print("\nB05 same scale twice: events involved", len(rep), "| sessions", rep.groupby(["population", "session_id"]).ngroups,
      "| second-or-later events", len(rp))
print(rp.groupby("population").gap_s.describe(percentiles=[.1, .5, .9]).round(1))
print("share of repeat pairs <=30s:", round(100 * (rp.gap_s <= 30).mean(), 1), "%  <=60s:", round(100 * (rp.gap_s <= 60).mean(), 1),
      "% | same name as previous:", round(100 * rp.same_name_as_prev.mean(), 1), "%")
print("repeat weight vs previous: second smaller than first in", round(100 * (rp.w < rp.prev_w).mean(), 1), "% ; second <=3g:", int((rp.w <= 3).sum()))
rp.to_csv(OUT / "b05_same_scale_repeats.csv", index=False)
R["b05"] = {"events_involved": len(rep), "sessions": int(rep.groupby(["population", "session_id"]).ngroups),
            "pairs": len(rp), "gap_p50": float(rp.gap_s.median()), "gap_p90": float(rp.gap_s.quantile(.9))}
# how much does the repeat inflate the derived weight?
infl = rp.groupby(["population", "session_id"]).w.sum().rename("repeat_weight_g").reset_index().merge(
    s[["population", "session_id", "derived_selected_meal_weight_g"]], on=["population", "session_id"])
infl["pct_of_total"] = 100 * infl.repeat_weight_g / infl.derived_selected_meal_weight_g
print("weight carried by repeat events, % of session total: median", round(infl.pct_of_total.median(), 1), "p90", round(infl.pct_of_total.quantile(.9), 1))

# ---- G. session span / gaps ---------------------------------------------------------------------
print("\n== G. span / gaps ==")
gaps = ed_core.groupby(["population", "session_id"]).t.diff().dt.total_seconds().dropna()
print("inter-event gap (s) within a session:", gaps.describe(percentiles=[.5, .9, .99, .999]).round(1).to_dict())
for lab, d in [("registered-export", sr), ("non-registered-export", sn)]:
    print(lab, "span_s:", d.session_span_s.describe(percentiles=[.5, .9, .99, .999]).round(1).to_dict())
long = s[(s.session_span_s > 600)].sort_values("session_span_s", ascending=False)
print("sessions with span >600s:", len(long))
print(long[["session_id", "population", "component_weighing_event_count", "derived_selected_meal_weight_g", "first_weighing_at", "session_span_s", "crossover"]].to_string(index=False))
big_gaps = ed_core.assign(gap=ed_core.groupby(["population", "session_id"]).t.diff().dt.total_seconds())
print("events after a gap >300s within session:", int((big_gaps.gap > 300).sum()), "| >120s:", int((big_gaps.gap > 120).sum()))
print(big_gaps[big_gaps.gap > 120][["session_id", "population", "scale_identifier", "component_name", "w", "gap"]].to_string(index=False))
neg = s[s.identified_minus_last_s < 0]
print("\nT04 identification before last weighing:"); print(neg[["session_id", "population", "first_weighing_at", "last_weighing_at", "identified_at", "identified_minus_last_s", "crossover"]].to_string(index=False))
print("identification lag (s) after last weighing:", sr.identified_minus_last_s.describe(percentiles=[.5, .95, .99]).round(1).to_dict())
print("sessions with >1 identification values:"); print(s[s.n_identified_values > 1][["session_id", "population", "crossover"]].to_string(index=False))
R["span"] = {"spans_gt_600": len(long), "gap_p99": float(gaps.quantile(.99)), "gap_p999": float(gaps.quantile(.999)),
             "reg_span_p99": float(sr.session_span_s.quantile(.99)), "reg_span_p999": float(sr.session_span_s.quantile(.999)),
             "reg_span_max": float(sr.session_span_s.max())}

# ---- F. component-name normalisation stability --------------------------------------------------
print("\n== F. component-name stability ==")
names = e.component_name
print("raw distinct:", names.nunique(), "| after trim+space-collapse:", names.str.strip().str.replace(r"\s+", " ", regex=True).nunique(),
      "| after +casefold:", e.name_norm.nunique())
print("rows with edge whitespace:", int((names != names.str.strip()).sum()), "| names affected:", int(names[names != names.str.strip()].nunique()))
cv = e.groupby("name_norm").component_name.apply(lambda x: sorted(set(x.str.strip()))); cv = cv[cv.apply(len) > 1]
print("case/space variants collapsing to one normalised name:", len(cv)); print(cv.to_string())
# names per scale, scales per name
ns = e.groupby("name_norm").scale_identifier.nunique()
print("names appearing on >1 scale:", int((ns > 1).sum()), "of", len(ns))
twin = e.assign(twin=e.scale_identifier.str.replace(r"-(vasen|oikea)-", "-X-", regex=True))
nt = twin.groupby("name_norm").twin.nunique()
print("names appearing on >1 scale even after treating left/right twin scales as one:", int((nt > 1).sum()))
# scale-day name multiplicity
sd = e.groupby(["scale_identifier", "service_date", "population"]).name_norm.nunique().rename("names").reset_index()
print("scale-day-population cells:", len(sd), "| with >1 normalised name:", int((sd.names > 1).sum()),
      "| share:", round(100 * (sd.names > 1).mean(), 1), "%  distribution:", sd.names.value_counts().sort_index().to_dict())
# cross-export agreement on the same scale-day
sets = e.groupby(["scale_identifier", "service_date", "population"]).name_norm.apply(set).unstack("population")
both = sets.dropna()
def jac(a, b): return len(a & b) / len(a | b)
both = both.assign(jaccard=[jac(a, b) for a, b in zip(both[REG], both[NON])],
                   identical=[a == b for a, b in zip(both[REG], both[NON])],
                   disjoint=[len(a & b) == 0 for a, b in zip(both[REG], both[NON])],
                   day_in_override_file=[d in set(e[e.source_file.isin(UTC_FILES)].service_date) for _, d in both.index])
print("scale-days observed in BOTH exports:", len(both), "| identical name sets:", int(both.identical.sum()),
      "| disjoint:", int(both.disjoint.sum()), "| mean Jaccard:", round(both.jaccard.mean(), 3))
print("by override-file days:", both.groupby("day_in_override_file").agg(cells=("jaccard", "size"), identical=("identical", "mean"), jaccard=("jaccard", "mean"), disjoint=("disjoint", "mean")).round(3).to_dict())
both.drop(columns=[REG, NON]).to_csv(OUT / "component_name_cross_export_agreement.csv")
# does the session-level count differ if we used scale-day identity? (registered-export)
R["names"] = {"raw_distinct": int(names.nunique()), "norm_distinct": int(e.name_norm.nunique()),
              "variant_groups": int(len(cv)), "multi_scale_names": int((ns > 1).sum()),
              "scaleday_multi_name_share": float((sd.names > 1).mean()),
              "cross_export_cells": int(len(both)), "cross_export_identical": int(both.identical.sum()),
              "cross_export_disjoint": int(both.disjoint.sum()), "jaccard_mean": float(both.jaccard.mean())}

# ---- H. daily volume + Nov 16-20 ----------------------------------------------------------------
print("\n== H. daily volume ==")
day = s[~s.crossover].groupby(["service_date", "population"]).agg(sessions=("session_id", "size"), events=("component_weighing_event_count", "sum"),
       single_event_pct=("component_weighing_event_count", lambda x: 100 * (x == 1).mean()),
       median_weight=("derived_selected_meal_weight_g", "median")).round(1).reset_index()
day["weekday"] = pd.to_datetime(day.service_date).dt.day_name()
dv = day.pivot(index="service_date", columns="population", values="sessions")
dv["weekday"] = pd.to_datetime(dv.index).day_name()
print(dv.to_string())
day.to_csv(OUT / "daily_volume_by_population.csv", index=False)
reg_day = dv[REG].dropna()
ref = reg_day[reg_day.index < pd.Timestamp("2020-11-16").date()]
wk = pd.DataFrame({"reg": ref, "wd": pd.to_datetime(ref.index).day_name()})
wmed = wk.groupby("wd").reg.median()
print("\nregistered-export daily sessions before Nov 16: median", ref.median(), "| min", ref.min(), "| max", ref.max(), "| weekday medians", wmed.to_dict())
late = reg_day[reg_day.index >= pd.Timestamp("2020-11-16").date()]
lo = pd.DataFrame({"sessions": late, "weekday": pd.to_datetime(late.index).day_name()})
lo["weekday_median_before"] = lo.weekday.map(wmed); lo["ratio"] = (lo.sessions / lo.weekday_median_before).round(2)
print(lo.to_string())
# robust z relative to weekday-adjusted baseline
base_ratio = (ref / pd.Series(pd.to_datetime(ref.index).day_name(), index=ref.index).map(wmed))
med, mad = base_ratio.median(), (base_ratio - base_ratio.median()).abs().median()
print("baseline ratio (day/weekday median): median", round(med, 2), "MAD", round(mad, 3), "min", round(base_ratio.min(), 2), "max", round(base_ratio.max(), 2))
lo["robust_z"] = ((lo.sessions / lo.weekday_median_before - med) / (1.4826 * mad)).round(1)
print(lo[["sessions", "ratio", "robust_z"]].T.to_string())
R["volume"] = {"reg_median_pre_nov16": float(ref.median()), "reg_min_pre": int(ref.min()), "reg_max_pre": int(ref.max()),
               "baseline_ratio_min": float(base_ratio.min()), "baseline_ratio_max": float(base_ratio.max()),
               "nov": lo.reset_index().astype(str).to_dict("records")}

print("\n-- Nov 16-20 composition vs earlier registered-export days --")
sr2 = sr.assign(period=np.where(pd.to_datetime(sr.service_date) >= pd.Timestamp("2020-11-16"), "Nov16-20", "Oct5-Nov13"))
sr2["day"] = sr2.service_date.astype(str)
comp = sr2.groupby("day").agg(sessions=("session_id", "size"), events_per_session=("component_weighing_event_count", "mean"),
    single_event_pct=("component_weighing_event_count", lambda x: 100 * (x == 1).mean()), hot_pct=("has_hot", lambda x: 100 * x.mean()),
    median_weight=("derived_selected_meal_weight_g", "median"), p90_weight=("derived_selected_meal_weight_g", lambda x: x.quantile(.9)),
    trays=("tray_id", "nunique"), first=("first_weighing_at", lambda x: x.min().strftime("%H:%M")), last=("first_weighing_at", lambda x: x.max().strftime("%H:%M")),
    id_min=("session_id", lambda x: int(x.str.extract(r"(\d+)")[0].astype(int).min())), id_max=("session_id", lambda x: int(x.str.extract(r"(\d+)")[0].astype(int).max()))).round(2)
print(comp.loc["2020-11-09":].to_string())
print("earlier-period reference (Oct 5-Nov 13) mean of day metrics:", comp.loc[:"2020-11-13"][["events_per_session", "single_event_pct", "hot_pct", "median_weight"]].mean().round(2).to_dict())
comp.to_csv(OUT / "registered_export_daily_composition.csv")
# hourly shape Nov 20 vs earlier Fridays
def hshape(d): return d.first_weighing_at.dt.hour.value_counts(normalize=True).sort_index().round(3).to_dict()
print("hour shape Nov 20:", hshape(sr[sr.service_date == pd.Timestamp("2020-11-20").date()]))
print("hour shape earlier Fridays:", hshape(sr[pd.to_datetime(sr.service_date).dt.day_name().eq("Friday") & (pd.to_datetime(sr.service_date) < pd.Timestamp("2020-11-16"))]))
print("hour shape Nov 16-19:", hshape(sr[(pd.to_datetime(sr.service_date) >= pd.Timestamp("2020-11-16")) & (pd.to_datetime(sr.service_date) <= pd.Timestamp("2020-11-19"))]))
# scale coverage
sc = e[(e.population == REG)].assign(p=lambda d: np.where(pd.to_datetime(d.service_date) >= pd.Timestamp("2020-11-16"), "late", "early"))
cov = sc.groupby("p").scale_identifier.nunique(); print("distinct scales used early/late:", cov.to_dict())
sf = pd.crosstab(sc.station_family, sc.p, normalize="columns").round(3); print("station-family share early/late:\n", sf)
# session id vs time ordering: are ids chronological within the export?
sr_id = sr.assign(idn=sr.session_id.str.extract(r"(\d+)")[0].astype(int)).sort_values("first_weighing_at")
from scipy.stats import spearmanr
print("Spearman(session number, first_weighing_at) registered-export:", round(spearmanr(sr_id.idn, sr_id.first_weighing_at.astype("int64"))[0], 3))
print("session number ranges per file:"); print(s.assign(idn=s.session_id.str.extract(r"(\d+)")[0].astype(int)).groupby(["population", "source_file"]).idn.agg(["min", "max", "size"]).to_string())
nov20 = sr[sr.service_date == pd.Timestamp("2020-11-20").date()]
print("Nov 20 registered-export sessions:", len(nov20), "| single-event %:", round(100 * (nov20.component_weighing_event_count == 1).mean(), 1))
R["nov"] = {"nov20_sessions": len(nov20)}

# ---- I. the 2,097 g event ------------------------------------------------------------------------
print("\n== I. the 2,097 g event ==")
big = e[e.w >= 1500].sort_values("w", ascending=False)
print(big[["session_id", "population", "source_file", "scale_identifier", "component_name", "w", "t_naive"]].to_string(index=False))
top = e[e.w == e.w.max()].iloc[0]
ctx = e[(e.session_id == top.session_id)].sort_values("t")
print("\ncontext of", top.session_id); print(ctx[["population", "t_naive", "scale_identifier", "component_name", "w", "user_identification_time"]].to_string(index=False))
same_scale = e[(e.scale_identifier == top.scale_identifier)].w
same_name = e[(e.name_norm == top.name_norm)].w
print(f"\nscale {top.scale_identifier}: n={len(same_scale)} median={same_scale.median()} p95={same_scale.quantile(.95)} p99={same_scale.quantile(.99)} max={same_scale.max()}; 2097 is percentile {round(100*(same_scale<top.w).mean(),2)}")
print(f"name '{top.component_name}': n={len(same_name)} median={same_name.median()} p95={same_name.quantile(.95)} max={same_name.max()}")
print("hot-scale (lammin) events: p50", e[e.scale_kind == "lammin"].w.median(), "p99", e[e.scale_kind == "lammin"].w.quantile(.99), "p99.9", e[e.scale_kind == "lammin"].w.quantile(.999),
      "| cold (salaatti): p50", e[e.scale_kind == "salaatti"].w.median(), "p99", e[e.scale_kind == "salaatti"].w.quantile(.99), "p99.9", e[e.scale_kind == "salaatti"].w.quantile(.999))
print("session total of that session:", int(ctx.w.sum()), "| session total percentile within registered:", round(100 * (sr.derived_selected_meal_weight_g < ctx.w.sum()).mean(), 2))
R["outlier"] = {"weight": int(top.w), "session": top.session_id, "session_total": int(ctx.w.sum()), "events_ge_1500": len(big),
                "scale_p99": float(same_scale.quantile(.99)), "scale_max_other": float(same_scale[same_scale < top.w].max())}

# ---- J. single-event registered-export sessions ---------------------------------------------------
print("\n== J. single-event registered-export sessions ==")
one = sr[sr.component_weighing_event_count == 1].copy()
one = one.merge(ed[["session_id", "population", "scale_identifier", "component_name", "w"]], on=["session_id", "population"])
one["weekday"] = pd.to_datetime(one.service_date).dt.day_name()
print(one[["session_id", "service_date", "weekday", "first_weighing_at", "scale_identifier", "component_name", "w", "identified_minus_last_s", "source_file"]].to_string(index=False))
print("scale kinds:", one.scale_identifier.str.extract(r"-(salaatti|lammin)")[0].value_counts().to_dict(),
      "| weight median", one.w.median(), "| <=3g:", int((one.w <= 3).sum()), "| in Nov16-20:", int((pd.to_datetime(one.service_date) >= pd.Timestamp("2020-11-16")).sum()),
      "| by file:", one.source_file.value_counts().to_dict())
print("registered-export sessions overall: share with weight<=50g:", round(100 * (sr.derived_selected_meal_weight_g <= 50).mean(), 2), "| of single-event:", int((one.w <= 50).sum()))
one.to_csv(OUT / "single_event_registered_export_sessions.csv", index=False)
R["single"] = {"n": len(one), "in_nov16_20": int((pd.to_datetime(one.service_date) >= pd.Timestamp("2020-11-16")).sum()),
               "median_w": float(one.w.median()), "le3g": int((one.w <= 3).sum())}

# ---- K. threshold evidence ----------------------------------------------------------------------
print("\n== K. threshold evidence (registered-export, crossover excluded, duplicates removed) ==")
er = ed[(ed.population == REG) & ~ed.session_id.isin(xo)]
K = {}
for k in [.5, .9, .95, .99, .995, .999]:
    K[f"event_weight_p{k*100:g}"] = float(er.w.quantile(k))
for k in [.005, .01, .05, .95, .99, .995, .999]:
    K[f"session_weight_p{k*100:g}"] = float(sr.derived_selected_meal_weight_g.quantile(k))
K["events_le3g_pct"] = float(100 * (er.w <= 3).mean()); K["events_le1g_pct"] = float(100 * (er.w <= 1).mean())
K["events_ge1500"] = int((er.w >= 1500).sum()); K["events_gt1000_pct"] = float(100 * (er.w > 1000).mean())
print(json.dumps(K, indent=1))
R["thresholds"] = K
json.dump(R, open(OUT / "results_b.json", "w"), indent=1, default=str)
print("\nsaved")
