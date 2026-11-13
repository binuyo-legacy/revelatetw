@echo off
rem Start RevelateTW Lite. Double click this file.
cd /d "%~dp0\.."
python lite\run_lite.py
if errorlevel 1 (
    echo.
    echo RevelateTW Lite did not start. Read the message above, or see lite\README.md.
    pause
)
