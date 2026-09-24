"""Lead persistence: CSV file and/or an HTTP webhook (e.g. Google Sheets).

The webhook sink POSTs the lead as JSON. Point it at a Google Apps Script
web app (see README) to land bookings directly in a Google Sheet.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .intake import CSV_HEADER, Lead


class CsvSink:
    """Append captured leads to a CSV file, writing the header once."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, lead: Lead) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = (
            not self.path.exists() or self.path.stat().st_size == 0
        )
        captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if needs_header:
                writer.writerow(CSV_HEADER)
            writer.writerow(lead.to_row(captured_at))
        return self.path


class WebhookSink:
    """POST captured leads as JSON to a webhook URL."""

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"webhook URL must be http(s): {url!r}")
        self.url = url
        self.timeout = timeout

    @staticmethod
    def build_payload(lead: Lead) -> dict[str, str]:
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "business": lead.business,
            "name": lead.name or "",
            "phone": lead.phone or "",
            "service": lead.service or "",
            "date": lead.date or "",
            "time": lead.time or "",
            "address": lead.address or "",
            "notes": lead.notes or "",
        }

    def save(self, lead: Lead) -> int:
        body = json.dumps(self.build_payload(lead)).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.status


class MultiSink:
    """Fan a lead out to several sinks; one failing sink does not block others."""

    def __init__(self, *sinks) -> None:
        self.sinks = list(sinks)
        self.errors: list[Exception] = []

    def save(self, lead: Lead) -> None:
        self.errors.clear()
        for sink in self.sinks:
            try:
                sink.save(lead)
            except Exception as exc:  # noqa: BLE001 - record and continue
                self.errors.append(exc)
