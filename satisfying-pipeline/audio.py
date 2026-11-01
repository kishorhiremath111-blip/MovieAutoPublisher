#!/usr/bin/env python3
"""Soft ASMR-style sound, bina kisi copyrighted music ke.

Scene har event ka time deta hai (pop / tick / plink / beat). Yahan unse
numpy se awaaz banti hai: bubble pops, wood ticks, glass plinks, soft beat
aur halka pad. Sab kuch pentatonic scale me, isliye kabhi bura nahi lagta.
"""
import wave

import numpy as np

SR = 44100
PENT = [0, 2, 4, 7, 9]
MELODY = [0, 2, 4, 2, 5, 4, 2, 1]


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def _note(base, idx):
    return base + PENT[idx % 5] + 12 * ((idx // 5) % 2)


def _synth(kind, freq, rng):
    if kind == "pop":
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        f = freq * (1 + 1.2 * np.exp(-t * 60))
        y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26) * 0.7
        y += rng.standard_normal(n) * np.exp(-t * 220) * 0.25
        return y
    if kind == "tick":
        n = int(0.12 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 55) * 0.45
        y += rng.standard_normal(n) * np.exp(-t * 300) * 0.35
        return np.convolve(y, np.ones(3) / 3.0, mode="same")
    if kind == "plink":
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        y = np.zeros(n)
        for mult, amp, dec in ((1.0, 0.6, 5.0), (2.76, 0.25, 9.0), (5.4, 0.12, 16.0)):
            y += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t * dec)
        return y
    n = int(0.2 * SR)  # beat
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * freq * 0.5 * t) * np.exp(-t * 22) * 0.5
    y += rng.standard_normal(n) * np.exp(-t * 160) * 0.05
    return y


GAIN = {"pop": 0.55, "tick": 0.5, "plink": 0.4, "beat": 0.28}


def make_audio(events, params, out_path):
    duration = float(params["duration"])
    total = int(duration * SR)
    rng = np.random.default_rng(int(params["seed"]) & 0xFFFFFFFF)
    base = 57 + int(params["seed"]) % 7  # A3 ke aas paas
    out = np.zeros((2, total))

    t = np.arange(total) / SR
    pad = np.zeros(total)
    for off, g in ((0, 1.0), (7, 0.7), (12, 0.6), (16, 0.35)):
        f = _hz(base + off)
        pad += g * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t))
    pad *= (0.65 + 0.35 * np.sin(2 * np.pi * 0.11 * t)) * 0.03
    out[0] += pad
    out[1] += pad

    for i, ev in enumerate(events):
        start = int(max(0.0, float(ev["t"])) * SR)
        if start >= total:
            continue
        kind = ev.get("kind", "beat")
        idx = int(ev.get("pitch", 0))
        if kind == "beat":
            idx = MELODY[idx % len(MELODY)]
        freq = _hz(_note(base + 12, idx))
        y = _synth(kind, freq, rng) * GAIN.get(kind, 0.3)
        end = min(total, start + len(y))
        y = y[: end - start]
        pan = 0.5 + 0.35 * np.sin(i * 1.7)
        out[0, start:end] += y * np.cos(pan * np.pi / 2)
        out[1, start:end] += y * np.sin(pan * np.pi / 2)

    out = np.tanh(out * 1.4)
    peak = float(np.max(np.abs(out))) or 1.0
    out *= 0.85 / peak
    fin = int(0.15 * SR)
    fout = int(0.6 * SR)
    out[:, :fin] *= np.linspace(0, 1, fin)
    out[:, -fout:] *= np.linspace(1, 0, fout)

    pcm = (out.T * 32767).astype("<i2")
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out_path
