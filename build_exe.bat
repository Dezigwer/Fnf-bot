@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo    Creating .venv ...
    py -3 -m venv .venv
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 goto :fail
)

echo [2/4] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [3/4] Building one-file EXE...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "FNF-Pixel-Player-Bot" ^
    --icon "assets\icon.ico" ^
    --add-data "selftest.py;." ^
    --add-data "assets\icon.ico;assets" ^
    --collect-submodules mss ^
    --hidden-import PIL.ImageTk ^
    main.py
if errorlevel 1 goto :fail

echo [4/4] Copying EXE to project root...
copy /y "dist\FNF-Pixel-Player-Bot.exe" "FNF-Pixel-Player-Bot.exe" >nul
if errorlevel 1 goto :fail

echo.
echo Done: FNF-Pixel-Player-Bot.exe
echo You can copy this single file anywhere. config.json and shots\ will appear next to it.
goto :eof

:fail
echo.
echo Build failed. Read the messages above.
exit /b 1
