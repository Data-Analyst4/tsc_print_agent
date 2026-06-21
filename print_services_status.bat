@echo off
setlocal EnableExtensions

set "SERVER_SERVICE=Pdf2Tspl-Server"
set "AGENT_SERVICE=Pdf2Tspl-Agent-%COMPUTERNAME%"
set "TUNNEL_SERVICE=Pdf2Tspl-Tunnel"
set "PUBLIC_URL=https://tspl.k95foods.com"

echo ============================================================
echo   PDF2TSPL Service Status
echo ============================================================
echo.
echo [Server]
sc query "%SERVER_SERVICE%"
echo.
echo [Agent]
sc query "%AGENT_SERVICE%"
echo.
echo [Cloudflare Tunnel]
sc query "%TUNNEL_SERVICE%" 2>nul
if errorlevel 1 echo Tunnel service not installed.
echo.
echo [Listener :8089]
netstat -ano | findstr ":8089"
echo.
echo [Local Health]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8089/health' -TimeoutSec 4; Write-Host ('status=' + $r.StatusCode); Write-Host $r.Content } catch { Write-Host ('error=' + $_.Exception.Message) }"
echo.
echo [Public Health - %PUBLIC_URL%/health]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri '%PUBLIC_URL%/health' -TimeoutSec 8; Write-Host ('status=' + $r.StatusCode); Write-Host $r.Content } catch { Write-Host ('error=' + $_.Exception.Message) }"
echo ============================================================
exit /b 0
