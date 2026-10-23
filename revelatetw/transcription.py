"""Speech-to-text hook (spec F1: faster-whisper, local).

Transcriber is the seam. FasterWhisperTranscriber needs `pip install faster-whisper`
and downloads the model once; it is never called when the app runs in text mode.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Transcriber(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


DEFAULT_COMPUTE_TYPE = "int8"       # audit: smallest and fastest on CPU; the Settings default
COMPUTE_TYPES = ("int8", "int8_float32", "float32")
DEFAULT_CPU_THREADS = 0              # 0 = let ctranslate2 choose


class FasterWhisperTranscriber:
    def __init__(self, model_size: str = "small", device: str = "cpu",
                 compute_type: str = DEFAULT_COMPUTE_TYPE, language: str = "en",
                 cpu_threads: int = DEFAULT_CPU_THREADS):
        from faster_whisper import WhisperModel  # lazy import
        self.language = language
        kwargs = {"cpu_threads": int(cpu_threads)} if cpu_threads else {}
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type, **kwargs)

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _info = self._model.transcribe(audio, language=self.language, vad_filter=True,
                                                 beam_size=1)
        return " ".join(s.text.strip() for s in segments)


class LazyWhisperTranscriber:
    """Loads the model on first use, so the GUI opens even if faster-whisper is missing.

    Lazy-load contract (audit): construction loads NOTHING. The model loads on the first
    transcribe() call (first live mic start), and unload() drops it, so with live detection
    off no whisper model is resident. configure() changes size/compute/threads; it takes
    effect on the next load (the running model is unloaded so settings never mix)."""

    def __init__(self, model_size: str = "small", compute_type: str = DEFAULT_COMPUTE_TYPE,
                 cpu_threads: int = DEFAULT_CPU_THREADS):
        self.model_size = model_size
        self.compute_type = compute_type if compute_type in COMPUTE_TYPES else DEFAULT_COMPUTE_TYPE
        self.cpu_threads = max(0, int(cpu_threads or 0))
        self._inner: FasterWhisperTranscriber | None = None

    @property
    def loaded(self) -> bool:
        return self._inner is not None

    def configure(self, model_size: str | None = None, compute_type: str | None = None,
                  cpu_threads: int | None = None) -> None:
        changed = False
        if model_size and model_size != self.model_size:
            self.model_size, changed = model_size, True
        if compute_type in COMPUTE_TYPES and compute_type != self.compute_type:
            self.compute_type, changed = compute_type, True
        if cpu_threads is not None and int(cpu_threads) != self.cpu_threads:
            self.cpu_threads, changed = max(0, int(cpu_threads)), True
        if changed:
            self.unload()

    def unload(self) -> None:
        self._inner = None   # drops the ctranslate2 model; freed by refcount

    def transcribe(self, audio: np.ndarray) -> str:
        if self._inner is None:
            self._inner = FasterWhisperTranscriber(self.model_size, compute_type=self.compute_type,
                                                   cpu_threads=self.cpu_threads)
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
