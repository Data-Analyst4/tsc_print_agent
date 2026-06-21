@echo off
setlocal EnableExtensions

rem Removes PDF2TSPL server + agent Windows services.

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator permission...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $argList = @('/c','\"\"%~f0\"\"'); $p = Start-Process -FilePath 'cmd.exe' -Verb RunAs -WorkingDirectory '%~dp0' -ArgumentList $argList -PassThru -Wait; exit $p.ExitCode } catch { Write-Host '[ERROR] Administrator permission was not granted.'; exit 1 }"
  if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Administrator permission was not granted or uninstall failed.
    exit /b 1
  )
  exit /b 0
)

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "PS_EXE=powershell.exe"

if not exist "%ROOT_DIR%\scripts\uninstall_windows_service.ps1" (
  echo [ERROR] Missing script: scripts\uninstall_windows_service.ps1
  exit /b 1
)

echo Removing server service...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\uninstall_windows_service.ps1" -Mode server
if errorlevel 1 (
  echo [WARNING] Server uninstall returned non-zero exit code.
)

echo Removing agent service...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\uninstall_windows_service.ps1" -Mode agent
if errorlevel 1 (
  echo [WARNING] Agent uninstall returned non-zero exit code.
)

echo Removing Cloudflare tunnel service...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\uninstall_cloudflare_tunnel.ps1" -RepoRoot "%ROOT_DIR%"
if errorlevel 1 (
  echo [WARNING] Tunnel uninstall returned non-zero exit code.
)

echo.
echo Done. Services removed if present.
exit /b 0
