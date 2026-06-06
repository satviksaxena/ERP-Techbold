from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("audit")


class AuditLog:
    """In-memory + file audit trail for every command and key action."""

    def __init__(self, log_path: str | None = None):
        self._entries: list[dict[str, Any]] = []
        self._path = Path(log_path) if log_path else None

    def record(self, action: str, **details: Any) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **details,
        }
        self._entries.append(entry)
        logger.info("AUDIT %s", json.dumps(entry, default=str))
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        return entry

    def list_entries(self, ticket_id: str | None = None) -> list[dict[str, Any]]:
        if not ticket_id:
            return list(self._entries)
        return [e for e in self._entries if e.get("ticket_id") == ticket_id]

    def clear(self) -> None:
        self._entries.clear()
