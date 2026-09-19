"""Stable exit codes of `python -m src.pipeline.run`. Codes 0, 2, 4, 5 and 6 keep their established meaning; 7-11 name the failing stage class.

When a stage fails, every later stage is BLOCKED (not run, stale outputs removed) and the exit code is the class of the FIRST failed stage.
A weather-lane problem alone exits 6; if a core stage also failed, the core code wins. Nothing ever exits 0 with a failed or blocked stage.
"""
from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    CONFIG = 2               # configuration missing, malformed, or violating an approved decision
    RETIRED_NOT_IMPLEMENTED = 3   # retired in pipeline orchestration: every stage is now implemented, so a full run can no longer stop for that reason
    SOURCE = 4               # missing / corrupt / unverified raw source, timezone override out of scope, ingestion or staging failure (core lane)
    FETCH = 5                # explicit retrieval (python -m src.pipeline.fetch) failed
    WEATHER = 6              # core lane usable, weather context lane BLOCKED
    VALIDATION = 7           # validation BLOCKED: staging unusable or a reconciliation identity broke
    MODEL = 8                # canonical model BLOCKED: validation output unusable or a control check failed
    METRICS = 9              # metric contract failure: canonical input unusable or a metric missed its approved value
    SENSITIVITY = 10         # sensitivity FAILED or BLOCKED: baseline moved, profiling reference not reproduced, registry invalid, input unusable
    ORCHESTRATION = 11       # the orchestrator itself failed: invalid stage order, unexpected exception, unwritable run manifest


STAGE_EXIT = {"ingest": ExitCode.SOURCE, "stage": ExitCode.SOURCE, "validate": ExitCode.VALIDATION, "model": ExitCode.MODEL, "metrics": ExitCode.METRICS,
              "sensitivity": ExitCode.SENSITIVITY}

EXIT_TABLE = (
    (ExitCode.OK, "OK", "every requested stage passed; both lanes healthy"),
    (ExitCode.CONFIG, "CONFIG", "configuration missing, malformed, or violating an approved decision (wrong timezone offset, changed M5 denominator, altered treatment, automatic retrieval)"),
    (ExitCode.RETIRED_NOT_IMPLEMENTED, "RETIRED", "no longer returned: all six stages are implemented"),
    (ExitCode.SOURCE, "SOURCE", "raw source missing, corrupt or unverified; timezone override out of scope; ingestion or staging failed. Retrieve explicitly with python -m src.pipeline.fetch"),
    (ExitCode.FETCH, "FETCH", "explicit retrieval failed (python -m src.pipeline.fetch only; the pipeline never fetches)"),
    (ExitCode.WEATHER, "WEATHER", "core lane usable but the weather context lane is BLOCKED; weather-dependent outputs are blocked"),
    (ExitCode.VALIDATION, "VALIDATION", "validation blocked: a staging table is missing or altered, or a reconciliation identity broke"),
    (ExitCode.MODEL, "MODEL", "canonical model blocked: a validation output is missing or altered, or a control check failed"),
    (ExitCode.METRICS, "METRICS", "metric contract failure: a canonical table is missing or altered, or a metric missed its approved value or tolerance"),
    (ExitCode.SENSITIVITY, "SENSITIVITY", "sensitivity failed: a canonical table is unusable, the baseline moved, an approved reference stopped reproducing, or the registry is invalid"),
    (ExitCode.ORCHESTRATION, "ORCHESTRATION", "the orchestrator failed: invalid stage order, unexpected exception, or an unwritable pipeline manifest"),
)
