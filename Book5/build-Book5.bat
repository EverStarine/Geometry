@echo off
title Geometry Book5 Build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-Book5.ps1" %*
exit /b %ERRORLEVEL%
