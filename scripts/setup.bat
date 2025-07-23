@echo off
echo ========================================
echo   FinFlash - Initial Setup
echo ========================================
echo.

REM Check Python version
echo [INFO] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.9 or higher from:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version

REM Create virtual environment
echo.
echo [INFO] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
)

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo.
echo [INFO] Installing dependencies...
pip install -r requirements.txt

REM Create .env file if not exists
echo.
if not exist ".env" (
    echo [INFO] Creating .env file...
    copy .env.example .env >nul 2>&1
    echo [ACTION] Please edit .env file with your API keys
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo To start the application, run:
echo   python run.py
echo.
pause 