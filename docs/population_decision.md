# Population Decision

**Decision.** The archive contains two exports. We keep them as **separate populations**, never pooled:

- **registered-export population** (primary, feeds the KPIs)
- **non-registered-export population** (diagnostic / source-quality only)

## 1. What these labels are, and are not

The labels are **inherited from the source filenames** (`registered_*.csv`, `non_registered_*.csv`). The public documentation reviewed for this project does not define their business meaning. **We therefore use them only as population labels. We do not interpret "registered" as customer-registration status**, and we never write "registered diners", "registered customers", "registered users" or "registered meals". Code values are `registered_export` and `non_registered_export`. Session keys are `(session_id, population)`.

## 2. Evidence that the populations behave differently

Phase 2 profile, the two crossover sessions excluded from both (`outputs/phase2/population_profile.csv`):

| Measure | registered-export | non-registered-export |
|---|---:|---:|
| Sessions | 1,697 | 1,644 |
| Weighing events | 8,360 | 3,900 |
| Events per session, mean / median | 4.93 / 5 | 2.37 / 2 |
| Single-event sessions | 17 (1.00%) | 620 (37.71%) |
| Sessions with a hot-food scale | 97.2% | 74.9% |
| Derived selected weight, P10 / median / P90 | 314 / 499 / 1,040 g | 4 / 192 / 855 g |
| Sessions under 50 g | 0.41% | 28.41% |
| Median distinct components | 5 | 2 |
| Session span, median / P99 | 71 s / 155 s | 24 s / 122 s |
| Service days covered | 35 of 35 | 30 (ends 2020-11-13) |
| Daily sessions | 2 to 107, **bimodal by weekday** | 36 to 75, flat |

A 4 g tenth-percentile "meal" is not a plausible plate. It reads as a fragment of what was taken, or an item picked up outside a weighed station; the data cannot say which.

## 3. Why the registered-export population is primary

1. **Capture shape matches the workflow the KPIs describe.** 97% of its sessions include a hot-food scale and about 5 components, consistent with a full lunch tray.
2. **Coverage is complete.** All 35 service days.
3. **The other population's shape is unexplained**, so including it would mean guessing.

## 4. Why the non-registered-export population is kept, not dropped

It is the clearest evidence in the repository of a **capture-behaviour difference**, and it is reported in `outputs/metrics/population_diagnostics.csv`, labelled `DIAGNOSTIC`, never mixed into a KPI. It also gives the daily-volume contrast that shows registered-export volume is not a demand signal (Section 5).

## 5. Consequences we accept

- **Selection risk.** We do not know how sessions enter each export. KPIs describe the registered-export population, not "the average diner".
- **M3 is not a demand indicator.** Registered-export daily volume follows a weekday pattern (Mon-Wed 41-107 sessions, Thu-Fri 2-18 in the four baseline weeks) that the non-registered-export population does not share, and six days break it. So M3 is *observed valid sessions in the registered-export population*.
- We do not know why non-registered-export sessions look partial (Q2).

## 6. Crossover sessions

`session2266` (identical in both exports) and `session3222` (timestamps differ by exactly 10,800 s; 2 of 6 component names differ) appear in both. They are **quarantined** until the client says which record is authoritative. Primary population: 1,699 IDs minus 2 = **1,697** candidate sessions. Including them would move M1 by 0.0 g and M2 by +2.8 g.

## 7. Residual uncertainty

The mechanism that splits the two exports; whether registered-export capture is subtly incomplete in ways single-event counts cannot show; whether the weekday volume pattern reflects participation, scheduling or export filtering. Confirmation from the source owner is required before any claim that generalises beyond this export.
