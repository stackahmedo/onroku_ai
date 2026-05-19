@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo  Onroku AI V6.0 -- Production Launcher
echo ============================================

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM Check Node / npm
call npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
)

REM Resolve which venv to use
set "V2_VENV=%~dp0venv\Scripts"
set "V1_VENV=i:\smart_grid_home\projects\transcript_ai\venv\Scripts"
set "CHOSEN_PYTHON="

if exist "%V2_VENV%\python.exe" (
    echo [Info] Using V2 virtual environment.
    set "CHOSEN_PYTHON=%V2_VENV%\python.exe"
    set "CHOSEN_PIP=%V2_VENV%\pip.exe"
    call "%V2_VENV%\activate.bat"
    goto :VENV_OK
)

if exist "%V1_VENV%\python.exe" (
    echo [Info] V2 venv not found - using shared V1 virtual environment.
    set "CHOSEN_PYTHON=%V1_VENV%\python.exe"
    set "CHOSEN_PIP=%V1_VENV%\pip.exe"
    call "%V1_VENV%\activate.bat"
    goto :VENV_OK
)

echo [Setup] No virtual environment found. Creating V2 venv...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] venv creation failed.
    pause
    exit /b 1
)
set "CHOSEN_PYTHON=%V2_VENV%\python.exe"
set "CHOSEN_PIP=%V2_VENV%\pip.exe"
call "%V2_VENV%\activate.bat"

:VENV_OK

REM Install Python deps if needed
if not exist "%~dp0.deps_v2_installed" (
    echo [Setup] Checking / installing Python packages...
    "%CHOSEN_PIP%" install faster-whisper sse-starlette psutil ffmpeg-python >nul 2>&1
    echo installed > "%~dp0.deps_v2_installed"
)

REM Install npm deps if node_modules missing
if not exist node_modules (
    echo [Setup] Installing npm packages...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

REM Ensure production assets are built
if not exist build (
    echo [Setup] Compiling offline production assets...
    call npm run build
)

REM Kill any stale backend on port 8000
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
ping 127.0.0.1 -n 2 >nul

echo.
echo Starting Onroku AI V6.0 (Offline Mode)...
echo (Close this window or press Ctrl+C to stop)
echo.
"%CHOSEN_PYTHON%" "%~dp0launcher.py" --prod

echo.
echo Application stopped.
pause
