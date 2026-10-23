"""Headless performance bench for RevelateTW (no display, no audio, no model).

Usage: QT_QPA_PLATFORM=offscreen python scripts/bench.py [N]

Measures, offscreen:
  * paint events for N slide changes (each change should paint a bounded number of times)
  * time to composite one transition frame offscreen (old/new pixmaps already rendered once)
  * whether the transition timer is still running after the transitions settle (must be False)
Numbers are for THIS machine only. Real church PCs are unmeasured.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from revelatetw.songs import Slide, Song  # noqa: E402
from revelatetw.theme import Theme  # noqa: E402
from revelatetw.ui import ProjectionWindow  # noqa: E402


def main(n: int = 50) -> int:
    app = QApplication.instance() or QApplication([])
    w = ProjectionWindow()
    w.resize(1280, 720)
    w.show_theme(Theme(transition="slide", transition_ms=400))
    w._live = True                       # headless: no showFullScreen, state machine only
    slides = [Slide(label=f"Verse {i}", lines=[f"line {i} text for the bench"]) for i in range(n)]
    song = Song(id="bench", title="Bench", artist="", slides=slides)

    paints = {"count": 0}
    orig = ProjectionWindow.paintEvent

    def counting(self, event):
        paints["count"] += 1
        orig(self, event)

    ProjectionWindow.paintEvent = counting
    try:
        t0 = time.perf_counter()
        for i, s in enumerate(slides):
            w.show_song_slide(s, song, i, n)
            deadline = time.monotonic() + 1.0
            while w._anim is not None and time.monotonic() < deadline:   # drive the timer
                app.processEvents()
                time.sleep(0.004)
        elapsed = time.perf_counter() - t0
    finally:
        ProjectionWindow.paintEvent = orig

    settled_timer_running = w._timer.isActive()

    # One transition frame composite, timed offscreen (the per-tick cost).
    w.show_song_slide(slides[0], song, 0, n)
    w.show_song_slide(slides[1], song, 1, n)
    start = time.perf_counter()
    for _ in range(20):
        w._composite_pixmap()
    frame_ms = (time.perf_counter() - start) / 20 * 1000.0
    w._stop_anim()

    print(f"slide changes: {n}")
    print(f"paint events: {paints['count']} ({paints['count'] / n:.2f} per change)")
    print(f"wall time for {n} changes (incl. transition waits): {elapsed:.2f}s")
    print(f"offscreen transition frame composite: {frame_ms:.2f} ms/frame")
    print(f"transition timer running after settle: {settled_timer_running}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))
