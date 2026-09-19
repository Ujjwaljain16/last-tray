# Demo Script (3 to 5 minutes)

The demo explains one FDE judgement: **we can measure what was selected at the lunch line with reasonable reproducibility, but the current evidence cannot tell us what was consumed or wasted, so the next data requirement is direct waste-linked evidence rather than a waste proxy.** Engineering is shown only where it proves dependability. No Python classes are explained.

Framing to say once, early: this is an FDE-style reconstruction using publicly available Flavoria research data and public weather data, not an analysis of Flavoria's operational systems.

## Before recording

```
python -m src.pipeline.run                 # about 10 seconds; regenerates outputs/
```

Have open: `README.md`, `docs/source_map.md`, `docs/final_evidence.md`, `diagrams/workflow.png`, `diagrams/weight-distribution.png`, `outputs/evidence/evidence_matrix.csv`, `docs/judgement_call.md`, and a terminal at the repository root.

## Timeline

| Time | Show | Say |
|---|---|---|
| 0:00-0:30 | `README.md`, sections 1-3 | "The question: can we reconstruct a trustworthy view of dining measurements from the data available, and is it enough to support food-waste decisions? Public research data, so the answer has to be honest about what is not there." |
| 0:30-1:15 | `docs/source_map.md`, section 2 | "Five sources, four classes. The scales are authoritative for what was selected. FMI is context only. The catalogue and the Weigh & Dine page are documentation. The waste source is documented but not publicly accessible: that is the decisive gap." |
| 1:15-2:00 | `diagrams/workflow.png`, then the terminal: `python -m src.pipeline.run` finishing with `6 PASSED`; open `outputs/pipeline/pipeline_controls.csv` | "Raw files are pinned by checksum, then staging, validation, the canonical model, metrics, and sensitivity. Each stage re-verifies the one before it. Eleven pipeline controls pass, including an 18-link provenance chain from raw file to evidence." |
| 2:00-2:45 | `docs/final_evidence.md` headline table, then `diagrams/weight-distribution.png` | "M1 median 499 grams, M2 P90 1,039.6 grams over 1,697 sessions; five components at the median; 99.88 percent of eligible sessions are measurement-ready. These are derived selected meal weights: what was placed on the tray." |
| 2:45-3:30 | `outputs/evidence/evidence_matrix.csv` (Robustness column) | "26 scenarios. The median is stable at 493 to 505 grams. The upper end is sensitive to the study period. Valid-session count depends on one timezone assumption that the source has not confirmed; +2, +3 and +4 hours agree, 0 and +1 do not." |
| 3:30-4:15 | `diagrams/workflow.png` (lower half) and the W1 row of `docs/final_evidence.md` | "Selected weight is not consumption, and consumption is not waste. Waste is BLOCKED: the sample section of the waste documentation reads 'TODO, Ask!' and there is no public download. I did not build a proxy." |
| 4:15-5:00 | `docs/judgement_call.md` | "The judgement: we can measure what was selected, reproducibly, but the current evidence cannot tell us what was consumed or wasted. The next data requirement is tray-linked waste records, not a waste estimate. If that source becomes available, selection and return can be compared as observations." |

## Optional 30-second dependability proof (if time allows, inside the 1:15-2:00 slot)

```
python -m src.pipeline.run --out ../demo_out
echo tampered >> ../demo_out/model/fact_dining_session.csv
python -m src.pipeline.run --out ../demo_out --resume-from metrics
```

Expected: the model stage fails (exit code 8), metrics and sensitivity are BLOCKED, and their stale outputs are removed. "Nothing is trusted because a file exists." Delete `../demo_out` afterwards.

## What not to say

- Do not make any statement about intake, consumption or waste, or say that anything caused anything.
- Do not describe M3 as demand or as how many people came.
- Do not call the +3h timezone confirmed.
- Do not describe the scenarios as alternative truths: they are sensitivity tests.

## Checklist

- [ ] `python -m src.pipeline.run` exits 0 and prints `6 PASSED`
- [ ] the numbers on screen equal `docs/final_evidence.md`
- [ ] the judgement is stated as conditional, once, at the end
