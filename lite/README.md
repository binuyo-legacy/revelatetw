# RevelateTW Lite

A small, offline version of RevelateTW for old PCs (target: Windows 8.1, 32-bit, 2GB RAM). Same
look as the main app (navy and gold, same logo, same colour/type/spacing values from
`revelatetw/ui_tokens.py`). The heavy parts (live sermon listening, verse detection, theme editor, audio routing,
NDI/OBS output) are left out on purpose.

**Status: NOT tested on a real Windows 8.1 32-bit PC yet.** All logic is unit tested and the app was started
and screenshot-checked on Linux (peak memory about 62 MB there). Please run it on the real PC and send the
numbers from the checklist below.

## What it does
- Offline Bible lookup from the bundled packs (KJV, ASV, WEB, Yoruba Contemporary). Type `John 3:16`, `rom 8:28-30`,
  `1 cor 13`, `first john 4:8`.
- Next / previous verse (crosses chapter and book ends). PageDown / PageUp also projects it straight away.
- Search by words ("loved world").
- Service list: line up verses before the service, reorder, saved automatically.
- Projection: borderless full-screen window on the extended (second) display, text auto-sized to fit, 3 colour
  styles, text size, show/hide reference. Black screen button (Esc). Project (F5).
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
`python lite\tests\test_lite.py` (22 tests: reference parsing, verse/range/step/search, all four packs, display
picking, settings and service list files). `python lite\tests\test_poc.py` still runs the old proof of concept.

## Files
- `lite/revelatelite/bible.py` Bible access. `layout.py` display choice and font fitting. `projection.py` projection window.
  `app.py` operator window. `settings.py`, `servicelist.py` small JSON files. `paths.py` finds data in source or EXE.
- `lite/poc.py` the original proof of concept, kept for reference.

## Not in Lite (yet)
Live listening and auto verse detection, songs, theme editor, backgrounds/media, audio routing, NDI/OBS output, importing
licensed Bibles. Main branch is untouched; all of this is on `poc/lite-pyqt5`.
