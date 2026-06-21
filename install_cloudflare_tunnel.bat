@echo off
setlocal EnableExtensions

rem Installs Cloudflare tunnel as Windows service (auto-start + auto-restart).
rem Requires config\cloudflared.token OR config\cloudflared.yml before running.

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator permission...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $argList = @('/c','\"\"%~f0\" %*\"'); $p = Start-Process -FilePath 'cmd.exe' -Verb RunAs -WorkingDirectory '%~dp0' -ArgumentList $argList -PassThru -Wait; exit $p.ExitCode } catch { Write-Host '[ERROR] Administrator permission was not granted.'; exit 1 }"
  if not "%ERRORLEVEL%"=="0" exit /b 1
  exit /b 0
)

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "PS_ARGS=-NoProfile -ExecutionPolicy Bypass -File ""%ROOT_DIR%\scripts\install_cloudflare_tunnel.ps1"" -RepoRoot ""%ROOT_DIR%"""
if not "%~1"=="" set "PS_ARGS=%PS_ARGS% -TunnelToken ""%~1"""

powershell.exe %PS_ARGS%
exit /b %ERRORLEVEL%
