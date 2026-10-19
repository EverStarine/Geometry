@echo off
title Geometry Book1 Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-Book1.ps1" %*
exit /b %ERRORLEVEL%
