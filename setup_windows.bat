@echo off
setlocal EnableExtensions

cd /d "%~dp0"
if not exist "%~dp0setup_windows.ps1" (
    echo [ERROR] setup_windows.ps1 was not found in this folder.
    exit /b 1
)

rem Ensure the setup script runs elevated for service/task installation.
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting Administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%CD%' -ArgumentList '%*' -PassThru -Wait; exit $p.ExitCode } catch { Write-Host '[ERROR] Administrator permission was not granted.'; exit 1 }"
    exit /b %ERRORLEVEL%
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*

exit /b %ERRORLEVEL%
