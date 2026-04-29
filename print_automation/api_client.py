from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class ApiClientError(RuntimeError):
    pass


class PrintApiClient:
    def __init__(self, base_url: str, auth_token: str, timeout_seconds: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url=url, method=method)
            req.add_header("Content-Type", "application/json")
            req.add_header("X-Auth-Token", self.auth_token)
            try:
                with urllib.request.urlopen(req, data=body, timeout=self.timeout_seconds) as resp:
                    raw = resp.read()
                    if resp.status >= 400:
                        raise ApiClientError(f"{method} {path} failed with HTTP {resp.status}")
                    if not raw:
                        return {}
                    return json.loads(raw.decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
                if attempt >= retries:
                    break
                time.sleep(min(2 ** (attempt - 1), 5))
        raise ApiClientError(f"{method} {path} failed after {retries} tries: {last_err}")

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/v1/agents/heartbeat", payload=payload)

    def claim_next_job(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/v1/agents/{agent_id}/claim-next", payload={})

    def set_job_status(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", f"/v1/jobs/{job_id}/status", payload=payload)

