# demo: the recorded walkthrough

`last_tray_demo.webm` (about 5:15, 1280x720) is a silent, scripted recording of the demo in [`docs/demo_script.md`](../docs/demo_script.md). Each of its seven segments matches that script's timeline exactly, on-screen captions carry the script's "Say" lines verbatim, and every number and image comes from this repository's own real outputs and diagrams, not invented content.

It is generated, not hand-recorded: `demo.html` is a static page built from the values in `README.md`, `docs/final_evidence.md`, `docs/source_map.md`, `outputs/evidence/evidence_matrix.csv`, `outputs/pipeline/pipeline_controls.csv` and a captured run of `python -m src.pipeline.run`, and `record.py` plays it back in a headless browser while Playwright records the viewport. If the pipeline's numbers ever change, this page and the video should be regenerated rather than hand-edited.

## Regenerate

Requires `playwright` (not a pipeline dependency, so it is not in `requirements.txt`):

```
pip install playwright
playwright install chromium
python demo/record.py
```

Run from the repository root. It reads `demo/demo.html`, writes the recording to `demo/out/`, and takes about 5.5 minutes (real time, matching the video's own length). Copy the result over `demo/last_tray_demo.webm` when you are satisfied with it.

`.webm` is Playwright's native output. Converting to `.mp4` needs `ffmpeg`, which this repository does not assume is installed.
