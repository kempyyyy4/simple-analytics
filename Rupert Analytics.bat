@echo off
rem Double-click to open Rupert Analytics. Runs the app without a console window.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Rupert Analytics isn't set up on this computer yet. Running setup first...
  call "%~dp0setup.bat"
  exit /b
)
start "" ".venv\Scripts\pythonw.exe" app.py
