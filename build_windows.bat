@echo off
setlocal

REM ============================================================
REM Usage examples:
REM
REM build_windows.bat
REM   Runs a normal build with default settings:
REM   - Does NOT clean previous build artifacts
REM   - Does NOT force reinstall dependencies
REM   - Opens the output folder after build
REM
REM build_windows.bat --clean
REM   Performs a clean build:
REM   - Removes previous build/dist/temp files before building
REM   - Useful when builds are failing or behaving inconsistently
REM
REM build_windows.bat --clean --install-deps
REM   Full rebuild with dependency reinstall:
REM   - Cleans previous build artifacts
REM   - Forces reinstallation of dependencies
REM   - Useful after changing requirements or fixing broken environments
REM
REM build_windows.bat --no-open
REM   Runs build but does NOT open the output folder afterward
REM   - Useful for automation or CI-like workflows
REM
REM Available flags:
REM   --clean           -> sets CLEAN_BUILD=1
REM   --install-deps    -> sets FORCE_DEPS=1
REM   --upgrade-pip     -> sets UPGRADE_PIP=1
REM   --no-open         -> sets OPEN_DIST=0
REM ============================================================

cd /d "%~dp0"

set "CLEAN_BUILD=0"
set "FORCE_DEPS=0"
set "UPGRADE_PIP=0"
set "OPEN_DIST=1"

if "%~1"=="" goto show_menu

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--clean" set "CLEAN_BUILD=1"
if /i "%~1"=="--install-deps" set "FORCE_DEPS=1"
if /i "%~1"=="--upgrade-pip" set "UPGRADE_PIP=1"
if /i "%~1"=="--no-open" set "OPEN_DIST=0"
shift
goto parse_args

:show_menu
echo.
echo Select a build option:
echo   [1] Fast build
echo   [2] Clean build
echo   [3] Clean build + reinstall dependencies
echo   [4] Fast build, do not open dist folder
choice /C 1234 /N /M "Enter choice: "
if errorlevel 4 (
    set "OPEN_DIST=0"
    goto args_done
)
if errorlevel 3 (
    set "CLEAN_BUILD=1"
    set "FORCE_DEPS=1"
    goto args_done
)
if errorlevel 2 (
    set "CLEAN_BUILD=1"
    goto args_done
)
goto args_done

:args_done

echo [1/6] Checking Python...
where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher ^("py"^) was not found. Install Python for Windows first.
    exit /b 1
)

echo [2/6] Checking for running SystemMonitor instances...
tasklist /FI "IMAGENAME eq SystemMonitor.exe" | find /I "SystemMonitor.exe" >nul
if not errorlevel 1 (
    echo SystemMonitor.exe is currently running.
    echo Close it before building so PyInstaller can replace dist\SystemMonitor.exe.
    exit /b 1
)

echo [3/6] Checking runtime and build dependencies...
if "%FORCE_DEPS%"=="1" goto install_deps
py -c "import importlib.util, sys; mods=['PyInstaller','pynput','win32api','pystray','PIL','mss','numpy','pygame','pyautogui','pytesseract','psutil','pymem','cv2']; missing=[m for m in mods if importlib.util.find_spec(m) is None]; print('Dependencies already installed.' if not missing else 'Missing modules: ' + ', '.join(missing)); sys.exit(0 if not missing else 1)"
if not errorlevel 1 goto deps_done

:install_deps
if "%UPGRADE_PIP%"=="1" (
    echo Upgrading pip...
    py -m pip install --upgrade pip
    if errorlevel 1 exit /b 1
)
echo Installing missing dependencies...
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

:deps_done

echo [4/6] Cleaning previous build artifacts...
if "%CLEAN_BUILD%"=="1" (
    if exist build rmdir /s /q build
    if exist dist rmdir /s /q dist
    if exist SystemMonitor.spec-build rmdir /s /q SystemMonitor.spec-build
    echo Clean build requested.
) else (
    echo Reusing existing build caches for a faster incremental build.
)

echo [5/6] Preparing bundled Tesseract...
set TESSERACT_SOURCE=
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set TESSERACT_SOURCE=%ProgramFiles%\Tesseract-OCR
if not defined TESSERACT_SOURCE if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set TESSERACT_SOURCE=%ProgramFiles(x86)%\Tesseract-OCR
if not defined TESSERACT_SOURCE (
    echo Tesseract was not found in a standard install location.
    echo Install Tesseract on the build machine first, or copy it into vendor\tesseract manually.
    exit /b 1
)
mkdir vendor\tesseract >nul 2>nul
robocopy "%TESSERACT_SOURCE%" "vendor\tesseract" /MIR /FFT /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 exit /b 1

echo [6/6] Building executable with PyInstaller...
set "PYINSTALLER_FLAGS=--noconfirm"
if "%CLEAN_BUILD%"=="1" set "PYINSTALLER_FLAGS=%PYINSTALLER_FLAGS% --clean"
py -m PyInstaller %PYINSTALLER_FLAGS% "SystemMonitor.spec"
if errorlevel 1 exit /b 1

REM Remove stray bootloader exe (COLLECT output has the correct bundled version)
if exist "dist\SystemMonitor.exe" (
    echo Removing stray executable at dist\SystemMonitor.exe...
    del "dist\SystemMonitor.exe"
)

echo Build complete.
echo Executable path: "%cd%\dist\SystemMonitor\SystemMonitor.exe"

if "%OPEN_DIST%"=="1" if exist "dist\SystemMonitor\SystemMonitor.exe" (
    echo Launching output folder...
    start "" "%cd%\dist\SystemMonitor"
)

endlocal
