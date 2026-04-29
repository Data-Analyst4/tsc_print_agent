from __future__ import annotations

import datetime as dt
from typing import Any


def _parse_iso(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _heartbeat_epoch(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return _parse_iso(ts).timestamp()
    except Exception:
        return 0.0


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


def normalize_size_code(value: str | None) -> str | None:
    if value is None:
        return None
    out = value.strip().lower()
    return out or None


def resolve_required_size_code(job: dict[str, Any]) -> str | None:
    metadata = job.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("requested_size_code"):
            return normalize_size_code(str(metadata["requested_size_code"]))
        if metadata.get("requested_label_size"):
            return normalize_size_code(str(metadata["requested_label_size"]))

    profile = job.get("profile")
    if isinstance(profile, dict):
        profile_size = profile.get("size_code")
        if profile_size:
            return normalize_size_code(str(profile_size))
    return None


def _profile_matches_size(profile: dict[str, Any], required_size_code: str | None) -> bool:
    if not required_size_code:
        return True

    profile_size = normalize_size_code(str(profile.get("size_code") or ""))
    if profile_size:
        return profile_size == required_size_code

    width = profile.get("roll_width_mm")
    height = profile.get("roll_height_mm")
    if isinstance(width, int) and isinstance(height, int):
        normalized_pair = f"{int(round(width / 25.0))}x{int(round(height / 25.0))}"
        return normalized_pair == required_size_code
    return False


def pick_printer_profile_for_agent(
    *,
    job: dict[str, Any],
    agent: dict[str, Any],
    printer_profiles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    required_size_code = resolve_required_size_code(job)
    target_printer = str(job.get("target_printer") or "").strip() or None

    candidates = [p for p in printer_profiles if p.get("enabled", True)]
    if target_printer:
        candidates = [p for p in candidates if str(p.get("printer_name", "")).strip() == target_printer]

    if not candidates:
        # Backward compatibility: when there is no profile row yet, allow plain printer name matching.
        if target_printer and target_printer in agent.get("printers", []):
            return {"printer_name": target_printer, "size_code": None}
        if not target_printer and agent.get("printers"):
            return {"printer_name": agent.get("printers")[0], "size_code": None}
        return None

    sized = [p for p in candidates if _profile_matches_size(p, required_size_code)]
    if not sized:
        return None

    # Prefer exact target printer, then profile with explicit size_code.
    sized.sort(key=lambda p: (0 if p.get("size_code") else 1, str(p.get("printer_name", ""))))
    return sized[0]


def pick_agent_printer_for_job(
    *,
    job: dict[str, Any],
    agents: list[dict[str, Any]],
    printer_profiles: list[dict[str, Any]],
    fallback_order: list[str] | None = None,
    max_age_seconds: int = 45,
) -> dict[str, Any] | None:
    profiles_by_agent: dict[str, list[dict[str, Any]]] = {}
    for profile in printer_profiles:
        agent_id = str(profile.get("agent_id", "")).strip()
        if not agent_id:
            continue
        profiles_by_agent.setdefault(agent_id, []).append(profile)

    requested_workstation = None
    metadata = job.get("metadata") or {}
    if isinstance(metadata, dict):
        requested_workstation = metadata.get("requested_workstation_id")
    requested_workstation = str(requested_workstation or "").strip() or None
    fallback_rank = {wid: idx for idx, wid in enumerate(fallback_order or [], start=1)}

    candidates: list[dict[str, Any]] = []
    for agent in agents:
        if not is_agent_online(agent, max_age_seconds=max_age_seconds):
            continue
        if not agent_matches_job(job, agent):
            continue

        profile = pick_printer_profile_for_agent(
            job=job,
            agent=agent,
            printer_profiles=profiles_by_agent.get(agent["agent_id"], []),
        )
        if not profile:
            continue

        workstation_id = str(agent.get("workstation_id") or "").strip() or None
        if requested_workstation:
            if workstation_id == requested_workstation:
                priority = 0
            elif workstation_id and workstation_id in fallback_rank:
                priority = 10 + fallback_rank[workstation_id]
            else:
                priority = 1000
        else:
            priority = 50

        candidates.append(
            {
                "agent": agent,
                "printer_profile": profile,
                "priority": priority,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda c: (
            int(c["priority"]),
            0 if c["printer_profile"].get("size_code") else 1,
            -_heartbeat_epoch(c["agent"].get("heartbeat_at")),
        ),
        reverse=False,
    )
    return candidates[0]


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
