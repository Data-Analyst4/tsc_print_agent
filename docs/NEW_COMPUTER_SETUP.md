# New Computer Setup (Print Server + Agent)

Use this guide when setting up the project on a fresh Windows PC.

Release covered by this document: `v1.1.0`.

See also:

- `docs/DOCUMENTATION_INDEX.md`
- `docs/SETUP_AND_OPERATIONS_GUIDE.md`
- `docs/WINDOWS_EXE_PACKAGING.md`

## 1) Minimum Requirements

- Windows 10/11
- Python 3.11+
- Network access between server PC and workstation PCs
- Printer driver installed on each workstation (for real printing)
- Shared auth token value for server and agents

## 2) Copy Project and Install Dependencies

Open PowerShell in project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or use one-command installer setup:

```powershell
.\setup_windows.ps1 -Mode both -InstallDir "C:\Pdf2Tspl" -AuthToken "change-me-token"
```

Agent-only machine example:

```powershell
.\setup_windows.ps1 `
  -Mode agent `
  -InstallDir "C:\Pdf2Tspl" `
  -ServerUrl "http://192.168.1.20:8089" `
  -AuthToken "change-me-token" `
  -PrinterName "TSC_TE244"
```

If script execution is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 3) Setup Central Server PC

Run server once (manual test):

```powershell
python .\scripts\run_server.py `
  --host 0.0.0.0 `
  --port 8089 `
  --auth-token "change-me-token" `
  --routing-mode server_managed
```

Health check:

```powershell
curl http://127.0.0.1:8089/health
```

Expected:

- `{"ok": true}`

## 4) Setup Workstation PC (Agent + Printer)

Edit `config/agent.local.json` with unique values:

- `agent_id` (unique)
- `workstation_id`
- `server_url` (`http://<server-ip>:8089`)
- `auth_token` (same as server)
- `printer_name` (exact Windows printer name)
- `printers` profile values (size_code/roll)

Run agent once (manual test):

```powershell
python .\scripts\run_agent.py `
  --config .\config\agent.local.json `
  --templates .\config\templates.json
```

## 5) Verify Agent Registration

From server PC:

```powershell
curl -H "X-Auth-Token: change-me-token" http://127.0.0.1:8089/v1/agents
curl -H "X-Auth-Token: change-me-token" http://127.0.0.1:8089/v1/discovery
```

Check in response:

- agent appears in `agents`
- live printer appears in `active_printers`

## 6) Enable Auto-Start on Reboot (Recommended)

Choose one mode:

- `Task Scheduler` (existing): supports `-RunAs current_user` when printer mapping is user-profile-scoped.
- `Windows Service (NSSM)`: closest to Rynan-style headless auto-start.

Run PowerShell as Administrator.

### 6.1 Task Scheduler mode

Server PC:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed `
  -RunAs system
```

Workstation PC:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json" `
  -RunAs system
```

If printer is only available in logged-in user profile, use:

```powershell
-RunAs current_user
```

### 6.2 Windows Service mode

Server PC:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed
```

Workstation PC:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json"
```

If `nssm.exe` is not available, installer downloads it automatically (disable with `-NoNssmDownload`).

## 7) Uninstall Auto-Start

Task Scheduler tasks:

```powershell
.\scripts\uninstall_windows_autostart.ps1 -Mode server
.\scripts\uninstall_windows_autostart.ps1 -Mode agent
```

Windows services:

```powershell
.\scripts\uninstall_windows_service.ps1 -Mode server
.\scripts\uninstall_windows_service.ps1 -Mode agent
```

## 8) Quick Troubleshooting

Server not reachable:

- confirm server process is running
- confirm port `8089` is open/listening
- verify firewall/network rules

Printer not active:

- confirm agent is running
- confirm heartbeat is fresh (default 45s window)
- confirm printer profile is enabled
- use `GET /v1/discovery` and check `active_printers`

Print fails:

- verify exact `printer_name` string
- print Windows test page
- validate template `size_code` matches printer profile `size_code`
