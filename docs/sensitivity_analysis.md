# Sensitivity Analysis

**Purpose.** Show that assumptions were **tested rather than selected for favourable KPI results**. Every scenario recomputes M1-M5 under one alternative assumption. Machine-readable: `outputs/validation/sensitivity_analysis.csv` (25 scenarios). Produced by `research/phase2/phase2_e_sensitivity.py`; the pipeline will regenerate it on every run and its baseline row must equal the headline KPIs.

Thresholds and the materiality convention below are **diagnostic conventions derived from this data**, not claims of physical or practical significance. **Materiality convention:** |ΔM1| ≥ 10 g, |ΔM2| ≥ 25 g, or ΔM4 ≠ 0 relative to baseline.

## Results

Baseline S00: registered-export population, 1,697 canonical sessions, eligible denominator 1,699.

| ID | Scenario | M1 g | M2 g | M3 | M4 | M5 | ΔM1 | ΔM2 | Material |
|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|
| **S00** | **Baseline** | **499.0** | **1,039.6** | **1,697** | **5** | **99.88%** | 0 | 0 | |
| S01 | Include both crossover sessions | 499.0 | 1,042.4 | 1,699 | 5 | 100.00%* | 0.0 | +2.8 | |
| S02 | Include only `session2266` (exact duplicate) | 499.0 | 1,039.2 | 1,698 | 5 | 99.94%* | 0.0 | -0.4 | |
| S03 | Include only `session3222` (version conflict) | 499.5 | 1,042.6 | 1,698 | 5 | 99.94%* | +0.5 | +3.0 | |
| S04 | Remove the 2,097 g **session** | 499.0 | 1,038.0 | 1,696 | 5 | n/a | 0.0 | -1.6 | |
| S05 | Remove only the 2,097 g **event** | 499.0 | 1,038.0 | 1,697 | 5 | n/a | 0.0 | -1.6 | |
| S06 | Exclude outside data percentiles P0.5-P99.5 | 499.0 | 1,017.0 | 1,679 | 5 | n/a | 0.0 | -22.6 | |
| S07 | Exclude outside [50, 2,200] g (B07) | 499.0 | 1,020.5 | 1,682 | 5 | n/a | 0.0 | -19.1 | |
| S08 | Exclude single-event sessions (B04) | 501.0 | 1,044.2 | 1,680 | 5 | n/a | +2.0 | +4.6 | |
| S09 | Exclude span > 600 s (T05) | 498.0 | 1,037.1 | 1,690 | 5 | n/a | -1.0 | -2.5 | |
| S10 | Exclude any WARN (session or event) | 499.5 | 1,015.0 | 1,660 | 5 | n/a | +0.5 | -24.6 | |
| TZ0 | Override file treated as local (no shift), T03 applied | 505.0 | 989.1 | 1,394 | 5 | 82.05% | +6.0 | -50.5 | **yes** |
| TZ1 | +1h | 498.5 | 1,019.5 | 1,594 | 5 | 93.82% | -0.5 | -20.1 | |
| TZ2 | +2h | 499.0 | 1,039.6 | 1,697 | 5 | 99.88% | 0 | 0 | |
| **TZ3** | **+3h (baseline decision)** | 499.0 | 1,039.6 | 1,697 | 5 | 99.88% | 0 | 0 | |
| TZ4 | +4h | 499.0 | 1,039.6 | 1,697 | 5 | 99.88% | 0 | 0 | |
| S20 | Exclude the 6 volume-irregularity days (test only) | 505.0 | 1,066.0 | 1,445 | 5 | n/a | +6.0 | +26.4 | **yes** |
| S21 | Exclude 2020-11-16..20 (test only) | 499.5 | 1,052.1 | 1,530 | 5 | n/a | +0.5 | +12.5 | |
| S22 | Exclude the 16 low-observed-volume days (test only) | 493.0 | 1,053.0 | 1,507 | 5 | n/a | -6.0 | +13.4 | |
| S23 | Exclude 2020-10-05..16 (the +3h file period) | 505.0 | 977.0 | 1,312 | 5 | n/a | +6.0 | -62.6 | **yes** |
| S30 | M4 with raw names | 499.0 | 1,039.6 | 1,697 | 5 | n/a | 0 | 0 | |
| S31 | M4 as distinct scales | 499.0 | 1,039.6 | 1,697 | 5 | n/a | 0 | 0 | |
| S32 | M4 as weighing events | 499.0 | 1,039.6 | 1,697 | 5 | n/a | 0 | 0 | |
| S33 | Do not exclude the exact duplicate from sums | 499.0 | 1,039.6 | 1,697 | 5 | n/a | 0 | 0 | |
| S40 | DIAGNOSTIC: non-registered-export population | 192.0 | 855.4 | 1,644 | 2 | n/a | (not a KPI) | | |

\* Reaches these values only because the quarantine is lifted; not a valid readiness figure. `n/a`: analytic exclusion, M5 not redefined. The volume scenarios (S20-S22) are **tests only**; the pipeline's volume flags never exclude anything (D19).

## Timezone hypotheses in detail

| Hypothesis | Sessions failing T03 | Weather hour changed (of 385) | Mean absolute temperature difference vs +3h |
|---|---:|---:|---:|
| +0h | 303 | 385 | 1.23 C |
| +1h | 103 | 385 | 0.87 C |
| +2h | 0 | 385 | 0.53 C |
| **+3h** | 0 | 0 | 0 |
| +4h | 0 | 385 | 0.47 C |

## What the analysis shows

1. **M1 is robust:** 493-505 g in every scenario, within about ±1.2% of baseline. **M4 is 5 everywhere.**
2. **M2 is the sensitive metric.** It ranges 977-1,066 g. It moves materially in three scenarios: excluding the first two weeks (-62.6 g), the no-shift timezone hypothesis (-50.5 g), excluding irregular days (+26.4 g). The first is a **period effect**, not a timezone effect (TZ2-TZ4 leave M2 unchanged).
3. **Crossover inclusion cannot change a conclusion:** M2 -0.4 to +3.0 g. Readiness reaches 100% only by lifting the quarantine, which is why the denominator rule exists.
4. **The 2,097 g event is immaterial:** -1.6 g on M2 whether the session or just the event is removed.
5. **The KPIs cannot tell +2h from +3h from +4h.** Only the cross-export evidence (exact 10,800 s on `session3222`; hour-of-day distance 0.046 vs about 1.03) distinguishes them. The +3h decision was taken from that evidence on 2026-09-18, before this comparison was run, and it is tied on every KPI with +2h and +4h; it is therefore not a choice that favours the KPIs.
6. **The no-shift hypothesis is not a neutral alternative:** it would lower M5 to 82.05% by quarantining 303 sessions whose events fall before 09:00. T07 and T03 exist to catch precisely this.
7. **Weather is the only output that depends on the timezone.** Under any non-baseline hypothesis all 385 sessions in the file join a different weather hour.
8. **Warn-free rate:** canonical 97.88% (session-level WARNs) vs 97.70% if event-level WARNs (B02, I02) are also counted; three sessions (`session320`, `session1116`, `session1274`) carry event-level WARNs only (D28).

## How to read this

The sensitivity file is evidence of **assumption testing**, not a confidence interval. A scenario that moves a KPI is a scenario the client should know about; none of them reverses a conclusion.
