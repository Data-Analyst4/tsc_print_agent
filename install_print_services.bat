@echo off
setlocal EnableExtensions

rem Installs PDF2TSPL server + agent as Windows services (NSSM + supervisor).
rem Behavior after install:
rem - starts automatically on Windows boot
rem - runs without user login
rem - restarts automatically after crashes or sudden close

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator permission...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $argList = @('/c','\"\"%~f0\" %*\"'); $p = Start-Process -FilePath 'cmd.exe' -Verb RunAs -WorkingDirectory '%~dp0' -ArgumentList $argList -PassThru -Wait; exit $p.ExitCode } catch { Write-Host '[ERROR] Administrator permission was not granted.'; exit 1 }"
  if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Administrator permission was not granted or install failed.
    exit /b 1
  )
  exit /b 0
)

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "PS_EXE=powershell.exe"
set "SERVICE_SERVER=Pdf2Tspl-Server"
set "SERVICE_AGENT=Pdf2Tspl-Agent-%COMPUTERNAME%"
set "SERVER_HOST=0.0.0.0"
set "SERVER_PORT=8089"
set "ROUTING_MODE=server_managed"
set "AGENT_CONFIG=%ROOT_DIR%\config\agent.local.json"
set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  set "PYTHON_EXE=python"
)

if "%~1"=="" (
  set "AUTH_TOKEN=change-me-token"
) else (
  set "AUTH_TOKEN=%~1"
)

if not exist "%ROOT_DIR%\scripts\install_windows_service.ps1" (
  echo [ERROR] Missing script: scripts\install_windows_service.ps1
  exit /b 1
)

if not exist "%ROOT_DIR%\scripts\run_supervised.ps1" (
  echo [ERROR] Missing script: scripts\run_supervised.ps1
  exit /b 1
)

echo ============================================================
echo   PDF2TSPL Service Installer
echo ============================================================
echo Repo:          %ROOT_DIR%
echo Python:        %PYTHON_EXE%
echo Server:        %SERVER_HOST%:%SERVER_PORT%
echo Routing mode:  %ROUTING_MODE%
echo Agent config:  %AGENT_CONFIG%
echo Service names: %SERVICE_SERVER% , %SERVICE_AGENT%
if "%~1"=="" (
  echo Auth token:   change-me-token ^(default^)
  echo              Pass token as first arg to override.
) else (
  echo Auth token:   [provided via arg]
)
echo.

if not exist "%AGENT_CONFIG%" (
  echo [ERROR] Missing agent config: %AGENT_CONFIG%
  exit /b 1
)

echo [1/5] Syncing auth token into agent config...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -Command "$p = '%AGENT_CONFIG%'; $token = '%AUTH_TOKEN%'; $obj = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; $obj.auth_token = $token; $json = $obj | ConvertTo-Json -Depth 10; $enc = New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText($p, $json, $enc)"
if errorlevel 1 (
  echo [ERROR] Failed to update auth_token in %AGENT_CONFIG%.
  exit /b 1
)

echo [2/5] Installing server service...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\install_windows_service.ps1" -Mode server -RepoRoot "%ROOT_DIR%" -PythonExe "%PYTHON_EXE%" -Host "%SERVER_HOST%" -Port %SERVER_PORT% -AuthToken "%AUTH_TOKEN%" -RoutingMode "%ROUTING_MODE%"
if errorlevel 1 (
  echo [ERROR] Server service install failed.
  exit /b 1
)

echo [3/5] Installing agent service...
%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\install_windows_service.ps1" -Mode agent -RepoRoot "%ROOT_DIR%" -PythonExe "%PYTHON_EXE%" -AgentConfigPath "%AGENT_CONFIG%"
if errorlevel 1 (
  echo [ERROR] Agent service install failed.
  exit /b 1
)

set "TUNNEL_TOKEN_FILE=%ROOT_DIR%\config\cloudflared.token"
set "TUNNEL_CONFIG_FILE=%ROOT_DIR%\config\cloudflared.yml"
set "TUNNEL_TOKEN_ARG="
if not "%~2"=="" set "TUNNEL_TOKEN_ARG=-TunnelToken ""%~2"""

echo [4/5] Installing Cloudflare tunnel service (if credentials present)...
if exist "%TUNNEL_TOKEN_FILE%" (
  %PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\install_cloudflare_tunnel.ps1" -RepoRoot "%ROOT_DIR%" %TUNNEL_TOKEN_ARG%
  if errorlevel 1 (
    echo [WARN] Cloudflare tunnel install failed. Server/agent services are still installed.
  )
) else if exist "%TUNNEL_CONFIG_FILE%" (
  %PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\install_cloudflare_tunnel.ps1" -RepoRoot "%ROOT_DIR%"
  if errorlevel 1 (
    echo [WARN] Cloudflare tunnel install failed. Server/agent services are still installed.
  )
) else if not "%~2"=="" (
  %PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\install_cloudflare_tunnel.ps1" -RepoRoot "%ROOT_DIR%" %TUNNEL_TOKEN_ARG%
  if errorlevel 1 (
    echo [WARN] Cloudflare tunnel install failed. Server/agent services are still installed.
  )
) else (
  echo [SKIP] No config\cloudflared.token or config\cloudflared.yml found.
  echo        Public URL tspl.k95foods.com will not be active until tunnel is installed.
  echo        Run: install_cloudflare_tunnel.bat YOUR_TOKEN
)

echo [5/5] Service status...
sc query "%SERVICE_SERVER%"
sc query "%SERVICE_AGENT%"
sc query "Pdf2Tspl-Tunnel" 2>nul

echo.
echo ============================================================
echo   Install complete
echo ============================================================
echo - Services auto-start on boot
echo - Services auto-restart on crash/sudden close
echo - Tunnel (if installed): https://tspl.k95foods.com
echo - Logs: logs\server-service-*.log , logs\agent-service-*.log , logs\tunnel-service-*.log
echo.
echo Quick checks:
echo   powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8089/health'"
echo   .\print_services_status.bat
echo   install_cloudflare_tunnel.bat YOUR_TOKEN   ^(if tunnel was skipped^)
echo ============================================================

exit /b 0
