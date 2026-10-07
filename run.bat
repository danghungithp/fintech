@echo off
REM FinViet Pro - khoi dong ung dung phan tich dau tu chung khoan Viet Nam
title FinViet Pro
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ va them vao PATH.
  pause
  exit /b 1
)

echo Dang kiem tra thu vien...
python -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo Dang cai dat Flask...
  python -m pip install -r requirements.txt
)

echo.
echo ============================================
echo   FinViet Pro - http://127.0.0.1:5000
echo   Nhan CTRL+C de dung ung dung
echo ============================================
echo.
start "" http://127.0.0.1:5000
python app.py
pause
