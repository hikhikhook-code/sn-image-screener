@echo off
rem -----------------------------------------------------------------------
rem  Build a single-file Windows .exe for SN Image Screener.
rem
rem  Usage: open a CMD prompt with Python 3.11 (or 3.10/3.12) on PATH, run:
rem      build_windows.bat
rem
rem  Output:  dist\"SN Image Screener.exe"
rem -----------------------------------------------------------------------
setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python.exe not found on PATH.
    exit /b 1
)

if not exist .venv (
    echo [INFO] creating virtualenv .venv ...
    python -m venv .venv || exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || exit /b 1

if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

pyinstaller sn_image_screener.spec --noconfirm || exit /b 1

echo.
echo [DONE] build complete: dist\"SN Image Screener.exe"
endlocal
