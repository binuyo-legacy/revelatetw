RevelateTW v0 scaffold (prototype)
==================================

This is a runnable skeleton, not the finished product. It follows revelatetw-mvp-spec.md (the source of truth) and is laid out so each module maps to a spec module (section 7).

What is in here
- revelatetw/books.py: 66-book canon with English aliases.
- revelatetw/store.py: verse store (JSON dev samples now, SQLite packs in the spec format).
- revelatetw/detection.py: exact citation parser (digits, spoken numbers, ordinals, aliases) plus a lexical paraphrase stub. The embedding matcher (spec F1) replaces LexicalParaphraseMatcher.
- revelatetw/approval.py: operator queue. Detection only adds candidates. Only approve or blank changes the output. Dedupe window 5 minutes. Session log (JSON lines).
- revelatetw/audio.py: device listing (incl. WASAPI loopback), gain, noise gate, meter, 16 kHz resampling. Uses sounddevice.
- revelatetw/transcription.py: speech-to-text hook (faster-whisper) and a rolling window with overlap.
- revelatetw/pipeline.py: transcript segments to detection to queue.
- revelatetw/theme.py: theme model as JSON (portable export/import), six ready-made themes.
- revelatetw/outputs.py: output sinks. NDI is off behind a flag (licence review, spec section 10). Virtual camera is a stub.
- revelatetw/ui.py: PyQt6 operator window (queue, keys, live indicator) and borderless projection window.
- tests/test_detection.py: detection and queue tests. No audio or Qt required.
- data/sample_kjv.json: 9 KJV verses for development. Not a full translation.

Setup (Windows, Python 3.11+)
1. py -3.11 -m venv .venv
2. .venv\Scripts\activate
3. pip install -r requirements.txt
   faster-whisper downloads its model on first use. Requires internet once.
4. Run the tests: python -m unittest discover -s tests -v
5. Try detection on typed text: python -m revelatetw --text-demo
   Then type a line such as "turn to john chapter three verse sixteen" and press Enter. Leave a blank line to quit.
6. List audio inputs: python -m revelatetw --list-devices
7. Operator UI: python -m revelatetw --gui

Not implemented yet (see spec)
- Live audio to the transcriber (wiring AudioCapture into TranscriptionWorker). The classes exist; the loop is not connected.
- Speech-to-text runs only where faster-whisper is installed. Model download is needed.
- Ed25519 pack signature checks, entitlement and licence server, pack store (F6).
- Theme editor UI (the model and presets exist; no editor screen yet). Transitions, image and video backgrounds.
- NDI sender, virtual camera driver (F5).
- Embedding paraphrase matcher and BM25 fallback (F1).
- Keyboard remapping, Approve and Edit persistence (Edit currently only sets edited_text in the queue).
- Packaging (PyInstaller or Nuitka) and installer.

Spec files (revelatetw-mvp-spec.md, pdfs/) are unchanged.
