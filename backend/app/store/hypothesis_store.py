from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Shared across AgentOrchestrator instances (one per HTTP request).
_GLOBAL_MEMORY: dict[str, dict[str, Any]] = {}


class HypothesisStore:
    """Persist hypothesis tabs per ticket (Supabase with in-memory fallback)."""

    def __init__(self, store: Any):
        self._store = store

    @staticmethod
    def clear_all() -> None:
        _GLOBAL_MEMORY.clear()

    def get(self, ticket_uuid: str) -> dict[str, Any] | None:
        if ticket_uuid in _GLOBAL_MEMORY:
            return _GLOBAL_MEMORY[ticket_uuid]
        try:
            resp = (
                self._store.client.table("ticket_hypotheses")
                .select("*")
                .eq("ticket_id", ticket_uuid)
                .limit(1)
                .execute()
            )
            rows = resp.data or []
            if rows:
                row = rows[0]
                _GLOBAL_MEMORY[ticket_uuid] = {
                    "hypotheses": row.get("hypotheses") or [],
                    "selected_index": row.get("selected_index", 0),
                }
                return _GLOBAL_MEMORY[ticket_uuid]
        except Exception as exc:
            logger.debug("hypotheses table read failed (run migration?): %s", exc)
        return None

    def save(self, ticket_uuid: str, hypotheses: list[dict[str, Any]], selected_index: int = 0) -> dict[str, Any]:
        payload = {"hypotheses": hypotheses, "selected_index": selected_index}
        _GLOBAL_MEMORY[ticket_uuid] = payload
        try:
            self._store.client.table("ticket_hypotheses").upsert(
                {
                    "ticket_id": ticket_uuid,
                    "hypotheses": hypotheses,
                    "selected_index": selected_index,
                },
                on_conflict="ticket_id",
            ).execute()
        except Exception as exc:
            logger.debug("hypotheses table write failed: %s", exc)
        return payload

    def select(self, ticket_uuid: str, index: int) -> dict[str, Any]:
        current = self.get(ticket_uuid) or {"hypotheses": [], "selected_index": 0}
        hypotheses = current.get("hypotheses") or []
        if hypotheses:
            index = max(0, min(index, len(hypotheses) - 1))
        return self.save(ticket_uuid, hypotheses, index)
