@echo off
echo.
echo SystemMonitor Build Script
echo Usage: build.bat [--luxe] [--both] [--clean] [--install-deps] [--upgrade-pip] [--no-open]
echo   --luxe           Build Luxe (CustomTkinter) UI instead of default Tkinter
echo   --both           Build both Tkinter and Luxe UIs
echo   Or run without arguments for the interactive menu.
echo.

REM Try Python 3.12 first, then 3.14
set PY_CMD=
py -3.12-64 -c "import sys; sys.exit(0)" >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=py -3.12-64
) else (
    py -3.14-64 -c "import sys; sys.exit(0)" >nul 2>nul
    if %errorlevel% equ 0 (
        set PY_CMD=py -3.14-64
    )
)

if "%PY_CMD%"=="" (
    echo.
    echo Python 3.12 or 3.14 64-bit was not found.
    echo Install Python 3.12.x or 3.14.x 64-bit from https://www.python.org/downloads/windows/
    echo Make sure the Windows Python launcher ^("py"^) is installed and available.
    echo Then verify it with: py -3.12-64 --version
    echo.
    pause
    exit /b 1
)

%PY_CMD% "%~dp0build.py" %*
