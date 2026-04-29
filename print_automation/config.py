from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any


@dataclasses.dataclass(frozen=True)
class TemplateProfile:
    template_id: str
    version: int
    label_width_mm: int
    label_height_mm: int
    dpi: float
    rotate: int
    x_offset_dots: int = 0
    y_offset_dots: int = 0
    speed: int | None = None
    density: int | None = None
    direction: int = 0
    reference_x: int = 0
    reference_y: int = 0
    sensor: str = "gap"
    gap_mm: float = 3.0
    gap_offset_mm: float = 0.0
    description: str = ""
    size_code: str = ""

    @property
    def render_kwargs(self) -> dict[str, Any]:
        return {
            "labelwidth_mm": self.label_width_mm,
            "labelheight_mm": self.label_height_mm,
            "dpi": self.dpi,
            "rotate": self.rotate,
        }


@dataclasses.dataclass(frozen=True)
class PrinterCapability:
    name: str
    roll_width_mm: int | None = None
    roll_height_mm: int | None = None
    size_code: str = ""
    is_default: bool = False


@dataclasses.dataclass(frozen=True)
class AgentRuntimeConfig:
    agent_id: str
    agent_name: str
    workstation_id: str
    server_url: str
    auth_token: str
    poll_interval_seconds: float
    heartbeat_interval_seconds: float
    download_timeout_seconds: float
    download_max_retries: int
    work_dir: Path
    printer_name: str
    printers: list[PrinterCapability]
    templates: list[str]
    groups: list[str]
    max_job_retries: int = 2


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_templates(path: str | Path) -> dict[str, TemplateProfile]:
    raw = _load_json(path)
    out: dict[str, TemplateProfile] = {}
    for item in raw.get("templates", []):
        profile = TemplateProfile(
            template_id=item["template_id"],
            version=int(item.get("version", 1)),
            label_width_mm=int(item["label_width_mm"]),
            label_height_mm=int(item["label_height_mm"]),
            dpi=float(item.get("dpi", 203.2)),
            rotate=int(item.get("rotate", 0)),
            x_offset_dots=int(item.get("x_offset_dots", 0)),
            y_offset_dots=int(item.get("y_offset_dots", 0)),
            speed=int(item["speed"]) if item.get("speed") is not None else None,
            density=int(item["density"]) if item.get("density") is not None else None,
            direction=int(item.get("direction", 0)),
            reference_x=int(item.get("reference_x", 0)),
            reference_y=int(item.get("reference_y", 0)),
            sensor=str(item.get("sensor", "gap")),
            gap_mm=float(item.get("gap_mm", 3.0)),
            gap_offset_mm=float(item.get("gap_offset_mm", 0.0)),
            description=str(item.get("description", "")),
            size_code=str(item.get("size_code", "")).strip().lower(),
        )
        out[profile.template_id] = profile
    return out


def _load_printer_capabilities(raw: dict[str, Any]) -> list[PrinterCapability]:
    configured = raw.get("printers")
    out: list[PrinterCapability] = []

    if isinstance(configured, list):
        for idx, item in enumerate(configured):
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                out.append(PrinterCapability(name=name, is_default=(idx == 0)))
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            out.append(
                PrinterCapability(
                    name=name,
                    roll_width_mm=int(item["roll_width_mm"]) if item.get("roll_width_mm") is not None else None,
                    roll_height_mm=int(item["roll_height_mm"]) if item.get("roll_height_mm") is not None else None,
                    size_code=str(item.get("size_code", "")).strip().lower(),
                    is_default=bool(item.get("is_default", idx == 0)),
                )
            )

    if out:
        return out

    fallback = str(raw.get("printer_name", "")).strip()
    if fallback:
        return [PrinterCapability(name=fallback, is_default=True)]
    raise ValueError("agent config must define printer_name or printers")


def load_agent_runtime_config(path: str | Path) -> AgentRuntimeConfig:
    raw = _load_json(path)
    printer_capabilities = _load_printer_capabilities(raw)
    printer_name = str(raw.get("printer_name", "")).strip() or printer_capabilities[0].name
    workstation_id = str(raw.get("workstation_id", raw.get("agent_id", ""))).strip()
    if not workstation_id:
        raise ValueError("agent config must define workstation_id or agent_id")
    return AgentRuntimeConfig(
        agent_id=str(raw["agent_id"]),
        agent_name=str(raw.get("agent_name", raw["agent_id"])),
        workstation_id=workstation_id,
        server_url=str(raw["server_url"]).rstrip("/"),
        auth_token=str(raw["auth_token"]),
        poll_interval_seconds=float(raw.get("poll_interval_seconds", 2.0)),
        heartbeat_interval_seconds=float(raw.get("heartbeat_interval_seconds", 10.0)),
        download_timeout_seconds=float(raw.get("download_timeout_seconds", 20.0)),
        download_max_retries=int(raw.get("download_max_retries", 4)),
        work_dir=Path(raw.get("work_dir", "./agent_work")).resolve(),
        printer_name=printer_name,
        printers=printer_capabilities,
        templates=list(raw.get("templates", [])),
        groups=list(raw.get("groups", [])),
        max_job_retries=int(raw.get("max_job_retries", 2)),
    )
