@echo off
setlocal
cd /d "%~dp0"
title FNF Pixel Player Bot

if not exist ".venv\Scripts\python.exe" (
    echo First run: creating virtual environment...
    where python >nul 2>nul
    if errorlevel 1 goto nopython
    python -m venv .venv
    if errorlevel 1 goto fail
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo Bot exited with an error. Details: error.log
    pause
)
exit /b 0

:nopython
echo Python not found in PATH.
echo Install Python 3.9+ from python.org and tick "Add python.exe to PATH".
pause
exit /b 1

:fail
echo.
echo Failed to prepare the environment. Check the internet connection.
pause
exit /b 1
