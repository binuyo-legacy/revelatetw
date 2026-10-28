"""Entry point.

  python -m revelatetw --verses data/sample_kjv.json --text-demo
      Runs the detector on typed text (stdin) and shows the approval queue. No audio needed.

  python -m revelatetw --verses data/sample_kjv.json --gui
      Opens the operator window and projection window (PyQt6). Text in the 'Feed' box
      is detected like transcript.

  python -m revelatetw --gui --transcriber-model small
      Also enables the Live microphone source (needs faster-whisper and sounddevice).

  python -m revelatetw --list-devices
      Prints audio inputs (needs sounddevice).
"""
from __future__ import annotations

import argparse
import sys

from .approval import ApprovalQueue
from .detection import VerseDetector
from .pipeline import DetectionPipeline
from .store import VerseStore
from .theme import Theme


def load_store(verses_path: str) -> VerseStore:
    """Open a verse source: a SQLite pack (bundled translations) or a JSON sample file.

    A default that points at the 9-verse sample is replaced by the full bundled KJV pack when
    it is present, so the Verses tab lists every chapter and verse instead of a handful.
    """
    from .paths import resolve_data_arg, bundled
    if verses_path == "data/sample_kjv.json":
        pack = bundled("data", "bible", "KJV.sqlite")
        if pack.is_file():
            return VerseStore.open(pack)
    real = resolve_data_arg(verses_path)
    if str(real).lower().endswith(".sqlite"):
        return VerseStore.open(real)
    return VerseStore.from_json(verses_path)


def build(verses_path: str, log_path: str | None = "session_log.jsonl", threshold: int = 60):
    store = load_store(verses_path)
    detector = VerseDetector(store, paraphrase_threshold=threshold)
    queue = ApprovalQueue(log_path=log_path)
    pipeline = DetectionPipeline(detector, queue)
    return store, queue, pipeline


def text_demo(verses_path: str) -> None:
    store, queue, pipeline = build(verses_path, log_path=None)
    print(f"Loaded {store.translation_id} ({sum(1 for _ in store.items())} verses). "
          "Type sermon text, blank line to quit.")
    for line in sys.stdin:
        if not line.strip():
            break
        for c in pipeline.on_transcript(line):
            print(f"  candidate: {c.reference} [{c.match_type}, {c.confidence}%] {c.display_text}")
    print("pending:", [c.reference for c in queue.pending()])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="revelatetw")
    ap.add_argument("--verses", default="data/sample_kjv.json", help="verse JSON or SQLite pack")
    ap.add_argument("--text-demo", action="store_true")
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--log", default="session_log.jsonl")
    ap.add_argument("--transcriber-model", default=None,
                    help="faster-whisper model size (tiny, base, small). Enables live mic in --gui.")
    ap.add_argument("--songs-dir", default="data/songs",
                    help="folder for saved songs (one JSON file per song)")
    ap.add_argument("--output-screen", type=int, default=None,
                    help="index of the monitor for the live output (default: the second monitor in extended mode)")
    ap.add_argument("--dev", action="store_true",
                    help="show the Dev feed (typed text instead of the mic). Off by default.")
    ap.add_argument("--settings", default="data/settings.json",
                    help="JSON settings file (created on first save).")
    ap.add_argument("--no-splash", action="store_true",
                    help="skip the startup splash screen (GUI only)")
    ap.add_argument("--paraphrase-threshold", type=int, default=60,
                    help="0-100. Lower finds more paraphrases (default 60).")
    args = ap.parse_args(argv)

    if args.list_devices:
        from .audio import list_input_devices
        for d in list_input_devices():
            print(f"{d.index:3d}  {d.name}  ch={d.channels}  {d.default_rate} Hz  {d.host_api}")
        return 0
    if args.text_demo:
        text_demo(args.verses)
        return 0
    if args.gui:
        from .ui import run_app
        splash = None
        # Keep a named reference: a bare `QApplication([])` expression is garbage-collected at once,
        # and a QPixmap then aborts the process ("Must construct a QGuiApplication before a QPixmap").
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        if not args.no_splash:
            from .splash import start_splash
            splash = start_splash()          # shown before the heavy startup below
        _, queue, pipeline = build(args.verses, args.log, args.paraphrase_threshold)
        live = None
        if args.transcriber_model:
            from .live import LiveTranscriptionLoop
            from .transcription import LazyWhisperTranscriber
            live = LiveTranscriptionLoop(pipeline, LazyWhisperTranscriber(args.transcriber_model))
        from .store import load_settings
        settings = load_settings(args.settings)
        if live is not None:                     # saved performance options apply to the lazy model
            live.transcriber.configure(compute_type=settings.compute_type, cpu_threads=settings.cpu_threads)
        if args.paraphrase_threshold != 60:          # explicit CLI value wins over the saved file
            settings.paraphrase_threshold = args.paraphrase_threshold
        return run_app(queue, Theme(), pipeline=pipeline, live=live, songs_dir=args.songs_dir,
                       projection_screen=args.output_screen, settings=settings,
                       settings_path=args.settings, dev=args.dev, splash=splash)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
