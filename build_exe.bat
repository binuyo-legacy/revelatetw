@echo off
rem Build RevelateTW.exe with PyInstaller. Run from anywhere; it cd's to the repo root.
cd /d "%~dp0"

pyinstaller run.py --name RevelateTW --windowed --noconfirm --add-data "revelatetw\assets;revelatetw\assets" --add-data "data;data"
if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)

echo.
echo Build finished. Run dist\RevelateTW\RevelateTW.exe
