# Pipeline

`python -m src.pipeline.run` runs the whole project, offline, from the committed repository:

```
python -m src.pipeline.run                    # all six stages
python -m src.pipeline.run --stages model     # stop after a stage (each earlier stage still runs)
python -m src.pipeline.run --resume-from model --stages sensitivity
python -m src.pipeline.run --profile-memory   # also record peak Python allocation per stage
```

The orchestration adds no business logic. It calls the stage runners that already exist, in order, behind explicit gates, and records what happened. M1-M5, S2, the populations, the timezone decision, the quarantine treatment, the aliases and every table grain are exactly as approved.

## 1. Stage order and contract

| # | Stage | Reads | Writes | It verifies before it runs |
|---|---|---|---|---|
| 1 | `ingest` | `data/raw/**`, `config/` | `outputs/ingestion/` | size, MD5, SHA-256, row counts, schemas, timezone-override scope of every pinned raw file |
| 2 | `stage` | the ingestion handoff, raw bytes through the verified reader only | `outputs/staging/` | the SHA-256 of every raw member it reads, against the handoff |
| 3 | `validate` | `outputs/staging/` | `outputs/validation/` | each staging table against the checksum, header and row count staging recorded |
| 4 | `model` | staging and validation outputs | `outputs/model/` | every staging and validation file against its recorded checksum and the validation run id |
| 5 | `metrics` | `outputs/model/` | `outputs/metrics/` | each canonical table against the model manifest (checksum, header, row count) |
| 6 | `sensitivity` | `outputs/model/`, validation status | `outputs/evidence/` | the canonical tables against the model manifest; the frozen baseline against the approved package |

The order is fixed. The orchestrator refuses to start (exit 11) if the stage list is not exactly this sequence.

## 2. Gates

A stage runs only if the stage before it **PASSED** (or was reused by a resume). If a stage FAILS:

* every later stage is **BLOCKED**: it is not run and its stale outputs are removed, whether or not the run asked for it, so an earlier run's tables can never look current;
* the exit code is the class of the **first** failed stage;
* stages before the failure keep their outputs (they are still valid).

The weather lane never closes the gate. A weather problem blocks weather outputs only (`stg_weather_observation.csv`, `fact_weather.csv`, weather-dependent metrics), the core stages all run, and the run exits **6**. If a core stage also failed, the core code wins.

Stage statuses: `PASSED`, `FAILED`, `BLOCKED` (gate closed, outputs removed), `INVALIDATED` (a partial run replaced an upstream output, so a later stage's outputs were removed), `NOT_RUN` (outside the requested range, upstream unchanged, outputs left alone) and `REUSED` (before the `--resume-from` stage).

Nothing is skipped because a file exists. Every stage re-verifies its upstream contract (table above). The `run_manifest.json` of the previous run adds a second check: on `--resume-from`, the reused stages' current files are compared with the hashes that manifest recorded, and any difference fails that stage (its own exit class) and blocks everything after it. This catches a change the stage checks cannot, such as an edit to a summary field no later stage reads.

## 3. Exit codes

| Code | Name | Meaning |
|---|---|---|
| 0 | OK | every requested stage passed, both lanes healthy (quarantine is a finding, not a failure) |
| 2 | CONFIG | configuration missing, malformed, or violating an approved decision (wrong timezone offset, changed M5 denominator, altered quarantine treatment, a non-flag rule that excludes, automatic retrieval) |
| 3 | retired | no longer returned; every stage is implemented |
| 4 | SOURCE | a raw source is missing, corrupt or unverified, a timezone override is out of scope, ingestion or staging failed. Retrieve explicitly with `python -m src.pipeline.fetch` |
| 5 | FETCH | explicit retrieval failed (`src.pipeline.fetch` only; the pipeline never fetches) |
| 6 | WEATHER | core usable, weather context lane BLOCKED |
| 7 | VALIDATION | a staging table is missing or altered, or a reconciliation identity broke |
| 8 | MODEL | a validation output is missing or altered, or a canonical control failed |
| 9 | METRICS | a canonical table is missing or altered, or a metric missed its approved value |
| 10 | SENSITIVITY | a canonical table is unusable, the baseline moved, an approved reference stopped reproducing, or the registry is invalid |
| 11 | ORCHESTRATION | invalid stage order, an unexpected exception inside a stage, or an unwritable pipeline manifest |

## 4. Offline guarantee

The run has no download path. `--stages all` completes with every socket operation and `urllib.request.urlopen` forbidden (test). A missing raw source is a core failure that names the explicit command (`python -m src.pipeline.fetch --source <flavoria|weather>`) and downloads nothing. The orchestration modules import no network library (static test), and the configuration refuses any key that asks for automatic retrieval.

## 5. Outputs: `outputs/pipeline/`

| File | Deterministic | Content |
|---|---|---|
| `run_manifest.json` | no | run id, pipeline version, start/end, elapsed, target and resume point, exit code, weather flag, Python version, config fingerprint, provenance chain, and for every stage: status, gate, exit class, reason, row counts, warning/error counts, elapsed seconds, what it verifies, removed outputs, and the path, SHA-256 and size of every output |
| `stage_summary.csv` | yes | one row per stage: status, gate, exit class, reason, warnings, errors, output files, bytes, a hash of the outputs, removed outputs |
| `pipeline_controls.csv` | yes | controls P01-P11 (below) |
| `runtime_summary.json` | no | total and per-stage seconds, output bytes, peak Python allocation with `--profile-memory` |
| `run_log.jsonl` | no | one structured event per stage transition (`run_start`, `stage_start`, `stage_end`, `stage_blocked`, `stage_reused`, `cleanup`, `run_end`) with run id, stage, status, counts and reason; no paths and no row data |

`run_manifest.json`, `runtime_summary.json` and `run_log.jsonl` carry wall-clock values and are not tracked by git; `stage_summary.csv` and `pipeline_controls.csv` are. Any earlier pipeline output is removed at the start of a run, so a previous run's manifest never looks current.

Controls: P01 stage order; P02 no stage ran after a failure; P03 blocked or invalidated stages have no outputs; P04 every recorded hash matches the file on disk; P05 no temporary file remains; P06 the provenance chain is unbroken; P07 every passed stage recorded outputs; P08 raw files unchanged during ingestion; P09 weather-lane status (info); P10 network retrieval (info: none); P11 the exit code is a documented class. A failed control makes the run fail; it can never exit 0.

## 6. Provenance chain

`raw snapshot > ingestion > staging > validation > canonical model > metrics > sensitivity/evidence`. The manifest walks 18 links using only identifiers and checksums the stages recorded, and re-derives every checksum from the file on disk: the input fingerprint and both source snapshot ids are equal across ingestion, staging, validation, the model manifest and the metrics; each stage's recorded output hashes equal the files; validation's staging hashes, the model's staging and validation hashes and the model manifest's table hashes equal the files; the validation run id appears unchanged in the model and the metrics; the sensitivity baseline reproduces the metrics.

## 7. Atomic outputs and cleanup

Every deterministic file is written to a hidden temporary file in the same directory (`.<name>.tmp-<pid>`) and moved into place with `os.replace`. A failure at any point leaves the previous complete file or nothing, never a truncated file; a failed write removes its own temporary. Cleanup removes exactly a stage's deterministic outputs and any leftover temporaries in that stage's directory; the ingestion stage has no cleanup (its outputs are rewritten and its own failure removes nothing needed by later stages, because later stages are blocked).

## 8. Re-running

* The same command twice gives byte-identical deterministic outputs (test: two real runs, every file compared).
* A different `PYTHONHASHSEED`, working directory and output directory give identical outputs (test).
* `--resume-from X` re-runs X and later stages on the artifacts already on disk; earlier files are neither rewritten nor touched (mtime and hash unchanged, tested).
* Running fewer stages leaves later outputs alone if the upstream outputs did not change, and removes them (status `INVALIDATED`) if they did.

## 9. Reproducibility from a clean checkout

`git clone`, `pip install -r requirements.txt`, `python -m src.pipeline.run`, `python -m pytest`. No backup, no network and no file outside the repository is needed: the raw data is committed byte-exact (`.gitattributes`), and every generated output is regenerated. Regenerated tracked outputs equal the committed ones.

## 10. Measured runtime

Measured on the development machine (Windows 11, Python 3.11) by the pipeline itself; see `runtime_summary.json` from your own run.

| Stage | Seconds | Output files | Output bytes | Peak Python allocation (MB, `--profile-memory`) |
|---|---|---|---|---|
| ingest | 0.26 | 6 | 34,449 | 5.4 |
| stage | 1.42 | 4 | 10,288,976 | 40.8 |
| validate | 1.26 | 9 | 3,216,241 | 70.0 |
| model | 4.33 | 8 | 12,547,701 | 92.6 |
| metrics | 0.49 | 6 | 47,960 | 61.3 |
| sensitivity | 2.01 | 13 | 448,524 | 67.0 |
| total | 9.9 | 46 | 26,583,851 | max 92.6 |

Seconds are from a normal run. Memory comes from a separate `--profile-memory` run, which is slower (about 77 s in total) because it traces every Python allocation; it counts Python allocations only, not the interpreter or native libraries.

## 11. What this does not do

It does not decide anything new: it cannot make a failing metric pass, retry a failed stage, download a missing file or hide a weather problem. It reports; the stage that owns the rule decides.
