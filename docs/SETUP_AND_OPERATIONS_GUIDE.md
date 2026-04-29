# Print Automation Setup and Operations Guide

This guide explains how to deploy and operate the system in the exact model discussed:

- One **central print server** machine.
- Multiple **workstation PCs** with printers connected.
- Web app sends print requests to central server.
- Central server routes by workstation + label size.
- If requested workstation is not available, central server falls back to configured nearby workstations.

---

## 1) Architecture Overview

### Components

1. **Central Print Server**
   - Runs the HTTP API.
   - Stores jobs, agent health, printer profiles, workstation fallback rules.
   - Performs routing decisions.

2. **Print Agent (one per workstation printer process)**
   - Runs on workstation PC with printer connection.
   - Sends heartbeat to server.
   - Receives/claims routed jobs.
   - Downloads PDF, renders TSPL, prints locally.
   - Reports status transitions.

3. **Web App**
   - Calls `POST /v1/jobs` on central server.
   - Reads status via `GET /v1/jobs/{job_id}` or `GET /v1/jobs`.
   - Can query discovery data with `GET /v1/discovery`.

### Data flow (high level)

1. Agent heartbeat -> central server (`/v1/agents/heartbeat`)
2. Web app submits print job -> central server (`/v1/jobs`)
3. Server selects best online agent/printer profile by workstation + size.
4. Agent prints and reports status (`/v1/jobs/{job_id}/status`).

---

## 2) Required Software and Hardware

### Central server machine

Recommended minimum (small setup):

- Windows or Linux server
- 2 vCPU
- 4 GB RAM
- 20+ GB disk
- Stable internet/LAN

### Workstation PC (per printer)

- Windows 10/11
- Python 3.11+
- Printer driver installed and tested
- Network access to central server URL

### Printer requirements

- TSPL-compatible thermal printer (or test output using `file:` sink profile).

---

## 3) Network and Exposure Model

### What to expose publicly

Expose **only central print server**, never workstation agents directly.

- Recommended: Cloudflare Tunnel/domain to central server.
- Example public URL: `https://print.yourdomain.com`.

### What not to expose

- No per-agent public URL.
- No need to expose each workstation to internet.

---

## 4) Central Server Installation

From project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run server:

```powershell
python .\scripts\run_server.py --host 0.0.0.0 --port 8089 --auth-token change-me-token
```

Health check:

```powershell
curl http://127.0.0.1:8089/health
```

---

## 5) Workstation Agent Installation

Install same repo + Python on each workstation.

### Agent config essentials

Edit `config/agent.local.json` per workstation:

- `agent_id`: unique per agent instance.
- `workstation_id`: unique workstation identifier used for routing/fallback.
- `server_url`: central server URL.
- `auth_token`: same shared token as server.
- `printer_name`: local printer used by this agent process.
- `printers[]`: printer capability profile (name + roll size + size code).
- `templates[]`: supported templates.

Start agent:

```powershell
python .\scripts\run_agent.py --config .\config\agent.local.json --templates .\config\templates.json
```

---

## 6) Admin UI for Printer Roll Size and Workstation Rules

Open:

- `http://<server-host>:8089/admin`

The UI supports:

1. Save/update printer profiles:
   - `agent_id`
   - `printer_name`
   - `roll_width_mm`, `roll_height_mm`
   - `size_code` (for example `4x3`, `4x6`)
   - `enabled`

2. Save/update workstations:
   - `workstation_id`
   - display name
   - location tag
   - enabled flag

3. Set fallback order:
   - Primary workstation
   - Ordered fallback workstations (nearest first)

4. View active printers from discovery.

All admin API calls require `X-Auth-Token`.

---

## 7) Routing Behavior

When a job is submitted, server decides in this order:

1. Match template/size compatibility.
2. Match target constraints (`agent`, `group`, `printer`) if provided.
3. Prefer requested workstation.
4. If unavailable, use configured fallback workstation order.
5. If still unavailable, select any online compatible printer.

---

## 8) API Usage

### Submit print job

`POST /v1/jobs`

Example payload:

```json
{
  "source": {"type": "url", "value": "https://example.com/label.pdf"},
  "label_size": "4x3",
  "copies": 1,
  "target": {
    "workstation_id": "ws_shipping_1",
    "group": "shipping"
  },
  "idempotency_key": "order-1001-label-1"
}
```

You can also send `template_id` instead of `label_size`.

### Check job status

`GET /v1/jobs/{job_id}?include_events=true`

### Discovery

`GET /v1/discovery`

Includes:

- templates
- workstations
- workstation fallback rules
- agents
- printer profiles
- currently active printers

---

## 9) Operational Workflow for Roll Change

When operator changes roll on a workstation printer:

1. Open central admin UI.
2. Update that printer profile `size_code` and/or roll dimensions.
3. Keep `enabled=true`.
4. Refresh discovery view and validate active printer size list.
5. Submit a test print for that size.

This keeps routing accurate without code changes.

---

## 10) Recommended Production Practices

1. Use HTTPS in front of central server.
2. Rotate auth tokens periodically.
3. Run agents as Windows services (auto restart).
4. Backup server DB daily.
5. Keep at least one fallback workstation per critical label size.
6. Monitor agent heartbeat freshness and failed jobs.

---

## 11) Current Limitation (Important)

Current transport path uses agent-side claim/polling (`/claim-next`) for dispatch.
Routing, workstation fallback, and roll-size profile management are implemented.
If you need full real-time push dispatch (socket-based), add a persistent agent connection layer in next version.

