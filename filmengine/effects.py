"""Audio effects that scripts can ask for by name, such as echo or telephone.

Each effect takes stereo audio and returns stereo audio. Effects with a tail
(echo, reverb) return audio that is longer than what went in.
"""

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100


def _filter(audio, kind, freq, order=4):
    sos = butter(order, freq, btype=kind, fs=SR, output="sos")
    return sosfilt(sos, audio, axis=0).astype(np.float32)


def _pad(audio, seconds):
    return np.concatenate([audio, np.zeros((int(seconds * SR), 2), dtype=np.float32)])


def _peak_match(new, reference):
    """Keep the loudness peak roughly where it was before the effect."""
    ref, out = np.abs(reference).max(), np.abs(new).max()
    if out > 0 and ref > 0:
        new = new * (ref / out)
    return new.astype(np.float32)


def reverb(audio, seconds=1.5, wet=0.35, brightness=5000, seed=7):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    impulse = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-t * 6.9 / seconds)[:, None]
    impulse = _filter(impulse, "lowpass", brightness, order=2)
    impulse /= np.sqrt((impulse ** 2).sum(axis=0, keepdims=True))
    tail = fftconvolve(audio, impulse, axes=0).astype(np.float32)
    dry = _pad(audio, seconds)[: len(tail)]
    return _peak_match((1 - wet) * dry + wet * tail * 3.0, audio)


def echo(audio, delay=0.3, decay=0.45, repeats=4):
    step = int(delay * SR)
    out = _pad(audio, delay * repeats)
    for i in range(1, repeats + 1):
        out[step * i: step * i + len(audio)] += audio * (decay ** i)
    return _peak_match(out, audio)


def drive(audio, amount=3.0):
    """Distortion. Matched by average loudness, since squashing peaks makes it sound louder."""
    out = np.tanh(audio * amount)
    before, after = np.sqrt((audio ** 2).mean()), np.sqrt((out ** 2).mean())
    return (out * (before * 1.2 / after if after > 0 else 1)).astype(np.float32)


def tremolo(audio, rate=5.0, depth=0.3):
    t = np.arange(len(audio)) / SR
    return (audio * (1 - depth + depth * np.sin(2 * np.pi * rate * t))[:, None]).astype(np.float32)


def mono(audio):
    m = audio.mean(axis=1, keepdims=True)
    return np.repeat(m, 2, axis=1)


def telephone(audio):
    out = _filter(_filter(mono(audio), "highpass", 350), "lowpass", 3200)
    return drive(out, 2.0)


def radio(audio):
    out = _filter(_filter(mono(audio), "highpass", 500), "lowpass", 4500)
    out = drive(out, 2.5)
    rng = np.random.default_rng(3)
    hiss = _filter(rng.standard_normal(out.shape).astype(np.float32), "highpass", 2000) * 0.01
    return (out + hiss).astype(np.float32)


def megaphone(audio):
    return drive(_filter(_filter(mono(audio), "highpass", 700), "lowpass", 3000), 6.0)


def robot(audio):
    t = np.arange(len(audio)) / SR
    ring = audio * np.sin(2 * np.pi * 55 * t)[:, None]
    mixed = 0.6 * ring + 0.4 * audio
    step = int(0.008 * SR)
    comb = mixed.copy()
    for i in range(1, 6):
        comb[step * i:] += mixed[: len(mixed) - step * i] * (0.5 ** i)
    return _peak_match(comb, audio)


def ghost(audio):
    out = _filter(audio, "highpass", 200)
    out = tremolo(out, 4.0, 0.25)
    out = echo(out, 0.25, 0.4, 3)
    return reverb(out, 3.0, 0.55)


def monster(audio):
    out = drive(audio, 2.5)
    out = _filter(out, "lowpass", 5000)
    return reverb(out, 0.8, 0.25)


def underwater(audio):
    return tremolo(_filter(audio, "lowpass", 450), 1.5, 0.2)


def muffled(audio):
    return _peak_match(_filter(audio, "lowpass", 900), audio) * 0.7


def far(audio):
    out = _filter(_filter(audio, "lowpass", 2500), "highpass", 250)
    return reverb(out, 1.2, 0.5) * 0.5


def dream(audio):
    out = _filter(audio, "lowpass", 4000)
    out = echo(out, 0.35, 0.3, 3)
    return reverb(out, 2.5, 0.45)


def whisper(audio):
    return _peak_match(_filter(audio, "highpass", 900, order=2), audio)


def thought(audio):
    return reverb(_filter(audio, "highpass", 150), 0.5, 0.2)


def voice_chat(audio):
    """Like TeamTalk or Discord: a narrow, squashed, slightly crunchy voice."""
    out = _filter(_filter(mono(audio), "highpass", 250), "lowpass", 6500)
    return drive(out, 1.8)


def announcer(audio):
    """A public address speaker in a big space, like a stadium or station."""
    out = drive(_filter(_filter(mono(audio), "highpass", 400), "lowpass", 5000), 2.0)
    return reverb(echo(out, 0.12, 0.25, 2), 2.5, 0.4)


def _pan_gains(angle):
    """Constant-power left/right gains for an angle (degrees, 0 ahead, 90 right)."""
    side = np.sin(np.radians(angle))
    theta = (side + 1.0) * np.pi / 4.0
    return np.cos(theta) * np.sqrt(2), np.sin(theta) * np.sqrt(2)


def position(audio, angle=None, distance=None, movement=None):
    """Place a sound around the listener.

    angle: 0 ahead, 90 right, -90 left, 180 behind. Sounds behind are a little
    duller, as they are to real ears. distance: 1 is normal, 2 twice as far.
    movement: "left to right", "right to left", "closer" or "away".
    """
    if angle is None and distance is None and movement is None:
        return audio
    m = audio.mean(axis=1)
    n = len(m)
    if movement in ("left to right", "right to left"):
        sweep = np.linspace(-80, 80, n) if movement == "left to right" else np.linspace(80, -80, n)
        left, right = _pan_gains(sweep)
    else:
        left, right = _pan_gains(angle or 0.0)
    out = np.stack([m * left, m * right], axis=1).astype(np.float32)

    behind = max(0.0, -np.cos(np.radians(angle))) if angle is not None else 0.0
    if behind > 0:
        out = (1 - 0.7 * behind) * out + 0.7 * behind * _filter(out, "lowpass", 2200, order=2)
        out *= 1 - 0.2 * behind

    if distance is not None:
        out *= min(1.6, 1.0 / max(distance, 0.3))
        if distance > 1.5:  # far sounds lose their top end and pick up the room
            out = _filter(out, "lowpass", max(1200, 8000 / distance), order=2)
            out = reverb(out, 1.0, min(0.6, 0.15 * distance))

    if movement in ("closer", "away"):
        ramp = np.linspace(0.25, 1.0, len(out)) if movement == "closer" else np.linspace(1.0, 0.25, len(out))
        out = out * ramp[:, None]
    return out.astype(np.float32)


EFFECTS = {
    "voice chat": voice_chat,
    "teamtalk": voice_chat,
    "announcer": announcer,
    "dry": lambda a: a,
    "echo": echo,
    "big echo": lambda a: echo(a, 0.5, 0.55, 6),
    "reverb": reverb,
    "room": lambda a: reverb(a, 0.6, 0.25),
    "hall": lambda a: reverb(a, 2.2, 0.4),
    "church": lambda a: reverb(a, 4.0, 0.5, 4000),
    "cave": lambda a: reverb(echo(a, 0.22, 0.3, 3), 3.0, 0.45),
    "telephone": telephone,
    "radio": radio,
    "megaphone": megaphone,
    "robot": robot,
    "ghost": ghost,
    "monster": monster,
    "underwater": underwater,
    "muffled": muffled,
    "far": far,
    "dream": dream,
    "whisper": whisper,
    "thought": thought,
    "drive": drive,
    "distorted": lambda a: drive(a, 8.0),
    "wobble": lambda a: tremolo(a, 6.0, 0.5),
}


def apply(audio, names):
    for name in names:
        audio = EFFECTS[name](audio)
    return audio.astype(np.float32)
