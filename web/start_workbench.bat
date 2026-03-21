@echo off
setlocal

cd /d "%~dp0"

set "QUANT_PYTHON=C:\ProgramData\miniconda3\envs\quant\python.exe"

if exist "%QUANT_PYTHON%" (
  set "RUN_PYTHON=%QUANT_PYTHON%"
) else (
  set "RUN_PYTHON=python"
)

start "" http://127.0.0.1:8765
"%RUN_PYTHON%" server.py
