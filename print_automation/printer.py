from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class PrintError(RuntimeError):
    pass


def _print_to_file(printer_name: str, data: bytes) -> dict[str, Any]:
    output = printer_name.removeprefix("file:").strip()
    if not output:
        raise PrintError("file printer target is empty")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return {"job_id": None, "bytes_written": len(data), "status": "FILE_WRITTEN"}


def _print_windows_raw(printer_name: str, data: bytes, document_name: str, timeout_seconds: float) -> dict[str, Any]:
    import pywintypes  # type: ignore
    import win32print  # type: ignore

    error_mask = (
        win32print.JOB_STATUS_ERROR
        | win32print.JOB_STATUS_OFFLINE
        | win32print.JOB_STATUS_PAPEROUT
        | win32print.JOB_STATUS_BLOCKED_DEVQ
        | win32print.JOB_STATUS_USER_INTERVENTION
    )

    hprinter = win32print.OpenPrinter(printer_name)
    try:
        job_id = win32print.StartDocPrinter(hprinter, 1, (document_name, None, "RAW"))
        try:
            win32print.StartPagePrinter(hprinter)
            written = win32print.WritePrinter(hprinter, data)
            win32print.EndPagePrinter(hprinter)
        finally:
            win32print.EndDocPrinter(hprinter)

        deadline = time.time() + timeout_seconds
        last_status = 0
        while time.time() < deadline:
            try:
                job_info = win32print.GetJob(hprinter, job_id, 2)
                status = int(job_info.get("Status", 0))
                last_status = status
                if status & error_mask:
                    raise PrintError(f"spooler reported job error status={status}")
            except pywintypes.error:
                # Job no longer exists in queue; assume spooled successfully.
                return {"job_id": job_id, "bytes_written": written, "status": "SPOOLED"}
            time.sleep(0.3)

        raise PrintError(f"timed out waiting for spool job completion; last_status={last_status}")
    finally:
        win32print.ClosePrinter(hprinter)


def print_raw(
    *,
    printer_name: str,
    data: bytes,
    document_name: str,
    copies: int,
    timeout_seconds: float = 45.0,
) -> list[dict[str, Any]]:
    if copies < 1:
        raise PrintError("copies must be >= 1")

    results: list[dict[str, Any]] = []
    for copy_no in range(1, copies + 1):
        doc_name = f"{document_name} copy {copy_no}/{copies}" if copies > 1 else document_name
        if printer_name.lower().startswith("file:"):
            result = _print_to_file(printer_name, data)
        else:
            result = _print_windows_raw(printer_name, data, doc_name, timeout_seconds)
        result["copy"] = copy_no
        results.append(result)
    return results

