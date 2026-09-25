# The FDE judgement

**My one judgement.** I trust the reconstructed selected-meal measurement layer to describe what was selected at the lunch line, and I would not base a food-waste decision on it. The next thing worth going after is tray-linked waste evidence, not a waste estimate built from selection.

This is an FDE-style reconstruction using publicly available Flavoria research data and public weather data. The judgement below is about what that public evidence can and cannot support. It says nothing about Flavoria's actual internal systems, which I have never seen.

## 1. Decision / question

*Can I reconstruct a trustworthy operational view of dining measurements from the available source data, and is that evidence sufficient to support a future food-waste decision?*

The decision on the table is whether to commit to a food-waste measurement or reduction programme on this evidence, or to go get more data first. I land on the second.

## 2. Evidence

| Evidence | Value | Where |
|---|---|---|
| Observed component weighing events | 12,284 across 11 files, 35 weekday lunches | `outputs/ingestion/`, `docs/data_provenance.md` |
| Sessions reconstructed and measurement-ready | 1,697 of 1,699 registered-export sessions (M5 99.88%) | `outputs/metrics/metrics.csv` |
| Typical derived selected meal weight | M1 499 g; upper end M2 1,039.6 g | `outputs/metrics/metrics.csv` |
| Robustness of the median | M1 stays within 493-505 g across the comparable scenarios | `outputs/evidence/`, `docs/sensitivity_analysis.md` |
| Robustness of the upper end | M2 ranges 977-1,066 g; it is SENSITIVE to the study period | same |
| Waste | W1 BLOCKED / SOURCE GAP; no scenario produces a waste estimate, band or proxy | `docs/source_map.md` section 6, `outputs/evidence/evidence_matrix.csv` |
| Consumption | UNKNOWN; classified BLOCKED in the evidence matrix | same |
| Dependability | six gated stages, offline, byte-identical reruns, failure injection, clean-clone reproduction | `docs/pipeline.md`, `outputs/pipeline/` |

The pattern here is simple: the scales weigh what is placed on the tray, so I can reconstruct a selected-meal layer reproducibly. But **selected meal weight is not actual consumption, and actual consumption is not food waste.** The one quantity that would actually measure waste sits in a source that is documented but not publicly accessible in the required usable form.

## 3. What the evidence supports

- Describing what was selected at the lunch line for the registered-export population, with a stated range: a median of 499 g and a P90 of 1,039.6 g over 1,697 sessions.
- Trusting the pipeline's readiness: it is dependable enough to extend, with 99.88% of eligible sessions core-ready and every number I show traceable back to a checksummed raw file.
- Prioritising what data to go get next, because the evidence shows precisely what is missing.

## 4. What the evidence does not support

- Any statement about what was consumed, left over or wasted.
- A waste-reduction target, saving or impact figure.
- Treating selected weight as a proxy for waste: nothing in the data links selection to what was returned.
- Conclusions about all operations, other periods or other capture systems. The data is five weeks of research capture in autumn 2020, and the non-registered export has a different profile.
- Causal statements about weather, which is context only.

## 5. Critical missing evidence

**Tray-linked waste weight.** Flavoria's waste documentation describes a per-tray waste total, but its sample section reads "TODO, Ask!", the detail sits in a restricted repository, and there is no public download, API, schema or contact. Until that record exists in an accessible form, W1 stays BLOCKED and consumption stays UNKNOWN.

## 6. What we would ask for next

The additional data that would most reduce my uncertainty, in priority order:

1. **Accessible waste-point event records with tray-linked waste weights** (tray identifier, waste time, weight, waste point, and any imputed-value flag). This is the only item that changes the business answer.
2. **Reliable consumption or leftover semantics, if the source defines them**: what a waste reading includes, and how missing days are handled (the catalogue itself warns of imputed days).
3. **Source definitions of the registered and non-registered populations**, so the primary population can be read in business terms.
4. **Source confirmation of the timestamp semantics of the one suspect export**, which currently rests on evidence rather than confirmation.
5. **Stable operational event definitions**: what starts and ends a tray pass, and how scales are tared.

### The concrete request (item 1, ready to send)

This is what I would actually ask the source owner for, so it can be evaluated the moment it exists instead of staying a description in the abstract:

| Field | Type | Meaning |
|---|---|---|
| `tray_id` | string | the same identifier already present in the public lunch-line export, so it can be linked to `fact_weighing_event.tray_id` without a fuzzy match |
| `waste_time` | timestamp | when the waste weighing happened, in the same convention (stated timezone) the source uses for its own clocks |
| `waste_weight_g` | integer, grams | the weight measured at the waste point |
| `waste_point` | string | which station or bin recorded it, analogous to `scale_identifier` on the selection side |
| `imputed` | boolean | whether this row was filled in rather than measured (the catalogue's own documentation warns some days are imputed; without this flag, an imputed day would look identical to a measured one) |

**Grain.** One row per waste-weighing event, the same grain as `fact_weighing_event` on the selection side.
**Join key.** `tray_id`, restricted to a time window around the tray's session (its first and last weighing plus a bounded margin, since a tray is returned some time after the meal, not instantly).
**Format.** Any structured export (CSV, JSON or a REST endpoint) that preserves these five fields is sufficient; none of the pipeline's retrieval or validation code assumes a particular format beyond that.

**What I don't know yet, and what this cannot promise.** Whether `tray_id` in the waste system matches the public lunch-line export's `tray_id` one-to-one, or whether the waste system uses a different identifier entirely, is unverified: the waste schema itself is not public. If a request like this gets fulfilled, the join and its consistency would still need the same validation treatment I already give every other join in this project, checked, not assumed, before I would trust any waste number that came out of it.

## 7. Why that evidence changes the future decision

The documented waste record is a per-tray weight returned at a waste station, so it is the natural counterpart of the selected side I already have. This project already produces the selected side reproducibly and keeps `tray_id` and time on every session. If waste records with a tray identifier and time become available, I could finally compare the two sides as observations instead of guesses, and a waste decision would rest on measurement instead of assumption. Whether the two sources actually join cleanly is **not yet verified**, because the waste schema is not public. Without that source, any waste figure I produced would be an assumption dressed up as a result, which is exactly why I don't produce one.

## How this is shown in the demo

The demo shows the weight distribution with M1 and M2 (what was selected), then the source-gap evidence (what was not observed), and ends on this judgement: I can measure what was selected with reasonable reproducibility, but the current evidence cannot tell me what was consumed or wasted, so the next thing worth getting is direct waste-linked evidence, not a waste proxy. See `demo_script.md`.
