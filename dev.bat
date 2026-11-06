@echo off
set "ROOT=%~dp0"
set "PYTHON=%ROOT%backend\env\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo No encuentro el entorno en backend\.env
  echo Ajusta la ruta de PYTHON en este archivo.
  pause
  exit /b 1
)

start "RaceStrategy API" /D "%ROOT%backend\src" cmd /k ""%PYTHON%" -m uvicorn api:app --reload --port 8000"
start "RaceStrategy Frontend" powershell.exe -NoExit -Command "Set-Location -LiteralPath '%ROOT%frontend'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
start "" http://localhost:5173