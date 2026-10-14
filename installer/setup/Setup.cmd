@echo off
rem Entry point invoked by the self-extracting setup stub.
setlocal
set "SCRIPT=%~dp0Install.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo Setup failed with code %RC%.
    pause
)
exit /b %RC%
