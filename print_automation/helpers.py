import datetime as _dt
import json
import uuid
from typing import Any


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def to_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def from_json(data: str | None, default: Any) -> Any:
    if not data:
        return default
    return json.loads(data)

