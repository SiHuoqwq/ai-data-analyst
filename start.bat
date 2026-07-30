@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] Preparing AI Data Analyst database...
py -m app.migrate
if errorlevel 1 (
    echo Migration failed. Backend startup has been stopped.
    pause
    exit /b 1
)

if /I "%AI_DATA_ANALYST_MIGRATE_ONLY%"=="1" (
    echo Migration-only verification completed.
    exit /b 0
)

echo [2/2] Starting AI Data Analyst backend...
py -m app.run
set "BACKEND_EXIT_CODE=%ERRORLEVEL%"
if not "%BACKEND_EXIT_CODE%"=="0" (
    echo Backend stopped with exit code %BACKEND_EXIT_CODE%.
)
pause
exit /b %BACKEND_EXIT_CODE%
