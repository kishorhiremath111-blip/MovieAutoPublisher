#!/usr/bin/env python3
"""Seeded original ASMR soundtracks: each topic gets its own musical identity."""
import wave
import numpy as np

SR = 44100
SCALES = [
    [0, 2, 4, 7, 9],
    [0, 3, 5, 7, 10],
    [0, 2, 4, 6, 8, 10],
    [0, 2, 3, 5, 7, 9, 10],
    [0, 2, 5, 7, 9],
]
TIMBRES = [
    ((1.0, 0.58, 5.0), (2.01, 0.22, 10.0), (3.0, 0.10, 17.0)),
    ((1.0, 0.54, 4.0), (2.76, 0.26, 8.0), (5.40, 0.12, 15.0)),
    ((1.0, 0.62, 6.0), (1.50, 0.18, 11.0), (3.70, 0.10, 20.0)),
    ((1.0, 0.52, 4.8), (2.40, 0.28, 9.0), (4.90, 0.10, 18.0)),
]


def _hz(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _tone(freq, duration, rng, timbre=0, noise=0.0):
    n = max(1, int(duration * SR))
    t = np.arange(n, dtype=np.float64) / SR
    profile = TIMBRES[timbre % len(TIMBRES)]
    y = np.zeros(n, dtype=np.float64)
    for multiple, amp, decay in profile:
        y += amp * np.sin(2 * np.pi * freq * multiple * t) * np.exp(-t * decay)
    if noise:
        y += rng.standard_normal(n) * np.exp(-t * 180) * noise
    return y


def _event_sound(kind, freq, rng, timbre):
    if kind == "pop":
        n = int(0.23 * SR)
        t = np.arange(n) / SR
        sweep = freq * (1.0 + 1.15 * np.exp(-t * 58))
        y = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.exp(-t * 25) * 0.72
        y += rng.standard_normal(n) * np.exp(-t * 210) * 0.20
        y += 0.16 * np.sin(2 * np.pi * freq * 2.8 * t) * np.exp(-t * 38)
        return y
    if kind == "tick":
        n = int(0.14 * SR)
        t = np.arange(n) / SR
        y = np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 52) * 0.42
        y += rng.standard_normal(n) * np.exp(-t * 280) * 0.25
        return np.convolve(y, np.ones(3) / 3.0, mode="same")
    if kind == "plink":
        return _tone(freq, 0.62, rng, timbre, noise=0.004)
    n = int(0.19 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * freq * 0.5 * t) * np.exp(-t * 21) * 0.48
    click = rng.standard_normal(n) * np.exp(-t * 150) * 0.035
    return body + click


def _mix(out, start, samples, pan=0.5, gain=1.0):
    start = int(start)
    if start < 0 or start >= out.shape[1]:
        return
    end = min(out.shape[1], start + len(samples))
    samples = samples[:end - start] * gain
    angle = min(1.0, max(0.0, pan)) * np.pi / 2.0
    out[0, start:end] += samples * np.cos(angle)
    out[1, start:end] += samples * np.sin(angle)


def make_audio(events, params, out_path):
    duration = float(params["duration"])
    total = int(duration * SR)
    seed = int(params["seed"]) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    scale = SCALES[(seed >> 5) % len(SCALES)]
    timbre = (seed >> 11) % len(TIMBRES)
    root = 48 + (seed % 13)
    motif = rng.integers(0, len(scale), size=16)
    out = np.zeros((2, total), dtype=np.float64)

    t = np.arange(total, dtype=np.float64) / SR
    chord = scale[(seed >> 17) % len(scale)]
    pad = (
        0.62 * np.sin(2 * np.pi * _hz(root) * t) +
        0.24 * np.sin(2 * np.pi * _hz(root + chord + 12) * t) +
        0.12 * np.sin(2 * np.pi * _hz(root + scale[(chord + 2) % len(scale)] + 24) * t)
    )
    pulse = 0.72 + 0.28 * np.sin(2 * np.pi * (0.075 + (seed % 7) * 0.006) * t)
    out[0] += pad * pulse * 0.025
    out[1] += pad * pulse * 0.025

    for i, event in enumerate(events):
        raw = int(event.get("pitch", 0))
        degree = (int(motif[(i + raw) % len(motif)]) + raw // len(scale)) % len(scale)
        octave = 1 + ((raw // 3 + i // 5 + (seed % 3)) % 2)
        freq = _hz(root + scale[degree] + octave * 12)
        kind = event.get("kind", "beat")
        sound = _event_sound(kind, freq, rng, timbre)
        gain = {"pop": 0.56, "tick": 0.48, "plink": 0.38, "beat": 0.25}.get(kind, 0.3)
        _mix(out, float(event.get("t", 0)) * SR, sound,
             pan=0.5 + 0.36 * np.sin(i * 1.71 + (seed % 31)), gain=gain)

    outro_start = max(0.15, duration - 1.75)
    for j in range(4):
        degree = (int(motif[(j * 3 + 1) % len(motif)]) + j + 1) % len(scale)
        freq = _hz(root + 12 + scale[degree] + (j // 2) * 12)
        chime = _tone(freq, 0.48, rng, (timbre + j) % len(TIMBRES), noise=0.002)
        _mix(out, (outro_start + j * 0.34) * SR, chime,
             pan=0.32 + j * 0.12, gain=0.24)

    out = np.tanh(out * 1.45)
    peak = float(np.max(np.abs(out))) or 1.0
    out *= 0.84 / peak
    fade_in = min(int(0.12 * SR), total)
    fade_out = min(int(0.52 * SR), total)
    if fade_in:
        out[:, :fade_in] *= np.linspace(0.0, 1.0, fade_in)
    if fade_out:
        out[:, -fade_out:] *= np.linspace(1.0, 0.0, fade_out)
    pcm = (out.T * 32767).astype("<i2")
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(pcm.tobytes())
    return out_path
