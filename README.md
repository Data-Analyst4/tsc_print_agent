# PDF to TSPL Print Automation

A production-oriented service for converting PDF label intents into deterministic TSPL printer output, with centralized queueing, workstation-aware routing, retry handling, and operator visibility.

Current release: `v1.1.1` (see `VERSION` and `CHANGELOG.md`).

This repository contains:

1. `pdf2tspl.py`: standalone PDF -> TSPL converter.
2. `print_automation/`: central server + agent workflow for real operations.

## Why This Exists

This app is designed for environments where browser printing is unreliable for label operations.

It provides:

- Silent RAW printing from agent workstation.
- Template-driven rendering (size, rotation, offsets, print parameters).
- Central queue with status timeline and retries.
- Routing by workstation + size code + fallback order.
- Admin UI to view jobs, artifacts, printers, and routing data.

## Core Capabilities

- Submit print jobs via API (`POST /v1/jobs`).
- Route jobs to matching online agent/printer.
- Download source PDF on workstation.
- Render TSPL and print locally.
- Persist statuses/events/artifacts in SQLite.
- View job list, events, PDF artifact, and TSPL artifact in frontend (`/admin`).

## Architecture (Generic)

### Central Server

Responsibilities:

- API endpoints.
- Job queue and status lifecycle.
- Agent heartbeat registry.
- Workstation and fallback rules.
- Printer profile compatibility checks.
- Admin UI and discovery APIs.

Default bind: `127.0.0.1:8089`

### Workstation Agent

Responsibilities:

- Heartbeat with printer/template capabilities.
- Claim assigned/compatible jobs.
- Download PDF from path or URL.
- Render TSPL and send RAW to local printer.
- Report transitions and artifact paths.

### Web App / Integration Client

Responsibilities:

- Submit print intent payloads.
- Poll/list jobs and events.
- Optionally fetch PDF/TSPL artifacts.

## Status Lifecycle

Normal path:

`QUEUED -> ASSIGNED -> DOWNLOADING -> RENDERING -> PRINTING -> SUCCESS`

Failure path:

- Retryable failures requeue up to `max_retries`.
- Final failures move to `FAILED`.

## Repository Layout

- `scripts/run_server.py`: start central server.
- `scripts/run_agent.py`: start workstation agent.
- `scripts/submit_job.py`: CLI to submit test jobs.
- `print_automation/server.py`: HTTP routes and orchestration.
- `print_automation/agent.py`: workstation print runtime.
- `print_automation/db.py`: SQLite schema and persistence.
- `print_automation/admin_ui.py`: built-in frontend UI.
- `config/templates.json`: template rendering profiles.
- `config/agent.local.json`: sample local agent config.
- `docs/SETUP_AND_OPERATIONS_GUIDE.md`: full deployment runbook.

## Documentation Hub

- [docs/DOCUMENTATION_INDEX.md](docs/DOCUMENTATION_INDEX.md)
- [docs/SETUP_AND_OPERATIONS_GUIDE.md](docs/SETUP_AND_OPERATIONS_GUIDE.md)
- [docs/NEW_COMPUTER_SETUP.md](docs/NEW_COMPUTER_SETUP.md)
- [docs/WINDOWS_EXE_PACKAGING.md](docs/WINDOWS_EXE_PACKAGING.md)
- [CHANGELOG.md](CHANGELOG.md)

## Prerequisites

- Python 3.11+
- OS printer installed and working on each workstation
- Network connectivity from workstation to server
- Shared API token for server and agents

## Quick Start (Local)

### 1) Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Run server

```powershell
python .\scripts\run_server.py --auth-token change-me-token --routing-mode server_managed
```

### 3) Run agent

```powershell
python .\scripts\run_agent.py --config .\config\agent.local.json --templates .\config\templates.json
```

### 4) Submit test job

```powershell
python .\scripts\submit_job.py `
  --server http://127.0.0.1:8089 `
  --auth-token change-me-token `
  --label-size 4x3 `
  --copies 1 `
  --pdf-path "C:\labels\sample.pdf" `
  --workstation ws_te244_local `
  --group shipping `
  --idempotency-key local-test-001
```

### 5) Verify

- Admin UI: `http://127.0.0.1:8089/admin`
- Health: `http://127.0.0.1:8089/health`

In `Recent Jobs and Artifacts`:

- See job rows.
- Open `View PDF` when available.
- Use `Download TSPL` for generated command stream.
- Inspect timeline with `View Events`.

## One-Command Windows Setup (Installer Script)

For new PCs, you can run a single setup file that:

- Copies project files to install directory.
- Installs Python 3.11 if missing.
- Creates `.venv` and installs `requirements.txt`.
- Prepares agent config.
- Installs Windows services for auto-start (server/agent).

Run in Admin PowerShell from repo root:

```powershell
.\setup_windows.ps1 -Mode both -InstallDir "C:\Pdf2Tspl" -AuthToken "change-me-token"
```

Server-only machine:

```powershell
.\setup_windows.ps1 -Mode server -InstallDir "C:\Pdf2Tspl" -AuthToken "change-me-token"
```

Agent-only machine:

```powershell
.\setup_windows.ps1 `
  -Mode agent `
  -InstallDir "C:\Pdf2Tspl" `
  -ServerUrl "http://192.168.1.20:8089" `
  -AuthToken "change-me-token" `
  -PrinterName "TSC_TE244"
```

Optional launcher:

```cmd
setup_windows.bat -Mode both -InstallDir C:\Pdf2Tspl -AuthToken change-me-token
```

### Build EXE / Installer

Build portable app EXEs:

```powershell
.\scripts\build_windows_exe.ps1 -Target all
```

Build installer EXE:

```powershell
.\scripts\build_windows_installer.ps1 -Mode both -AuthToken "change-me-token"
```

## Routing Modes

### `server_managed`

- Server chooses compatible online agent/printer.
- Can use preferred `workstation_id` and fallback chain.

### `webapp_managed`

- Client must send explicit `target.agent_id` and `target.printer`.
- Use this when external logic owns routing.

## API Summary

All endpoints except `/health` require:

- `X-Auth-Token: <token>`

Key endpoints:

- `POST /v1/jobs`
- `GET /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/artifacts/pdf`
- `GET /v1/jobs/{job_id}/artifacts/tspl`
- `POST /v1/agents/heartbeat`
- `POST /v1/agents/{agent_id}/claim-next`
- `POST /v1/jobs/{job_id}/status`
- `GET /v1/discovery`
- `GET /v1/admin/printer-profiles`
- `POST /v1/admin/printer-profiles`
- `GET /v1/admin/workstations`
- `POST /v1/admin/workstations`
- `GET /v1/admin/workstation-fallbacks`
- `POST /v1/admin/workstation-fallbacks`

## Frontend Coverage

The built-in frontend at `/admin` currently supports:

1. Printer profile management.
2. Workstation management.
3. Workstation fallback management.
4. Active printer discovery view.
5. Recent jobs list with filters and limit.
6. Job event timeline preview.
7. PDF artifact open-in-new-tab action.
8. TSPL artifact download action.
9. Live refresh toggle.

## Configuration Tips

- Keep template `size_code` aligned with printer profile `size_code`.
- Use stable naming for `workstation_id`, `agent_id`, and printers.
- Set fallback workstations for every critical print path.
- Keep `work_dir` persistent enough for troubleshooting artifacts.

## Operations and Reliability

Recommended practices:

1. Run server and agents as managed services (auto restart).
2. Put server behind HTTPS (reverse proxy/tunnel).
3. Rotate auth token periodically.
4. Back up `print_automation.db` daily.
5. Monitor stale heartbeats and failed jobs.

### Windows Auto-Start on Boot/Restart

Use one of these production patterns:

- Option A (`Task Scheduler`): easier if printers are available only in a logged-in user profile.
- Option B (`Windows Service + NSSM`): best match for headless always-on middleware behavior.

Run all install/uninstall commands in an elevated PowerShell window.

#### Option A: Task Scheduler (existing)

Server:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed `
  -RunAs system
```

Agent:

```powershell
.\scripts\install_windows_autostart.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json" `
  -RunAs system
```

Remove tasks:

```powershell
.\scripts\uninstall_windows_autostart.ps1 -Mode server
.\scripts\uninstall_windows_autostart.ps1 -Mode agent
```

#### Option B: Windows Service (NSSM, Rynan-style)

Server:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode server `
  -Host 0.0.0.0 `
  -Port 8089 `
  -AuthToken "change-me-token" `
  -RoutingMode server_managed
```

Agent:

```powershell
.\scripts\install_windows_service.ps1 `
  -Mode agent `
  -AgentConfigPath ".\config\agent.local.json"
```

Remove services:

```powershell
.\scripts\uninstall_windows_service.ps1 -Mode server
.\scripts\uninstall_windows_service.ps1 -Mode agent
```

Notes:

- `install_windows_service.ps1` auto-downloads `nssm.exe` if missing (disable with `-NoNssmDownload`).
- `run_supervised.ps1` keeps restarting child process if it exits, and NSSM service recovery is also enabled.
- If printer mapping is user-profile-scoped, Task Scheduler with `-RunAs current_user` may be a better fit than LocalSystem service mode.

## Common Problems

- Jobs stuck `QUEUED`: no compatible online agent/printer for requested size/workstation.
- Artifact buttons missing: render/print stage never reached, or artifact paths/files unavailable.
- Download failures (403/404): source URL inaccessible from workstation.
- Print failures: incorrect printer name or spooler/device issue.

## Full Setup Guide

Detailed step-by-step deployment, verification, troubleshooting, and go-live checklist:

- [docs/SETUP_AND_OPERATIONS_GUIDE.md](docs/SETUP_AND_OPERATIONS_GUIDE.md)
- [docs/NEW_COMPUTER_SETUP.md](docs/NEW_COMPUTER_SETUP.md)

## Versioning and Branching

- Stable releases should be tagged on `main` using semantic versions (`vMAJOR.MINOR.PATCH`).
- Day-to-day integration can happen on `develop` via PRs.

## License

MIT License. See `LICENSE`.
