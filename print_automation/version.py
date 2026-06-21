from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VERSION_FILE = _ROOT / "VERSION"

DEFAULT_VERSION = "0.0.0"


def read_version() -> str:
    try:
        value = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_VERSION
    return value or DEFAULT_VERSION


APP_VERSION = read_version()
