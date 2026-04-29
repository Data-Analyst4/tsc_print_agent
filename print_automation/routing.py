from __future__ import annotations

import datetime as dt
from typing import Any


def _parse_iso(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def is_agent_online(agent: dict[str, Any], max_age_seconds: int = 45) -> bool:
    try:
        last = _parse_iso(agent["heartbeat_at"])
    except Exception:
        return False
    age = dt.datetime.now(dt.timezone.utc) - last
    return age.total_seconds() <= max_age_seconds and agent.get("status") == "ONLINE"


def agent_matches_job(job: dict[str, Any], agent: dict[str, Any]) -> bool:
    template_id = job["template_id"]
    if template_id not in agent.get("templates", []):
        return False

    target_agent_id = job.get("target_agent_id")
    if target_agent_id and target_agent_id != agent.get("agent_id"):
        return False

    target_group = job.get("target_group")
    if target_group and target_group not in agent.get("groups", []):
        return False

    target_printer = job.get("target_printer")
    if target_printer and target_printer not in agent.get("printers", []):
        return False

    return True


def pick_agent_for_job(job: dict[str, Any], agents: list[dict[str, Any]], max_age_seconds: int = 45) -> dict[str, Any] | None:
    candidates = [
        agent
        for agent in agents
        if is_agent_online(agent, max_age_seconds=max_age_seconds) and agent_matches_job(job, agent)
    ]
    if not candidates:
        return None

    # Deterministic fallback: choose most recently heartbeating candidate.
    candidates.sort(key=lambda a: a["heartbeat_at"], reverse=True)
    return candidates[0]

