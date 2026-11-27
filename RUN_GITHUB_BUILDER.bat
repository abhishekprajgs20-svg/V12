@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title TXT 2 SHORTS V12 - GitHub APK Builder
chcp 65001 >nul

echo ================================================================
echo   TXT 2 SHORTS V12 - GITHUB APK BUILDER
echo ================================================================
echo.
echo Git for Windows is NOT required. Python 3 and internet are required.
echo This window will remain open so errors can be read.
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)
if not defined PYTHON_CMD (
  echo ERROR: Python 3 was not found.
  echo Install Python 3 from https://www.python.org/downloads/windows/
  echo During setup, enable Add Python to PATH.
  echo.
  pause
  exit /b 1
)

if not exist "upload_to_github.py" (
  echo ERROR: upload_to_github.py is missing.
  echo Extract the complete ZIP and run this BAT from the txt2shorts_android folder.
  echo.
  pause
  exit /b 1
)

echo Checking requests package...
%PYTHON_CMD% -c "import requests" >nul 2>nul
if errorlevel 1 (
  echo Installing requests for the current Windows user...
  %PYTHON_CMD% -m pip install --user requests
  if errorlevel 1 (
    echo.
    echo ERROR: requests could not be installed. Check internet and pip.
    echo Try: py -3 -m pip install --user requests
    echo.
    pause
    exit /b 1
  )
)

echo.
echo Starting uploader. Token entry is hidden.
echo Keep this window open. If an error occurs it will remain visible.
echo.
%PYTHON_CMD% -u upload_to_github.py
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Uploader exited with code %RESULT%.
  echo If needed, inspect github_uploader_error.log in this folder.
) else (
  echo Uploader finished. Check for TXT2SHORTS_V12_Universal.apk in this folder.
)
echo.
pause
exit /b %RESULT%
