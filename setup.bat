@echo off
REM ============================================================
REM SmartCivic AI - Windows Setup Script
REM Run this after cloning the repo: setup.bat
REM ============================================================

echo.
echo ====================================
echo   SmartCivic AI - Project Setup
echo ====================================
echo.

REM --- Step 1: Create Python virtual environment ---
echo [1/4] Creating Python virtual environment...
if exist .venv (
    echo       .venv already exists, skipping...
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python not found. Please install Python 3.9+ from https://python.org
        pause
        exit /b 1
    )
    echo       Done!
)

REM --- Step 2: Activate venv and install dependencies ---
echo [2/4] Installing Python dependencies...
call .venv\Scripts\activate.bat
pip install -r backend\requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done!

REM --- Step 3: Create .env from .env.example if it doesn't exist ---
echo [3/4] Setting up environment variables...
if exist backend\.env (
    echo       backend\.env already exists, skipping...
) else (
    copy backend\.env.example backend\.env
    echo       Created backend\.env from .env.example
    echo       IMPORTANT: Edit backend\.env with your actual credentials!
)

REM --- Step 4: Done ---
echo [4/4] Setup complete!
echo.
echo ====================================
echo   To start the server, run:
echo     .venv\Scripts\activate
echo     python backend\app.py
echo.
echo   Then open: http://127.0.0.1:5000
echo ====================================
echo.
pause
