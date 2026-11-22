@echo off
title Stop StudySoft
echo Stopping StudySoft backend processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'backend.server|STUDYSOFT\\\\main.py|STUDYSOFT\\main.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Done.
timeout /t 2 >nul
