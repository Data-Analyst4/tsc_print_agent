# Documentation Index

Use this as the starting point for onboarding, installation, operations, and release packaging.

## Core Guides

- `README.md`: quick start, architecture, and high-level commands.
- `docs/SETUP_AND_OPERATIONS_GUIDE.md`: full deployment and operations runbook.
- `docs/NEW_COMPUTER_SETUP.md`: practical fresh-machine checklist.
- `docs/DASHBOARD_ACCESS_AND_FLOW.md`: dashboard access, section-by-section behavior, and end-to-end runtime flow.

## Installation Paths

- `setup_windows.ps1`: one-command Windows setup (dependencies + config + service install).
- `setup_windows.bat`: launcher wrapper for `setup_windows.ps1` (auto-elevates to Administrator).
- `INSTALL_ON_NEW_PC.bat`: one-click fresh-PC installer (no manual pre-install required).

## Auto-Start / Service Management

- `install_print_services.bat`: one-click server + agent (+ tunnel if configured).
- `print_services_status.bat`: check server, agent, tunnel, local and public health.
- `uninstall_print_services.bat`: remove all PDF2TSPL services.
- `scripts/install_windows_service.ps1`: install server/agent as Windows services (NSSM).
- `scripts/uninstall_windows_service.ps1`: remove installed services.
- `scripts/install_windows_autostart.ps1`: Task Scheduler mode (alternative).
- `scripts/uninstall_windows_autostart.ps1`: remove scheduled tasks.

## Cloudflare Tunnel (Public HTTPS)

- `install_cloudflare_tunnel.bat`: install tunnel as Windows service.
- `scripts/install_cloudflare_tunnel.ps1`: NSSM service for `cloudflared`.
- `scripts/uninstall_cloudflare_tunnel.ps1`: remove tunnel service.
- `config/cloudflared.token.example`: copy to `config/cloudflared.token` with your token.
- `config/cloudflared.yml.example`: alternative config-file mode.

## Packaging and Release

- `docs/WINDOWS_EXE_PACKAGING.md`: how to package app as EXE bundles/installer.
- `scripts/build_windows_exe.ps1`: build server/agent/submit executable bundles.
- `scripts/build_windows_installer.ps1`: compile installer EXE using Inno Setup.
- `installer/windows/Pdf2TsplInstaller.iss`: installer definition.
- `CHANGELOG.md`: release notes.
- `VERSION`: canonical release version for runtime + docs.
