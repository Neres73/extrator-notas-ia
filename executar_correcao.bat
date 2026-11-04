@echo off
rem Dois cliques aqui: processo completo das OMs de correção (Base Geral -> PLU -> ME2K -> criação -> IW32).
rem Deixe o SAP aberto e logado.
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" correcao.py
) else (
    python correcao.py
)
echo.
pause
