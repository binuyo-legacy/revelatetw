"""Glue: transcript segments -> detection -> approval queue.

Runs on a worker thread. The UI thread polls the queue; nothing here touches the screen.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Iterable, Optional

from .approval import ApprovalQueue
from .detection import VerseDetector
from .navigation import candidate_from_suggestion, continuation_suggestions


class DetectionPipeline:
    def __init__(self, detector: VerseDetector, queue: ApprovalQueue, context_segments: int = 3,
                 on_candidates: Optional[Callable] = None):
        self.detector = detector
        self.queue = queue
        self._recent: deque[str] = deque(maxlen=context_segments)
        self._on_candidates = on_candidates
        self.history: deque = deque(maxlen=200)   # (time, text, [references]) for the operator UI
        self.last_latency_ms: float = 0.0          # time to detect one segment
        self.on_segment: Optional[Callable] = None

    def on_transcript(self, segment: str) -> list:
        """Called for every transcript segment. The rolling context lets 'John' at the end
        of one segment and '3:16' at the start of the next still match."""
        segment = segment.strip()
        if not segment:
            return []
        t0 = time.perf_counter()
        self._recent.append(segment)
        # Exact citations can span segments, so search the rolling context.
        found = [c for c in self.detector.detect(" ".join(self._recent)) if c.match_type == "exact"]
        # Paraphrases only from the new segment, so an old citation does not hide a new paraphrase.
        if not any(c.match_type == "exact" for c in self.detector.detect(segment)):
            found += [c for c in self.detector.detect(segment) if c.match_type == "paraphrase"]
        # 'verse two' / 'next verse' after a projected verse: same chapter, queued for approval.
        if not any(c.match_type == "exact" for c in found) and self.queue.live is not None:
            live = self.queue.live
            store = self.detector.store
            for s in continuation_suggestions(store, live.book_id, live.chapter, live.verse, segment):
                found.append(candidate_from_suggestion(store, s, "continuation", 90, segment[-200:]))
        added = self.queue.add(found)
        self.last_latency_ms = (time.perf_counter() - t0) * 1000
        self.history.append((time.time(), segment, [(c.reference, c.confidence) for c in added]))
        if self.on_segment:
            self.on_segment(segment, added)
        if added and self._on_candidates:
            self._on_candidates(added)
        return added


def run_transcript_worker(segments: Iterable[str], pipeline: DetectionPipeline,
                          stop: threading.Event) -> threading.Thread:
    """Feed a stream of transcript segments (from Whisper or a test source) into the pipeline."""
    def _run():
        for seg in segments:
            if stop.is_set():
                break
            pipeline.on_transcript(seg)
    t = threading.Thread(target=_run, name="transcript-worker", daemon=True)
    t.start()
    return t
