# RevelateTW Lite: proof of concept

Tiny test to see if PyQt5 runs on a Windows 8.1 32-bit PC with 2GB RAM. It shows the RevelateTW
logo and colours, looks up a verse (default John 3:16) from the bundled Bible files, and shows it
in a second "Projection" window (full screen on a second monitor if one is plugged in).

**Status: NOT tested on Windows 8.1 32-bit yet.** Only the pure-Python tests were run, on Linux. Docs and PyPI metadata say it should work (see Prerequisites), but that is not a real test.

## Prerequisites (from Microsoft/Python/Qt docs and the wheel itself)
- Windows 8.1 with the April 2014 update (KB2919355) and the Universal C Runtime update (KB2999226) installed. Windows Update normally gives you both. Without UCRT you get errors like api-ms-win-crt-runtime-l1-1-0.dll missing.
- PyQt5 5.15.2 win32 wheel ships its own vcruntime140/msvcp140 DLLs, so no separate VC++ redistributable is expected to be needed.
- The wheel also ships opengl32sw.dll (software OpenGL), so no graphics driver is required for this widget-only PoC.

## Set up on Windows 8.1 (32-bit), step by step
1. Install Python 3.8.10 **32-bit** ("Windows x86 executable installer") from python.org/downloads/release/python-3810/.
   Tick "Add Python to PATH". (3.8.10 is the last 3.8 release with installers. Python 3.9/3.10 also run on 8.1, but 3.8.10 is what this PoC targets.)
2. Download this branch as a ZIP from GitHub (green Code button, branch `poc/lite-pyqt5`) and unzip it.
3. Open the unzipped folder, click the address bar, type `cmd`, press Enter.
4. Run: `python -m pip install PyQt5==5.15.2`   (if it says no matching file for 32-bit, tell us; 5.15.2 is the 32-bit wheel to try).
5. Run: `python lite\poc.py`

You should see the logo, "John 3:16" and the KJV text. Press **Project** to open the second window.

## Memory check
Run `python lite\poc.py --smoke`. It opens, looks up, projects, prints "peak memory: N MB" and quits.
Also open Task Manager while it runs. Send us the number.

## Tests (no PyQt needed)
`python lite\tests\test_poc.py`

## Notes
- Only plain `sqlite3` and `PyQt5` are used. Brand colours and sizes come from `revelatetw/ui_tokens.py`; logo from `revelatetw/assets/logo.png`; verses from `data/bible/*.sqlite` (licenses: `data/bible/LICENSES.md`).
- Database schema: table `verses(book_id, chapter, verse, text)`, table `meta(key, value)`.
- Main branch is untouched; this lives on branch `poc/lite-pyqt5`.
