@echo off
chcp 65001 >nul 2>&1
cd /d i:\smart_grid_home\projects\transcript_ai_v2

echo Starting React dev server...
start "V2 React" cmd /c "npm run react-start 2>&1"

echo Waiting for React to start (15 seconds)...
timeout /t 15 /nobreak >nul

echo Starting Electron...
start "V2 Electron" cmd /c "npm run electron-dev 2>&1"

echo.
echo App launched! Check for Electron window.
