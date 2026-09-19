"""exploratory research helpers. HISTORICAL EVIDENCE, not the production pipeline (that lives in src/).

Reads the raw archive directly and writes nothing to data/raw. Kept small and boring on purpose.
"""
from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # repo root (this file lives in research/exploration/)
TAR = ROOT / "data" / "raw" / "flavoria" / "dataset_csv.tar"
OUT = ROOT / "outputs" / "exploration"

# Labels are inherited from the source FILENAMES. The public source does not define their meaning.
POP_LABEL = {"registered_export": "registered-export population",
             "non_registered_export": "non-registered-export population"}
# Initial timezone decision: +3h normalisation for this file (see docs/timezone_decision.md).
UTC_FILES = {"registered_2020_10_05-2020_10_18.csv"}
REQUIRED = ["session_id", "weighing_event_time", "scale_identifier", "weight_of_a_component",
            "component_name", "tray_id", "user_identification_time"]


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (events, file_meta). Every row is kept; values stay strings until parsed below."""
    frames, meta = [], []
    with tarfile.open(TAR) as tf:
        for m in sorted(tf.getmembers(), key=lambda m: m.name):
            raw = tf.extractfile(m).read()
            text = raw.decode("utf-8-sig")
            df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
            named = [c for c in df.columns if not c.startswith("Unnamed")]
            blank = [c for c in df.columns if c.startswith("Unnamed")]
            blank_nonempty = int(sum((df[c] != "").sum() for c in blank))
            meta.append({
                "file": m.name, "bytes": len(raw), "bom": raw[:3] == b"\xef\xbb\xbf", "crlf": b"\r\n" in raw,
                "rows": len(df), "columns_named": len(named), "columns_blank": len(blank),
                "blank_cells_nonempty": blank_nonempty, "has_weighting_type": "weighting_type" in named,
                "missing_required": ",".join(c for c in REQUIRED if c not in named),
                "header": "|".join(named),
                "population": "registered_export" if m.name.startswith("registered") else "non_registered_export",
            })
            df = df[named].copy()
            if "weighting_type" not in df:
                df["weighting_type"] = None
            df["source_file"] = m.name
            df["source_row_number"] = range(1, len(df) + 1)
            df["population"] = meta[-1]["population"]
            frames.append(df)
    ev = pd.concat(frames, ignore_index=True)
    return ev, pd.DataFrame(meta)


def parse(ev: pd.DataFrame) -> pd.DataFrame:
    """Typed copy. Adds parsed naive times, the initial review tz-normalised local time, and simple derived keys."""
    e = ev.copy()
    e["w"] = pd.to_numeric(e["weight_of_a_component"], errors="coerce")
    e["ts_format"] = e["weighing_event_time"].str.replace(r"\d", "9", regex=True)
    for src, dst in [("weighing_event_time", "t_naive"), ("user_identification_time", "u_naive")]:
        e[dst] = pd.to_datetime(e[src].str.replace(".", "-", regex=False))
    shift = e["source_file"].isin(UTC_FILES)
    off = pd.to_timedelta(shift.astype(int) * 3, unit="h")  # +3h == UTC->EEST for 2020-10-05..16
    e["t"] = e["t_naive"] + off
    e["u"] = e["u_naive"] + off
    e["tz_treatment"] = shift.map({True: "NORMALISED_PLUS_3H_STRONGEST_SUPPORT", False: "SOURCE_LOCAL_ASSUMED"})
    e["name_norm"] = e["component_name"].str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()
    e["station_family"] = e["scale_identifier"].str.split("-").str[0]
    e["scale_kind"] = e["scale_identifier"].str.extract(r"-(salaatti|lammin)\d+$")[0]
    e["service_date"] = e["t"].dt.date
    return e


def crossover_ids(e: pd.DataFrame) -> set[str]:
    n = e.groupby("session_id")["population"].nunique()
    return set(n[n > 1].index)


def exact_dup_mask(e: pd.DataFrame) -> pd.Series:
    """Repeat of an earlier row inside the same file with every source column equal."""
    cols = [c for c in ["session_id", "weighing_event_time", "weighting_type", "scale_identifier",
                        "weight_of_a_component", "component_name", "tray_id", "user_identification_time"]]
    return e.duplicated(subset=cols + ["source_file"], keep="first")


def sessions(e: pd.DataFrame) -> pd.DataFrame:
    """One row per (session_id, population). Duplicates excluded from sums; crossover sessions flagged."""
    x = crossover_ids(e)
    d = e[~exact_dup_mask(e)]
    g = d.groupby(["session_id", "population"])
    s = g.agg(component_weighing_event_count=("w", "size"), derived_selected_meal_weight_g=("w", "sum"),
              distinct_component_count=("name_norm", "nunique"),
              distinct_raw_names=("component_name", "nunique"),
              distinct_scales=("scale_identifier", "nunique"),
              first_weighing_at=("t", "min"), last_weighing_at=("t", "max"), identified_at=("u", "first"),
              n_identified_values=("u", "nunique"), n_trays=("tray_id", "nunique"), tray_id=("tray_id", "first"),
              source_file=("source_file", "first"), n_files=("source_file", "nunique"),
              has_hot=("scale_kind", lambda v: (v == "lammin").any())).reset_index()
    s["session_span_s"] = (s.last_weighing_at - s.first_weighing_at).dt.total_seconds()
    s["identified_minus_last_s"] = (s.identified_at - s.last_weighing_at).dt.total_seconds()
    s["service_date"] = s.first_weighing_at.dt.date
    s["crossover"] = s.session_id.isin(x)
    return s


def q(series: pd.Series, qs=(0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)) -> dict:
    return {f"p{int(k * 100)}": float(series.quantile(k)) for k in qs} | {
        "min": float(series.min()), "max": float(series.max()), "mean": float(series.mean()), "n": int(series.size)}
