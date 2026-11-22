@echo off
cd /d "%~dp0"

set "PY="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python not found. Install Python 3.12+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  "%PY%" -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements-desktop.txt
) else (
  call .venv\Scripts\activate.bat
)

python main.py
pause
