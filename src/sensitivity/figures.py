"""Four compact figures for the sensitivity story. Deterministic (fixed backend, size, dpi and metadata) so the PNG bytes repeat exactly.

Design: neutral ink for text, one accent for the approved baseline, robustness class encoded by SHAPE as well as colour (circle STABLE,
diamond SENSITIVE, square CONDITIONAL), direct value labels only where they matter, a title stating the metric and population, units on
every axis, and a note that scenarios are sensitivity tests and not alternative truths.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.fsutil import atomic_path  # noqa: E402
from src.sensitivity import classify as cl  # noqa: E402
from src.sensitivity.evidence import Analysis, is_comparable, value_of  # noqa: E402
from src.sensitivity.registry import SCENARIOS, SCENARIO_BY_ID  # noqa: E402

INK, MUTED, GRID, ACCENT = "#1f2933", "#5f6b7a", "#e4e7eb", "#2563eb"
CLASS_STYLE = {"STABLE": ("o", "#6b7280"), "SENSITIVE": ("D", "#b45309"), "CONDITIONAL": ("s", "#b91c1c")}
NOTE = "Scenarios are sensitivity tests, not alternative truths. The baseline is the approved interpretation."
FIGURES = ("m1_m2_sensitivity.png", "m5_readiness_what_if.png", "timezone_evidence.png", "period_and_volume_tests.png")


def _style(ax) -> None:
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)


def _top(fig) -> float:
    """Top of the plot area, leaving room (in inches) for the title and subtitle."""
    return 1 - 1.05 / fig.get_size_inches()[1]


def _finish(fig, path: Path, title: str, subtitle: str) -> None:
    h = fig.get_size_inches()[1]
    fig.text(0.01, 1 - 0.14 / h, title, ha="left", va="top", fontsize=11, color=INK, fontweight="bold")
    fig.text(0.01, 1 - 0.50 / h, subtitle, ha="left", va="top", fontsize=8.5, color=MUTED)
    fig.text(0.01, 0.15 / h, NOTE, ha="left", va="bottom", fontsize=7.5, color=MUTED)
    with atomic_path(path) as tmp:
        fig.savefig(tmp, dpi=120, format="png", metadata={"Software": None})
    plt.close(fig)


def _label(spec) -> str:
    return f"{spec.scenario_id}  {spec.name}"[:46]


def fig_m1_m2(a: Analysis, path: Path) -> None:
    specs = [s for s in SCENARIOS if is_comparable(s) and s.scenario_id != "S00" and "M2" in s.metrics_recalculated]     # M4-definition variants do not recompute M1/M2
    classes = {(m["metric_id"], m["scenario_id"]): m["robustness_class"] for m in a.metric_rows}
    fig, axes = plt.subplots(1, 2, figsize=(11, 8.2), sharey=True)
    fig.subplots_adjust(left=0.30, right=0.97, top=_top(fig) - 0.03, bottom=0.16, wspace=0.10)
    for ax, metric in zip(axes, ("M1", "M2")):
        base = value_of(a.results["S00"], metric)
        for i, s in enumerate(specs):
            v = value_of(a.results[s.scenario_id], metric)
            marker, color = CLASS_STYLE[classes[(metric, s.scenario_id)]]
            ax.plot([v], [i], marker=marker, color=color, markersize=7, markeredgecolor="white", markeredgewidth=1.2, linestyle="none")
            if classes[(metric, s.scenario_id)] != "STABLE":
                ax.annotate(f"{v:,.1f}", (v, i), xytext=(7, 0), textcoords="offset points", fontsize=7.5, color=INK, va="center")
        ax.axvline(base, color=ACCENT, linewidth=1.6)
        ax.set_title(f"{metric}: baseline {base:,.1f} g (blue line)", fontsize=9, color=ACCENT, loc="left")
        ax.margins(x=0.12)
        ax.set_yticks(range(len(specs)))
        ax.set_yticklabels([_label(s) for s in specs], fontsize=7.5, color=INK)
        ax.invert_yaxis()
        ax.set_xlabel(f"{metric} ({'median' if metric == 'M1' else '90th percentile'} of derived selected meal weight, g)", fontsize=8.5, color=MUTED)
        _style(ax)
    handles = [plt.Line2D([], [], marker=m, color=c, linestyle="none", markersize=7, label=f"{k.lower()} ({'circle' if k == 'STABLE' else 'diamond' if k == 'SENSITIVE' else 'square'})") for k, (m, c) in CLASS_STYLE.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.62, 0.035))
    _finish(fig, path, "M1 and M2 across the registered-export sensitivity scenarios",
            "Population: core-ready registered-export sessions (1,697 in the baseline). Derived selected meal weight is not consumption or waste.")


def fig_m5(a: Analysis, path: Path) -> None:
    ids = ["S00", "S01", "S02", "S03", "TZ0", "TZ1", "TZ2", "TZ3", "TZ4"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    fig.subplots_adjust(left=0.36, right=0.96, top=_top(fig), bottom=0.16)
    base = a.results["S00"].m5
    labels = {"S01": "what-if: both crossover sessions counted", "S02": "what-if: session2266 counted", "S03": "what-if: session3222 counted"}
    for i, sid in enumerate(ids):
        v = a.results[sid].m5
        ax.barh(i, v - 75, left=75, height=0.55, color=ACCENT if sid == "S00" else "#9aa5b1", edgecolor="white")
        ax.annotate(f"{v:.2f}%", (v, i), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8, color=INK)
    ax.axvline(base, color=ACCENT, linewidth=1.4)
    ax.set_yticks(range(len(ids)))
    ax.set_yticklabels([("S00  approved baseline" if s == "S00" else f"{s}  {labels.get(s, 'suspect export shifted ' + s[2:] + 'h' if s.startswith('TZ') else '')}") for s in ids], fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(75, 112)
    ax.set_xlabel("M5 core measurement readiness (%, denominator fixed at 1,699 eligible registered-export sessions)", fontsize=8, color=MUTED)
    ax.annotate("<- quarantine lifted:\n    not a valid\n    readiness figure", (104.2, 1), ha="left", va="center", fontsize=7.5, color="#b91c1c")
    _style(ax)
    _finish(fig, path, "M5 readiness under what-if treatments and timezone hypotheses", "Population: eligible registered-export sessions (C). Only the suspect export is shifted; +3h is evidence-backed, not source-confirmed.")


def fig_timezone(a: Analysis, path: Path) -> None:
    tz = a.timezone
    fig, (l, r) = plt.subplots(1, 2, figsize=(10, 4.4))
    fig.subplots_adjust(left=0.08, right=0.98, top=_top(fig) - 0.04, bottom=0.19, wspace=0.28)
    hours = [row["offset_hours"] for row in tz]
    l.axhspan(10, 11, color="#dbeafe", zorder=0)
    l.axhline(tz[0]["other_registered_files_median_hour"], color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    l.plot(hours, [row["median_first_event_hour"] for row in tz], color=INK, linewidth=1.2, zorder=1)
    for row in tz:
        l.plot([row["offset_hours"]], [row["median_first_event_hour"]], marker="o" if not row["is_baseline"] else "D", color=ACCENT if row["is_baseline"] else "#6b7280", markersize=8,
               markeredgecolor="white", markeredgewidth=1.2, zorder=2)
        l.annotate(f"{row['median_first_event_hour']:.2f}", (row["offset_hours"], row["median_first_event_hour"]), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=8, color=INK)
    l.annotate("shaded: T07 band, 10-11 h", (0.05, 10.78), fontsize=7.5, color=MUTED)
    l.annotate(f"other registered-export files: {tz[0]['other_registered_files_median_hour']:.2f} h", (0.05, 10.28), fontsize=7.5, color=MUTED)
    l.set_xticks(hours)
    l.set_xticklabels([f"+{h}h" for h in hours])
    l.set_xlabel("offset applied to the suspect export only", fontsize=8, color=MUTED)
    l.set_ylabel("median first-event hour (local time, h)", fontsize=8, color=MUTED)
    l.set_title("Time of day", fontsize=9, color=INK, loc="left")
    _style(l)
    l.grid(axis="y", color=GRID)
    r.bar(hours, [row["t03_quarantined_sessions"] for row in tz], width=0.55, color=["#2563eb" if row["is_baseline"] else "#9aa5b1" for row in tz], edgecolor="white")
    for row in tz:
        r.annotate(str(row["t03_quarantined_sessions"]), (row["offset_hours"], row["t03_quarantined_sessions"]), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8, color=INK)
    r.set_xticks(hours)
    r.set_xticklabels([f"+{h}h" for h in hours])
    r.set_xlabel("offset applied to the suspect export only", fontsize=8, color=MUTED)
    r.set_ylabel("sessions outside service hours (T03), of 385", fontsize=8, color=MUTED)
    r.set_title("Sessions the service-hours rule would quarantine", fontsize=9, color=INK, loc="left")
    _style(r)
    r.grid(axis="y", color=GRID)
    r.grid(axis="x", visible=False)
    _finish(fig, path, "Timezone hypotheses for the suspect registered export (385 sessions)",
            "KPIs M1-M4 cannot separate +2h, +3h and +4h; the time-of-day evidence favours +3h. Population: sessions of the shifted file.")


def fig_exclusions(a: Analysis, path: Path) -> None:
    ids = ["S20", "S21", "S22", "S23"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True)
    fig.subplots_adjust(left=0.22, right=0.98, top=_top(fig) - 0.02, bottom=0.2, wspace=0.12)
    panels = (("M1", "change in M1 (g)"), ("M2", "change in M2 (g)"), ("M3", "sessions left out"))
    base = a.results["S00"]
    for ax, (metric, label) in zip(axes, panels):
        for i, sid in enumerate(ids):
            r = a.results[sid]
            v = (value_of(r, metric) - value_of(base, metric))
            v = -v if metric == "M3" else v
            cls = next(m["robustness_class"] for m in a.metric_rows if m["metric_id"] == metric and m["scenario_id"] == sid)
            ax.barh(i, v, height=0.5, color=CLASS_STYLE[cls][1], edgecolor="white")
            ax.annotate(f"{v:+,.1f}" if metric != "M3" else f"{v:,.0f}", (v, i), xytext=(5 if v >= 0 else -5, 0), textcoords="offset points", ha="left" if v >= 0 else "right", va="center", fontsize=8, color=INK)
        ax.axvline(0, color=ACCENT, linewidth=1.4)
        ax.set_xlabel(label, fontsize=8, color=MUTED)
        ax.margins(x=0.25)
        _style(ax)
    axes[0].set_yticks(range(len(ids)))
    axes[0].set_yticklabels([_label(SCENARIO_BY_ID[s]).replace("Exclude ", "").replace("Period sensitivity: ", "period: ")[:40] for s in ids], fontsize=8, color=INK)
    axes[0].invert_yaxis()
    _finish(fig, path, "Period and volume-day exclusion tests (diagnostic only; nothing is excluded in the pipeline)",
            "Population: core-ready registered-export sessions. Bar colour = robustness class (grey stable, amber sensitive, red conditional). Baseline = 0.")


def write_figures(a: Analysis, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_m1_m2(a, out_dir / FIGURES[0])
    fig_m5(a, out_dir / FIGURES[1])
    fig_timezone(a, out_dir / FIGURES[2])
    fig_exclusions(a, out_dir / FIGURES[3])
