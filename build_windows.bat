@echo off
setlocal

cd /d "%~dp0"

echo [1/5] Checking Python...
where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher ^("py"^) was not found. Install Python for Windows first.
    exit /b 1
)

echo [2/5] Installing runtime and build dependencies...
py -m pip install --upgrade pip
if errorlevel 1 exit /b 1

py -m pip install pyinstaller pynput pywin32 pystray pillow mss numpy pygame pyautogui
if errorlevel 1 exit /b 1

echo [3/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SystemMonitor.spec-build rmdir /s /q SystemMonitor.spec-build

echo [4/5] Building executable with PyInstaller...
py -m PyInstaller --noconfirm --clean "SystemMonitor.spec"
if errorlevel 1 exit /b 1

echo [5/5] Build complete.
echo Executable path: "%cd%\dist\SystemMonitor.exe"

if exist "dist\SystemMonitor.exe" (
    echo Launching output folder...
    start "" "%cd%\dist"
)

endlocal
