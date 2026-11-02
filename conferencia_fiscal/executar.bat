@echo off
rem Dois cliques aqui rodam o processo inteiro com o que estiver no config.json.
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" processar.py
) else (
    python processar.py
)
echo.
pause
