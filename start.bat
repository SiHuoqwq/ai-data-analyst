@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Starting AI Data Analyst...
py -m app.run
pause
