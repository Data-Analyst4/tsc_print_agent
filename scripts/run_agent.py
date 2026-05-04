#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from print_automation.agent import PrintAgent
from print_automation.config import load_agent_runtime_config
from print_automation.version import APP_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local print agent.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--config", default="./config/agent.local.json", help="Agent config JSON path")
    parser.add_argument("--templates", default="./config/templates.json", help="Template config JSON path")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    config = load_agent_runtime_config(Path(args.config).resolve())
    agent = PrintAgent(config=config, templates_path=Path(args.templates).resolve())
    agent.run_forever()


if __name__ == "__main__":
    main()
