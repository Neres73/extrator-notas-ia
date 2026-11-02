@echo off
rem Dois cliques aqui: preenche o PLU da planilha das OMs com o que estiver no config.json.
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" escolher_plu.py
) else (
    python escolher_plu.py
)
echo.
pause
