# RevelateTW Lite

A small, offline version of RevelateTW for old PCs (target: Windows 8.1, 32-bit, 2GB RAM). Same
look as the main app (navy and gold, same logo, same colour/type/spacing values from
`revelatetw/ui_tokens.py`). The heavy parts (live sermon listening, verse detection, theme editor, audio routing,
NDI/OBS output) are left out on purpose.

**Status: NOT tested on a real Windows 8.1 32-bit PC yet.** All logic is unit tested and the app was started
and screenshot-checked on Linux (peak memory about 62 MB there). Please run it on the real PC and send the
numbers from the checklist below.

## What it does
- Typing suggestions: start typing a book (`jo`), pick with Up/Down + Enter, then pick a chapter, then a verse. `John` alone opens John 1:1.
- Offline Bible lookup from the bundled packs (KJV, ASV, WEB, Yoruba Contemporary). Type `John 3:16`, `rom 8:28-30`,
  `1 cor 13`, `first john 4:8`.
- Next / previous verse (crosses chapter and book ends). PageDown / PageUp also projects it straight away.
- Keyboard editing of the box (EasyWorship style): Left / Right move the highlight between Book, Chapter and Verse. Up / Down change the highlighted part (if the screen is live, the projection updates too). Typing replaces the highlighted part and the suggestions still appear. Tab into the box highlights the book.
- Search by words ("loved world").
- Service list: line up verses before the service, reorder, saved automatically.
- Projection: borderless full-screen window on the extended (second) display, text auto-sized to fit, 3 colour
  styles, text size, show/hide reference. Project (F1) sends the preview to the full-screen display; Project Off (Esc) closes it. F5 and Ctrl+Enter also project (aliases). Everything else (Enter, arrows, Next/Previous) only changes the preview.
- **Text outline** (Settings, next to the colours): tick "Outline around text", pick a colour (or press Auto: dark outline on light text, light on dark), and set Thickness 1 to 10. It is drawn on verse, reference and credit, and looks the same on the preview and the screen (thickness scales with screen size). Works on solid, gradient and picture backgrounds. A hint appears if the outline colour is too close to the text colour. Like other look changes, it reaches the screen only when you press Project. Saved in settings.
- **Settings tab** (was "Look and screen"): projector screen, colours, text size, font, bold, show reference, plus the background.
  Background choices: Solid colour (as before), Gradient (Colour 1, Colour 2, Swap, direction: top to bottom, left to right,
  two diagonals) or Picture (Choose picture..., Remove picture, size: Fill, Fit, Stretch, Tile, and Darken picture 0-80%).
  PNG, JPG, BMP or GIF up to 30 MB; bigger pictures are shrunk to at most 1920x1080 while loading to save memory. A damaged,
  wrong-type or missing picture shows a plain message and the plain colour is used instead (nothing crashes; the choice is kept
  so the picture comes back if the file returns). All of it is saved in settings.json. The preview and the full-screen display
  draw the background with the same code, and changes only show in the preview until you click Project.
  Font picker is grouped (easy to read, clean, big and bold, decorative, fixed width) and lists only fonts that ship with
  Windows 8.1 and are installed on that PC; nothing to download. A missing font falls back to Georgia, then Arial. The choice is
  saved, and the preview and full-screen display use the same font.
  If a picture is bright enough that white text would be hard to read, Settings shows a hint to raise Darken picture.
  Tiled and scaled copies are cached per picture, so repainting does not redo work on a 2 GB PC.
- **Screen effects (transitions)** in Settings: Cut, Fade through black, Dissolve, Wipe, Slide (push), Blinds, Open from centre, plus six more: Checkerboard, Diagonal wipe, Iris (circle), Zoom, Mosaic, Clock sweep.
  Pick the effect, speed (0 to 3000 ms, 0 = instant) and direction (follow Next/Previous, or left/right/up/down; used by Wipe, Slide,
  Blinds and Open). Two tick boxes turn the effect off for Project / Project Off, or for screen changes while live.
  - Fade: old picture fades out, then the new one fades in. Dissolve: new picture fades in over the old one.
  - New: Checkerboard (chequer squares grow, two rounds), Diagonal wipe (slanted edge corner to corner, follows direction), Iris (circle opens from the middle), Zoom (old zooms out, new zooms in), Mosaic (squares pop in at scattered places), Clock sweep (a hand sweeps round from 12 o'clock). All use plain Qt painting, no new packages.
  - Wipe: a straight edge sweeps across. Slide: old and new push across together. Blinds: 8 slats open one after another.
    Open: the new picture opens from the middle outwards.
  - Plays ONLY on the full-screen display, when you click Project (comes on), Project while live (switches, direction follows whether you
    pressed Next or Previous before Project) or Project Off (goes away). Enter, Next/Previous, edits and settings still change the preview
    only, and the preview never animates. Same picture projected again = no animation.
  - Light on old PCs: two snapshots of the screen are drawn with plain Qt painting (opacity, clipping), no GPU effects, nothing is
    re-laid-out each frame. Cut, 0 ms or a ticked-off box = instant.
  - Code: `revelatelite/transitions.py` (pure maths, tested), `projection.py` (`ProjectionWindow.transition`). Tests: `tests/test_transitions.py`.
- If only one screen is found, the projection opens as a normal window so you can still test.
- Yoruba verses show the required credit line on screen (CC BY-SA 4.0). KJV/ASV/WEB are public domain.
- Settings and the service list live in `%APPDATA%\RevelateTWLite`.

## Set up on Windows 8.1 (32-bit), step by step
1. Windows Update should have April 2014 update (KB2919355) and Universal C Runtime (KB2999226). Without them you
   get "api-ms-win-crt-runtime-l1-1-0.dll is missing".
2. Install Python 3.8.10 **32-bit** ("Windows x86 executable installer") from python.org. Tick "Add Python to PATH".
3. Download this branch (`poc/lite-pyqt5`) as ZIP from GitHub and unzip it.
4. Open the unzipped folder, click the address bar, type `cmd`, press Enter.
5. Run `python -m pip install -r lite\requirements-lite.txt`  (installs PyQt5 5.15.2).
6. Run `lite\run_lite.bat` (or `python lite\run_lite.py`).

## Make a double-click app (no Python needed on other PCs)
On the same PC after step 5: run `lite\build_lite.bat`. It runs the tests, then builds `dist\RevelateTWLite\RevelateTWLite.exe`
with PyInstaller 4.10 (last line that supports 32-bit Windows 8.1 with Python 3.8). Copy the whole `RevelateTWLite` folder.
Not yet run on Windows. If it fails, send the last 20 lines.

## Checklist to send back
1. Does it open? Does the logo show?
2. `python lite\run_lite.py --smoke` prints "peak memory: N MB".
3. Plug in a projector/second monitor (Extend, not Duplicate): does Project fill that screen?
4. Does `Windows key + P` set to "Duplicate" still look right? (the app then shows on both)
5. Task Manager memory while running.

## Tests (no PyQt needed)
`python lite\tests\test_lite.py` (31 tests: reference parsing, verse/range/step/search, all four packs, display
picking, settings and service list files). `python lite\tests\test_poc.py` still runs the old proof of concept.

## Files
- `lite/revelatelite/bible.py` Bible access. `layout.py` display choice and font fitting. `projection.py` projection window.
  `app.py` operator window. `settings.py`, `servicelist.py` small JSON files. `paths.py` finds data in source or EXE.
- `lite/poc.py` the original proof of concept, kept for reference.

## Songs: import and export
Songs use the same `.rtsong` file as the main RevelateTW, so songs move both ways. Export song / Export all write
`{"format": "rtsong", "version": 1, "songs": [{"title", "author", "sections": [{"label", "lines"}]}]}`
(UTF-8, safe Windows file names, written to a temp file then renamed). Import reads `.rtsong`, single-song `.json`
and plain `.txt` lyrics; a same-title song becomes "Title (2)" and nothing is ever overwritten. Neither import nor
export touches the preview or the projected screen.

## Add Bible (import your own licensed Bible)
Press **Add Bible...** next to Look up. Choose a USFM, OSIS (XML) or plain text file. Lite reuses the main app's
converter (`revelatetw/bible_import.py`) so both editions read these files the same way, and writes the same
`.sqlite` pack. You see books/chapters/verses and sample verses before saving, then give a name, short code
(2 to 16 letters/digits) and licence. Packs go in your user folder (created on first import), never replace
bundled KJV/ASV/WEB/Yoruba, and appear in the translation list at once. Files over 60 MB are refused (a whole Bible
is a few MB), and only the Python standard library is used. Removing an imported Bible is available in code
(`bibleconvert.remove`) but has no button yet. Still missing versus main: pasting text, Zefania/other formats the
main dialog may add, and a remove button.

## Tests
`python -m pytest lite/tests` (Python 3.8 + PyQt5 5.15.2). Tests that compare with the main app's `song_io` are
skipped on 3.8 because the main app needs 3.9+. Not yet run on real Windows 8.1 32-bit hardware.

## Not in Lite (yet)
Live listening and auto verse detection, theme editor, backgrounds/media, audio routing, NDI/OBS output.
Main branch is untouched; all of this is on `poc/lite-pyqt5`.


Note: tests run headless (offscreen). Smoothness on a real Windows 8.1 32-bit / 2 GB PC has not been tested.
