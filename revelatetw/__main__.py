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


def build(verses_path: str, log_path: str | None = "session_log.jsonl", threshold: int = 60):
    store = VerseStore.from_json(verses_path)
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
    ap.add_argument("--output-screen", type=int, default=0,
                    help="index of the monitor for the live output (see the display picker)")
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
        _, queue, pipeline = build(args.verses, args.log, args.paraphrase_threshold)
        live = None
        if args.transcriber_model:
            from .live import LiveTranscriptionLoop
            from .transcription import LazyWhisperTranscriber
            live = LiveTranscriptionLoop(pipeline, LazyWhisperTranscriber(args.transcriber_model))
        return run_app(queue, Theme(), pipeline=pipeline, live=live, songs_dir=args.songs_dir,
                       projection_screen=args.output_screen)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
