# outputs/exploration: historical research outputs

Files here were written by the exploration scripts in `research/exploration/` during profiling. They are **historical evidence, not pipeline outputs**: `python -m src.pipeline.run` neither writes nor reads them, and they are not part of the approved metric package.

Two further profiling files sit outside this directory for historical reasons: `outputs/validation/profile_summary.csv` and `outputs/validation/sensitivity_analysis.csv`. They are also written by the research scripts and are not produced by the pipeline. The pipeline's own validation and sensitivity outputs are listed in `docs/data_dictionary.md` (sections 11 and 14); the pipeline's sensitivity results are in `outputs/evidence/`.
