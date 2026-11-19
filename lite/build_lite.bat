@echo off
rem Build RevelateTW Lite as a folder you can copy to another PC (no Python needed there).
rem Run this on the 32-bit Windows 8.1 PC with Python 3.8.10 (32-bit) installed.
cd /d "%~dp0\.."

python -m pip install -r lite\requirements-lite.txt pyinstaller==4.10
if errorlevel 1 goto fail

python lite\tests\test_lite.py
if errorlevel 1 goto fail

python -m PyInstaller lite\run_lite.py --name RevelateTWLite --windowed --noconfirm ^
  --icon "lite\revelatelite\resources\logo_icon.ico" ^
  --paths lite --paths . ^
  --add-data "revelatetw\assets\logo.png;revelatetw\assets" ^
  --add-data "lite\assets\logo\splash.jpg;lite\assets\logo" ^
  --add-data "lite\revelatelite\resources\logo_icon.png;lite\revelatelite\resources" ^
  --add-data "lite\revelatelite\resources\logo_icon.ico;lite\revelatelite\resources" ^
  --add-data "data\bible;data\bible" ^
  --exclude-module tkinter --exclude-module unittest --exclude-module numpy ^
  --exclude-module PyQt5.QtWebEngineWidgets --exclude-module PyQt5.QtMultimedia ^
  --exclude-module PyQt5.QtNetwork --exclude-module PyQt5.QtQml --exclude-module PyQt5.QtQuick
if errorlevel 1 goto fail

echo.
echo Done. Copy the folder dist\RevelateTWLite to any Windows PC and run RevelateTWLite.exe
exit /b 0

:fail
echo.
echo Build failed. Read the message above.
exit /b 1
