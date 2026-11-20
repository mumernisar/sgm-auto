"""Generate the app's run-ended chime: three soft rising bell notes (E5, G#5, B5), ~1.1 s, mono 16-bit WAV.

    .venv/bin/python tools/make_sound.py   # writes android/app/src/main/res/raw/run_end.wav
"""
import wave
from pathlib import Path

import numpy as np

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "android/app/src/main/res/raw/run_end.wav"


def bell(freq, length):
    t = np.arange(int(RATE * length)) / RATE
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) + 0.12 * np.sin(2 * np.pi * 3 * freq * t)
    attack = np.minimum(t / 0.008, 1.0)  # no click at the start
    return tone * attack * np.exp(-t * 4.5)


notes = [(659.25, 0.0), (830.61, 0.16), (987.77, 0.32)]
out = np.zeros(int(RATE * 1.1))
for freq, start in notes:
    s = bell(freq, 1.1 - start)
    i = int(RATE * start)
    out[i:i + len(s)] += s
out *= 0.6 / np.abs(out).max()
OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes((out * 32767).astype(np.int16).tobytes())
print(f"wrote {OUT}")
