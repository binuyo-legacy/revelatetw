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
- Projection slide look (mockups A and B): song slides show centred lyrics (shrunk to fit inside safe margins, never below 24 px), an optional section label above, a footer "Song Title · Artist" bottom-left, and a gold chip "Chorus · 2/8" bottom-right. Sermon info slides show the church line, a large serif title, the speaker, and a gold scripture chip. Generic labels such as "Slide 3" get no chip.
- Theme schema v2 (theme JSON, schema_version 2). New fields:
  - background.kind: "linear" (vertical gradient, default), "solid", "radial", "image", or "video" (saved, not painted yet).
  - background.colors: one colour for solid, two or more for gradients. Default is the navy+gold gradient ["#1E1B4B", "#0F0B2E"].
  - background.image_path: a file name only, no folder path. It lives in data/backgrounds next to the app (BACKGROUNDS_DIR). Use "Pick image..." in the theme editor to copy a file there. Supported: png, jpg, jpeg, webp, bmp. Path separators and ".." are refused.
  - background.image_scrim: 0 to 1 dark overlay on image backgrounds so lyrics stay readable (default 0.4).
  - accent_color: gold for chips and frame (default "#D4A017").
  - dim_color: small footer and speaker text (default "#A9A4C8").
  - church_line: small line above the sermon title (optional).
  - Missing image or unreadable image: the slide falls back to the first background colour. It never goes black.
- Legacy themes (schema v1, no schema_version): they still load. accent_color takes the old reference_color so the look does not change, and the new fields get defaults. Saving from the editor writes schema_version 2.
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

Media tab: images and videos (this round)
- Media folder: data/media next to the app by default. Change it in Settings > Output > Media folder (Browse picks any folder). The choice is saved.
- Supported formats: images png, jpg, jpeg, webp, gif. Videos mp4, mkv, webm, mov. Other files in the folder are ignored.
- Import: the Import button copies the files you choose into the media folder (never overwrites; a name clash becomes "name (2).ext"). Rescan rebuilds the list after you drop files in by hand.
- The grid shows each item with its type badge and duration. Search filters by name, and All / Images / Videos narrows the type. Double-click an item, or select it and press Project, to project it.
- Media projects straight away with no approval step. It still respects LIVE: with the output off, the selection is held and shows when you turn LIVE back on. It stays on screen until you project something else or turn the output off. Images are scaled to fill the screen with the aspect kept. Videos play full-frame with a black letterbox and sound is muted (route audio through your audio mixer). Tick Loop video to replay when it ends.
- Fades: images and the video's first frame fade in and out with the theme transition. Video playback itself is not warped.
- If a video will not play, the slide shows "Cannot play this video format" instead of crashing. This needs the Qt multimedia backend: PyQt6 ships it, but Windows needs the codecs for the format (mp4 with H.264 is the safe choice).
- Optional ffprobe and ffmpeg: with ffprobe on PATH, video durations show on the cards (otherwise "length unknown"). With ffmpeg on PATH, videos get a first-frame thumbnail (otherwise a placeholder). Install from https://ffmpeg.org/download.html and add the bin folder to PATH. Neither is required. No paid SDK is used.
- The index cache is saved as .revelatetw-media-index.json in the media folder, with thumbnails in .thumbs. Delete both to start fresh.

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
- Video background rendering (the schema accepts kind "video"; the projection window does not paint it yet, it falls back to the first colour).
- Keyboard remapping, Approve and Edit persistence (Edit currently only sets edited_text in the queue).
- Polyphase resampler (capture still uses linear interpolation).
- Packaging (PyInstaller or Nuitka) and installer.

Spec files (revelatetw-mvp-spec.md, pdfs/) are unchanged.
