# Phase 2 Validation Findings and Final Thresholds

**Status: thresholds approved 2026-09-19.** They are diagnostic validation thresholds derived from the observed structure of this data, not claims of physical impossibility or universal abnormality. The authoritative rule table is `validation_rules.md`.

Draft rules from `docs/validation_rules.md` were applied to the real data by `research/phase2/phase2_d_findings.py`. Output: `outputs/validation/validation_issues.csv` (1,278 rows) and `validation_summary_by_rule.csv`. **Nothing was deleted or excluded from the raw or staging data.** "Handling" describes what the production pipeline will do.

Severity: **ERROR** breaks `core_ready`. **WARN** is visible and kept. **INFO** records a fact.

## 1. Results by rule (rows = issues; entity is an event, session, file or day)

| Rule | Description | Severity | registered-export | non-registered-export | Handling |
|---|---|---|---:|---:|---|
| S03 | optional `weighting_type` absent | INFO | 4 files | 3 files | FLAG |
| T08 | dotted timestamp format | INFO | 1 file | 1 file | FLAG |
| T07 | file median first-event hour outside 10:00-11:00 | WARN | 1 file | 0 | FLAG; +3h normalisation via override |
| I01 | session in both populations | ERROR | 2 sessions | 2 sessions | QUARANTINE |
| I02 | exact duplicate event rows | WARN | 1 | 1 | keep first |
| I06 | cross-export version disagreement | WARN / INFO | 1 session (`session3222`) + 1 exact duplicate (`session2266`) | | FLAG |
| B02 | event weight at or above the threshold | WARN | 3 | 3 | FLAG |
| B03 | trace weight, 3 g or less | INFO | 99 | 413 | FLAG |
| B04 | single-event session | WARN | 17 | not applied | FLAG |
| B05 | same scale weighed repeatedly in a session | INFO | 212 sessions | 10 sessions | FLAG; summed |
| B07 | derived session weight outside range | WARN | 15 (7 low, 8 high) | 470 | FLAG |
| T04 | identification before last weighing | WARN | 2 | 1 | FLAG |
| T05 | session span above threshold | WARN | 7 | 0 | FLAG |
| T03 | event outside service hours (after tz rule) | ERROR | **0** | **0** | n/a |
| S01, S02, S05, S06, S07, B01, T01, I04 | structural, positive weight, window, one tray per session | ERROR | **0** | **0** | pass |
| C02 | volume irregularity vs weekday regime | WARN | 6 days | n/a | FLAG `volume_irregularity`; retained |
| C02 | days under 30 sessions | INFO | 16 of 35 days | | FLAG `low_observed_volume_day` |
| C03 | expected export file missing | WARN | | 1 (2020-11-16..20) | FLAG |

## 2. What the findings say

1. **The registered-export population is structurally clean.** Two ERROR rows (the crossover sessions) and no other ERROR-level violation. That makes M5 high but honest (section 4).
2. **Almost all issues are WARN or INFO and concern interpretation, not corruption:** long sessions, single-item lunches, heavy-tail weights, repeat scoops.
3. **The non-registered-export population fails B07 for 470 sessions.** That is the population finding, not 470 data errors.
4. **Two issues would silently harm results if unhandled:** the timezone shift (T07) and cross-export identity (I01).

## 3. Proposed final thresholds

Each threshold is placed where the data shows a natural gap or a defined tail, not at a round number chosen in advance. All are declared in `config/thresholds.yml` with this rationale.

| Rule | Proposed threshold | Evidence (registered-export unless stated) | Severity | Alternatives considered |
|---|---|---|---|---|
| **B02** event weight | **>= 1,500 g** | P99.5 = 996 g, P99.9 = 1,252 g. Hot-scale P99.9 across all data = 1,449 g. Threshold sits just above it, flagging 6 events (3 registered). A ">1,000 g" rule would flag 0.5% of events, i.e. ordinary tail. | WARN | P99.9 (1,252 g): flags 9 registered events, reads as ordinary tail |
| **B03** trace weight | **<= 3 g** | 1.18% of registered events, 10.6% of non-registered. | INFO | none; informational only |
| **B04** single-event session | **= 1 event** (registered-export only) | 17 sessions (1.0%). 10 exceed 100 g, 6 are 50 g or less. | WARN | excluding them moves M1 by +2 g |
| **B05** repeated scale | any repeat | 93.8% within 30 s, 100% same name, additive | INFO | a 30 s gap threshold is unnecessary and **B06 is retired** as a separate rule |
| **B07** session weight | **outside [50, 2,200] g** | P0.5 = 56 g, P99.5 = 2,156 g. Yields 7 low and 8 high registered-export sessions (0.9%). | WARN | percentile bounds computed per run would move with the data, so fixed values are used |
| **T03** service window | **09:00 to 15:00 local** (after tz rule) | Observed 10:13 to 14:43 local. Zero violations. | ERROR | only meaningful once the tz rule is applied |
| **T04** identification order | identification < last weighing | 3 sessions | WARN | n/a |
| **T05** session span | **> 600 s** | Registered spans jump from 545 s to 1,783 s; 600 s sits inside the gap. 7 sessions. Within-session gap P99.9 = 218 s. | WARN | 300 s would add only 1 more session |
| **T07** file timezone check | **median first-event hour in [10.0, 11.0)** | Ten files: 10.48-10.58. Suspect file: 7.54. | WARN | n/a |
| **C01** service-day coverage | 35 of 35 weekdays | met overall; non-registered 30 | WARN | n/a |
| **C02a** low observed volume | **registered-export sessions < 30** | registered-export daily counts have a gap between 22 and 41 (lows <= 22, highs >= 41) | INFO flag | fixed threshold, not statistical z-scores: the distribution is bimodal, so a median/MAD rule mislabels Thursdays |
| **C02b** volume irregularity | **observed regime differs from the weekday's regime** (Mon-Wed high, Thu-Fri low) | derived from Oct 5-30, where separation is perfect (Mon-Wed >= 41, Thu-Fri <= 12). 6 days break it. | WARN flag | the weekday pattern is a **hypothesis from four weeks**, so days are flagged and never excluded |
| **X01** weather hour coverage | 100% of required hours | 1,129 of 1,129 | WARN | n/a |
| **X02** session weather match | reported, INFO | 1,697 of 1,697 matched | INFO | context only |
| **X03** precipitation NULL | reported, INFO | 67 sessions (`r_1h`), 25 (`ri_10min`) | INFO | never imputed |

## 4. Core measurement readiness (M5), definition as proposed

- **Numerator:** primary-population sessions with **no ERROR-level violation** and no identity conflict, weights all valid, timestamps parsed.
- **Denominator:** all registered-export session IDs in the source (**1,699**), fixed before any record is removed.
- **Preview:** 1,697 of 1,699 = **99.88%**.
- **Supporting diagnostic (not a KPI):** *warn-free rate* = 1,663 of 1,699 = **97.88%** (session-level WARNs; 34 sessions carry one). Also counting event-level WARNs (B02, I02: three more sessions) gives 1,660 of 1,699 = 97.70%, a reconciled diagnostic (`decision_log.md` D28, `metric_contract.md`). The denominator is the fixed 1,699 in both.
- Weather, precipitation NULLs, volume irregularity and timezone status **never** enter M5.

## 5. Handling policy summary

| Class | Applies to |
|---|---|
| **QUARANTINE** (kept in model, excluded from primary metrics, listed) | crossover sessions (I01), events outside service hours (T03, none today), structural failures |
| **FLAG, kept in metrics** | every WARN and INFO row above |
| **Exclude duplicates from sums** | the 2 exact duplicate rows |
| **Never excluded for being unusual** | Nov 16-20 and all volume-irregularity days; the 2,097 g event; single-event sessions |

## 6. Provisional caveat on B07 for the non-registered-export population

B07 and B04 exist to protect the primary KPIs. Applied to the non-registered-export population they fire in huge numbers because that population behaves differently. They are reported there as a **diagnostic** contrast, never as a cleaning action.
