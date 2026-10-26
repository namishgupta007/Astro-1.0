@echo off
cd /d "%~dp0"
echo Starting Astrograph Backend...
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
