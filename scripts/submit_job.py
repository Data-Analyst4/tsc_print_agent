#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a print job to print automation server.")
    parser.add_argument("--server", default="http://127.0.0.1:8089", help="Server base URL")
    parser.add_argument("--auth-token", default="change-me-token", help="Auth token")
    parser.add_argument("--template", help="Template ID, ex: label_4x3")
    parser.add_argument("--label-size", help="Label size code, ex: 4x3 or 4x6")
    parser.add_argument("--copies", type=int, default=1, help="Number of copies")
    parser.add_argument("--pdf-path", help="Local/UNC path to PDF")
    parser.add_argument("--pdf-url", help="HTTP URL to PDF")
    parser.add_argument("--group", help="Target group")
    parser.add_argument("--workstation", help="Preferred workstation ID")
    parser.add_argument("--agent", help="Target specific agent ID")
    parser.add_argument("--printer", help="Target specific printer name")
    parser.add_argument("--idempotency-key", help="Idempotency key")
    args = parser.parse_args()

    if not args.pdf_path and not args.pdf_url:
        raise SystemExit("Pass either --pdf-path or --pdf-url")
    if not args.template and not args.label_size:
        raise SystemExit("Pass either --template or --label-size")

    source = {"type": "path", "value": args.pdf_path} if args.pdf_path else {"type": "url", "value": args.pdf_url}
    payload: dict[str, object] = {
        "copies": args.copies,
        "source": source,
        "target": {
            "group": args.group,
            "workstation_id": args.workstation,
            "agent_id": args.agent,
            "printer": args.printer,
        },
        "idempotency_key": args.idempotency_key,
    }
    if args.template:
        payload["template_id"] = args.template
    if args.label_size:
        payload["label_size"] = args.label_size

    req = urllib.request.Request(
        url=args.server.rstrip("/") + "/v1/jobs",
        method="POST",
        headers={"Content-Type": "application/json", "X-Auth-Token": args.auth_token},
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        print(resp.read().decode("utf-8"))


if __name__ == "__main__":
    main()
