from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from .helpers import from_json, to_json, utc_now_iso
from .states import STATUS_ASSIGNED, STATUS_FAILED, STATUS_QUEUED, VALID_STATUS_TRANSITIONS


class PrintDB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    template_version INTEGER NOT NULL,
                    copies INTEGER NOT NULL,
                    target_agent_id TEXT,
                    target_group TEXT,
                    target_printer TEXT,
                    status TEXT NOT NULL,
                    assigned_agent_id TEXT,
                    profile_json TEXT NOT NULL,
                    metadata_json TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    output_pdf_path TEXT,
                    output_tspl_path TEXT
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    message TEXT,
                    details_json TEXT
                );

                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workstation_id TEXT,
                    groups_json TEXT NOT NULL,
                    printers_json TEXT NOT NULL,
                    templates_json TEXT NOT NULL,
                    host TEXT,
                    version TEXT,
                    heartbeat_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workstations (
                    workstation_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    location_tag TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workstation_fallbacks (
                    workstation_id TEXT NOT NULL,
                    fallback_workstation_id TEXT NOT NULL,
                    rank INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(workstation_id,fallback_workstation_id)
                );

                CREATE TABLE IF NOT EXISTS agent_printer_profiles (
                    agent_id TEXT NOT NULL,
                    printer_name TEXT NOT NULL,
                    roll_width_mm INTEGER,
                    roll_height_mm INTEGER,
                    size_code TEXT,
                    notes TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(agent_id, printer_name)
                );
                """
            )
            self._ensure_schema_evolution()
            self._create_indexes()
            self._conn.commit()

    def _ensure_schema_evolution(self) -> None:
        self._add_column_if_missing("agents", "workstation_id", "TEXT")
        self._add_column_if_missing("agent_printer_profiles", "enabled", "INTEGER NOT NULL DEFAULT 1")

    def _add_column_if_missing(self, table: str, column: str, spec: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row["name"] for row in rows}
        if column in columns:
            return
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def _create_indexes(self) -> None:
        self._create_index_if_columns_exist("idx_jobs_status_created_at", "jobs", ["status", "created_at"])
        self._create_index_if_columns_exist("idx_events_job_id", "job_events", ["job_id"])
        self._create_index_if_columns_exist("idx_printer_profiles_agent_id", "agent_printer_profiles", ["agent_id"])
        self._create_index_if_columns_exist("idx_agents_workstation_id", "agents", ["workstation_id"])
        self._create_index_if_columns_exist("idx_fallbacks_ws_rank", "workstation_fallbacks", ["workstation_id", "rank"])

    def _create_index_if_columns_exist(self, index: str, table: str, columns: list[str]) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        available = {row["name"] for row in rows}
        if not all(col in available for col in columns):
            return
        cols = ",".join(columns)
        self._conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table}({cols})")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create_job(
        self,
        *,
        job_id: str,
        idempotency_key: str | None,
        source_type: str,
        source_value: str,
        template_id: str,
        template_version: int,
        copies: int,
        target_agent_id: str | None,
        target_group: str | None,
        target_printer: str | None,
        profile: dict[str, Any],
        metadata: dict[str, Any],
        max_retries: int,
    ) -> tuple[dict[str, Any], bool]:
        now = utc_now_iso()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id,idempotency_key,source_type,source_value,template_id,template_version,
                        copies,target_agent_id,target_group,target_printer,status,assigned_agent_id,
                        profile_json,metadata_json,retry_count,max_retries,error_message,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        idempotency_key,
                        source_type,
                        source_value,
                        template_id,
                        template_version,
                        copies,
                        target_agent_id,
                        target_group,
                        target_printer,
                        STATUS_QUEUED,
                        None,
                        to_json(profile),
                        to_json(metadata),
                        0,
                        max_retries,
                        None,
                        now,
                        now,
                    ),
                )
                self._conn.execute(
                    """
                    INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (job_id, now, None, STATUS_QUEUED, "Job queued", None),
                )
                self._conn.commit()
                row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                return self._job_row_to_dict(row), True
            except sqlite3.IntegrityError:
                if not idempotency_key:
                    raise
                row = self._conn.execute(
                    "SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
                if not row:
                    raise
                return self._job_row_to_dict(row), False

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        return self._job_row_to_dict(row)

    def list_jobs(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        args: tuple[Any, ...]
        if status:
            query += " WHERE status=?"
            args = (status, limit)
            query += " ORDER BY created_at DESC LIMIT ?"
        else:
            query += " ORDER BY created_at DESC LIMIT ?"
            args = (limit,)
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
        return [self._job_row_to_dict(row) for row in rows]

    def get_job_events(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id,job_id,at,from_status,to_status,message,details_json
                FROM job_events
                WHERE job_id=?
                ORDER BY event_id ASC
                """,
                (job_id,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "job_id": row["job_id"],
                "at": row["at"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "message": row["message"],
                "details": from_json(row["details_json"], None),
            }
            for row in rows
        ]

    def upsert_agent(
        self,
        *,
        agent_id: str,
        name: str,
        workstation_id: str | None,
        groups: list[str],
        printers: list[str],
        templates: list[str],
        host: str | None,
        version: str | None,
        status: str = "ONLINE",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO agents(agent_id,name,workstation_id,groups_json,printers_json,templates_json,host,version,heartbeat_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name=excluded.name,
                    workstation_id=excluded.workstation_id,
                    groups_json=excluded.groups_json,
                    printers_json=excluded.printers_json,
                    templates_json=excluded.templates_json,
                    host=excluded.host,
                    version=excluded.version,
                    heartbeat_at=excluded.heartbeat_at,
                    status=excluded.status
                """,
                (
                    agent_id,
                    name,
                    workstation_id,
                    to_json(groups),
                    to_json(printers),
                    to_json(templates),
                    host,
                    version,
                    now,
                    status,
                ),
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        return self._agent_row_to_dict(row)

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if not row:
            return None
        return self._agent_row_to_dict(row)

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM agents ORDER BY heartbeat_at DESC").fetchall()
        return [self._agent_row_to_dict(row) for row in rows]

    def upsert_workstation(
        self,
        *,
        workstation_id: str,
        name: str,
        location_tag: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workstations(workstation_id,name,location_tag,enabled,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(workstation_id) DO UPDATE SET
                    name=excluded.name,
                    location_tag=excluded.location_tag,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (workstation_id, name, location_tag, 1 if enabled else 0, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                """
                SELECT workstation_id,name,location_tag,enabled,updated_at
                FROM workstations
                WHERE workstation_id=?
                """,
                (workstation_id,),
            ).fetchone()
        return self._workstation_row_to_dict(row)

    def list_workstations(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT workstation_id,name,location_tag,enabled,updated_at
                FROM workstations
                ORDER BY workstation_id ASC
                """
            ).fetchall()
        return [self._workstation_row_to_dict(row) for row in rows]

    def delete_workstation(self, workstation_id: str) -> bool:
        with self._lock:
            self._conn.execute(
                "DELETE FROM workstation_fallbacks WHERE workstation_id=? OR fallback_workstation_id=?",
                (workstation_id, workstation_id),
            )
            cur = self._conn.execute("DELETE FROM workstations WHERE workstation_id=?", (workstation_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def set_workstation_fallbacks(self, *, workstation_id: str, fallback_workstation_ids: list[str]) -> list[dict[str, Any]]:
        now = utc_now_iso()
        clean_ids: list[str] = []
        seen: set[str] = set()
        for wid in fallback_workstation_ids:
            normalized = wid.strip()
            if not normalized or normalized == workstation_id or normalized in seen:
                continue
            seen.add(normalized)
            clean_ids.append(normalized)

        with self._lock:
            self._conn.execute("DELETE FROM workstation_fallbacks WHERE workstation_id=?", (workstation_id,))
            for idx, fallback_id in enumerate(clean_ids, start=1):
                self._conn.execute(
                    """
                    INSERT INTO workstation_fallbacks(workstation_id,fallback_workstation_id,rank,updated_at)
                    VALUES(?,?,?,?)
                    """,
                    (workstation_id, fallback_id, idx, now),
                )
            self._conn.commit()

        return self.list_workstation_fallbacks(workstation_id=workstation_id)

    def list_workstation_fallbacks(self, *, workstation_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if workstation_id:
                rows = self._conn.execute(
                    """
                    SELECT workstation_id,fallback_workstation_id,rank,updated_at
                    FROM workstation_fallbacks
                    WHERE workstation_id=?
                    ORDER BY rank ASC
                    """,
                    (workstation_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT workstation_id,fallback_workstation_id,rank,updated_at
                    FROM workstation_fallbacks
                    ORDER BY workstation_id ASC, rank ASC
                    """
                ).fetchall()
        return [self._workstation_fallback_row_to_dict(row) for row in rows]

    def get_workstation_fallback_order(self, workstation_id: str) -> list[str]:
        rows = self.list_workstation_fallbacks(workstation_id=workstation_id)
        return [row["fallback_workstation_id"] for row in rows]

    def upsert_agent_printer_profile(
        self,
        *,
        agent_id: str,
        printer_name: str,
        roll_width_mm: int | None = None,
        roll_height_mm: int | None = None,
        size_code: str | None = None,
        notes: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        normalized_size = (size_code or "").strip().lower() or None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO agent_printer_profiles(
                    agent_id,printer_name,roll_width_mm,roll_height_mm,size_code,notes,enabled,updated_at
                )
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(agent_id,printer_name) DO UPDATE SET
                    roll_width_mm=excluded.roll_width_mm,
                    roll_height_mm=excluded.roll_height_mm,
                    size_code=excluded.size_code,
                    notes=excluded.notes,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    agent_id,
                    printer_name,
                    roll_width_mm,
                    roll_height_mm,
                    normalized_size,
                    notes,
                    1 if enabled else 0,
                    now,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                """
                SELECT agent_id,printer_name,roll_width_mm,roll_height_mm,size_code,notes,enabled,updated_at
                FROM agent_printer_profiles
                WHERE agent_id=? AND printer_name=?
                """,
                (agent_id, printer_name),
            ).fetchone()
        return self._agent_printer_profile_row_to_dict(row)

    def list_agent_printer_profiles(self, *, agent_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if agent_id:
                rows = self._conn.execute(
                    """
                    SELECT agent_id,printer_name,roll_width_mm,roll_height_mm,size_code,notes,enabled,updated_at
                    FROM agent_printer_profiles
                    WHERE agent_id=?
                    ORDER BY printer_name ASC
                    """,
                    (agent_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT agent_id,printer_name,roll_width_mm,roll_height_mm,size_code,notes,enabled,updated_at
                    FROM agent_printer_profiles
                    ORDER BY agent_id ASC, printer_name ASC
                    """
                ).fetchall()
        return [self._agent_printer_profile_row_to_dict(row) for row in rows]

    def delete_agent_printer_profile(self, *, agent_id: str, printer_name: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM agent_printer_profiles WHERE agent_id=? AND printer_name=?",
                (agent_id, printer_name),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list_candidate_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN (?,?)
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (STATUS_QUEUED, STATUS_ASSIGNED, limit),
            ).fetchall()
        return [self._job_row_to_dict(row) for row in rows]

    def assign_job(self, job_id: str, agent_id: str) -> bool:
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute("SELECT status,assigned_agent_id FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return False
            status = row["status"]
            current_agent = row["assigned_agent_id"]
            if status == STATUS_ASSIGNED and current_agent == agent_id:
                return True
            if status != STATUS_QUEUED:
                return False
            self._conn.execute(
                "UPDATE jobs SET status=?,assigned_agent_id=?,updated_at=? WHERE job_id=?",
                (STATUS_ASSIGNED, agent_id, now, job_id),
            )
            self._conn.execute(
                """
                INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                VALUES(?,?,?,?,?,?)
                """,
                (job_id, now, STATUS_QUEUED, STATUS_ASSIGNED, "Assigned to agent", to_json({"agent_id": agent_id})),
            )
            self._conn.commit()
        return True

    def release_assigned_job(self, job_id: str, reason: str) -> bool:
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute(
                "SELECT status,assigned_agent_id FROM jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if not row:
                return False
            if row["status"] != STATUS_ASSIGNED:
                return False
            assigned_agent = row["assigned_agent_id"]
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?,assigned_agent_id=NULL,updated_at=?
                WHERE job_id=?
                """,
                (STATUS_QUEUED, now, job_id),
            )
            self._conn.execute(
                """
                INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    job_id,
                    now,
                    STATUS_ASSIGNED,
                    STATUS_QUEUED,
                    "Released stale assignment",
                    to_json({"reason": reason, "previous_agent_id": assigned_agent}),
                ),
            )
            self._conn.commit()
        return True

    def set_job_status(
        self,
        *,
        job_id: str,
        new_status: str,
        message: str = "",
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
        allow_any_transition: bool = False,
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            current = row["status"]
            if not allow_any_transition:
                allowed = VALID_STATUS_TRANSITIONS.get(current, set())
                if new_status not in allowed and new_status != current:
                    raise ValueError(f"invalid transition {current} -> {new_status}")

            if new_status == current:
                self._conn.execute("UPDATE jobs SET updated_at=? WHERE job_id=?", (now, job_id))
                self._conn.commit()
                out = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                return self._job_row_to_dict(out)

            self._conn.execute(
                """
                UPDATE jobs
                SET status=?,error_message=?,updated_at=?
                WHERE job_id=?
                """,
                (new_status, error_message, now, job_id),
            )
            self._conn.execute(
                """
                INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                VALUES(?,?,?,?,?,?)
                """,
                (job_id, now, current, new_status, message, to_json(details) if details else None),
            )
            self._conn.commit()
            out = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return self._job_row_to_dict(out)

    def increment_retry(self, job_id: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute("UPDATE jobs SET retry_count=retry_count+1,updated_at=? WHERE job_id=?", (now, job_id))
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        return self._job_row_to_dict(row)

    def requeue_if_retryable(self, job_id: str, message: str, error_message: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            retry_count = int(row["retry_count"])
            max_retries = int(row["max_retries"])
            current_status = row["status"]
            if retry_count >= max_retries:
                self._conn.execute(
                    "UPDATE jobs SET status=?,error_message=?,updated_at=? WHERE job_id=?",
                    (STATUS_FAILED, error_message, now, job_id),
                )
                self._conn.execute(
                    """
                    INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        now,
                        current_status,
                        STATUS_FAILED,
                        message,
                        to_json({"retry_count": retry_count, "max_retries": max_retries}),
                    ),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE jobs
                    SET status=?,error_message=?,updated_at=?,assigned_agent_id=NULL
                    WHERE job_id=?
                    """,
                    (STATUS_QUEUED, error_message, now, job_id),
                )
                self._conn.execute(
                    """
                    INSERT INTO job_events(job_id,at,from_status,to_status,message,details_json)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        now,
                        current_status,
                        STATUS_QUEUED,
                        message,
                        to_json({"retry_count": retry_count, "max_retries": max_retries}),
                    ),
                )
            self._conn.commit()
            out = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job_row_to_dict(out)

    def set_job_artifacts(self, job_id: str, pdf_path: str | None, tspl_path: str | None) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET output_pdf_path=?,output_tspl_path=?,updated_at=?
                WHERE job_id=?
                """,
                (pdf_path, tspl_path, now, job_id),
            )
            self._conn.commit()

    def set_job_target_printer(self, job_id: str, printer_name: str | None) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                UPDATE jobs
                SET target_printer=?,updated_at=?
                WHERE job_id=?
                """,
                (printer_name, now, job_id),
            )
            self._conn.commit()

    def _job_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "idempotency_key": row["idempotency_key"],
            "source_type": row["source_type"],
            "source_value": row["source_value"],
            "template_id": row["template_id"],
            "template_version": row["template_version"],
            "copies": row["copies"],
            "target_agent_id": row["target_agent_id"],
            "target_group": row["target_group"],
            "target_printer": row["target_printer"],
            "status": row["status"],
            "assigned_agent_id": row["assigned_agent_id"],
            "profile": from_json(row["profile_json"], {}),
            "metadata": from_json(row["metadata_json"], {}),
            "retry_count": row["retry_count"],
            "max_retries": row["max_retries"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "output_pdf_path": row["output_pdf_path"],
            "output_tspl_path": row["output_tspl_path"],
        }

    def _agent_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "agent_id": row["agent_id"],
            "name": row["name"],
            "workstation_id": row["workstation_id"],
            "groups": from_json(row["groups_json"], []),
            "printers": from_json(row["printers_json"], []),
            "templates": from_json(row["templates_json"], []),
            "host": row["host"],
            "version": row["version"],
            "heartbeat_at": row["heartbeat_at"],
            "status": row["status"],
        }

    def _workstation_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "workstation_id": row["workstation_id"],
            "name": row["name"],
            "location_tag": row["location_tag"],
            "enabled": bool(row["enabled"]),
            "updated_at": row["updated_at"],
        }

    def _workstation_fallback_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "workstation_id": row["workstation_id"],
            "fallback_workstation_id": row["fallback_workstation_id"],
            "rank": row["rank"],
            "updated_at": row["updated_at"],
        }

    def _agent_printer_profile_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        enabled_raw = row["enabled"]
        return {
            "agent_id": row["agent_id"],
            "printer_name": row["printer_name"],
            "roll_width_mm": row["roll_width_mm"],
            "roll_height_mm": row["roll_height_mm"],
            "size_code": row["size_code"],
            "notes": row["notes"],
            "enabled": bool(1 if enabled_raw is None else enabled_raw),
            "updated_at": row["updated_at"],
        }
