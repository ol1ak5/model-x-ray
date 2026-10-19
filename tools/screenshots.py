import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

WIDTHS = ((1280, 800), (1440, 900))
STORIES = ("done",)
OUTPUT = Path("/tmp/model-x-ray-screenshots")
BASE = "http://localhost:5173"


def browser() -> str:
    for name in ("chromium-browser", "chromium", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("No Chromium or Chrome found; install one to take the screenshots")


def reachable() -> bool:
    try:
        with urllib.request.urlopen(BASE, timeout=3):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> None:
    if not reachable():
        raise SystemExit(f"{BASE} is not answering; start the app with scripts/dev.sh first")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    executable = browser()
    for story in STORIES:
        for width, height in WIDTHS:
            target = OUTPUT / f"{story}-{width}x{height}.png"
            subprocess.run(
                [
                    executable, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    f"--window-size={width},{height}", "--virtual-time-budget=4000",
                    f"--screenshot={target}", f"{BASE}/?story={story}",
                ],
                check=True, capture_output=True,
            )
            print(target)
    print("A before -> after pair must stay on one line, and the sheet must fit without horizontal scroll")


main()
