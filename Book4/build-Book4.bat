@echo off
title Geometry Book4 Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-Book4.ps1" %*
exit /b %ERRORLEVEL%
