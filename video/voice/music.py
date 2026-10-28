# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "soundfile"]
# ///
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
RATE = 44100
BPM = 96
BEAT = 60 / BPM


def scenes() -> dict[str, tuple[float, float, list[float]]]:
    pace = json.loads((ROOT / "src" / "pace.json").read_text())
    voice = json.loads((ROOT / "src" / "voice.json").read_text())
    fps = pace["fps"]
    cursor = 0
    out = {}
    for name in pace["order"]:
        p = pace["scenes"][name]
        at = p["lead"]
        starts = []
        for line in voice["lines"]:
            if line["scene"] == name:
                starts.append((cursor + at) / fps)
                at += math.ceil(line["seconds"] * fps) + p["gap"]
        duration = at - p["gap"] + p["tail"]
        out[name] = (cursor / fps, (cursor + duration) / fps, starts)
        cursor += duration
    return out


def env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)[: n]
    e[-r:] *= np.linspace(1, 0, r)[-n:]
    return e


def note(freq: float, seconds: float, attack=0.6, release=1.2, bright=0.25) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    wave = np.sin(2 * np.pi * freq * t) + bright * np.sin(4 * np.pi * freq * t) * 0.5 + bright * 0.3 * np.sin(6 * np.pi * freq * t + 0.3)
    detune = np.sin(2 * np.pi * freq * 1.004 * t)
    return (wave + 0.6 * detune) * env(n, attack, release)


def thump(seconds=0.5, freq=52.0) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    pitch = freq * (1 + 1.5 * np.exp(-t * 30))
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    return np.sin(phase) * np.exp(-t * 7)


def tick(seconds=0.06) -> np.ndarray:
    n = int(seconds * RATE)
    noise = np.random.default_rng(7).standard_normal(n)
    high = np.diff(noise, prepend=0)
    return high * np.exp(-np.arange(n) / RATE * 70)


def add(track: np.ndarray, at: float, sound: np.ndarray, gain: float) -> None:
    i = int(at * RATE)
    if i >= len(track):
        return
    j = min(len(track), i + len(sound))
    track[i:j] += sound[: j - i] * gain


def midi(m: int) -> float:
    return 440 * 2 ** ((m - 69) / 12)


CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]


def main() -> None:
    parts = scenes()
    end = parts["close"][1]
    track = np.zeros(int((end + 1) * RATE))
    reveal_start, _, reveal_lines = parts["reveal"]
    hit = reveal_lines[0] - 0.25
    open_start = parts["open"][0]
    dark_end = parts["ai"][1]

    t = open_start + 0.8
    while t < dark_end - 0.2:
        progress = (t - open_start) / (dark_end - open_start)
        add(track, t, note(midi(33), BEAT * 8 + 1.5, attack=2.0, release=2.5, bright=0.1), 0.05 + 0.05 * progress)
        add(track, t, note(midi(40), BEAT * 8 + 1.5, attack=2.5, release=2.5, bright=0.1), 0.03 + 0.03 * progress)
        t += BEAT * 8
    t = parts["stakes"][0]
    while t < dark_end - 0.3:
        progress = (t - parts["stakes"][0]) / (dark_end - parts["stakes"][0])
        add(track, t, thump(), 0.22 + 0.2 * progress)
        if progress > 0.35:
            add(track, t + BEAT / 2, tick(), 0.04 + 0.05 * progress)
        t += BEAT
    riser = int(2.2 * RATE)
    rt = np.arange(riser) / RATE
    noise = np.random.default_rng(3).standard_normal(riser)
    sweep = np.sin(2 * np.pi * np.cumsum(200 + 1600 * (rt / 2.2) ** 2) / RATE)
    add(track, reveal_start - 2.2, (noise * 0.25 + sweep * 0.3) * (rt / 2.2) ** 2, 0.18)
    track[int(reveal_start * RATE) : int(hit * RATE)] = 0
    add(track, hit, thump(1.8, 40), 0.7)
    for m in (45, 57, 64, 69, 76):
        add(track, hit, note(midi(m), 5.5, attack=0.02, release=4.0, bright=0.4), 0.06)

    bright_start = hit + BEAT * 4
    bright_end = parts["close"][1] - 2.5
    t = bright_start
    bar = 0
    while t < bright_end:
        chord = CHORDS[(bar // 2) % 4]
        if bar % 2 == 0:
            for m in chord:
                add(track, t, note(midi(m), BEAT * 8 + 1.0, attack=0.8, release=1.6, bright=0.3), 0.035)
            add(track, t, note(midi(chord[0] - 12), BEAT * 8 + 1.0, attack=0.3, release=1.2, bright=0.1), 0.06)
        for b in range(4):
            beat_at = t + b * BEAT
            if beat_at >= bright_end:
                break
            add(track, beat_at, thump(0.45, 50), 0.26)
            add(track, beat_at + BEAT / 2, tick(), 0.05)
            arp = chord[(b + bar) % 3] + 12
            add(track, beat_at + BEAT * 0.75, note(midi(arp), 0.35, attack=0.005, release=0.3, bright=0.5), 0.02)
        t += BEAT * 4
        bar += 1
    final = parts["close"][2][0]
    for m in (45, 52, 57, 60, 64, 69):
        add(track, final, note(midi(m), 9.0, attack=1.2, release=6.0, bright=0.3), 0.045)

    fade = int(3.0 * RATE)
    stop = int(end * RATE)
    track[stop - fade : stop] *= np.linspace(1, 0, fade)
    track[stop:] = 0
    peak = np.max(np.abs(track))
    track = np.tanh(track / peak * 1.2) * 0.8
    stereo = np.stack([track, np.roll(track, 220)], axis=1)
    out = ROOT / "public" / "music.wav"
    sf.write(out, stereo.astype(np.float32), RATE)
    print(f"{out.name}: {end:.1f}s, hit at {hit:.2f}s")


main()
