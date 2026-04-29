from __future__ import annotations

import hashlib
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path


class DownloadError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_pdf(path: Path) -> None:
    with path.open("rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        raise DownloadError(f"downloaded file is not a PDF: {path}")


def download_pdf(
    *,
    source_type: str,
    source_value: str,
    destination: Path,
    timeout_seconds: float,
    max_retries: int,
) -> tuple[Path, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if source_type == "path":
        src = Path(source_value)
        if not src.exists():
            raise DownloadError(f"source file not found: {src}")
        shutil.copyfile(src, destination)
        _ensure_pdf(destination)
        return destination, _sha256_file(destination)

    if source_type != "url":
        raise DownloadError(f"unsupported source_type: {source_type}")

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                source_value,
                headers={"User-Agent": "pdf2tspl-print-agent/1.0", "Accept": "application/pdf"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                if resp.status != 200:
                    raise DownloadError(f"unexpected HTTP status {resp.status}")
                data = resp.read()
            destination.write_bytes(data)
            _ensure_pdf(destination)
            return destination, _sha256_file(destination)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, DownloadError) as exc:
            last_err = exc
            if attempt >= max_retries:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    raise DownloadError(f"failed to download PDF after {max_retries} tries: {last_err}")

