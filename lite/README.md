# RevelateTW Lite: proof of concept

Tiny test to see if PyQt5 runs on a Windows 8.1 32-bit PC with 2GB RAM. It shows the RevelateTW
logo and colours, looks up a verse (default John 3:16) from the bundled Bible files, and shows it
in a second "Projection" window (full screen on a second monitor if one is plugged in).

**Status: NOT tested on Windows 8.1 32-bit yet.** It was only run on Linux. Please run it and tell us.

## Set up on Windows 8.1 (32-bit), step by step
1. Install Python 3.8.10 **32-bit** ("Windows x86 executable installer") from python.org/downloads/release/python-3810/.
   Tick "Add Python to PATH". (Python 3.9+ does not support Windows 8.1.)
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
