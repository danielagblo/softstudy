@echo off
title StudySoft Launcher
cd /d "%~dp0"

echo ========================================
echo   StudySoft - one-click start
echo ========================================
echo.

set "PY="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY where python >nul 2>&1 && for /f "delims=" %%i in ('where python') do (
  set "PY=%%i"
  goto :have_py
)
:have_py
if not defined PY (
  echo Python is not installed.
  echo Install from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup: creating environment and installing packages...
  "%PY%" -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo [1/3] Starting backend web page...
start "StudySoft Backend" /min cmd /c "cd /d \"%~dp0\" && call .venv\Scripts\activate.bat && python -m backend.server"

timeout /t 4 /nobreak >nul

echo [2/3] Opening web control page in your browser...
start "" "http://127.0.0.1:8000"

echo [3/3] Starting desktop overlay...
echo.
echo Tip: Keep this window open while studying.
echo Close the overlay with Quit, then close this window.
echo.
python main.py

echo.
echo StudySoft closed.
pause
