@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Checking port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo Port 8000 occupied by PID %%a, killing...
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting AI Data Analyst...
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
