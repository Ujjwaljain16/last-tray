"""Does FMI `r_1h` at time t cover the hour ENDING at t or the hour STARTING at t?

Reproduces the empirical test from the preserved raw evidence (no network):
  * hourly `r_1h`      <- data/raw/weather/fmi_100949_*.xml
  * 10-minute `ri_10min` <- data/raw/weather/probe_fmi_100949_20201021_20201023_10min_r1h_semantics.xml

Method: for each full hour t with six 10-minute slots on both sides, compare r_1h(t) with the rain accumulated in
(t-60min, t] (hour ending) and in [t, t+60min) (hour starting). ri_10min is an intensity in mm/h, so a 10-minute
slot contributes ri/6 mm. Result reported in docs/source_truth_decisions.md. One rainy day only.
"""
import glob
import re

import pandas as pd

from exploration_common import ROOT

PAT = r"<BsWfs:Time>([^<]*)</BsWfs:Time>\s*<BsWfs:ParameterName>([^<]*)</BsWfs:ParameterName>\s*<BsWfs:ParameterValue>([^<]*)<"


def read(path: str) -> pd.DataFrame:
    rows = re.findall(PAT, open(path, encoding="utf-8").read())
    d = pd.DataFrame(rows, columns=["t", "p", "v"])
    d["t"] = pd.to_datetime(d.t).dt.tz_localize(None)
    d["v"] = pd.to_numeric(d.v, errors="coerce")
    return d.pivot_table(index="t", columns="p", values="v")


probe = read(str(ROOT / "data/raw/weather/probe_fmi_100949_20201021_20201023_10min_r1h_semantics.xml"))
ri, r1 = probe["ri_10min"], probe["r_1h"]
rows = []
for t in r1.index:
    if t.minute != 0 or pd.isna(r1[t]):
        continue
    ending = ri[(ri.index > t - pd.Timedelta(minutes=60)) & (ri.index <= t)]
    starting = ri[(ri.index >= t) & (ri.index < t + pd.Timedelta(minutes=60))]
    if len(ending) == 6 and len(starting) == 6:
        rows.append((t, r1[t], ending.sum() / 6, starting.sum() / 6))
r = pd.DataFrame(rows, columns=["t", "r_1h", "sum_hour_ending", "sum_hour_starting"])
mae_end = (r.r_1h - r.sum_hour_ending).abs().mean()
mae_start = (r.r_1h - r.sum_hour_starting).abs().mean()
print(f"hours compared: {len(r)}  |  MAE vs hour ENDING: {mae_end:.3f} mm  |  MAE vs hour STARTING: {mae_start:.3f} mm")
assert mae_end < mae_start, "hour-ending convention no longer supported by the evidence"

# The probe hours must agree with the hourly files that the production pipeline will use.
hourly = []
for f in sorted(glob.glob(str(ROOT / "data/raw/weather/fmi_100949_*.xml"))):
    hourly.append(read(f))
h = pd.concat(hourly)
h = h[~h.index.duplicated()]
common = r.set_index("t").join(h["r_1h"].rename("hourly_file"), how="inner")
print("probe r_1h equals the committed hourly file on", int((common.r_1h.round(2) == common.hourly_file.round(2)).sum()), "of", len(common), "shared hours")
