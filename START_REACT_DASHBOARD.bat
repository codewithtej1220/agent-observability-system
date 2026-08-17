@echo off
REM ============================================================================
REM  AGENT OBSERVABILITY SYSTEM - Professional React Dashboard
REM  
REM  This script:
REM  1. Starts the backend API server
REM  2. Starts the React frontend dashboard
REM  3. Opens browser automatically
REM  
REM  Requirements: Node.js installed
REM ============================================================================

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║          AGENT OBSERVABILITY SYSTEM - Professional UI            ║
echo ║          Starting Backend + React Frontend...                    ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js not found! Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo ✅ Node.js detected
echo.

REM Check if frontend dependencies are installed
if not exist "frontend\node_modules" (
    echo 📦 Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
    echo ✅ Dependencies installed
    echo.
)

REM Start backend API in new window
echo 🚀 Starting Backend API Server...
start "Backend API" cmd /k "call venv\Scripts\activate.bat && uvicorn api.main:app --reload --port 8001"
timeout /t 3 /nobreak >nul

REM Start frontend React app in new window
echo 🎨 Starting React Frontend Dashboard...
start "React Dashboard" cmd /k "cd frontend && npm start"

echo.
echo ═══════════════════════════════════════════════════════════════════
echo   ✅ SYSTEM STARTED!
echo ═══════════════════════════════════════════════════════════════════
echo.
echo   Backend API:    http://localhost:8001
echo   React Dashboard: http://localhost:3000 (opens automatically)
echo.
echo   Press Ctrl+C in each window to stop
echo ═══════════════════════════════════════════════════════════════════
echo.

pause
