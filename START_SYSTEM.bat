@echo off
REM ============================================================================
REM  AGENT OBSERVABILITY SYSTEM - ONE-CLICK STARTUP
REM  
REM  This script:
REM  1. Activates virtual environment
REM  2. Checks/trains ML models
REM  3. Starts API server
REM  4. Loads demo data
REM  5. Opens dashboard in browser
REM  
REM  Double-click to run!
REM ============================================================================

echo.
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║              AGENT OBSERVABILITY SYSTEM                          ║
echo ║              Starting Complete System...                         ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM Activate virtual environment and run
call venv\Scripts\activate.bat && python run_complete_system.py

pause
