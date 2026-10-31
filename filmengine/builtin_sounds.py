"""Sounds the engine can make by itself, so a script can say [ambience: rain]
without any sound files. A real file with the same name in a sounds folder
always wins over these.
"""

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100


def _t(seconds):
    return np.arange(int(seconds * SR)) / SR


def _noise(seconds, seed):
    return np.random.default_rng(seed).standard_normal(int(seconds * SR))


def _filter(x, kind, freq, order=2):
    return sosfilt(butter(order, freq, btype=kind, fs=SR, output="sos"), x)


def _stereo(left, right=None, peak=0.6):
    right = left if right is None else right
    out = np.stack([left, right], axis=1)
    top = np.abs(out).max()
    return (out * (peak / top if top > 0 else 1)).astype(np.float32)


def _loopable(x, fade=0.5):
    """Blend the end into the start so the sound repeats without a jump."""
    n = int(fade * SR)
    ramp = np.linspace(0, 1, n)
    head = x[:n] * ramp + x[-n:] * (1 - ramp)
    return np.concatenate([head, x[n:-n]])


def _hit(seconds, freq, decay, noise=0.0, seed=0):
    t = _t(seconds)
    tone = np.sin(2 * np.pi * freq * t * (1 - 0.3 * t))
    body = tone + noise * _filter(_noise(seconds, seed), "lowpass", 3000)
    return body * np.exp(-t * decay)


def _place(total, events):
    out = np.zeros(int(total * SR))
    for start, sound in events:
        i = int(start * SR)
        piece = sound[: len(out) - i]
        out[i:i + len(piece)] += piece
    return out


def rain():
    left = _filter(_noise(12, 1), "bandpass", [400, 9000])
    right = _filter(_noise(12, 2), "bandpass", [400, 9000])
    rng = np.random.default_rng(3)
    drops = _place(12, [(s, _hit(0.03, rng.uniform(2000, 5000), 150) * rng.uniform(0.5, 2))
                        for s in rng.uniform(0, 11.9, 300)])
    return _stereo(_loopable(left + drops), _loopable(right + drops * 0.7), 0.5)


def wind():
    t = _t(14)
    gust = 0.55 + 0.45 * np.sin(2 * np.pi * t / 7) * np.sin(2 * np.pi * t / 3.1 + 1)
    left = _filter(_noise(14, 4), "bandpass", [150, 900]) * gust
    right = _filter(_noise(14, 5), "bandpass", [150, 900]) * gust[::-1]
    return _stereo(_loopable(left, 1.0), _loopable(right, 1.0), 0.5)


def waves():
    t = _t(16)
    swell = np.sin(np.pi * t / 8) ** 4
    left = _filter(_noise(16, 6), "lowpass", 1200) * swell
    right = _filter(_noise(16, 7), "lowpass", 1400) * np.roll(swell, SR)
    return _stereo(_loopable(left, 1.0), _loopable(right, 1.0), 0.5)


def fire():
    base = _filter(_noise(10, 8), "lowpass", 400) * 0.6
    rng = np.random.default_rng(9)
    pops = _place(10, [(s, _filter(_noise(0.02, int(s * 100)), "highpass", 1500) * np.exp(-_t(0.02) * 200)
                        * rng.uniform(0.5, 3)) for s in rng.uniform(0, 9.95, 120)])
    return _stereo(_loopable(base + pops), _loopable(base + np.roll(pops, 777)), 0.95)


def thunder():
    t = _t(6)
    rumble = _filter(_noise(6, 10), "lowpass", 180, 4) * np.exp(-t * 0.8) * (1 - np.exp(-t * 20))
    crack = _filter(_noise(6, 11), "bandpass", [300, 4000]) * np.exp(-t * 6)
    return _stereo(rumble * 3 + crack * 0.6, rumble * 3 + crack * 0.5, 0.9)


def knock():
    hit = _hit(0.25, 110, 30, noise=0.6, seed=12)
    return _stereo(_place(1.2, [(0, hit), (0.28, hit), (0.56, hit * 1.1)]), peak=0.8)


def footsteps():
    rng = np.random.default_rng(13)
    steps = []
    for i in range(8):
        step = _filter(_noise(0.12, 20 + i), "bandpass", [100, 1500]) * np.exp(-_t(0.12) * 45)
        steps.append((i * 0.55 + rng.uniform(-0.03, 0.03), step * rng.uniform(0.7, 1.0)))
    out = _place(4.6, steps)
    return _stereo(out * np.linspace(0.6, 1.0, len(out)), out * np.linspace(1.0, 0.6, len(out)), 0.95)


def heartbeat():
    beat = _place(0.8, [(0, _hit(0.2, 55, 25)), (0.22, _hit(0.2, 50, 30) * 0.7)])
    return _stereo(_place(4.8, [(i * 0.8, beat) for i in range(6)]), peak=0.8)


def clock():
    tick = _filter(_noise(0.02, 14), "highpass", 3000) * np.exp(-_t(0.02) * 300)
    tock = _filter(_noise(0.02, 15), "bandpass", [1000, 3000]) * np.exp(-_t(0.02) * 300)
    return _stereo(_place(4, [(i, tick if i % 2 == 0 else tock) for i in range(4)]), peak=0.9)


def beep():
    t = _t(0.35)
    return _stereo(np.sin(2 * np.pi * 1000 * t) * np.minimum(1, (0.35 - t) * 100) * np.minimum(1, t * 100), peak=0.4)


def phone():
    t = _t(2)
    ring = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * (np.sin(2 * np.pi * 20 * t) > 0)
    return _stereo(_place(8, [(0, ring), (4, ring)]), peak=0.4)


def static():
    return _stereo(_loopable(_filter(_noise(6, 16), "bandpass", [800, 6000])), peak=0.3)


def drone():
    t = _t(16)
    tone = sum(np.sin(2 * np.pi * f * t + p) * a for f, p, a in
               [(55, 0, 1), (55.4, 1, 0.8), (82.5, 2, 0.5), (110.3, 3, 0.3), (164.8, 4, 0.15)])
    air = _filter(_noise(16, 17), "lowpass", 300) * 0.15
    swell = 0.7 + 0.3 * np.sin(2 * np.pi * t / 8)
    return _stereo(_loopable(tone * swell + air, 2.0), _loopable(tone * swell[::-1] + air, 2.0), 0.4)


def chime():
    t = _t(4)
    bell = sum(np.sin(2 * np.pi * f * t) * a * np.exp(-t * d) for f, a, d in
               [(880, 1, 1.5), (1760, 0.5, 2.5), (2640, 0.25, 3.5), (1318, 0.3, 2)])
    return _stereo(bell, peak=0.5)


def click():
    return _stereo(_filter(_noise(0.03, 18), "highpass", 2000) * np.exp(-_t(0.03) * 250), peak=0.6)


BUILTIN = {
    "rain": (rain, "steady rain, loops smoothly"),
    "wind": (wind, "gusty wind, loops smoothly"),
    "waves": (waves, "sea waves on a shore, loops smoothly"),
    "fire": (fire, "crackling fire, loops smoothly"),
    "drone": (drone, "dark low hum for tense scenes, loops smoothly"),
    "static": (static, "radio static hiss, loops smoothly"),
    "thunder": (thunder, "a crack and long rumble of thunder"),
    "knock": (knock, "three knocks on a door"),
    "footsteps": (footsteps, "eight footsteps walking"),
    "heartbeat": (heartbeat, "a slow heartbeat"),
    "clock": (clock, "a ticking clock"),
    "beep": (beep, "a short electronic beep"),
    "phone": (phone, "a telephone ringing twice"),
    "chime": (chime, "a bell chime"),
    "click": (click, "a light switch or button click"),
}

_made = {}


def get(name):
    name = name.lower()
    if name not in BUILTIN:
        return None
    if name not in _made:
        _made[name] = BUILTIN[name][0]()
    return _made[name]
