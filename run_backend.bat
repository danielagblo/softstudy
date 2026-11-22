@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first to create the virtual environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install fastapi "uvicorn[standard]" pydantic -q
echo Starting StudySoft backend at http://127.0.0.1:8000
echo API docs: http://127.0.0.1:8000/docs
python -m backend.server
pause
