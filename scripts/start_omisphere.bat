@echo off
title OMISPHERE - Launcher
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo.
echo   ============================================
echo    OMISPHERE - Starting
echo   ============================================
echo.

REM ----- Python check -----
set PYCMD=
where py >nul 2>nul && set PYCMD=py
if "%PYCMD%"=="" where python >nul 2>nul && set PYCMD=python
if "%PYCMD%"=="" (
    echo [FAIL] Python not found. Run setup_omisphere.bat first.
    pause & exit /b 1
)

REM ----- Node check -----
where node >nul 2>nul
if errorlevel 1 (
    echo [FAIL] Node.js not found. Run setup_omisphere.bat first.
    pause & exit /b 1
)

REM ----- Load .env for the API window -----
cd /d "%~dp0..\apps\api"
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" set "%%a=%%b"
    )
    echo [OK]   Loaded apps\api\.env
) else (
    echo [WARN] apps\api\.env not found.  Run setup_omisphere.bat or create it.
)

REM ----- Launch API in its own window -----
echo.
echo   Starting omi API on http://127.0.0.1:8000 ...
start "OMISPHERE - API (omi engine)" cmd /k "cd /d %~dp0..\apps\api && %PYCMD% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

REM ----- Launch Web in its own window -----
echo   Starting Web on http://localhost:3000 ...
start "OMISPHERE - Web" cmd /k "cd /d %~dp0..\apps\web && npm run dev"

REM ----- Open browser -----
echo   Opening browser in 8 seconds...
start "" cmd /c "timeout /t 8 /nobreak >nul && start http://localhost:3000 && exit"

echo.
echo   ============================================
echo    OMISPHERE is starting in two new windows.
echo    Leave both windows open while you use it.
echo    Close them when you're done.
echo   ============================================
echo.
echo   You can close this launcher window now.
echo.
pause
