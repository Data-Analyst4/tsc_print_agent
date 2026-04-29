from __future__ import annotations

import dataclasses
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .admin_ui import ADMIN_PRINTER_UI_HTML
from .config import TemplateProfile, load_templates
from .db import PrintDB
from .helpers import new_id
from .routing import (
    agent_matches_job,
    is_agent_online,
    normalize_size_code,
    pick_agent_printer_for_job,
)
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

    def build_discovery(self) -> dict[str, Any]:
        templates = [dataclasses.asdict(p) for p in self.templates.values()]
        agents = self.db.list_agents()
        workstations = self.db.list_workstations()
        fallback_rules = self.db.list_workstation_fallbacks()
        printer_profiles = self.db.list_agent_printer_profiles()

        agents_by_id = {a["agent_id"]: a for a in agents}
        active_printers: list[dict[str, Any]] = []
        for profile in printer_profiles:
            agent = agents_by_id.get(profile["agent_id"])
            if not agent:
                continue
            online = is_agent_online(agent, max_age_seconds=self.settings.max_agent_staleness_seconds)
            if not online or not profile.get("enabled", True):
                continue
            active_printers.append(
                {
                    "agent_id": agent["agent_id"],
                    "workstation_id": agent.get("workstation_id"),
                    "printer_name": profile.get("printer_name"),
                    "size_code": profile.get("size_code"),
                    "roll_width_mm": profile.get("roll_width_mm"),
                    "roll_height_mm": profile.get("roll_height_mm"),
                    "heartbeat_at": agent.get("heartbeat_at"),
                }
            )

        return {
            "templates": templates,
            "workstations": workstations,
            "workstation_fallbacks": fallback_rules,
            "agents": agents,
            "printer_profiles": printer_profiles,
            "active_printers": active_printers,
        }

    def submit_job(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        source_type, source_value = self._parse_source(payload)
        profile, requested_size_code = self._resolve_template_profile(payload)
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
        requested_workstation_id = self._coerce_optional_str(target.get("workstation_id")) or self._coerce_optional_str(
            target.get("workstation")
        )

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        metadata = dict(metadata)
        if requested_workstation_id:
            metadata["requested_workstation_id"] = requested_workstation_id
        if requested_size_code:
            metadata["requested_size_code"] = requested_size_code

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
            printer_profiles = self.db.list_agent_printer_profiles()
            fallback_order: list[str] = []
            if requested_workstation_id:
                fallback_order = self.db.get_workstation_fallback_order(requested_workstation_id)
            picked = pick_agent_printer_for_job(
                job=job,
                agents=agents,
                printer_profiles=printer_profiles,
                fallback_order=fallback_order,
                max_age_seconds=self.settings.max_agent_staleness_seconds,
            )
            if picked:
                picked_agent_id = picked["agent"]["agent_id"]
                picked_printer_name = str(picked["printer_profile"].get("printer_name") or "").strip() or None
                if picked_printer_name and not target_printer:
                    self.db.set_job_target_printer(job["job_id"], picked_printer_name)
                self.db.assign_job(job["job_id"], picked_agent_id)
                job = self.db.get_job(job["job_id"]) or job

        return job, created

    def claim_next_for_agent(self, agent_id: str) -> dict[str, Any] | None:
        agent = self.db.get_agent(agent_id)
        if not agent:
            raise ValueError(f"unknown agent_id '{agent_id}'")

        all_agents = self.db.list_agents()
        agents_by_id = {a["agent_id"]: a for a in all_agents}
        printer_profiles = self.db.list_agent_printer_profiles()
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

            metadata = job.get("metadata") or {}
            fallback_order: list[str] = []
            if isinstance(metadata, dict):
                requested_workstation_id = self._coerce_optional_str(metadata.get("requested_workstation_id"))
                if requested_workstation_id:
                    fallback_order = self.db.get_workstation_fallback_order(requested_workstation_id)

            picked = pick_agent_printer_for_job(
                job=job,
                agents=all_agents,
                printer_profiles=printer_profiles,
                fallback_order=fallback_order,
                max_age_seconds=self.settings.max_agent_staleness_seconds,
            )
            if not picked:
                continue
            picked_agent_id = picked["agent"]["agent_id"]
            if picked_agent_id != agent_id:
                continue
            picked_printer_name = str(picked["printer_profile"].get("printer_name") or "").strip() or None
            if picked_printer_name and not job.get("target_printer"):
                self.db.set_job_target_printer(job["job_id"], picked_printer_name)

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

    def _resolve_template_profile(self, payload: dict[str, Any]) -> tuple[TemplateProfile, str | None]:
        template_id = self._coerce_optional_str(payload.get("template_id"))
        requested_size_code = normalize_size_code(self._coerce_optional_str(payload.get("label_size")))
        if not requested_size_code:
            requested_size_code = normalize_size_code(self._coerce_optional_str(payload.get("size_code")))

        if template_id:
            if template_id not in self.templates:
                raise ValueError(f"unknown template_id '{template_id}'")
            profile = self.templates[template_id]
            profile_size = normalize_size_code(profile.size_code)
            if requested_size_code and profile_size and requested_size_code != profile_size:
                raise ValueError(
                    f"template '{template_id}' has size_code '{profile_size}' but request asked for '{requested_size_code}'"
                )
            return profile, requested_size_code or profile_size

        if not requested_size_code:
            raise ValueError("template_id or label_size/size_code is required")

        matches = [p for p in self.templates.values() if normalize_size_code(p.size_code) == requested_size_code]
        if not matches:
            raise ValueError(f"no template configured for size_code '{requested_size_code}'")

        matches.sort(key=lambda p: (p.version, p.template_id), reverse=True)
        return matches[0], requested_size_code

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

        if path in {"/admin", "/admin/"}:
            self._write_html(HTTPStatus.OK, ADMIN_PRINTER_UI_HTML)
            return

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

        if path == "/v1/admin/printer-profiles":
            agent_id = query.get("agent_id", [None])[0]
            self._write_json(
                HTTPStatus.OK,
                {"printer_profiles": self.server.app.db.list_agent_printer_profiles(agent_id=agent_id)},
            )
            return

        if path == "/v1/admin/workstations":
            self._write_json(
                HTTPStatus.OK,
                {"workstations": self.server.app.db.list_workstations()},
            )
            return

        if path == "/v1/admin/workstation-fallbacks":
            workstation_id = query.get("workstation_id", [None])[0]
            self._write_json(
                HTTPStatus.OK,
                {"workstation_fallbacks": self.server.app.db.list_workstation_fallbacks(workstation_id=workstation_id)},
            )
            return

        if path == "/v1/discovery":
            self._write_json(HTTPStatus.OK, self.server.app.build_discovery())
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

            if path == "/v1/admin/printer-profiles":
                agent_id = str(payload.get("agent_id", "")).strip()
                printer_name = str(payload.get("printer_name", "")).strip()
                if not agent_id:
                    raise ValueError("agent_id is required")
                if not printer_name:
                    raise ValueError("printer_name is required")

                roll_width_mm = payload.get("roll_width_mm")
                roll_height_mm = payload.get("roll_height_mm")
                size_code = payload.get("size_code")
                notes = payload.get("notes")
                enabled = payload.get("enabled")
                profile = self.server.app.db.upsert_agent_printer_profile(
                    agent_id=agent_id,
                    printer_name=printer_name,
                    roll_width_mm=self._coerce_optional_int(roll_width_mm),
                    roll_height_mm=self._coerce_optional_int(roll_height_mm),
                    size_code=str(size_code) if size_code is not None else None,
                    notes=str(notes) if notes is not None else None,
                    enabled=self._coerce_bool(enabled, default=True),
                )
                self._write_json(HTTPStatus.OK, {"printer_profile": profile})
                return

            if path == "/v1/admin/printer-profiles/delete":
                agent_id = str(payload.get("agent_id", "")).strip()
                printer_name = str(payload.get("printer_name", "")).strip()
                if not agent_id:
                    raise ValueError("agent_id is required")
                if not printer_name:
                    raise ValueError("printer_name is required")
                deleted = self.server.app.db.delete_agent_printer_profile(agent_id=agent_id, printer_name=printer_name)
                self._write_json(HTTPStatus.OK, {"deleted": deleted})
                return

            if path == "/v1/admin/workstations":
                workstation_id = str(payload.get("workstation_id", "")).strip()
                if not workstation_id:
                    raise ValueError("workstation_id is required")
                name = str(payload.get("name", workstation_id)).strip()
                location_tag = self.server.app._coerce_optional_str(payload.get("location_tag"))
                enabled = self._coerce_bool(payload.get("enabled"), default=True)
                workstation = self.server.app.db.upsert_workstation(
                    workstation_id=workstation_id,
                    name=name,
                    location_tag=location_tag,
                    enabled=enabled,
                )
                self._write_json(HTTPStatus.OK, {"workstation": workstation})
                return

            if path == "/v1/admin/workstations/delete":
                workstation_id = str(payload.get("workstation_id", "")).strip()
                if not workstation_id:
                    raise ValueError("workstation_id is required")
                deleted = self.server.app.db.delete_workstation(workstation_id)
                self._write_json(HTTPStatus.OK, {"deleted": deleted})
                return

            if path == "/v1/admin/workstation-fallbacks":
                workstation_id = str(payload.get("workstation_id", "")).strip()
                if not workstation_id:
                    raise ValueError("workstation_id is required")
                fallback_ids = payload.get("fallback_workstation_ids", [])
                if not isinstance(fallback_ids, list):
                    raise ValueError("fallback_workstation_ids must be an array")
                rules = self.server.app.db.set_workstation_fallbacks(
                    workstation_id=workstation_id,
                    fallback_workstation_ids=[str(x) for x in fallback_ids],
                )
                self._write_json(HTTPStatus.OK, {"workstation_fallbacks": rules})
                return

            if path == "/v1/agents/heartbeat":
                agent_id = str(payload.get("agent_id", "")).strip()
                if not agent_id:
                    raise ValueError("agent_id is required")
                name = str(payload.get("name", agent_id))
                workstation_id = self.server.app._coerce_optional_str(payload.get("workstation_id")) or agent_id
                groups = payload.get("groups", [])
                printers = payload.get("printers", [])
                templates = payload.get("templates", [])
                if not isinstance(groups, list) or not isinstance(printers, list) or not isinstance(templates, list):
                    raise ValueError("groups/printers/templates must be arrays")

                printer_names: list[str] = []
                printer_profiles: list[dict[str, Any]] = []
                for item in printers:
                    if isinstance(item, dict):
                        pname = str(item.get("name", "")).strip()
                        if not pname:
                            continue
                        printer_names.append(pname)
                        printer_profiles.append(
                            {
                                "printer_name": pname,
                                "roll_width_mm": self._coerce_optional_int(item.get("roll_width_mm")),
                                "roll_height_mm": self._coerce_optional_int(item.get("roll_height_mm")),
                                "size_code": str(item.get("size_code", "")).strip().lower() or None,
                                "notes": str(item.get("notes", "")).strip() or None,
                                "enabled": self._coerce_bool(item.get("enabled"), default=True),
                            }
                        )
                    else:
                        pname = str(item).strip()
                        if pname:
                            printer_names.append(pname)

                agent = self.server.app.db.upsert_agent(
                    agent_id=agent_id,
                    name=name,
                    workstation_id=workstation_id,
                    groups=[str(x) for x in groups],
                    printers=printer_names,
                    templates=[str(x) for x in templates],
                    host=str(payload.get("host", "")) or None,
                    version=str(payload.get("version", "")) or None,
                )
                self.server.app.db.upsert_workstation(
                    workstation_id=workstation_id,
                    name=str(payload.get("workstation_name", workstation_id)),
                    location_tag=self.server.app._coerce_optional_str(payload.get("location_tag")),
                    enabled=True,
                )

                for p in printer_profiles:
                    self.server.app.db.upsert_agent_printer_profile(
                        agent_id=agent_id,
                        printer_name=p["printer_name"],
                        roll_width_mm=p["roll_width_mm"],
                        roll_height_mm=p["roll_height_mm"],
                        size_code=p["size_code"],
                        notes=p["notes"],
                        enabled=bool(p.get("enabled", True)),
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

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return int(text)

    def _write_html(self, status: HTTPStatus, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
