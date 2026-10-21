@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_local.ps1"
set "buildResult=%ERRORLEVEL%"
echo.
if not "%buildResult%"=="0" echo Build stopped. Read the error above and windows\evidence\local-build.log.
pause
exit /b %buildResult%
