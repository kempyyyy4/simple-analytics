@echo off
rem One-time setup for each computer. Double-click once; safe to run again.
setlocal
cd /d "%~dp0"
echo.
echo === Rupert Analytics setup ===
echo.

set PY=python
where py >nul 2>nul && set PY=py -3

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  %PY% -m venv .venv || goto :fail
)

echo Installing the YouTube connector and the app libraries (a few minutes the first time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install -e connector -r requirements.txt || goto :fail

echo Creating the desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Rupert Analytics.lnk'); $s.TargetPath = '%~dp0Rupert Analytics.bat'; $s.WorkingDirectory = '%~dp0'; $s.Save()" || goto :fail

if not exist "%APPDATA%\youtube-analytics-mcp\token.json" (
  echo.
  echo This computer isn't signed in to YouTube yet. Signing in now...
  call "%~dp0Sign in to YouTube.bat"
)

echo.
echo Setup finished. Double-click "Rupert Analytics" on the desktop to open the app.
pause
exit /b 0

:fail
echo.
echo Setup stopped with an error. Copy the messages above and send them to Claude.
pause
exit /b 1
