# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "kokoro==0.9.4",
#   "soundfile",
#   "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
# ]
# ///
import json
import os
import sys
import urllib.request
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import soundfile as sf
import torch
from kokoro import KModel, KPipeline

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / ".cache"
OUT = ROOT / "public" / "voice"
TIMINGS = ROOT / "src" / "voice.json"
REPO = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/"
RATE = 24000
VOICE = os.environ.get("VOICE", "af_heart")
SPEED = float(os.environ.get("SPEED", "0.9"))


def fetch(name: str) -> Path:
    target = CACHE / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {name}", file=sys.stderr)
        urllib.request.urlretrieve(REPO + name, target)
    return target


def main() -> None:
    lines = json.loads((HERE / "lines.json").read_text())
    model = KModel(repo_id="hexgrad/Kokoro-82M", config=str(fetch("config.json")), model=str(fetch("kokoro-v1_0.pth"))).eval()
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", model=model)
    voice = torch.load(fetch(f"voices/{VOICE}.pt"), weights_only=True)
    OUT.mkdir(parents=True, exist_ok=True)
    timings = []
    for line in lines:
        audio = np.concatenate([chunk.numpy() for _, _, chunk in pipeline(line.get("say", line["text"]), voice=voice, speed=SPEED)])
        audio = audio / np.max(np.abs(audio)) * 0.89
        sf.write(OUT / f"{line['id']}.wav", audio, RATE)
        timings.append({"id": line["id"], "scene": line["scene"], "text": line["text"], "seconds": round(len(audio) / RATE, 3)})
        print(f"{line['id']}: {len(audio) / RATE:.2f}s")
    TIMINGS.write_text(json.dumps({"voice": VOICE, "speed": SPEED, "lines": timings}, indent=2) + "\n")
    print(f"total speech {sum(t['seconds'] for t in timings):.1f}s")


main()
