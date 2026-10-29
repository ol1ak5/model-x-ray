import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main() -> None:
    pace = json.loads((ROOT / "src" / "pace.json").read_text())
    voice = json.loads((ROOT / "src" / "voice.json").read_text())
    fps = pace["fps"]
    cursor = 0
    cues = []
    for name in pace["order"]:
        p = pace["scenes"][name]
        at = p["lead"]
        for line in voice["lines"]:
            if line["scene"] != name:
                continue
            frames = math.ceil(line["seconds"] * fps)
            cues.append(((cursor + at) / fps, (cursor + at + frames + 4) / fps, line["text"]))
            at += frames + p["gap"]
        cursor += at - p["gap"] + p["tail"]
    out = ROOT / "out" / "model-x-ray.en.srt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n" for i, (a, b, text) in enumerate(cues, 1)))
    print(f"{out.name}: {len(cues)} cues")


main()
