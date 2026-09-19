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
    items = [("obs", "OBSERVED"), ("der", "DERIVED"), ("ext", "CONTEXT (external)"), ("unk", "UNKNOWN"), ("gap", "SOURCE GAP")]
    x = 2
    for k, t in items:
        fc, ec = C[k]
        ax.add_patch(FancyBboxPatch((x, y), 2.2, 1.9, boxstyle="round,pad=0.1", fc=fc, ec=ec, lw=2,
                                    ls="--" if k == "gap" else "-"))
        ax.text(x + 3.2, y + 0.95, t, fontsize=11.5, va="center", color=INK)
        x += 19


def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / name.replace(".png", ".svg"), bbox_inches="tight", facecolor="white", metadata={"Date": None})   # editable vector copy
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
    fig, ax = canvas(16, 9, "Workflow: from dining activity to evidence",
                     "What is observed, what is derived, what is unknown, and what is a source gap. Public research data, not a live operational feed.")
    w, gap = 11.6, 2.3
    steps = [
        ("DINING\nACTIVITY\nlunch line, one\ntray pass", "obs"),
        ("TRAY / SESSION\nIDENTIFICATION\ntray_id,\nsession_id", "obs"),
        ("COMPONENT\nWEIGHING EVENTS\n12,284 events\n(grams per scale)", "obs"),
        ("DERIVED SESSION\nMEASUREMENT\nselected meal\nweight, 1,697 core-\nready sessions", "der"),
        ("AVAILABLE\nCONTEXT\nFMI weather by\nhour (context only)", "ext"),
        ("VALIDATION /\nRECONCILIATION\nrules, quarantine,\nidentities", "pipe"),
        ("EVIDENCE\nM1-M5, S2,\nsensitivity,\nW1 BLOCKED", "pipe"),
    ]
    y, h = 55, 24
    xs = []
    x = 1.2
    for t, k in steps:
        box(ax, x, y, w, h, t, k, 10.2, bold=False)
        xs.append(x)
        x += w + gap
    kinds = ["obs", "obs", "der", "ext", "pipe", "pipe"]
    for i in range(6):
        arrow(ax, xs[i] + w, y + h / 2, xs[i + 1], y + h / 2, kinds[i], lw=2.0)
    ax.text(1.2, y + h + 3.2, "OBSERVED", fontsize=11, color=C["obs"][1], fontweight="bold")
    ax.text(xs[3], y + h + 3.2, "DERIVED (our rule)", fontsize=11, color=C["der"][1], fontweight="bold")
    ax.text(xs[4], y + h + 3.2, "CONTEXT", fontsize=11, color=C["ext"][1], fontweight="bold")
    ax.text(xs[5], y + h + 3.2, "CONTROLS", fontsize=11, color=C["pipe"][1], fontweight="bold")

    # what the chain does not reach
    box(ax, 4, 24, 20, 12, "ACTUAL CONSUMPTION", "unk", 11.5, True)
    box(ax, 32, 24, 20, 12, "NOT OBSERVED\nno source measures it", "unk", 11.5, True)
    arrow(ax, 24.4, 30, 31.6, 30, "unk", lw=2.0)
    box(ax, 4, 6, 20, 12, "FOOD WASTE", "gap", 11.5, True, dashed=True)
    box(ax, 32, 6, 24, 12, "REQUIRED SOURCE\nNOT ACCESSIBLE", "gap", 11.5, True, dashed=True)
    box(ax, 64, 6, 22, 12, "SOURCE GAP\nW1 BLOCKED, never 0", "gap", 11.5, True, dashed=True)
    arrow(ax, 24.4, 12, 31.6, 12, "gap", dashed=True, lw=2.0)
    arrow(ax, 56.4, 12, 63.6, 12, "gap", dashed=True, lw=2.0)
    arrow(ax, xs[3] + w / 2, y - 0.4, 14, 36.6, "unk", dashed=True, lw=1.6)
    ax.text(58, 30, "selected weight  is not  consumption,\nconsumption  is not  waste", fontsize=15, fontweight="bold", color=INK, va="center")
    ax.text(58, 22, "Only the first half of the diner's path is public.\nEvery number above the line is a reconstruction, never a waste figure.", fontsize=11, color="#4b5563", va="center")
    legend(ax, 0.2)
    save(fig, "workflow.png")


# 3. DATA MODEL ---------------------------------------------------------------------------
def data_model():
    fig, ax = canvas(16, 9, "Business data model",
                     "Grain first: the atomic row is a weighing event; the session is derived; the session key is (session_id, population)")
    box(ax, 1.5, 58, 29, 24, "fact_weighing_event\n\nGRAIN: one component\nweighing event  (12,284)\ncomponent_weight_g  OBSERVED", "obs", 10.5)
    box(ax, 36, 58, 31, 24, "fact_dining_session\n\nGRAIN: one derived session\nkey (session_id, population)  (3,345)\nderived_selected_meal_weight_g\ncore_ready flag", "der", 10.5)
    box(ax, 72, 58, 26.5, 24, "fact_session_component\n\nGRAIN: one distinct component\nin one session  (11,925)\nderived_component_weight_g", "der", 10.5)
    arrow(ax, 30.8, 70, 35.6, 70, "obs", label="group", ly=0.8)
    arrow(ax, 67.2, 70, 71.6, 70, "der", label="split", ly=0.8)

    box(ax, 1.5, 33, 22, 16, "fact_validation_issue\nvalidation_issues.csv\none rule finding on\none event or session", "aud", 10)
    arrow(ax, 12.5, 49.4, 12.5, 57.6, "aud", lw=2)
    box(ax, 26, 33, 22, 16, "fact_daily_volume\n\none service date x\npopulation; flags only,\nnever excludes a day", "der", 10)
    arrow(ax, 44, 57.6, 44, 49.4, "der", lw=2)
    box(ax, 50.5, 33, 22, 16, "fact_weather\n\none station x UTC hour\nCONTEXT; NULL kept", "ext", 10)
    arrow(ax, 61.5, 57.6, 61.5, 49.4, "ext", dashed=True, label="context join", lx=8, ly=-2.2)
    box(ax, 75.5, 33, 23, 16, "waste_weight_g\nSOURCE GAP\nnever produced; never 0", "gap", 10.5, True, dashed=True)
    arrow(ax, 88, 57.6, 88, 49.4, "gap", dashed=True, lw=2)

    box(ax, 1.5, 6, 29, 14, "pipeline_run / provenance\nrun_manifest.json, source snapshot,\nraw_artifact_manifest (checksums)", "aud", 10)
    box(ax, 36, 3.5, 62.5, 19, "Why session_id alone is not enough\nsession2266 and session3222 appear in BOTH exports: 3,343 distinct session_ids but 3,345 keys.\nThe same ID in two exports is two records, not one session, so the key is (session_id, population).\nBoth crossover keys are quarantined and never pooled.", "der", 10, align="left")
    legend(ax, 0.0)
    save(fig, "data-model.png")


# 4. PIPELINE -----------------------------------------------------------------------------
def pipeline():
    fig, ax = canvas(16, 9, "Pipeline: python -m src.pipeline.run",
                     "Six gated stages, offline by default; a failed stage blocks everything after it and removes its stale outputs")
    names = [("ingest", "outputs/ingestion", "pinned raw files,\nchecksums, schema"), ("stage", "outputs/staging", "verified reads only"), ("validate", "outputs/validation", "rules, quarantine"),
             ("model", "outputs/model", "facts, controls"), ("metrics", "outputs/metrics", "M1-M5, S2,\nW1 BLOCKED"),("sensitivity", "outputs/evidence", "scenarios, robustness")]
    w, gap, y, h = 14.2, 2.4, 52, 26
    x = 1.2
    xs = []
    for i, (n, d, t) in enumerate(names):
        box(ax, x, y, w, h, f"{i + 1}  {n}\n\n{t}\n\n{d}", "pipe" if i < 3 else "der", 10.2)
        xs.append(x)
        x += w + gap
    for i in range(5):
        arrow(ax, xs[i] + w, y + h / 2, xs[i + 1], y + h / 2, "pipe", lw=2.0)
    ax.text(1.2, y + h + 3, "GATE: a stage runs only if the previous one passed; each stage re-verifies its upstream checksums, headers and row counts", fontsize=11.5, color=C["pipe"][1], fontweight="bold")
    box(ax, 1.2, 26, 45, 19, "On failure: later stages BLOCKED (not run, stale outputs removed)\nExit code names the first failed stage: 4 source, 7 validation,\n8 model, 9 metrics, 10 sensitivity, 11 orchestration\nWeather-only problem: exit 6, core outputs unaffected", "aud", 10.8, align="left")
    box(ax, 50, 26, 48.6, 19, "outputs/pipeline/: run_manifest.json (run id, snapshot ids, config\nfingerprint, per-stage status, output SHA-256), stage_summary.csv,\npipeline_controls.csv (P01-P11), runtime_summary.json, run_log.jsonl\nAtomic writes; same inputs give byte-identical outputs", "pipe", 10.8, align="left")
    ax.text(1.2, 16.5, "Default run is OFFLINE: it never downloads. A missing raw source fails with exit 4 and names python -m src.pipeline.fetch.", fontsize=11.5, color=INK)
    ax.text(1.2, 11.5, "Resume: --resume-from <stage> re-runs from that stage; reused stages are checked against the last manifest, never trusted because a file exists.", fontsize=11.5, color=INK)
    ax.text(1.2, 6.5, "Reproducible: a clean clone reproduced every output byte for byte and passed the full test suite.", fontsize=11.5, color=INK, style="italic")
    save(fig, "pipeline.png")


# 5. M1 / M2 DISTRIBUTION -------------------------------------------------------------------
def weight_distribution():
    """Reads outputs/model/fact_dining_session.csv (regenerate it first: python -m src.pipeline.run)."""
    import csv

    with (OUT.parent / "outputs" / "model" / "fact_dining_session.csv").open(newline="", encoding="utf-8") as fh:
        weights = [float(r["derived_selected_meal_weight_g"]) for r in csv.DictReader(fh)
                   if r["population"] == "registered_export" and r["core_ready"] == "true" and r["derived_selected_meal_weight_g"]]
    weights.sort()
    n = len(weights)
    m1 = (weights[(n - 1) // 2] + weights[n // 2]) / 2
    pos = 0.9 * (n - 1)
    lo = int(pos)
    m2 = weights[lo] + (pos - lo) * (weights[min(lo + 1, n - 1)] - weights[lo])
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=110)
    ax.hist(weights, bins=range(0, 3501, 50), color=C["der"][0], edgecolor=C["der"][1], lw=1.0)
    ax.axvline(m1, color=C["obs"][1], lw=2.4)
    ax.axvline(m2, color=C["gap"][1], lw=2.4, ls="--")
    top = ax.get_ylim()[1]
    ax.text(m1 + 15, top * 0.94, f"M1 median\n{m1:,.0f} g", color=C["obs"][1], fontweight="bold", va="top")
    ax.text(m2 + 15, top * 0.94, f"M2 P90\n{m2:,.1f} g", color=C["gap"][1], fontweight="bold", va="top")
    ax.set_xlim(0, 3500)
    ax.set_xlabel("Derived selected meal weight per session (grams, sum of component weighing events)")
    ax.set_ylabel(f"Sessions (n = {n:,})")
    ax.set_title("Derived selected meal weight, registered-export core-ready sessions", loc="left", fontsize=15, fontweight="bold", color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, -0.02, "Population: core_ready_registered_export_sessions (baseline; 50 g bins). Weight is derived from observed component events. It is what was selected at the\n"
             "lunch line, not what was consumed and not food waste. P90 uses linear interpolation. Source: outputs/model/fact_dining_session.csv.", fontsize=9, color="#4b5563", va="top")
    save(fig, "weight-distribution.png")
    return n, m1, m2


if __name__ == "__main__":
    source_map()
    workflow()
    data_model()
    pipeline()
    print("weight-distribution", weight_distribution())
    print("ok")
