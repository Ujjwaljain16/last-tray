# Final Evidence

This is the compact, assessment-facing evidence set. Every value is produced by `python -m src.pipeline.run` and stored in `outputs/metrics/metrics.csv`; a test fails if this page and that file disagree. Metric names and definitions are the approved ones in `metric_contract.md` and are not changed here.

Scope: an FDE-style reconstruction using publicly available Flavoria research data (FlavoriaFoodWeight1700) and public FMI weather data. It is not an analysis of Flavoria's proprietary operational systems, and it does not describe all current dining operations.

## Headline metrics

Population for M1-M4: `core_ready_registered_export_sessions` (1,697 session keys). Population for M5: `eligible_registered_export_sessions` (1,699 session keys). Grain: one session key, `(session_id, population)`.

| Metric | Value | Population | What it tells us | What it does NOT tell us |
|---|---|---|---|---|
| M1 — Median Derived Selected Meal Weight | 499 g | core-ready registered-export sessions | the typical derived selected meal weight | intake: it is derived from weighing events at the line and is not consumption |
| M2 — P90 Derived Selected Meal Weight | 1,039.6 g | core-ready registered-export sessions | the upper end of the derived selected meal weight distribution (P90, linear interpolation) | anything eaten; it is the most period-sensitive metric (five weeks) |
| M3 — Observed Valid Sessions — Registered-Export Population | 1,697 | core-ready registered-export sessions | how many registered-export sessions were observed and are valid | restaurant volume or how many people came: the weekday pattern and six irregular days prevent that reading |
| M4 — Median Distinct Normalized Components per Session | 5 | core-ready registered-export sessions | how many different named components a typical session selected | dish identity across days or exports: there is no alias table |
| M5 — Core Measurement Readiness | 99.88% (1,697 / 1,699) | eligible registered-export sessions | the share of eligible sessions meeting the approved core readiness criteria | that the data is error-free: it is high because few sessions carry an ERROR finding |

## Supporting evidence

| Metric | Value | Population | What it tells us | What it does NOT tell us |
|---|---|---|---|---|
| S2 — Warn-Free Rate | 97.88% (1,663 / 1,699) | eligible registered-export sessions | how many sessions carry no session-level warning | a data-quality score: a warning never removes a session from the KPIs |
| W1 — Direct Food Waste Measurement | BLOCKED / SOURCE GAP | not computable | that no waste figure can be produced from the accessible data | nothing about waste: no estimate, band or proxy exists |

Other supporting diagnostics (S1 weather coverage 99.88%, the S2D reconciliation variant 97.70%) are in `outputs/metrics/metrics.csv` and are deliberately not in the headline table.

## Evidence interpretation

The evidence separates five kinds of statement, and never mixes them.

- **OBSERVED.** 12,284 component weighing events recorded by lunch-line scales across 11 files, plus hourly FMI weather observations (1,129 hours).
- **DERIVED.** The session-level selected meal weight (`derived_selected_meal_weight_g`), the session reconstruction and the readiness status. They follow stated rules applied to observed events.
- **DESCRIPTIVE.** Registered-export session volume: 1,697 valid sessions over 35 weekday lunches in autumn 2020. It describes what the export contains, not restaurant volume.
- **CONTEXTUAL.** Weather coverage: 1,697 of the 1,699 eligible sessions join an FMI hour (S1 99.88%). Weather is context; the analysis makes no causal statement about it.
- **UNKNOWN.** How much of the selected food was consumed. No source measures it.
- **BLOCKED.** Actual food waste. The waste source is documented but not publicly accessible in the required usable form.

Reading M1 and M2: half of the core-ready sessions have a derived selected meal weight at or below 499 g, and one in ten is above 1,039.6 g. These figures describe what was selected at the lunch line and recorded by the scales.

## How firm the evidence is

From the sensitivity analysis (`sensitivity_analysis.md`, `outputs/evidence/`): 25 scenarios reproduced from the earlier profiling plus one forbidden guardrail, classified by declared thresholds.

| Robustness | Count of questions | Examples |
|---|---|---|
| STABLE | 6 | a selected-weight distribution can be reconstructed; the median (M1 stays 493-505 g); the component count (M4 stays 5 across the comparable scenarios); the two crossover sessions; the largest single event; the warn-free rate |
| SENSITIVE | 3 | the upper end (M2 ranges 977-1,066 g); the six irregular-volume days; the study period (dropping the first two weeks moves M2 by about -63 g) |
| CONDITIONAL | 2 | valid-session count and readiness (depend on the timezone reading of one file); which timezone that file uses |
| BLOCKED | 2 | actual consumption; food waste |

The timezone normalisation of one file is an assumption, not a source-confirmed fact: +2h, +3h and +4h give identical M1-M5, while +0h and +1h quarantine 303 and 103 sessions.

## Figures

1. `diagrams/workflow.png`: the observed → derived → unknown → source-gap chain.
2. `diagrams/data-model.png`: the business data model and the session key.
3. `diagrams/weight-distribution.png`: the M1 and M2 distribution.
4. `outputs/evidence/figures/m1_m2_sensitivity.png`: the M1 and M2 ranges across scenarios.
