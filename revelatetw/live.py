"""Live sermon loop: audio capture -> rolling window -> speech-to-text -> detection pipeline.

The operator chooses the source:
  mic   AudioCapture on the chosen device (mic, USB interface, soundcard, or WASAPI loopback
        of the mixing desk). Audio is transcribed in windows and each text segment goes
        into the pipeline. Detection only queues; nothing projects without approval.
  text  dev feed. Typed sentences go straight into the pipeline. No audio, no model.

Transcription runs on its own thread so capture never blocks on inference.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from .audio import AudioCapture, InputDevice, NoiseGate, TARGET_RATE
from .transcription import RollingWindow, Transcriber

SOURCE_MIC = "mic"
SOURCE_TEXT = "text"


class LiveTranscriptionLoop:
    def __init__(self, pipeline, transcriber: Transcriber, window_s: float = 8.0,
                 overlap_s: float = 2.0, on_status=None):
        self.pipeline = pipeline
        self.transcriber = transcriber
        self.window_s = window_s
        self.overlap_s = overlap_s
        self.on_status = on_status or (lambda msg: None)
        self.source = SOURCE_TEXT
        self.capture: Optional[AudioCapture] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_text = ""

    # ---- operator controls -------------------------------------------------------------
    def start_mic(self, device: InputDevice, channel: int = 0, gain_db: float = 0.0,
                  gate_db: float = -45.0) -> None:
        self.stop()
        self.capture = AudioCapture(device, channel=channel, gain_db=gain_db,
                                    gate=NoiseGate(threshold_db=gate_db))
        self.capture.start()
        self.source = SOURCE_MIC
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="live-transcriber", daemon=True)
        self._thread.start()
        self.on_status(f"listening: {device.name}")

    def use_text_feed(self) -> None:
        self.stop()
        self.source = SOURCE_TEXT
        self.on_status("dev text feed")

    def feed_text(self, text: str) -> list:
        """Dev feed: typed sermon text, detected exactly like a transcript segment."""
        return self.pipeline.on_transcript(text)

    def stop(self) -> None:
        self._stop.set()
        if self.capture:
            self.capture.stop()
            self.capture = None
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None

    def meter(self) -> dict:
        if self.capture:
            return dict(self.capture.meter)
        return {"peak_db": -120.0, "rms_db": -120.0}

    # ---- worker ------------------------------------------------------------------------
    def _run(self) -> None:
        window = RollingWindow(rate=TARGET_RATE, window_s=self.window_s, overlap_s=self.overlap_s)
        chunks = self.capture.chunks
        while not self._stop.is_set():
            try:
                chunk = chunks.get(timeout=0.2)
            except queue.Empty:
                continue
            for win in window.push(chunk):
                if self._stop.is_set():
                    break
                try:
                    text = self.transcriber.transcribe(win).strip()
                except Exception as exc:  # model errors must not kill the loop
                    self.on_status(f"transcriber error: {exc}")
                    time.sleep(0.5)
                    continue
                if text:
                    self.last_text = text
                    self.pipeline.on_transcript(text)
