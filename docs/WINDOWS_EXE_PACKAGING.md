# Windows EXE Packaging Guide

This guide explains two packaging options:

1. `App EXE bundles` (portable server/agent executables) via PyInstaller.
2. `Installer EXE` (setup wizard) via Inno Setup.

## 1) Build App EXE Bundles (PyInstaller)

Script:

- `scripts/build_windows_exe.ps1`

What it builds:

- `pdf2tspl-server` from `scripts/run_server.py`
- `pdf2tspl-agent` from `scripts/run_agent.py`
- `pdf2tspl-submit-job` from `scripts/submit_job.py`

### Command

Run in PowerShell from repo root:

```powershell
.\scripts\build_windows_exe.ps1 -Target all
```

Optional one-file output:

```powershell
.\scripts\build_windows_exe.ps1 -Target all -OneFile
```

Output path:

- `artifacts\exe\v<VERSION>\`

Notes:

- Script installs/updates `pyinstaller` automatically in selected Python env.
- It also copies `config\`, `VERSION`, and `README.md` into output.
- For production reliability, `--onedir` (default) is recommended over `--onefile`.

## 2) Build Installer EXE (Inno Setup)

Scripts/files:

- `scripts/build_windows_installer.ps1`
- `installer/windows/Pdf2TsplInstaller.iss`

Prerequisite:

- Install Inno Setup 6 (must provide `ISCC.exe`).

### Command

```powershell
.\scripts\build_windows_installer.ps1 -Mode both -AuthToken "change-me-token"
```

Agent-only installer example:

```powershell
.\scripts\build_windows_installer.ps1 `
  -Mode agent `
  -AuthToken "change-me-token" `
  -ServerUrl "http://192.168.1.20:8089"
```

Output path:

- `artifacts\installer\v<VERSION>\Pdf2TsplSetup_v<VERSION>.exe`

## 3) What the Installer EXE Does

- Copies repository files into install directory.
- Adds start menu shortcuts for setup/readme.
- Offers post-install action to run:
  - `setup_windows.ps1` (recommended)

`setup_windows.ps1` then performs full machine setup:

- Install Python if missing.
- Create `.venv`, install requirements.
- Prepare server/agent configs.
- Install auto-start Windows services.

## 4) Verify Installed Result

After install/setup:

```powershell
Invoke-RestMethod http://127.0.0.1:8089/health
Get-Service Pdf2Tspl-Server
Get-Service Pdf2Tspl-Agent-$env:COMPUTERNAME
```

Expected:

- health returns `{"ok": true}`
- services exist and status is `Running`

## 5) Uninstall

Remove services first:

```powershell
.\scripts\uninstall_windows_service.ps1 -Mode server
.\scripts\uninstall_windows_service.ps1 -Mode agent
```

Then uninstall app via Windows Apps/Programs, or delete install directory if using portable deployment.
