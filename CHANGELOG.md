# Changelog

All notable changes to this project are documented in this file.

## [1.2.0] - 2026-06-21

### Added

- One-click Windows service wrappers:
  - `INSTALL_ON_NEW_PC.bat`
  - `install_print_services.bat`
  - `print_services_status.bat`
  - `uninstall_print_services.bat`
- Cloudflare tunnel automation for public HTTPS at `tspl.k95foods.com`:
  - `scripts/install_cloudflare_tunnel.ps1`
  - `scripts/uninstall_cloudflare_tunnel.ps1`
  - `install_cloudflare_tunnel.bat`
  - `config/cloudflared.token.example`
  - `config/cloudflared.yml.example`
- Dashboard and operations guide: `docs/DASHBOARD_ACCESS_AND_FLOW.md`
- CORS headers on server API responses for browser-based clients.

### Changed

- `setup_windows.ps1` installs Cloudflare tunnel service when credentials are present.
- Agent config loader accepts UTF-8 files with or without BOM.
- `.gitignore` excludes tunnel secrets and downloaded `nssm.exe` / `cloudflared.exe`.

### Operational Behavior

- Three Windows services on server PC: server, agent, and Cloudflare tunnel.
- All services auto-start on boot and auto-restart on crash/close.
- Tunnel service depends on server service and forwards `tspl.k95foods.com` to `localhost:8089`.

## [1.1.1] - 2026-05-04

### Changed

- Optimized `scripts/build_windows_exe.ps1` to avoid unnecessary `win32com` collection for non-agent builds, reducing build time and artifact bloat.
- Added build output directories to `.gitignore`:
  - `artifacts/`
  - `build/`
  - `dist/`

## [1.1.0] - 2026-05-04

### Added

- One-command Windows installer scripts:
  - `setup_windows.ps1`
  - `setup_windows.bat`
- Windows service management scripts (NSSM-based):
  - `scripts/install_windows_service.ps1`
  - `scripts/uninstall_windows_service.ps1`
- EXE packaging scripts:
  - `scripts/build_windows_exe.ps1` (PyInstaller app bundles)
  - `scripts/build_windows_installer.ps1` (Inno Setup installer EXE)
  - `installer/windows/Pdf2TsplInstaller.iss`
- New documentation coverage for setup/operations and packaging.

### Changed

- Introduced centralized app versioning:
  - `VERSION`
  - `print_automation/version.py`
- Agent heartbeat now reports release version from shared version source.
- `scripts/run_server.py` and `scripts/run_agent.py` now support `--version`.

### Operational Behavior

- Auto-start at boot and auto-restart on crash are available through Windows Service mode.
- Crash recovery now has layered restart handling:
  - `run_supervised.ps1` loop restart
  - NSSM restart policy
  - Windows Service recovery (`sc failure`)
