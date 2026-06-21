# Dashboard Access and Flow

This guide explains:

1. How to open the PDF2TSPL dashboard.
2. What each dashboard section does.
3. How job data moves from API request to printed output.

## 1) Open the Dashboard

The built-in dashboard URL is:

- Local machine: `http://127.0.0.1:8089/admin`
- Same network: `http://<server-ip>:8089/admin`

Current default service port is `8089` (from `install_print_services.bat`).

### Prerequisites

1. Server service is running (`Pdf2Tspl-Server`).
2. Agent service is running (`Pdf2Tspl-Agent-<COMPUTERNAME>`).
3. Server health endpoint responds: `http://127.0.0.1:8089/health`
4. You have the shared API token.

Quick check:

```cmd
print_services_status.bat
```

## 2) Enter Token in Dashboard

The `/admin` page loads without authentication, but all data/API actions require:

- Header: `X-Auth-Token: <your-token>`

In UI, paste this token in the top field:

- `API Token (X-Auth-Token)`

Then click:

- `Refresh All`

If token is wrong, dashboard actions fail with `unauthorized`.

## 3) What Each Dashboard Section Does

### Printer Profile

Purpose: Defines which printer/label size combinations are allowed per agent.

- Save profile: `POST /v1/admin/printer-profiles`
- List profiles: `GET /v1/admin/printer-profiles`
- Delete profile: `POST /v1/admin/printer-profiles/delete`

Used by routing to match jobs with compatible printers.

### Workstations

Purpose: Defines logical workstations used for routing preferences.

- Save workstation: `POST /v1/admin/workstations`
- List workstations: `GET /v1/admin/workstations`
- Delete workstation: `POST /v1/admin/workstations/delete`

### Fallback Routing

Purpose: Defines fallback workstation order if preferred workstation is unavailable.

- Save fallback order: `POST /v1/admin/workstation-fallbacks`
- List fallback rules: `GET /v1/admin/workstation-fallbacks`

### Recent Jobs and Artifacts

Purpose: Observe print lifecycle and inspect outputs.

- List jobs: `GET /v1/jobs?status=&limit=`
- View one job + events: `GET /v1/jobs/{job_id}?include_events=true`
- Open rendered PDF artifact: `GET /v1/jobs/{job_id}/artifacts/pdf`
- Download TSPL artifact: `GET /v1/jobs/{job_id}/artifacts/tspl`

Lifecycle shown in UI:

`QUEUED -> ASSIGNED -> DOWNLOADING -> RENDERING -> PRINTING -> SUCCESS`

Failure path:

- `FAILED` (retryable failures can be re-queued by agent/server logic)

Live refresh toggle updates all panels every 10 seconds.

### Active Printers (from discovery)

Purpose: Shows currently online printer targets based on latest agent heartbeats and enabled profiles.

- Discovery endpoint: `GET /v1/discovery`

## 4) How the System Is Doing Things (End-to-End Flow)

1. Client submits job to `POST /v1/jobs`.
2. Server validates source/template and writes job into SQLite (`print_automation.db`).
3. Routing chooses compatible online agent + printer profile.
4. Agent polls `claim-next`, downloads source PDF, renders TSPL, prints RAW to Windows printer.
5. Agent reports status updates (`/v1/jobs/{job_id}/status`) and artifact paths.
6. Dashboard reads jobs/events/discovery data and displays real-time state.

## 5) Common Issues

### Dashboard opens but tables are empty

- Missing/wrong token.
- No agent heartbeat yet.
- No printer profiles/workstations configured.

### Jobs stay in `QUEUED`

- No compatible online agent/printer for requested size/workstation.
- Fallback order not set for requested workstation.

### Artifact buttons are missing

- Job has not reached render/print stage.
- Artifact paths not recorded or files removed.

## 6) Useful URLs

- Dashboard: `http://127.0.0.1:8089/admin`
- Health: `http://127.0.0.1:8089/health`
- Discovery JSON: `http://127.0.0.1:8089/v1/discovery` (requires token)
