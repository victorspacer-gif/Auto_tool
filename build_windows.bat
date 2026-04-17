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

py -m pip install pyinstaller pynput pywin32 pystray pillow mss numpy pygame pyautogui pytesseract psutil pymem
if errorlevel 1 exit /b 1

echo [3/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SystemMonitor.spec-build rmdir /s /q SystemMonitor.spec-build
if exist vendor\tesseract rmdir /s /q vendor\tesseract

echo [4/6] Preparing bundled Tesseract...
set TESSERACT_SOURCE=
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set TESSERACT_SOURCE=%ProgramFiles%\Tesseract-OCR
if not defined TESSERACT_SOURCE if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set TESSERACT_SOURCE=%ProgramFiles(x86)%\Tesseract-OCR
if not defined TESSERACT_SOURCE (
    echo Tesseract was not found in a standard install location.
    echo Install Tesseract on the build machine first, or copy it into vendor\tesseract manually.
    exit /b 1
)
mkdir vendor\tesseract >nul 2>nul
xcopy /e /i /y "%TESSERACT_SOURCE%\*" "vendor\tesseract\" >nul
if errorlevel 1 exit /b 1

echo [5/6] Building executable with PyInstaller...
py -m PyInstaller --noconfirm --clean "SystemMonitor.spec"
if errorlevel 1 exit /b 1

echo [6/6] Build complete.
echo Executable path: "%cd%\dist\SystemMonitor.exe"

if exist "dist\SystemMonitor.exe" (
    echo Launching output folder...
    start "" "%cd%\dist"
)

endlocal
