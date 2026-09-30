@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kairisei MA Wiki - Local Server

if not exist "runtime\node.exe" (
  echo.
  echo   [ERROR] runtime\node.exe not found. Package is incomplete.
  echo.
  pause
  exit /b 1
)

"runtime\node.exe" "server.mjs"

echo.
echo   Server stopped. Press any key to close this window...
pause >nul
