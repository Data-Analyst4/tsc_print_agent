# tsc_print_agent (PDF to TSPL Print Automation)

This repository now contains two layers:

1. `pdf2tspl.py`: deterministic PDF -> TSPL renderer.
2. `print_automation/`: production print automation system (server + agent + queue + status).

## Core Objective

Turn web print intents into deterministic physical labels:

- No browser print dialogs.
- Template-driven sizing/orientation/offsets.
- Correct printer routing via online agents.
- Reliable queue states and retry behavior.
- Full observability for debugging.

## Architecture

### 1) Central Server

`scripts/run_server.py` runs an HTTP API + SQLite queue:

- Accept jobs from web app.
- Store job + events.
- Track agents via heartbeat.
- Route queued jobs to matching agents.
- Expose job/agent status.

Default bind: `127.0.0.1:8089`

### 2) Local Agent (per machine/printer)

`scripts/run_agent.py` runs next to the printer:

- Heartbeats capabilities (`templates`, `groups`, `printer`).
- Claims assigned/compatible jobs.
- Downloads source PDF with retries.
- Renders TSPL using template profile.
- Sends RAW bytes silently to local printer.
- Reports `QUEUED -> ... -> SUCCESS/FAILED`.

## Status Lifecycle

`QUEUED -> ASSIGNED -> DOWNLOADING -> RENDERING -> PRINTING -> SUCCESS`

On failures:

- Retryable failures (`download`, `print transport`) can be re-queued up to `max_retries`.
- Non-retryable failures become `FAILED`.

## Template Profiles

Templates are configured in [config/templates.json](config/templates.json):

- Label size (`label_width_mm`, `label_height_mm`)
- DPI
- Rotation (`rotate`)
- Alignment tuning (`x_offset_dots`, `y_offset_dots`)
- Sensor/feed settings (`sensor`, `gap_mm`, `gap_offset_mm`)
- Print behavior (`speed`, `density`, `direction`, `reference`)

### Your 3x4 PDF on 4x3 stock

Template: `label_4x3_pdf_3x4`

- PDF page: `75 x 100 mm`
- Stock: `100 x 75 mm`
- Profile uses `rotate: 90` and `SIZE 100 mm,75 mm`.

## Quick Start (Local)

### 1) Start server

```powershell
python .\scripts\run_server.py --auth-token change-me-token
```

### 2) Start local printer agent

Edit [config/agent.local.json](config/agent.local.json) if needed (printer name, token), then run:

```powershell
python .\scripts\run_agent.py --config .\config\agent.local.json --templates .\config\templates.json
```

### 3) Submit a job

```powershell
python .\scripts\submit_job.py `
  --server http://127.0.0.1:8089 `
  --auth-token change-me-token `
  --template label_4x3_pdf_3x4 `
  --copies 1 `
  --pdf-path "d:\Factory\MME-26-04-01274.pdf" `
  --group shipping `
  --idempotency-key MME-26-04-01274-1
```

### 4) Check status

```powershell
curl -H "X-Auth-Token: change-me-token" http://127.0.0.1:8089/v1/jobs
```

For detailed timeline:

```powershell
curl -H "X-Auth-Token: change-me-token" "http://127.0.0.1:8089/v1/jobs/<job_id>?include_events=true"
```

## API Summary

- `POST /v1/jobs`: submit print intent.
- `GET /v1/jobs`: list jobs.
- `GET /v1/jobs/{job_id}`: job detail.
- `POST /v1/agents/heartbeat`: online agent heartbeat.
- `POST /v1/agents/{agent_id}/claim-next`: claim next routed job.
- `POST /v1/jobs/{job_id}/status`: worker status update.
- `GET /v1/templates`: list template profiles.
- `GET /v1/agents`: list agents.
- `GET /health`: health check.

All endpoints except `/health` require header:

- `X-Auth-Token: <token>`

## Branching and Versioning

This repository uses a release-friendly Git model:

- `main`: stable production-ready code only.
- `develop`: integration branch for next release.
- `release/x.y.z`: release hardening branches created from `develop`.
- `hotfix/x.y.z`: urgent fixes created from `main`.

Version tags are created on `main` using Semantic Versioning: `vMAJOR.MINOR.PATCH` (for example `v1.2.0`).

### Release flow

1. Open feature PRs into `develop`.
2. Cut `release/x.y.z` from `develop` when freezing a release.
3. QA and final fixes on `release/x.y.z`.
4. Merge `release/x.y.z` into `main` and tag `vX.Y.Z`.
5. Merge `release/x.y.z` back into `develop`.

## Existing Converter CLI

You can still use direct conversion:

```powershell
python .\pdf2tspl.py input.pdf output.tspl -x 100 -y 75 -r 90 --x-offset-dots 0 --y-offset-dots 0
```

## Notes

- AppSocket script is kept for compatibility, but production path should be server+agent for deterministic routing, retries, and observability.
- Use profile versioning in `templates.json` when tuning offsets or print parameters.
