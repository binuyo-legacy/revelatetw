"""Speech-to-text hook (spec F1: faster-whisper, local).

Transcriber is the seam. FasterWhisperTranscriber needs `pip install faster-whisper`
and downloads the model once; it is never called when the app runs in text mode.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


class FasterWhisperTranscriber:
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        from faster_whisper import WhisperModel  # lazy import
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _info = self._model.transcribe(audio, language="en", vad_filter=True,
                                                 beam_size=1)
        return " ".join(s.text.strip() for s in segments)


class LazyWhisperTranscriber:
    """Loads the model on first use, so the GUI opens even if faster-whisper is missing."""

    def __init__(self, model_size: str = "small"):
        self.model_size = model_size
        self._inner: FasterWhisperTranscriber | None = None

    def transcribe(self, audio: np.ndarray) -> str:
        if self._inner is None:
            self._inner = FasterWhisperTranscriber(self.model_size)
        return self._inner.transcribe(audio)


class TextTranscriber:
    """Development hook: feed typed sermon text as if it were speech."""

    def transcribe(self, audio: np.ndarray) -> str:  # pragma: no cover - not used with audio
        raise NotImplementedError("TextTranscriber is driven by feed_text(), not audio")


class RollingWindow:
    """Buffers audio into fixed windows with overlap so references across boundaries are found."""

    def __init__(self, rate: int = 16000, window_s: float = 8.0, overlap_s: float = 2.0):
        self.rate = rate
        self.window = int(window_s * rate)
        self.step = self.window - int(overlap_s * rate)
        self._buf = np.zeros(0, dtype=np.float32)

    def push(self, chunk: np.ndarray):
        """Yield full windows as they become available."""
        self._buf = np.concatenate([self._buf, chunk])
        while len(self._buf) >= self.window:
            yield self._buf[:self.window].copy()
            self._buf = self._buf[self.step:]
