"""Audio input (spec F4): device list, per-device gain, noise gate, metering, channel choice.

Uses sounddevice (PortAudio). On Windows, WASAPI loopback lets you capture a sound
desk's main output directly (listed as '<device> (loopback)').
Requires: pip install sounddevice numpy. Both are imported lazily so the rest of the
app (and the tests) run without audio hardware.
"""
from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

TARGET_RATE = 16000  # faster-whisper expects 16 kHz mono

_log = logging.getLogger(__name__)


@dataclass
class InputDevice:
    index: int
    name: str
    channels: int
    default_rate: int
    host_api: str
    loopback: bool = False


def list_input_devices() -> list[InputDevice]:
    """Every input the OS exposes: mics, USB interfaces, soundcards, and WASAPI loopback of outputs."""
    import sounddevice as sd
    devices = []
    hostapis = [h["name"] for h in sd.query_hostapis()]
    for i, d in enumerate(sd.query_devices()):
        api = hostapis[d["hostapi"]]
        if d["max_input_channels"] > 0:
            devices.append(InputDevice(i, d["name"], d["max_input_channels"],
                                       int(d["default_samplerate"]), api))
        if api == "Windows WASAPI" and d["max_output_channels"] > 0:
            devices.append(InputDevice(i, f"{d['name']} (loopback)", d["max_output_channels"],
                                       int(d["default_samplerate"]), api, loopback=True))
    return devices


def default_input_index() -> Optional[int]:
    """Index of the system DEFAULT input device (sounddevice default), or None if there is none."""
    import sounddevice as sd
    try:
        idx = sd.default.device[0]
    except Exception:  # noqa: BLE001 - some hosts expose no default at all
        return None
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return None
    return idx if idx >= 0 else None


def pick_default_device(devices: list[InputDevice]) -> Optional[InputDevice]:
    """The system default mic from a list (never a loopback entry). Falls back to the first real input."""
    plain = [d for d in devices if not getattr(d, "loopback", False)]
    if not plain:
        return None
    try:
        default = default_input_index()
    except Exception:  # noqa: BLE001
        default = None
    for d in plain:
        if getattr(d, "index", None) == default:
            return d
    return plain[0]


def db_to_gain(db: float) -> float:
    return 10 ** (db / 20.0)


def level_db(samples) -> tuple[float, float]:
    """Return (peak_dBFS, rms_dBFS) for a block of float samples."""
    import numpy as np
    if len(samples) == 0:
        return -120.0, -120.0
    peak = float(np.max(np.abs(samples))) or 1e-9
    rms = float(np.sqrt(np.mean(np.square(samples)))) or 1e-9
    return 20 * math.log10(peak), 20 * math.log10(rms)


class NoiseGate:
    """Simple RMS gate with attack/release smoothing. Stops steady hum below the threshold."""

    def __init__(self, threshold_db: float = -45.0, attack_ms: float = 10, release_ms: float = 150,
                 rate: int = TARGET_RATE):
        self.threshold_db = threshold_db
        self.attack = math.exp(-1.0 / (rate * attack_ms / 1000))
        self.release = math.exp(-1.0 / (rate * release_ms / 1000))
        self._env = 0.0

    def process(self, block):
        import numpy as np
        _, rms = level_db(block)
        target = 1.0 if rms >= self.threshold_db else 0.0
        coef = self.attack if target > self._env else self.release
        self._env = coef * self._env + (1 - coef) * target
        return block * self._env


class AudioCapture:
    """Opens one device/channel, applies gain and gate, and yields 16 kHz mono chunks.

    Chunks go into a bounded queue (ring-buffer behaviour: oldest dropped when the
    transcriber falls behind), so capture never blocks on inference.
    """

    def __init__(self, device: InputDevice, channel: int = 0, gain_db: float = 0.0,
                 gate: Optional[NoiseGate] = None, max_backlog: int = 64,
                 tap: Optional[Callable] = None):
        self.device = device
        self.channel = channel
        self.gain = db_to_gain(gain_db)
        self.gate = gate or NoiseGate()
        self.chunks: queue.Queue = queue.Queue(maxsize=max_backlog)
        self.meter = {"peak_db": -120.0, "rms_db": -120.0}   # read by the UI meter
        # Optional observer on the SAME stream (header AUDIO SOURCE wave). Called on the audio
        # thread with (gained mono block at the native rate, native rate). Must be cheap.
        self.tap = tap
        self._stream = None
        self._lock = threading.Lock()
        # Health, read from the UI thread: `blocks` counts audio callbacks (even when nothing is
        # measured), so a stalled stream is visible; `error` holds the last callback failure.
        self.blocks = 0
        self.error: Optional[str] = None
        self.rate = int(device.default_rate)
        self.open_channels = min(max(1, int(device.channels)), 2)
        self.started_at = 0.0

    def stalled(self, after_s: float = 3.0) -> bool:
        """True when the stream opened but has delivered no audio callbacks for `after_s` seconds."""
        if self._stream is None or self.blocks:
            return False
        return time.monotonic() - self.started_at >= after_s

    # Gain and channel can change while running (no restart needed, spec F4).
    def set_gain(self, gain_db: float) -> None:
        with self._lock:
            self.gain = db_to_gain(gain_db)

    def set_gate_threshold(self, db: float) -> None:
        with self._lock:
            self.gate.threshold_db = db

    def _pick_format(self, sd, extra) -> tuple[int, int]:
        """(channels, sample rate) the device accepts for a shared-mode open.

        Windows WASAPI often refuses a device's full channel count or its advertised rate
        (a 32-channel mixer, or a 44.1 kHz USB card). Try the sane candidates first; if none
        passes the check, return the first one and let the real open report the error.
        """
        dev = self.device.index
        first_ch = self.open_channels
        channels = [first_ch] + ([1] if first_ch != 1 else [])
        rates: list[int] = []
        for r in (int(self.device.default_rate), 48000, 44100):
            if r and r not in rates:
                rates.append(r)
        for ch in channels:
            for r in rates:
                try:
                    sd.check_input_settings(device=dev, channels=ch, dtype="float32",
                                            samplerate=r, extra_settings=extra)
                    return ch, r
                except Exception:  # noqa: BLE001 - this candidate is refused, try the next
                    continue
        return first_ch, rates[0]

    def start(self) -> None:
        import sounddevice as sd
        import numpy as np
        extra = sd.WasapiSettings(loopback=True) if self.device.loopback else None
        channels, native = self._pick_format(sd, extra)
        self.rate, self.open_channels = native, channels
        self.blocks = 0
        self.error = None
        self.started_at = time.monotonic()

        def callback(indata, frames, time_info, status):
            # Never let an exception escape into PortAudio: that stops the stream silently.
            self.blocks += 1
            try:
                with self._lock:
                    block = indata[:, self.channel].astype(np.float32) * self.gain
                    pk, rms = level_db(block)
                    self.meter = {"peak_db": pk, "rms_db": rms}
                    block = self.gate.process(block)
                tap = self.tap
                if tap is not None:
                    tap(indata[:, self.channel] * self.gain, native)   # pre-gate: what the mic hears
                # naive resample to 16 kHz; replace with a polyphase resampler for production
                n_out = int(len(block) * TARGET_RATE / native)
                resampled = np.interp(np.linspace(0, len(block) - 1, n_out),
                                      np.arange(len(block)), block).astype(np.float32)
                try:
                    self.chunks.put_nowait(resampled)
                except queue.Full:
                    self.chunks.get_nowait()   # drop oldest
                    self.chunks.put_nowait(resampled)
            except Exception as exc:  # noqa: BLE001
                if self.error is None:
                    _log.error("audio callback failed on %r: %s", self.device.name, exc)
                self.error = f"{type(exc).__name__}: {exc}"

        self._stream = sd.InputStream(device=self.device.index, channels=channels,
                                      samplerate=native, dtype="float32", callback=callback,
                                      extra_settings=extra, blocksize=int(native * 0.1))
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
