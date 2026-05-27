@echo off
title OMISPHERE - First-run setup
setlocal enabledelayedexpansion
cd /d "%~dp0..\"
echo.
echo   ============================================
echo    OMISPHERE - First-run setup
echo   ============================================
echo.

REM ----- Python check -----
set PYCMD=
where py >nul 2>nul && set PYCMD=py
if "%PYCMD%"=="" where python >nul 2>nul && set PYCMD=python
if "%PYCMD%"=="" (
    echo [FAIL] Python is not installed or not in PATH.
    echo        Install Python 3.11+ from https://www.python.org/downloads/
    echo        Check "Add Python to PATH" during install.
    pause & exit /b 1
)
echo [OK]   Python detected: %PYCMD%

REM ----- Node check -----
where node >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Node.js is not installed or not in PATH.
    echo        Install Node.js 20 LTS from https://nodejs.org/
    echo        Check "Automatically install necessary tools" during install.
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do echo [OK]   Node detected: %%i

REM ----- API: pip install -----
echo.
echo   Installing API dependencies (Python)...
echo   ------------------------------------------------------------
cd /d "%~dp0..\apps\api"
%PYCMD% -m pip install -e .[youtube]
if errorlevel 1 (
    echo [FAIL] pip install failed. See messages above.
    pause & exit /b 1
)
echo [OK]   API deps installed.

REM ----- Web: npm install -----
echo.
echo   Installing Web dependencies (Node)...
echo   ------------------------------------------------------------
cd /d "%~dp0..\apps\web"
call npm install
if errorlevel 1 (
    echo [FAIL] npm install failed. See messages above.
    pause & exit /b 1
)
echo [OK]   Web deps installed.

REM ----- .env -----
cd /d "%~dp0..\apps\api"
if not exist ".env" (
    if exist "..\..\.env.example" (
        copy /Y "..\..\.env.example" ".env" >nul
        echo [OK]   Created apps\api\.env from .env.example
    ) else (
        echo OMI_ENV=development > .env
        echo OMI_REQUIRE_AUTH=false >> .env
        echo OMI_YOUTUBE_API_KEY= >> .env
        echo OMI_SESSION_SECRET=dev-only-change-me-12345678901234567890 >> .env
        echo [OK]   Created starter apps\api\.env
    )
    echo.
    echo   NEXT STEP: Edit apps\api\.env and set OMI_YOUTUBE_API_KEY=^<your key^>
    echo.
)

echo.
echo   ============================================
echo    Setup complete.
echo   ============================================
echo.
echo   To launch OMISPHERE, double-click:
echo     start_omisphere.bat
echo.
pause
