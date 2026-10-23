RevelateTW v0 scaffold (prototype)
==================================

This is a runnable skeleton, not the finished product. It follows revelatetw-mvp-spec.md (the source of truth) and is laid out so each module maps to a spec module (section 7).

What is in here
- revelatetw/books.py: 66-book canon with English aliases.
- revelatetw/store.py: verse store (JSON dev samples now, SQLite packs in the spec format).
- revelatetw/detection.py: exact citation parser (digits, spoken numbers, ordinals, aliases) plus paraphrase matching from paraphrase.py.
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

What changed in this round
- Live mic loop: revelatetw/live.py connects AudioCapture to the transcriber (window, overlap, transcribe on a worker thread). The operator window has a Source box (Dev text feed or Live microphone) and an Audio input picker that lists mics, interfaces, soundcards and WASAPI loopback. A failed device falls back to the text feed and says so. Start with: python -m revelatetw --gui --transcriber-model small
- Paraphrase matching: revelatetw/paraphrase.py replaces the word-overlap stub. Default is IDF-weighted token similarity with light stemming and fuzzy spelling repair (shepard -> shepherd). It is pure Python and works fully offline. If sentence-transformers is installed AND its model is already cached, detection can use embeddings (EmbeddingMatcher). It never downloads at church time, and any failure falls back to token matching. Threshold: python -m revelatetw --gui --paraphrase-threshold 60 (0-100, lower finds more, default 60).
- Theme editor: "Theme editor..." button in the operator window. Edits background kind and colours, image/video paths, text and reference colours, font, size, weight, line height, shadow, outline, frame, layout and transition. Open/Save theme JSON. The six ready-made themes load as starting points. Files are the same JSON as theme.py, and invalid themes are refused on save and load.
- Output: the projection window is borderless and titled "RevelateTW output". Optional virtual camera via pyvirtualcam (see OBS below). NDI stays disabled (spec section 10 licence review). No paid SDKs were added.

Feeding OBS (no extra software, recommended)
1. Start RevelateTW with --gui and drag the projection window to a display or leave it on the second screen.
2. In OBS add a Source, choose Window Capture, and pick "RevelateTW output". Choose Capture Method "Windows 10 (1903 and later)" for the best result.
3. Keep the projection window at 1920x1080 so the capture is not scaled.
Optional virtual camera: pip install pyvirtualcam, install OBS 26 or later, start its Virtual Camera once. RevelateTW's VirtualCameraSink then sends frames to "OBS Virtual Camera" in apps like Zoom or Teams.

Live output: ON/OFF, standalone output, and songs (this round)
- LIVE pill (toolbar, key O): click to switch the live projection output OFF. OFF hides the projection window, so another app can take a single projector. The pill shows OFF and dims. Click or press O again to bring it back.
- Display picker (Output display, preview panel): lists every monitor with its resolution and marks the primary one. Rescan re-reads the list after you plug in a projector. The live output goes borderless and fullscreen on the chosen monitor. Start-up choice: --output-screen N (index from the list, default 0).
- Route 1, direct fullscreen output: set the display picker to the projector. The window is the output. No OBS.
- Route 2, capture it with any software: OBS Window Capture of "RevelateTW output" (see Feeding OBS above), or the virtual camera route, or any studio or streaming software that can capture a window or a screen. The output is the same either way.
- Songs tab: Songs & sermon. Search the library, New song, or Import file (.txt pasted lyrics are split on import; .json is a saved song). Paste lyrics, Split into slides (a blank line or a header such as [Verse 1], Chorus:, Bridge starts a slide; --songs-dir sets the folder, default data/songs), then Save song. Each song is one JSON file.
- Song projection: pick a slide and Send (Enter approves, Esc rejects). Tick Direct to project at once. Prev and Next slide (Left/Right arrows, or Space to step on the Live tab too) move through the same song only. Live detection is untouched.
- Sermon info slide: type a title and optional speaker, then Show sermon info. The reference is the verse currently on the live output. Clear removes it. It uses the same theme as verses.
- Tests: python -m unittest discover -s tests -v (the GUI smoke tests run offscreen and skip if PyQt6 is missing).

Manual GUI test steps (not automated; PyQt6 needs a display)
1. python -m revelatetw --gui. Type "John 3:16" in the Dev feed and press Enter. The candidate must appear in the queue, and the projector must stay blank until you press Enter (Approve).
2. Press B to blank. Press Enter again on another candidate to project it.
3. Click Theme editor, pick "Royal Indigo", change the text colour, and Apply. The projection window must restyle at once.
4. In the editor, Save theme file, then reopen it with Open theme file. It must match what you saved.
5. Set Source to "Live microphone" and pick a device. The meter must move when someone speaks. Set it back to "Dev text feed" to confirm the loop stops cleanly.
6. Optional: choose a WASAPI loopback entry ("(loopback)") to capture the mixing desk output.

Automated checks (headless, no GUI, no audio hardware): python -m unittest discover -s tests -v

Not implemented yet (see spec)
- Ed25519 pack signature checks, entitlement and licence server, pack store (F6).
- NDI sender (licence review). Spout is not used; OBS window capture covers the same case.
- Theme transitions, image and video background rendering (the editor stores the choice; the projection window still paints the first colour only).
- Keyboard remapping, Approve and Edit persistence (Edit currently only sets edited_text in the queue).
- Polyphase resampler (capture still uses linear interpolation).
- Packaging (PyInstaller or Nuitka) and installer.

Spec files (revelatetw-mvp-spec.md, pdfs/) are unchanged.
