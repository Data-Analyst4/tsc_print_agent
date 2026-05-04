# Changelog

All notable changes to this project are documented in this file.

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
