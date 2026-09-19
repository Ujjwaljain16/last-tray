"""Profile report sections F2 (name disagreement in the Oct 5-16 window) and L (weather join dry-run, precipitation semantics)."""
import json, re
import numpy as np, pandas as pd
from exploration_common import OUT, UTC_FILES, ROOT, exact_dup_mask
pd.set_option("display.width", 250)
e = pd.read_pickle(OUT / "_events.pkl"); s = pd.read_pickle(OUT / "_sessions.pkl")
REG, NON = "registered_export", "non_registered_export"
R = {}
# ---- F2 ------------------------------------------------------------------------------------------
sets = e.groupby(["scale_identifier", "service_date", "population"]).name_norm.apply(set).unstack("population").dropna()
sets = sets.assign(override_day=[d in set(e[e.source_file.isin(UTC_FILES)].service_date) for _, d in sets.index])
dis = sets[(sets.override_day) & [len(a & b) == 0 for a, b in zip(sets[REG], sets[NON])]]
allsets = e[e.population == NON].groupby(["scale_identifier", "service_date"]).name_norm.apply(set)
hits = {}
for (sc, d), row in dis.iterrows():
    for k in (-4, -3, -2, -1, 1, 2, 3, 4):
        dd = (pd.Timestamp(d) + pd.Timedelta(days=k)).date()
        if (sc, dd) in allsets.index and row[REG] & allsets[(sc, dd)]:
            hits[k] = hits.get(k, 0) + 1
print("disjoint scale-days in the override window:", len(dis), "| registered-export names found in non-registered names of the same scale on other days (offset days -> count):", hits)
print("override window overall: cells", int(sets.override_day.sum()), "identical", sum(a == b for a, b, o in zip(sets[REG], sets[NON], sets.override_day) if o))
ex = dis.head(8).copy(); ex["registered_export_names"] = ex[REG].apply(lambda x: "; ".join(sorted(x))); ex["non_registered_export_names"] = ex[NON].apply(lambda x: "; ".join(sorted(x)))
print(ex[["registered_export_names", "non_registered_export_names"]].to_string())
ex.drop(columns=[REG, NON]).to_csv(OUT / "name_disagreement_examples_oct5_16.csv")  # sorted, joined names only: set reprs are hash-seed dependent
# is the disagreement present across the *whole* registered-export dot file or is it per-day? per day share
byday = sets[sets.override_day].assign(dis=[len(a & b) == 0 for a, b in zip(sets[sets.override_day][REG], sets[sets.override_day][NON])]).groupby(level=1).dis.mean().round(2)
print("share disjoint per day (override window):", byday.to_dict())
R["names_oct"] = {"disjoint": len(dis), "adjacent_day_hits": hits}

# ---- L. weather join dry run --------------------------------------------------------------------
import glob
_rows = []
for _f in sorted(glob.glob(str(ROOT / "data/raw/weather/fmi_100949_*.xml"))):
    _rows += re.findall(r"<BsWfs:Time>([^<]*)</BsWfs:Time>\s*<BsWfs:ParameterName>([^<]*)</BsWfs:ParameterName>\s*<BsWfs:ParameterValue>([^<]*)<", open(_f, encoding="utf-8").read())
wx = pd.DataFrame(_rows, columns=["t", "p", "v"]).drop_duplicates(["t", "p"])
wx["v"] = pd.to_numeric(wx.v, errors="coerce")
wx = wx.pivot(index="t", columns="p", values="v")
wx.index = pd.to_datetime(wx.index, utc=True)
wx = wx.rename_axis("obs_time_utc")
sr = s[(s.population == REG) & ~s.crossover].copy()
loc = sr.first_weighing_at.dt.tz_localize("Europe/Helsinki", ambiguous="raise", nonexistent="raise")
utc = loc.dt.tz_convert("UTC")
sr["utc"] = utc
sr["hour_floor"] = utc.dt.floor("h"); sr["hour_ceil"] = utc.dt.ceil("h")
for name, col in [("floor (hour starting)", "hour_floor"), ("ceil (hour ending, contains the meal)", "hour_ceil")]:
    j = sr.join(wx, on=col)
    print(f"{name}: matched {int(j.t2m.notna().sum())}/{len(j)}  | precipitation NULL: {int(j.r_1h.isna().sum())}  ri_10min NULL: {int(j.ri_10min.isna().sum())}")
j = sr.join(wx, on="hour_ceil")
R["weather"] = {"sessions": len(sr), "matched_ceil": int(j.t2m.notna().sum()), "r1h_null_sessions": int(j.r_1h.isna().sum()),
                "ri10_null_sessions": int(j.ri_10min.isna().sum()),
                "distinct_weather_hours": int(j.hour_ceil.nunique()), "dst_days": [str(x) for x in sorted(set(sr.service_date)) if str(x) in ("2020-10-24", "2020-10-25", "2020-10-26")]}
# UTC hours of meals (local 10:00-14:xx) -> UTC
print("UTC hours of first weighing:", sr.utc.dt.hour.value_counts().sort_index().to_dict())
# effect of a wrong timezone on the weather join for the override file
ov = sr[sr.source_file.isin(UTC_FILES)].copy()
wrong = (ov.first_weighing_at - pd.Timedelta(hours=3)).dt.tz_localize("Europe/Helsinki").dt.tz_convert("UTC").dt.ceil("h")   # if raw times had been treated as local
diff_hours = (ov.hour_ceil - wrong).dt.total_seconds() / 3600
jw = ov.join(wx, on="hour_ceil"); jx = pd.DataFrame({"hour": wrong}).join(wx, on="hour")
print("override-file sessions:", len(ov), "| joined to a different weather hour if timezone were mishandled:", int((diff_hours != 0).sum()),
      "| differing temperature (abs mean, C):", round((jw.t2m.values - jx.t2m.values).__abs__().mean(), 2))
R["weather"]["override_sessions"] = len(ov)
# how many sessions fall on a rainy hour (descriptive only)
print("sessions on hours with r_1h>0:", int((j.r_1h > 0).sum()), "of", int(j.r_1h.notna().sum()))
# DST: converts round-trip
rt = sr.first_weighing_at.dt.tz_localize("Europe/Helsinki").dt.tz_convert("UTC").dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)
print("round-trip local->UTC->local identical for all sessions:", bool((rt == sr.first_weighing_at).all()))
# missing precipitation hours in relation to service hours
nanh = wx[wx.r_1h.isna() | wx.ri_10min.isna()]; print("hours with null precipitation:", [str(x) for x in nanh.index])
# station distance to university campus (approx, degrees->km); Turku Artukainen vs Flavoria (university campus ~ 60.4515N 22.2870E)
from math import radians, sin, cos, asin, sqrt
def hav(a, b, c, d):
    a, b, c, d = map(radians, (a, b, c, d)); h = sin((c - a) / 2) ** 2 + cos(a) * cos(c) * sin((d - b) / 2) ** 2; return 2 * 6371 * asin(sqrt(h))
print("distance Artukainen(60.4544,22.1787) -> Turku university campus area(60.4515,22.2870) km:", round(hav(60.4544, 22.1787, 60.4515, 22.2870), 1),
      " | Rajakari(60.3779,22.0964):", round(hav(60.3779, 22.0964, 60.4515, 22.2870), 1))
json.dump(R, open(OUT / "results_c.json", "w"), indent=1, default=str)
