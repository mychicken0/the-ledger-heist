@echo off
setlocal

cd /d "%~dp0\.."

set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"

"%PYTHON_CMD%" -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --name TheLedgerHeist ^
  --onefile ^
  --console ^
  --add-data "data;data" ^
  --add-data "app\theme.tcss;app" ^
  main.py

if errorlevel 1 (
  echo.
  echo Build failed. Activate a Python 3.11+ environment with PyInstaller installed, then run this script again.
  exit /b %errorlevel%
)

echo.
echo Build complete: dist\TheLedgerHeist.exe

endlocal
