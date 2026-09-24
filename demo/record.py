"""Records the LAST TRAY demo (demo.html) as a viewport-only .webm using Playwright's built-in video capture."""
import pathlib
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
HTML = HERE / "demo.html"
OUT_DIR = HERE / "out"
OUT_DIR.mkdir(exist_ok=True)
SIZE = {"width": 1280, "height": 720}
TOTAL_S = 3 + 30 + 45 * 6 + 3  # matches the JS timeline in demo.html, plus a few seconds' pad at the end

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport=SIZE, record_video_dir=str(OUT_DIR), record_video_size=SIZE)
    page = context.new_page()
    page.goto(HTML.as_uri())
    print(f"recording for {TOTAL_S} s ...", flush=True)
    for elapsed in range(0, TOTAL_S, 15):
        time.sleep(15)
        print(f"  {elapsed + 15}s / {TOTAL_S}s", flush=True)
    video_path = page.video.path()
    context.close()
    browser.close()

final = OUT_DIR / "last_tray_demo.webm"
pathlib.Path(video_path).replace(final)
print("DONE:", final)
