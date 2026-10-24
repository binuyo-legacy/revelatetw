"""Operator header monitoring: PASTOR MIC level (AudioMonitor) and PC load (SystemMonitor).

Threading rules
- AudioMonitor.feed() runs on the PortAudio callback thread. It only updates numbers under a
  lock. It never touches widgets, the transcriber, or the approval queue.
- AudioMonitor does nothing while inactive (window hidden): feed() returns before any numpy work.
  With live detection off there is no capture, so no tap is ever called.
- SystemMonitor is a QThread. It samples psutil every SAMPLE_S seconds and emits `sampled`.
  The signal is connected to bound methods of QObjects that live on the main thread, so Qt
  delivers it as a queued call on the UI thread. Nothing else crosses threads.
- The operator window reads AudioMonitor from a main-thread timer (drain_peak / signal_present).
"""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

try:  # psutil is pure-python + a small C extension, installed from requirements.txt
    import psutil
except ImportError:  # pragma: no cover - exercised only on a broken install
    psutil = None

FRAME_S = 0.066          # one level frame (~15 per second); tap blocks are split into these
FLOOR_DB = -60.0         # level 0 at or below this RMS dBFS; level 1 at 0 dBFS
ON_DB = -42.0            # frame RMS at or above this turns "signal present" on
OFF_DB = -48.0           # ...and it turns off only after dropping below this (hysteresis)
HOLD_FRAMES = 4          # quiet frames required before "signal present" drops (~0.26 s)

SAMPLE_S = 2.0           # system sampling interval
CPU_AMBER_PCT = 60       # band thresholds shared by the CPU/RAM bars and the wave colour
CPU_RED_PCT = 85


def level_from_db(db: float) -> float:
    """Map frame RMS dBFS onto a 0..1 meter level."""
    return min(1.0, max(0.0, (db - FLOOR_DB) / -FLOOR_DB))


def band_for(pct: Optional[float]) -> str:
    """'green' under 60, 'amber' 60 to 85, 'red' above 85. 'none' when unknown."""
    if pct is None:
        return "none"
    if pct > CPU_RED_PCT:
        return "red"
    if pct >= CPU_AMBER_PCT:
        return "amber"
    return "green"


class AudioMonitor:
    """Turns the mic tap into 66 ms frames: current level 0..1, hysteresis 'signal present',
    and a peak-hold value the UI drains on its own timer.

    Wire it with AudioCapture(tap=monitor.feed). It shares the capture stream; it never opens
    a device of its own.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._carry = np.zeros(0, dtype=np.float32)
        self._carry_rate = 0
        self._level = 0.0
        self._peak = 0.0            # peak-hold since the last drain_peak()
        self._present = False
        self._quiet = 0
        self.last_frame_peak = 0.0  # linear peak of the most recent frame (for tests and tooling)
        self.frames_processed = 0

    # ---- lifecycle -------------------------------------------------------------------
    def set_active(self, on: bool) -> None:
        """Frames are computed only while active (operator window visible)."""
        with self._lock:
            self._active = bool(on)
            if not on:
                self._carry = np.zeros(0, dtype=np.float32)
                self._level = 0.0
                self._peak = 0.0
                self._present = False
                self._quiet = 0

    @property
    def active(self) -> bool:
        return self._active

    # ---- audio thread -----------------------------------------------------------------
    def feed(self, samples, rate: Optional[int] = None) -> int:
        """Consume one capture block. Returns how many frames were measured (0 when inactive)."""
        if not self._active:            # hidden window: cost is one attribute read
            return 0
        block = np.asarray(samples, dtype=np.float32).ravel()
        r = int(rate or 16000)
        with self._lock:
            if not self._active:
                return 0
            if r != self._carry_rate:
                self._carry = np.zeros(0, dtype=np.float32)
                self._carry_rate = r
            buf = np.concatenate((self._carry, block)) if self._carry.size else block
            n = max(1, int(round(r * FRAME_S)))
            full = (len(buf) // n) * n
            self._carry = buf[full:].copy()
            if full == 0:
                return 0
            frames = buf[:full].reshape(-1, n)
            rms = np.sqrt(np.mean(np.square(frames), axis=1))
            peaks = np.max(np.abs(frames), axis=1)
            for r_i, p_i in zip(rms, peaks):
                self._step(20.0 * np.log10(max(float(r_i), 1e-9)))
                self.last_frame_peak = float(p_i)
            self.frames_processed += len(rms)
            return len(rms)

    def _step(self, db: float) -> None:
        lv = level_from_db(db)
        self._level = lv
        if lv > self._peak:
            self._peak = lv
        if not self._present:
            if db >= ON_DB:
                self._present, self._quiet = True, 0
        elif db < OFF_DB:
            self._quiet += 1
            if self._quiet >= HOLD_FRAMES:
                self._present, self._quiet = False, 0
        else:
            self._quiet = 0

    # ---- reader (UI thread timer) -----------------------------------------------------
    @property
    def level(self) -> float:
        with self._lock:
            return self._level

    @property
    def signal_present(self) -> bool:
        with self._lock:
            return self._present

    def drain_peak(self) -> float:
        """Highest level since the previous call (peak-hold), then reset to the current level."""
        with self._lock:
            out = self._peak
            self._peak = self._level
            return out


def sample_system() -> tuple[Optional[float], Optional[float]]:
    """(cpu percent, ram percent), or (None, None) when psutil is unavailable."""
    if psutil is None:
        return None, None
    return float(psutil.cpu_percent(interval=None)), float(psutil.virtual_memory().percent)


class SystemMonitor(QThread):
    """Samples CPU and RAM every `interval_s` on a worker thread. Connect `sampled` to a
    bound method of a main-thread QObject."""

    sampled = pyqtSignal(float, float)   # cpu %, ram %

    def __init__(self, interval_s: float = SAMPLE_S, parent=None) -> None:
        super().__init__(parent)
        self._interval = float(interval_s)
        self._stop_evt = threading.Event()

    def start_sampling(self) -> None:
        if self.isRunning():
            return
        self._stop_evt = threading.Event()
        self.start()

    def stop_sampling(self, timeout_ms: int = 3000) -> None:
        self._stop_evt.set()
        if self.isRunning():
            self.wait(timeout_ms)

    def run(self) -> None:  # worker thread
        if psutil is not None:
            psutil.cpu_percent(interval=None)     # prime: the first call always reads 0.0
        first = min(0.5, self._interval)
        while not self._stop_evt.wait(first):
            cpu, ram = sample_system()
            if cpu is not None and ram is not None:
                self.sampled.emit(cpu, ram)
            first = self._interval
