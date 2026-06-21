@echo off
setlocal EnableExtensions

rem One-click installer for a fresh Windows PC.
rem - setup_windows.ps1 installs Python 3.11 if missing
rem - creates .venv, installs requirements
rem - installs server+agent Windows services for auto-start
rem - installs Cloudflare tunnel if config\cloudflared.token exists

cd /d "%~dp0"

set "MODE=both"
set "INSTALL_DIR=C:\Pdf2Tspl"
set "AUTH_TOKEN=change-me-token"
set "SERVER_HOST=0.0.0.0"
set "SERVER_PORT=8089"
set "ROUTING_MODE=server_managed"
set "SERVER_URL="
rem For agent-only machines:
rem set "MODE=agent"
rem set "SERVER_URL=http://<server-ip>:8089"
rem
rem For public HTTPS at tspl.k95foods.com, before running:
rem   copy config\cloudflared.token.example config\cloudflared.token
rem   edit config\cloudflared.token and paste your Cloudflare tunnel token

echo Installing PDF2TSPL...
echo Mode: %MODE%
echo InstallDir: %INSTALL_DIR%
echo Server: %SERVER_HOST%:%SERVER_PORT%
echo Public URL target: https://tspl.k95foods.com
echo.

set "SETUP_PS1=%~dp0setup_windows.ps1"
if not exist "%SETUP_PS1%" (
    echo [ERROR] setup_windows.ps1 not found. Keep this file in project root.
    exit /b 1
)

set "SETUP_ARGS=-NoProfile -ExecutionPolicy Bypass -File ""%SETUP_PS1%"" -Mode %MODE% -InstallDir ""%INSTALL_DIR%"" -AuthToken ""%AUTH_TOKEN%"" -ServerHost ""%SERVER_HOST%"" -ServerPort %SERVER_PORT% -RoutingMode ""%ROUTING_MODE%"" -ServerUrl ""%SERVER_URL%"""

net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting Administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WorkingDirectory '%~dp0' -ArgumentList '%SETUP_ARGS%' -PassThru -Wait; exit $p.ExitCode } catch { Write-Host '[ERROR] Administrator permission was not granted.'; exit 1 }"
) else (
    powershell %SETUP_ARGS%
)

if not "%errorlevel%"=="0" (
    echo.
    echo [ERROR] Installation failed with code %errorlevel%.
    echo [HINT] If a User Account Control popup appeared, choose Yes to allow admin setup.
    exit /b %errorlevel%
)

echo.
echo Installation completed.
echo Checking server health...

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%SERVER_PORT%/health' -TimeoutSec 8; if($r.ok -eq $true){ Write-Host '[OK] Server health check passed.'; exit 0 } else { Write-Host '[WARN] Server responded but health payload was unexpected.'; exit 2 } } catch { Write-Host '[WARN] Could not reach server health endpoint yet.'; exit 1 }"

echo.
echo Services auto-start on boot and auto-restart on crash/close.
echo If tunnel token was configured: https://tspl.k95foods.com
echo Otherwise run: install_cloudflare_tunnel.bat YOUR_TOKEN
echo Status check: print_services_status.bat
exit /b 0
