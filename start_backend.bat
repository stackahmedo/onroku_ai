@echo off
chcp 65001 >nul 2>&1
echo Starting V2 backend...
start "Transcript AI V2 Backend" cmd /k "cd /d i:\smart_grid_home\projects\transcript_ai_v2\app\backend && i:\smart_grid_home\projects\transcript_ai\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info"
echo Waiting 6 seconds for backend to initialize...
timeout /t 6 /nobreak >nul
echo Testing backend...
curl -s http://127.0.0.1:8000/health
echo.
curl -s http://127.0.0.1:8000/hardware
echo.
echo Backend check complete.
