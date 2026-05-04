from __future__ import annotations

import dataclasses
import logging
import socket
import time
from pathlib import Path
from typing import Any

from .api_client import ApiClientError, PrintApiClient
from .config import AgentRuntimeConfig, TemplateProfile, load_templates
from .downloader import DownloadError, download_pdf
from .printer import PrintError, print_raw
from .renderer import render_pdf_to_tspl
from .states import STATUS_DOWNLOADING, STATUS_FAILED, STATUS_PRINTING, STATUS_RENDERING, STATUS_SUCCESS
from .version import APP_VERSION

LOG = logging.getLogger("print_automation.agent")


class PrintAgent:
    def __init__(self, config: AgentRuntimeConfig, templates_path: Path):
        self.config = config
        self.templates = load_templates(templates_path)
        self.client = PrintApiClient(config.server_url, config.auth_token)
        self._last_heartbeat_at = 0.0
        self._hostname = socket.gethostname()
        self.config.work_dir.mkdir(parents=True, exist_ok=True)

    def run_forever(self) -> None:
        LOG.info("Agent %s starting, printer=%s", self.config.agent_id, self.config.printer_name)
        while True:
            now = time.monotonic()
            if now - self._last_heartbeat_at >= self.config.heartbeat_interval_seconds:
                self._heartbeat()
                self._last_heartbeat_at = now

            job = self._claim_next_job()
            if not job:
                time.sleep(self.config.poll_interval_seconds)
                continue

            self._process_job(job)

    def _heartbeat(self) -> None:
        printers_payload: list[dict[str, Any]] = []
        for p in self.config.printers:
            printers_payload.append(
                {
                    "name": p.name,
                    "roll_width_mm": p.roll_width_mm,
                    "roll_height_mm": p.roll_height_mm,
                    "size_code": p.size_code,
                }
            )

        payload = {
            "agent_id": self.config.agent_id,
            "name": self.config.agent_name,
            "workstation_id": self.config.workstation_id,
            "groups": self.config.groups,
            "printers": printers_payload if printers_payload else [self.config.printer_name],
            "templates": self.config.templates,
            "host": self._hostname,
            "version": APP_VERSION,
        }
        try:
            self.client.heartbeat(payload)
        except ApiClientError as exc:
            LOG.warning("heartbeat failed: %s", exc)

    def _claim_next_job(self) -> dict[str, Any] | None:
        try:
            response = self.client.claim_next_job(self.config.agent_id)
        except ApiClientError as exc:
            LOG.warning("claim_next failed: %s", exc)
            return None
        return response.get("job")

    def _process_job(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        job_dir = self.config.work_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        local_pdf = job_dir / "source.pdf"
        local_tspl = job_dir / "label.tspl"
        target_printer = str(job.get("target_printer") or "").strip() or None
        selected_printer = target_printer or self.config.printer_name

        template_id = job["template_id"]
        profile = self.templates.get(template_id)
        if not profile:
            self._fail_job(job_id, f"template '{template_id}' is not installed on agent", retryable=False)
            return
        if not self._is_known_printer(selected_printer):
            self._fail_job(job_id, f"target printer '{selected_printer}' is not configured on this agent", retryable=False)
            return

        try:
            self._set_status(job_id, STATUS_DOWNLOADING, "Downloading source PDF")
            pdf_path, pdf_sha = download_pdf(
                source_type=job["source_type"],
                source_value=job["source_value"],
                destination=local_pdf,
                timeout_seconds=self.config.download_timeout_seconds,
                max_retries=self.config.download_max_retries,
            )

            self._set_status(
                job_id,
                STATUS_RENDERING,
                "Rendering PDF to TSPL",
                details={
                    "template_id": profile.template_id,
                    "template_version": profile.version,
                    "profile": dataclasses.asdict(profile),
                    "pdf_sha256": pdf_sha,
                },
            )

            tspl_bytes = render_pdf_to_tspl(pdf_path, profile)
            local_tspl.write_bytes(tspl_bytes)

            self._set_status(
                job_id,
                STATUS_PRINTING,
                "Sending RAW TSPL to printer",
                details={
                    "printer_name": selected_printer,
                    "copies": job["copies"],
                    "output_pdf_path": str(local_pdf),
                    "output_tspl_path": str(local_tspl),
                },
                output_pdf_path=str(local_pdf),
                output_tspl_path=str(local_tspl),
            )

            print_results = print_raw(
                printer_name=selected_printer,
                data=tspl_bytes,
                document_name=job_id,
                copies=int(job["copies"]),
                timeout_seconds=45.0,
            )
            self._set_status(job_id, STATUS_SUCCESS, "Printed successfully", details={"print_results": print_results})

        except DownloadError as exc:
            self._fail_job(job_id, f"download failed: {exc}", retryable=True)
        except PrintError as exc:
            self._fail_job(job_id, f"print failed: {exc}", retryable=True)
        except Exception as exc:
            self._fail_job(job_id, f"unexpected failure: {exc}", retryable=False)

    def _set_status(
        self,
        job_id: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
        output_pdf_path: str | None = None,
        output_tspl_path: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"status": status, "message": message}
        if details is not None:
            payload["details"] = details
        if output_pdf_path:
            payload["output_pdf_path"] = output_pdf_path
        if output_tspl_path:
            payload["output_tspl_path"] = output_tspl_path
        self.client.set_job_status(job_id, payload)

    def _fail_job(self, job_id: str, error: str, retryable: bool) -> None:
        LOG.error("job %s failed: %s", job_id, error)
        try:
            self.client.set_job_status(
                job_id,
                {
                    "status": STATUS_FAILED,
                    "message": "Job failed",
                    "error_message": error,
                    "retryable": retryable,
                    "details": {"retryable": retryable},
                },
            )
        except ApiClientError as exc:
            LOG.error("failed to report job failure: %s", exc)

    def _is_known_printer(self, printer_name: str) -> bool:
        configured = {self.config.printer_name}
        configured.update(p.name for p in self.config.printers)
        return printer_name in configured
