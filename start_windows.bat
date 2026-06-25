@echo off
setlocal
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if exist .venv\Scripts\python.exe (
  set PYTHON=.venv\Scripts\python.exe
) else (
  set PYTHON=python
)
%PYTHON% -m uvicorn app:app --host 0.0.0.0 --port 8004
endlocal
