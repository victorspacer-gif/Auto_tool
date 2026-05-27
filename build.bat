@echo off
py -3.12-64 -c "import platform, sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and platform.architecture()[0] == '64bit' else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python 3.12 64-bit was not found.
    echo Install Python 3.12.x 64-bit from https://www.python.org/downloads/windows/
    echo Make sure the Windows Python launcher ^("py"^) is installed and available.
    echo Then verify it with: py -3.12-64 --version
    echo.
    pause
    exit /b 1
)
py -3.12-64 "%~dp0build.py" %*
