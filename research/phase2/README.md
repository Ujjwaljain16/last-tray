# research/phase2: historical evidence, not production code

These scripts reproduce the investigations that informed the production design. **The production pipeline (`src/`) is intentionally separate**: it is written fresh, under tests, and uses these results only as regression anchors (`tests/golden/`).

Nothing here is imported by `src/`. Nothing here writes to `data/raw/`.

## Reproduce

From the repository root, in this order (each step reads the raw archive and the preserved weather XML; `a` writes the intermediate pickles the others read):

```bash
python research/phase2/phase2_a_schema_population_tz.py
python research/phase2/phase2_b_sessions_components_volume.py
python research/phase2/phase2_c_names_weather.py
python research/phase2/phase2_d_findings.py
python research/phase2/phase2_e_sensitivity.py
python research/phase2/phase2_f_fmi_semantics.py
python research/phase2/build_notebook_01.py
```

Outputs go to `outputs/phase2/` and `outputs/validation/`. Two runs under different `PYTHONHASHSEED` values produce byte-identical files (checked when these scripts were moved here).

## What each script established

| Script | Investigation | Key result |
|---|---|---|
| `phase2_common.py` | loader and session builder shared by the others | event grain; sessions keyed (`session_id`, `population`) |
| `phase2_a_...` | schema drift, column profile, population profile, timezone, crossover sessions | 7 of 11 files lack a column; two populations differ; +3h supported by an offset scan and one exact 10,800 s session |
| `phase2_b_...` | session diagnostics, component-name stability, spans, daily volume, Nov 16-20, 2,097 g event, 17 single-event sessions | M4 median 5 under four identity definitions; weekday-bimodal volume; six irregular days |
| `phase2_c_...` | name disagreement in 2020-10-05..16; weather join dry run | 86 of 213 scale-days disjoint; 1,697 of 1,697 sessions matched (hour-ending rule) |
| `phase2_d_...` | draft rules applied to real data; `validation_issues.csv`; KPI preview | 1,278 issues, no rows deleted |
| `phase2_e_...` | 25 sensitivity scenarios | `sensitivity_analysis.csv` |
| `phase2_f_...` | FMI `r_1h` timestamp semantics | hour-ending: error 0.021 mm vs 0.378 mm (one rainy day) |
| `build_notebook_01.py` | builds `notebooks/01_source_exploration.ipynb` with real outputs | |

## What is NOT reproduced by a script here (honest limits)

- **Phase 0 source validation** (Zenodo API, Flavoria catalogue pages, FMI endpoint discovery, the original station lookup) was interactive. Its results are recorded in `docs/source_inventory.md`, `outputs/source_inventory.csv` and `docs/source_gap_register.md`. The raw artefacts it produced are committed under `data/raw/`.
- The FMI weather XML in `data/raw/weather/` was retrieved on 2026-09-18 and is preserved as retrieved; these scripts read it rather than re-downloading.

## Known differences from the originals (recorded, not hidden)

When the scripts were moved here three outputs changed, all intentionally:

1. `outputs/validation/sensitivity_analysis.csv`: `warn_free_rate_pct` is now the **canonical session-level** rate (97.88%); the event-level variant (97.70%) moved to `warn_free_incl_event_level_pct`. See `docs/decision_log.md` D28.
2. `outputs/validation/validation_summary_by_rule.csv`: now grouped by rule and population, as the docs describe.
3. `outputs/phase2/name_disagreement_examples_oct5_16.csv`: writes sorted, joined names instead of Python `set` reprs, which depended on the hash seed.
