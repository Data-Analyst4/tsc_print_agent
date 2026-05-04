# Print Automation Setup and Operations Guide

This guide provides a simple, generic, and detailed method to deploy and run the PDF -> TSPL print automation system.

Release covered by this document: `v1.1.1`.

It is written for this operating model:

- One central print server.
- Many workstation PCs connected to printers.
- A web app (or script) submits jobs to the central server.
- The central server routes jobs to the correct workstation/printer.
- Workstation fallback is used if the primary workstation is unavailable.

Related docs:

- `docs/DOCUMENTATION_INDEX.md`
- `docs/NEW_COMPUTER_SETUP.md`
- `docs/WINDOWS_EXE_PACKAGING.md`

## 1) What You Will Have After Setup

After completing this guide, you should be able to:

1. Open `http://<server-host>:8089/admin`.
2. See online agents and active printer profiles.
3. Submit a job and track status (`QUEUED -> ASSIGNED -> DOWNLOADING -> RENDERING -> PRINTING -> SUCCESS`).
4. Open each job's PDF artifact from the frontend (`View PDF`) and download TSPL (`Download TSPL`).

## 2) Quick Terminology

- `Server`: central API + queue + routing + admin UI.
- `Agent`: process on workstation that downloads PDF, renders TSPL, and prints.
- `Template`: label rendering profile from `config/templates.json`.
- `Size code`: short size key such as `4x3` or `4x6` used for routing compatibility.
- `Workstation`: logical desk/location ID used for preferred routing and fallback.

## 3) Prerequisites

### Central server machine

- OS: Windows or Linux.
- Python: 3.11 or newer.
- CPU/RAM (small setup): 2 vCPU, 4 GB RAM.
- Disk: 20 GB or more.
- Network: reachable by workstation PCs.

### Workstation machine (per printer)

- OS: Windows 10/11 (or Linux if printer stack supports RAW printing there).
- Python: 3.11 or newer.
- Printer driver installed and tested with a normal test page.
- Network path to central server URL.

### General

- Shared auth token for server and agents.
- Repository copied to each machine.
- If using URL-based PDFs, the workstation must be able to download those URLs.

## 4) Standard Naming Convention (Recommended)

Use predictable IDs to reduce routing mistakes.

- `agent_id`: `agent_<workstation>_<printer>`
- `workstation_id`: `ws_<location>_<number>`
- `size_code`: lowercase (`4x3`, `4x6`)

Example:

- `workstation_id`: `ws_shipping_1`
- `agent_id`: `agent_ws_shipping_1_te244`
- `printer_name`: `TSC_TE244`

## 5) Install Dependencies (All Machines)

From project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell execution policy blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Optional: One-Command Windows Setup

For fresh Windows PCs, use:

```powershell
.\setup_windows.ps1 -Mode both -InstallDir "C:\Pdf2Tspl" -AuthToken "change-me-token"
```

What this setup file does:

- Copies this project to install directory.
- Installs Python 3.11 if missing.
- Creates virtual environment and installs `requirements.txt`.
- Prepares agent config for the machine.
- Installs Windows services (server and/or agent) unless `-SkipServiceInstall` is used.

Common variants:

```powershell
# Server-only
.\setup_windows.ps1 -Mode server -InstallDir "C:\Pdf2Tspl" -AuthToken "change-me-token"

# Agent-only (connect to remote server)
.\setup_windows.ps1 `
  -Mode agent `
  -InstallDir "C:\Pdf2Tspl" `
  -ServerUrl "http://192.168.1.20:8089" `
  -AuthToken "change-me-token" `
  -PrinterName "TSC_TE244"
```

If you prefer manual mode (no service install):

```powershell
.\setup_windows.ps1 -Mode both -InstallDir "C:\Pdf2Tspl" -SkipServiceInstall
```

## 6) Central Server Setup

### Step 6.1: Choose runtime settings

- Host/port (default: `0.0.0.0:8089` for LAN access).
- Auth token (long random value).
- Routing mode:
  - `webapp_managed`: caller must send exact `target.agent_id` and `target.printer`.
  - `server_managed`: server chooses best online compatible agent/printer.

### Step 6.2: Start server

```powershell
python .\scripts\run_server.py --host 0.0.0.0 --port 8089 --auth-token change-me-token --routing-mode server_managed
```

Or webapp-managed mode:

```powershell
python .\scripts\run_server.py --host 0.0.0.0 --port 8089 --auth-token change-me-token --routing-mode webapp_managed
```

### Step 6.3: Verify server is alive

```powershell
curl http://127.0.0.1:8089/health
```

Expected response contains `{"ok": true}`.

### Step 6.4: Open admin UI

- URL: `http://<server-host>:8089/admin`
- Paste auth token in the `API Token` field.

## 7) Workstation Agent Setup

Do this on each workstation/printer machine.

### Step 7.1: Prepare agent config

Edit `config/agent.local.json` (copy one file per workstation if needed).

Required fields:

- `agent_id`: unique per running agent.
- `agent_name`: readable name.
- `workstation_id`: routing location ID.
- `server_url`: central server base URL.
- `auth_token`: same as server token.
- `printer_name`: default local printer.
- `printers`: printer capability list with size metadata.
- `templates`: template IDs available to this agent.
- `work_dir`: local job artifact folder.

Example (minimal generic):

```json
{
  "agent_id": "agent_ws_shipping_1_te244",
  "agent_name": "Shipping Desk 1 TE244",
  "workstation_id": "ws_shipping_1",
  "server_url": "http://192.168.1.20:8089",
  "auth_token": "change-me-token",
  "printer_name": "TSC_TE244",
  "groups": ["shipping"],
  "templates": ["label_4x3_pdf_3x4"],
  "printers": [
    {
      "name": "TSC_TE244",
      "roll_width_mm": 100,
      "roll_height_mm": 75,
      "size_code": "4x3"
    }
  ],
  "work_dir": "./agent_work",
  "heartbeat_interval_seconds": 10,
  "poll_interval_seconds": 2
}
```

### Step 7.2: Start agent

```powershell
python .\scripts\run_agent.py --config .\config\agent.local.json --templates .\config\templates.json
```

### Step 7.3: Verify heartbeat

From server machine:

```powershell
curl -H "X-Auth-Token: change-me-token" http://127.0.0.1:8089/v1/agents
```

You should see your `agent_id` with recent `heartbeat_at`.

## 8) Template and Size-Code Rules

File: `config/templates.json`

Keep these consistent:

1. Template `size_code` must match printer profile `size_code`.
2. Template geometry must match physical stock and expected rotation.
3. Use version increment when changing offsets/density/speed.

If size code mismatches, jobs may stay queued or fail compatibility checks.

## 9) Configure Routing Data in Admin UI

Open `http://<server-host>:8089/admin`.

### 9.1 Printer Profiles

Add one profile per `(agent_id, printer_name)`:

- `roll_width_mm`, `roll_height_mm`
- `size_code`
- `enabled=true`

### 9.2 Workstations

Create each workstation record:

- `workstation_id`
- display name
- optional location tag
- enabled flag

### 9.3 Fallback Order

Set ordered fallback list for each primary workstation.

Example:

- Primary: `ws_shipping_1`
- Fallback order: `ws_shipping_2,ws_backup_1`

## 10) Submit a Test Job

Use local file source:

```powershell
python .\scripts\submit_job.py `
  --server http://127.0.0.1:8089 `
  --auth-token change-me-token `
  --label-size 4x3 `
  --copies 1 `
  --pdf-path "C:\labels\sample.pdf" `
  --workstation ws_shipping_1 `
  --group shipping `
  --idempotency-key test-4x3-001
```

## 11) Verify in Frontend (Jobs + PDF)

In `/admin` -> `Recent Jobs and Artifacts`:

1. Click `Refresh Jobs` or enable `Live Refresh`.
2. Confirm job row appears.
3. Click `View Events` to inspect full timeline.
4. Click `View PDF` when PDF artifact is available.
5. Click `Download TSPL` to inspect printed commands.

Important behavior:

- `View PDF` appears only when `output_pdf_path` exists for that job.
- `Download TSPL` appears only when `output_tspl_path` exists.
- These are typically set at `PRINTING` stage and persist for `SUCCESS` jobs.

## 12) API Examples for Integration

### Create job (server-managed routing)

```json
{
  "source": {"type": "url", "value": "https://example.com/label.pdf"},
  "label_size": "4x3",
  "copies": 1,
  "target": {
    "workstation_id": "ws_shipping_1",
    "group": "shipping"
  },
  "idempotency_key": "order-1001-label"
}
```

### Create job (webapp-managed routing)

```json
{
  "source": {"type": "url", "value": "https://example.com/label.pdf"},
  "template_id": "label_4x3_pdf_3x4",
  "copies": 1,
  "target": {
    "agent_id": "agent_ws_shipping_1_te244",
    "printer": "TSC_TE244",
    "workstation_id": "ws_shipping_1"
  },
  "idempotency_key": "order-1002-label"
}
```

### Read job list

```powershell
curl -H "X-Auth-Token: change-me-token" "http://127.0.0.1:8089/v1/jobs?limit=100"
```

### Read one job with events

```powershell
curl -H "X-Auth-Token: change-me-token" "http://127.0.0.1:8089/v1/jobs/<job_id>?include_events=true"
```

### Fetch artifacts

```powershell
curl -H "X-Auth-Token: change-me-token" "http://127.0.0.1:8089/v1/jobs/<job_id>/artifacts/pdf"
curl -H "X-Auth-Token: change-me-token" "http://127.0.0.1:8089/v1/jobs/<job_id>/artifacts/tspl"
```

## 13) Daily Operations Checklist

1. Confirm `/health` is OK.
2. Confirm all expected agents are heartbeating.
3. Review failed/queued jobs in admin UI.
4. Validate printer profiles after any roll change.
5. Submit one test label after major changes.

## 14) Common Issues and Fixes

### Jobs stay `QUEUED`

- Agent offline or stale heartbeat.
- No compatible printer profile for requested `size_code`.
- Workstation/fallback chain has no online compatible agent.

Check:

- `/v1/agents`, `/v1/discovery`, admin `Active Printers`.

### `View PDF` button not visible

- Job did not reach stage where artifact paths were written.
- Download/render failed before `PRINTING`.
- Artifact file deleted from agent `work_dir`.

Check:

- Job events in admin UI.
- `error_message` in job row.
- Agent local folder `work_dir/<job_id>/source.pdf`.

### Download failures (403/404)

- Source URL is blocked, expired, or incorrect.
- Workstation cannot access remote URL/network.

Fix:

- Test URL from workstation browser.
- Use signed URLs with enough validity window.

### Print failures

- Wrong Windows printer name.
- Printer offline or spooler issue.
- Size/profile mismatch causing rejected output.

Fix:

- Validate exact `printer_name` string from OS printer list.
- Print OS test page.
- Verify template and profile dimensions.

## 15) Production Hardening

1. Put server behind HTTPS reverse proxy or tunnel.
2. Restrict inbound access to trusted clients.
3. Rotate auth token on schedule.
4. Run server and agents as auto-restart services.
5. Back up `print_automation.db` daily.
6. Keep at least one fallback workstation for each critical size code.

## 16) Service Model (Recommended)

- Run one long-lived server process on central host.
- Run one or more agent processes per workstation depending on printer layout.
- Keep logs centralized for troubleshooting.

### 16.1 Windows Auto-Start Tasks (Boot + Restart + Crash Recovery)

This project includes scripts to register startup tasks using Windows Task Scheduler.

Behavior:

- Starts automatically when PC boots.
- Starts again on user logon.
- If process exits/crashes, supervisor restarts it automatically.

Run these in an elevated PowerShell window (Run as Administrator).

Server machine:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed `
  -RunAs system
```

Workstation machine:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json" `
  -RunAs system
```

Optional:

- If printer mapping exists only under logged-in user profile, use `-RunAs current_user`.

Uninstall tasks:

```powershell
.\scripts\uninstall_windows_autostart.ps1 -Mode server
.\scripts\uninstall_windows_autostart.ps1 -Mode agent
```

### 16.2 Windows Service Mode (NSSM, headless)

If you want Rynan-style behavior (true Windows service, auto-start at boot, no user logon required), use these scripts.

Run in elevated PowerShell:

Server machine:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed
```

Workstation machine:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json"
```

Behavior:

- Installs a Windows service via NSSM (`Pdf2Tspl-Server` or `Pdf2Tspl-Agent-<COMPUTERNAME>`).
- Sets service start type to automatic.
- Enables restart on crash/exit (NSSM + Windows service recovery rules).
- Writes service stdout/stderr logs under `logs\`.

Uninstall services:

```powershell
.\scripts\uninstall_windows_service.ps1 -Mode server
.\scripts\uninstall_windows_service.ps1 -Mode agent
```

Notes:

- If `nssm.exe` is not available, the installer downloads `nssm-2.24` automatically unless `-NoNssmDownload` is passed.
- If your printer mapping is user-profile-only, Task Scheduler with `-RunAs current_user` can be more compatible than LocalSystem service mode.

## 17) Final Validation (Go-Live)

Before production cutover, confirm all points:

1. Server health endpoint responds.
2. Every workstation agent heartbeats consistently.
3. Discovery shows expected active printers and size codes.
4. Fallback routing behaves as expected when primary workstation is stopped.
5. Frontend shows jobs, events, PDF artifact preview, and TSPL download.
6. End-to-end print succeeds for each supported label size.
