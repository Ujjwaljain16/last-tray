"""Builds the four LAST TRAY diagrams. Documentation tooling only, not part of the pipeline.

Run from the repo root:  python diagrams/build_diagrams.py
Visual language (same in every diagram):
  blue   = OBSERVED (instrument / external authority)
  amber  = DERIVED (computed by us under a stated rule)
  grey   = UNKNOWN (never measured)
  red    = SOURCE GAP (exists, not retrievable); dashed outline
  green  = external context
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).parent
C = {
    "obs": ("#dbeafe", "#1d4ed8"),
    "der": ("#fef3c7", "#b45309"),
    "unk": ("#e5e7eb", "#4b5563"),
    "gap": ("#fee2e2", "#b91c1c"),
    "ext": ("#dcfce7", "#15803d"),
    "aud": ("#f3f4f6", "#6b7280"),
    "pipe": ("#ede9fe", "#6d28d9"),
}
INK = "#111827"


def canvas(w=16, h=9, title="", subtitle=""):
    fig, ax = plt.subplots(figsize=(w, h), dpi=110)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.text(2, 98, title, fontsize=22, fontweight="bold", color=INK, va="top")
    if subtitle:
        ax.text(2, 92, subtitle, fontsize=12.5, color="#4b5563", va="top")
    return fig, ax


def box(ax, x, y, w, h, text, kind="obs", fs=12, bold=False, dashed=False, align="center"):
    fc, ec = C[kind]
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1.0",
                       fc=fc, ec=ec, lw=2.2, ls="--" if dashed else "-")
    ax.add_patch(p)
    ha = "center" if align == "center" else "left"
    tx = x + w / 2 if align == "center" else x + 1.2
    ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fs, color=INK,
            fontweight="bold" if bold else "normal", linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, kind="obs", dashed=False, label=None, lw=2.4, lx=0, ly=1.2):
    col = C[kind][1]
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=lw, ls="--" if dashed else "-",
                                shrinkA=0, shrinkB=0, mutation_scale=20))
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, fontsize=11, color=col,
                ha="center", va="bottom", fontweight="bold")


def zone(ax, x, y, w, h, label, col="#9ca3af"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.2",
                                fc="none", ec=col, lw=1.6, ls=(0, (6, 4))))
    ax.text(x + 1, y + h - 1.2, label, fontsize=11.5, color=col, fontweight="bold", va="top")


def legend(ax, y=1.6):
    items = [("obs", "OBSERVED"), ("der", "DERIVED"), ("unk", "UNKNOWN"), ("gap", "SOURCE GAP")]
    x = 2
    for k, t in items:
        fc, ec = C[k]
        ax.add_patch(FancyBboxPatch((x, y), 2.2, 1.9, boxstyle="round,pad=0.1", fc=fc, ec=ec, lw=2,
                                    ls="--" if k == "gap" else "-"))
        ax.text(x + 3.2, y + 0.95, t, fontsize=11.5, va="center", color=INK)
        x += 15


def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# 1. SOURCE MAP ---------------------------------------------------------------------------
def source_map():
    fig, ax = canvas(16, 9, "Source map",
                     "Where each piece of truth lives, and which pieces we can actually retrieve")
    zone(ax, 1.5, 12, 33, 60, "PUBLIC AND RETRIEVED", C["obs"][1])
    box(ax, 3, 44, 30, 20, "Flavoria lunch-line scales\nFlavoriaFoodWeight1700\n(Zenodo, CC-BY-4.0)\n11 CSV files, 12,284 events\ngrain: one component weighing", "obs", 11.5, True)
    box(ax, 3, 18, 30, 20, "FMI weather (WFS API)\nTurku Artukainen, hourly\n1,129 hours, no API key\ngrain: station x hour", "ext", 11.5, True)

    zone(ax, 40, 12, 26, 60, "PIPELINE: LAST TRAY", C["pipe"][1])
    box(ax, 42, 52, 22, 10, "Raw preserved\nchecksum + manifest", "pipe", 11.5)
    box(ax, 42, 37, 22, 10, "Profile + validate\nquarantine, never delete", "pipe", 11.5)
    box(ax, 42, 22, 22, 10, "Derive sessions\nweights, components", "der", 11.5)
    arrow(ax, 53, 52, 53, 47.4, "pipe")
    arrow(ax, 53, 37, 53, 32.4, "pipe")
    arrow(ax, 33.5, 54, 42, 57, "obs", label="file", ly=0.3)
    arrow(ax, 33.5, 28, 42, 27, "ext", label="API", ly=0.3)

    zone(ax, 71, 12, 27.5, 60, "DOCUMENTED, NOT RETRIEVABLE", C["gap"][1])
    gaps = ["Lunch Line Waste\n\"TODO, Ask!\" (restricted)", "Weigh & Dine\ncheckout plate total", "Cash Register\n(restricted)",
            "Building data, MyFlavoria,\nSurveys (unspecified)"]
    for i, g in enumerate(gaps):
        box(ax, 73, 54 - i * 12.5, 23.5, 10, g, "gap", 11, i == 0, dashed=True)

    box(ax, 41, 79, 25, 9, "Client decision:\ncan we support waste\ndecisions yet?", "pipe", 12, True)
    arrow(ax, 53, 72.6, 53, 78.6, "pipe")
    box(ax, 71, 79, 27.5, 9, "UNKNOWN: food consumed\n(no source measures it)", "unk", 11.5, True)
    ax.text(2, 80, "Gap register: docs/source_gap_register.md", fontsize=11, color="#6b7280", va="center")
    legend(ax, 2.5)
    save(fig, "source-map.png")


# 2. WORKFLOW -----------------------------------------------------------------------------
def workflow():
    fig, ax = canvas(16, 9, "Business workflow: what the data can see",
                     "The public data covers only the first half of a diner's path through the restaurant")
    y = 40
    steps = [
        (2.5, "Take tray\nRFID tray_id", "obs"),
        (19, "Select and weigh\neach component\n(grams per scale)", "obs"),
        (35.5, "Tray identified\n(identification\ntime)", "obs"),
        (52, "Checkout scale\nWeigh & Dine total", "gap"),
        (68.5, "Eat", "unk"),
        (84, "Return tray\nwaste station", "gap"),
    ]
    for x, t, k in steps:
        box(ax, x, y, 13.5, 14, t, k, 11.5, dashed=(k == "gap"))
    for i in range(len(steps) - 1):
        x1 = steps[i][0] + 13.5
        x2 = steps[i + 1][0]
        arrow(ax, x1, y + 7, x2, y + 7, "obs" if i < 2 else "gap", dashed=i >= 2, lw=2.2)

    # derived session bracket
    ax.plot([2.5, 2.5, 49.2, 49.2], [58, 61, 61, 58], color=C["der"][1], lw=2.6)
    box(ax, 12, 63, 28, 8, "DINING SESSION (derived)\nevents grouped by session_id", "der", 12, True)
    ax.text(26, 56.3, "we reconstruct this; the source never states it", ha="center", fontsize=11, color=C["der"][1], style="italic")

    # measurement callouts
    box(ax, 5, 18, 43, 13, "DERIVED: derived_selected_meal_weight_g\n= sum of component events in the session\nNOT an observed meal weight", "der", 12, True)
    arrow(ax, 26, 31.3, 26, 39.4, "der", lw=2)
    box(ax, 55, 18, 20.5, 13, "UNKNOWN\nconsumed quantity\n(never measured)", "unk", 12, True)
    box(ax, 78, 18, 19.5, 13, "SOURCE GAP\nwaste_weight_g = NULL\nnever 0", "gap", 12, True, dashed=True)
    arrow(ax, 75.2, 39.4, 65.5, 31.4, "unk", lw=2)
    arrow(ax, 90.7, 39.4, 88, 31.4, "gap", dashed=True, lw=2)
    ax.text(50, 11.2, "selected weight  ≠  consumption  ≠  waste", ha="center", fontsize=17, fontweight="bold", color=INK)
    legend(ax, 2.2)
    save(fig, "workflow.png")


# 3. DATA MODEL ---------------------------------------------------------------------------
def data_model():
    fig, ax = canvas(16, 9, "Data model",
                     "Grain first: the atomic row is a weighing event; the session is derived")
    box(ax, 2, 58, 29, 25, "fact_weighing_event\n\nGRAIN: one component\nweighing event\nkey: event_id (file + row)\ncomponent_weight_g  OBSERVED", "obs", 11)
    box(ax, 36, 58, 30, 25, "fact_dining_session\n\nGRAIN: one derived session\n(session_id x population)\nderived_selected_meal_weight_g\ncore_ready (excludes weather)", "der", 11)
    box(ax, 71, 58, 27, 25, "fact_session_component\n\nGRAIN: one distinct\ncomponent in one session\nderived_component_weight_g", "der", 11)
    arrow(ax, 31.5, 70.5, 35.5, 70.5, "obs", label="group", ly=0.8)
    arrow(ax, 66.5, 70.5, 70.5, 70.5, "der", label="split", ly=0.8)

    box(ax, 2, 30, 22, 20, "dim_scale\n\nGRAIN: one physical\nscale (30 scales)", "aud", 10.5)
    arrow(ax, 13, 50.4, 13, 57.6, "aud", lw=2)
    box(ax, 26, 30, 22, 20, "fact_daily_volume\n\nGRAIN: one service date\nx population\nflags only, never\nexcludes a day", "der", 10.5)
    arrow(ax, 40, 57.6, 40, 50.6, "der", lw=2)
    box(ax, 50, 30, 22, 20, "fact_weather\n\nGRAIN: one station\nx UTC hour\nNULL kept as NULL", "ext", 10.5)
    arrow(ax, 58, 57.6, 58, 50.6, "ext", dashed=True, label="context join", lx=8, ly=-1.5)
    box(ax, 74, 30, 24, 20, "waste_weight_g\nSOURCE GAP\nalways NULL in MVP,\nnever 0", "gap", 11, True, dashed=True)
    arrow(ax, 84, 57.6, 86, 50.6, "gap", dashed=True, lw=2)

    ax.text(2, 24.5, "Audit tables: nothing is silently dropped", fontsize=11.5, color="#6b7280", style="italic")
    box(ax, 2, 10, 29, 11, "fact_validation_issue\none rule violation on one record", "aud", 10.5)
    box(ax, 36, 10, 30, 11, "raw_file_manifest\none raw file in one run", "aud", 10.5)
    box(ax, 71, 10, 27, 11, "pipeline_run\none execution", "aud", 10.5)
    legend(ax, 0.6)
    save(fig, "data-model.png")


# 4. PIPELINE -----------------------------------------------------------------------------
def pipeline():
    fig, ax = canvas(16, 9, "Pipeline: python -m src.pipeline.run",
                     "Core lane and context lane are independent: weather can fail without touching the KPIs")
    zone(ax, 1.5, 55, 97, 32, "CORE LANE (gate: raw checksum, required columns, no unexplained event loss)", C["pipe"][1])
    core = [
        ("1-3\nDiscover, ingest,\npreserve raw\n+ manifest", "pipe"),
        ("4\nProfile", "pipe"),
        ("5\nValidate\nquarantine", "pipe"),
        ("6, 9\nTransform,\nbuild model", "der"),
        ("10\nMetrics\nM1-M5", "der"),
        ("11\nEvidence\ntable", "der"),
    ]
    w, gap = 13.5, 2.7
    x = 3
    xs = []
    for t, k in core:
        box(ax, x, 59, w, 20, t, k, 11.5)
        xs.append(x)
        x += w + gap
    for i in range(len(core) - 1):
        arrow(ax, xs[i] + w, 69, xs[i + 1], 69, "pipe", lw=2.2)

    zone(ax, 1.5, 24, 64, 27, "CONTEXT LANE (failure = BLOCKED weather outputs only)", C["ext"][1])
    box(ax, 3, 28, 18, 16, "7\nFMI retrieve\nretry + backoff", "ext", 11.5)
    box(ax, 24, 28, 18, 16, "7\nParse XML\nNULL stays NULL", "ext", 11.5)
    box(ax, 45, 28, 18, 16, "8\nHour join\nS1 coverage", "ext", 11.5)
    arrow(ax, 21, 36, 24, 36, "ext")
    arrow(ax, 42, 36, 45, 36, "ext")
    arrow(ax, 54, 44.4, 54, 58.6, "ext", dashed=True, label="enrich only", lx=6, ly=-3)

    box(ax, 70, 26, 28, 22, "12-13  Gates + manifest\nCore gate: pass / fail\nContext gate: pass / fail\nrun_manifest.json + log", "pipe", 11.5, True)
    arrow(ax, 84, 58.6, 84, 48.4, "pipe", lw=2.2)

    ax.text(2, 18, "Failure classes", fontsize=12.5, fontweight="bold", color=INK)
    fc = [("RECOVERED", "retry or fallback worked"), ("WARNING", "output with a stated limitation"),
          ("FAILED", "stage could not run; stop"), ("BLOCKED", "one output impossible")]
    for i, (a, b) in enumerate(fc):
        ax.text(2 + i * 24.5, 12.5, a, fontsize=12.5, fontweight="bold", color=C["pipe"][1])
        ax.text(2 + i * 24.5, 8.5, b, fontsize=10.5, color="#4b5563")
    ax.text(2, 2.5, "Rerun on the same inputs: same row counts, same hashes, no duplicates.  --offline reproduces from saved raw files.",
            fontsize=11.5, color=INK, style="italic")
    save(fig, "pipeline.png")


if __name__ == "__main__":
    source_map()
    workflow()
    data_model()
    pipeline()
    print("ok")
