@echo off
setlocal
REM ============================================================
REM Launcher for build_windows.bat
REM Double-click this file to open a console in the Auto_tool
REM directory and run the build script. The window stays open
REM when finished so you can review output or errors.
REM ============================================================
cd /d "%~dp0"
echo.
echo =================== Auto_tool Build Launcher ====================
echo.
echo Running build_windows.bat...
echo.
call build_windows.bat %*
echo.
pause
