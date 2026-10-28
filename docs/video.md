# Demo video

The ≤3-minute submission video (#76) is code: a [Remotion](https://www.remotion.dev) project in `video/` that renders the script in `docs/video-script.md` with a synthetic voice, generated music and burned-in English subtitles. Output: 1920×1080, 30 fps, about 2:41.

## Pieces

| File | Holds |
|---|---|
| `video/voice/lines.json` | Every spoken line in order: `text` is the subtitle, `say` (when present) is how the voice should read it (numbers in words, "F P and A", the phonemes of Nemotron) |
| `video/voice/generate.py` | Reads the lines with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0, runs locally, voice `af_heart` at speed 0.9), one WAV per line in `video/public/voice/`, and writes the durations to `video/src/voice.json` |
| `video/src/pace.json` | The scene order and, per scene, the pause before the first line, between lines and after the last one. The film, the music and the subtitles all derive their timing from it and from `voice.json` |
| `video/voice/music.py` | Synthesises `video/public/music.wav` on the same timeline: a dark pulse under the problem, a riser, one second of silence and a hit on "Meet Model X-Ray", then a brighter four-chord loop and a final swell |
| `video/voice/subtitles.py` | Writes `video/out/model-x-ray.en.srt` for YouTube |
| `video/voice/capture.py` | Drives the live site in headless Chrome at 1440×900, 2x, and screenshots every state of a real check (spends about two cents of Token Factory credit). The images used by the film are copied into `video/public/demo/` |
| `video/src/scenes/Story.tsx` | Open, Stakes, Who, Ai: the problem, told with animated type, rolling counters and a spreadsheet built in code |
| `video/src/scenes/Product.tsx` | Reveal, Demo (the real screenshots in a browser frame with a moving camera), Engine, Proof, Close |

Voice and music files are generated and not committed; the demo screenshots are committed because a new capture depends on the live site and spends credits.

## Render

```bash
cd video
npm install
uv run --script voice/generate.py
uv run --script voice/music.py
uv run --no-project python voice/subtitles.py
npx remotion render Film out/model-x-ray.mp4
```

`npx remotion studio` opens the editor with a timeline. After changing a line, run `generate.py`, `music.py` and `subtitles.py` again, in that order, because the timings change.

To change the voice: `VOICE=am_michael uv run --script voice/generate.py`.

Remotion is free for individuals and companies of up to three people; see its license before using it in a larger company.
