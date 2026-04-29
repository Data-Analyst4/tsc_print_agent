from __future__ import annotations

import dataclasses
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import load_templates
from .db import PrintDB
from .helpers import new_id
from .routing import agent_matches_job, is_agent_online, pick_agent_for_job
from .states import STATUS_ASSIGNED, STATUS_FAILED, STATUS_QUEUED

LOG = logging.getLogger("print_automation.server")


@dataclasses.dataclass
class ServerSettings:
    host: str
    port: int
    db_path: Path
    templates_path: Path
    auth_token: str
    max_agent_staleness_seconds: int = 45
    default_max_job_retries: int = 2


class PrintAutomationApp:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.db = PrintDB(settings.db_path)
        self.templates = load_templates(settings.templates_path)

    def reload_templates(self) -> None:
        self.templates = load_templates(self.settings.templates_path)

    def submit_job(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        source_type, source_value = self._parse_source(payload)
        template_id = str(payload.get("template_id", "")).strip()
        if template_id not in self.templates:
            raise ValueError(f"unknown template_id '{template_id}'")

        profile = self.templates[template_id]
        copies = int(payload.get("copies", 1))
        if copies < 1 or copies > 200:
            raise ValueError("copies must be between 1 and 200")

        idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None:
            idempotency_key = str(idempotency_key).strip() or None

        target = payload.get("target", {}) or {}
        target_agent_id = self._coerce_optional_str(target.get("agent_id"))
        target_group = self._coerce_optional_str(target.get("group"))
        target_printer = self._coerce_optional_str(target.get("printer"))

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")

        job_id = new_id("job")
        job, created = self.db.create_job(
            job_id=job_id,
            idempotency_key=idempotency_key,
            source_type=source_type,
            source_value=source_value,
            template_id=profile.template_id,
            template_version=profile.version,
            copies=copies,
            target_agent_id=target_agent_id,
            target_group=target_group,
            target_printer=target_printer,
            profile=dataclasses.asdict(profile),
            metadata=metadata,
            max_retries=int(payload.get("max_retries", self.settings.default_max_job_retries)),
        )

        # Attempt immediate assignment for lower queue latency.
        if created and job["status"] == STATUS_QUEUED:
            agents = self.db.list_agents()
            picked = pick_agent_for_job(job, agents, max_age_seconds=self.settings.max_agent_staleness_seconds)
            if picked:
                self.db.assign_job(job["job_id"], picked["agent_id"])
                job = self.db.get_job(job["job_id"]) or job

        return job, created

    def claim_next_for_agent(self, agent_id: str) -> dict[str, Any] | None:
        agent = self.db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"unknown agent_id '{agent_id}'")

        agents_by_id = {a["agent_id"]: a for a in self.db.list_agents()}
        candidates = self.db.list_candidate_jobs(limit=200)
        for job in candidates:
            status = job["status"]
            assigned = job["assigned_agent_id"]

            if status == STATUS_ASSIGNED:
                if assigned and assigned != agent_id:
                    assigned_agent = agents_by_id.get(assigned)
                    is_stale = True
                    if assigned_agent:
                        is_stale = not is_agent_online(
                            assigned_agent,
                            max_age_seconds=self.settings.max_agent_staleness_seconds,
                        )
                    if is_stale:
                        self.db.release_assigned_job(job["job_id"], "assigned agent is offline/stale")
                        job = self.db.get_job(job["job_id"]) or job
                        status = job["status"]
                        assigned = job["assigned_agent_id"]
                    else:
                        continue
                if assigned == agent_id and agent_matches_job(job, agent):
                    return job

            if status != STATUS_QUEUED:
                continue

            if not agent_matches_job(job, agent):
                continue

            if self.db.assign_job(job["job_id"], agent_id):
                return self.db.get_job(job["job_id"])

        return None

    def update_job_status(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        new_status = str(payload.get("status", "")).strip().upper()
        if not new_status:
            raise ValueError("status is required")

        message = str(payload.get("message", ""))
        error_message = self._coerce_optional_str(payload.get("error_message"))
        details = payload.get("details")
        if details is not None and not isinstance(details, dict):
            raise ValueError("details must be an object")

        if payload.get("output_pdf_path") or payload.get("output_tspl_path"):
            self.db.set_job_artifacts(
                job_id,
                self._coerce_optional_str(payload.get("output_pdf_path")),
                self._coerce_optional_str(payload.get("output_tspl_path")),
            )

        retryable = bool(payload.get("retryable", False))
        if new_status == STATUS_FAILED and retryable:
            self.db.increment_retry(job_id)
            job = self.db.requeue_if_retryable(
                job_id,
                message=message or "Retrying job",
                error_message=error_message or "retry requested",
            )
            if not job:
                raise ValueError(f"unknown job_id '{job_id}'")
            return job

        job = self.db.set_job_status(
            job_id=job_id,
            new_status=new_status,
            message=message,
            error_message=error_message,
            details=details,
            allow_any_transition=False,
        )
        if not job:
            raise ValueError(f"unknown job_id '{job_id}'")
        return job

    @staticmethod
    def _parse_source(payload: dict[str, Any]) -> tuple[str, str]:
        source = payload.get("source")
        if isinstance(source, dict):
            source_type = str(source.get("type", "")).strip().lower()
            source_value = str(source.get("value", "")).strip()
            if source_type in {"path", "url"} and source_value:
                return source_type, source_value

        pdf_url = payload.get("pdf_url")
        if pdf_url:
            return "url", str(pdf_url)
        pdf_path = payload.get("pdf_path")
        if pdf_path:
            return "path", str(pdf_path)
        raise ValueError("source is required (use source.{type,value} or pdf_url/pdf_path)")

    @staticmethod
    def _coerce_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        out = str(value).strip()
        return out or None


class _ServerWithApp(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], app: PrintAutomationApp):
        super().__init__(server_address, handler_cls)
        self.app = app


class PrintAutomationHandler(BaseHTTPRequestHandler):
    server: _ServerWithApp

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True})
            return

        if not self._check_auth():
            return

        if path == "/v1/templates":
            templates = [dataclasses.asdict(p) for p in self.server.app.templates.values()]
            self._write_json(HTTPStatus.OK, {"templates": templates})
            return

        if path == "/v1/agents":
            self._write_json(HTTPStatus.OK, {"agents": self.server.app.db.list_agents()})
            return

        if path == "/v1/jobs":
            status = query.get("status", [None])[0]
            limit_raw = query.get("limit", ["100"])[0]
            try:
                limit = max(1, min(500, int(limit_raw)))
            except ValueError:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid limit"})
                return
            jobs = self.server.app.db.list_jobs(status=status, limit=limit)
            self._write_json(HTTPStatus.OK, {"jobs": jobs})
            return

        if path.startswith("/v1/jobs/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) == 3:
                job_id = parts[2]
                job = self.server.app.db.get_job(job_id)
                if not job:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "job not found"})
                    return
                include_events = query.get("include_events", ["false"])[0].lower() == "true"
                response: dict[str, Any] = {"job": job}
                if include_events:
                    response["events"] = self.server.app.db.get_job_events(job_id)
                self._write_json(HTTPStatus.OK, response)
                return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path

        if not self._check_auth():
            return

        try:
            payload = self._read_json()
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        try:
            if path == "/v1/jobs":
                job, created = self.server.app.submit_job(payload)
                code = HTTPStatus.CREATED if created else HTTPStatus.OK
                self._write_json(code, {"job": job, "created": created})
                return

            if path == "/v1/agents/heartbeat":
                agent_id = str(payload.get("agent_id", "")).strip()
                if not agent_id:
                    raise ValueError("agent_id is required")
                name = str(payload.get("name", agent_id))
                groups = payload.get("groups", [])
                printers = payload.get("printers", [])
                templates = payload.get("templates", [])
                if not isinstance(groups, list) or not isinstance(printers, list) or not isinstance(templates, list):
                    raise ValueError("groups/printers/templates must be arrays")
                agent = self.server.app.db.upsert_agent(
                    agent_id=agent_id,
                    name=name,
                    groups=[str(x) for x in groups],
                    printers=[str(x) for x in printers],
                    templates=[str(x) for x in templates],
                    host=str(payload.get("host", "")) or None,
                    version=str(payload.get("version", "")) or None,
                )
                self._write_json(HTTPStatus.OK, {"agent": agent})
                return

            if path.startswith("/v1/agents/") and path.endswith("/claim-next"):
                parts = [p for p in path.split("/") if p]
                if len(parts) != 4:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                agent_id = parts[2]
                job = self.server.app.claim_next_for_agent(agent_id)
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path.startswith("/v1/jobs/") and path.endswith("/status"):
                parts = [p for p in path.split("/") if p]
                if len(parts) != 4:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                job_id = parts[2]
                job = self.server.app.update_job_status(job_id, payload)
                self._write_json(HTTPStatus.OK, {"job": job})
                return
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:
            LOG.exception("Unhandled server error")
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _check_auth(self) -> bool:
        expected = self.server.app.settings.auth_token
        supplied = self.headers.get("X-Auth-Token")
        if supplied == expected:
            return True
        self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return False

    def _read_json(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_server(settings: ServerSettings) -> None:
    app = PrintAutomationApp(settings)
    httpd = _ServerWithApp((settings.host, settings.port), PrintAutomationHandler, app)
    LOG.info("Server starting on http://%s:%s", settings.host, settings.port)
    try:
        httpd.serve_forever()
    finally:
        app.db.close()
