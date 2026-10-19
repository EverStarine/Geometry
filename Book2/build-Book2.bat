@echo off
title Geometry Book2 Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-Book2.ps1" %*
exit /b %ERRORLEVEL%
