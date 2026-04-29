#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from print_automation.server import ServerSettings, run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run central print automation server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8089, help="Bind port")
    parser.add_argument("--db", default="./print_automation.db", help="SQLite DB path")
    parser.add_argument("--templates", default="./config/templates.json", help="Template config path")
    parser.add_argument("--auth-token", default="change-me-token", help="Shared API auth token")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    settings = ServerSettings(
        host=args.host,
        port=args.port,
        db_path=Path(args.db).resolve(),
        templates_path=Path(args.templates).resolve(),
        auth_token=args.auth_token,
    )
    run_server(settings)


if __name__ == "__main__":
    main()
