@echo off
rem Double-click to sign this computer in to the YouTube channel (opens your browser).
cd /d "%~dp0"
if not exist ".venv\Scripts\ytmcp.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\ytmcp.exe" auth
echo.
pause
