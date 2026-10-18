@echo off
setlocal
title Mail Secretary - Microsoft OAuth2
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Get-Outlook-Token.ps1"
echo.
pause
