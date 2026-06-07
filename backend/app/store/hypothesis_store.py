from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_GLOBAL_MEMORY: dict[str, dict[str, Any]] = {}


class HypothesisStore:
    """Persist hypothesis tabs and pipeline state per ticket."""

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
                payload = {
                    "hypotheses": row.get("hypotheses") or [],
                    "selected_index": row.get("selected_index", 0),
                    "reasoning_summary": row.get("reasoning_summary") or "",
                    "pipeline_state": row.get("pipeline_state") or {},
                }
                _GLOBAL_MEMORY[ticket_uuid] = payload
                return payload
        except Exception as exc:
            logger.debug("hypotheses table read failed (run migration?): %s", exc)
        return None

    def save(
        self,
        ticket_uuid: str,
        hypotheses: list[dict[str, Any]],
        selected_index: int = 0,
        reasoning_summary: str = "",
        pipeline_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.get(ticket_uuid) or {}
        state = pipeline_state if pipeline_state is not None else (current.get("pipeline_state") or {})
        payload = {
            "hypotheses": hypotheses,
            "selected_index": selected_index,
            "reasoning_summary": reasoning_summary,
            "pipeline_state": state,
        }
        _GLOBAL_MEMORY[ticket_uuid] = payload
        try:
            row: dict[str, Any] = {
                "ticket_id": ticket_uuid,
                "hypotheses": hypotheses,
                "selected_index": selected_index,
                "reasoning_summary": reasoning_summary or current.get("reasoning_summary") or "",
            }
            if state:
                row["pipeline_state"] = state
            self._store.client.table("ticket_hypotheses").upsert(
                row,
                on_conflict="ticket_id",
            ).execute()
        except Exception as exc:
            logger.debug("hypotheses table write failed: %s", exc)
            try:
                row.pop("pipeline_state", None)
                self._store.client.table("ticket_hypotheses").upsert(
                    row,
                    on_conflict="ticket_id",
                ).execute()
            except Exception:
                pass
        return payload

    def update_pipeline_state(self, ticket_uuid: str, **fields: Any) -> dict[str, Any]:
        current = self.get(ticket_uuid) or {
            "hypotheses": [],
            "selected_index": 0,
            "reasoning_summary": "",
            "pipeline_state": {},
        }
        state = dict(current.get("pipeline_state") or {})
        state.update(fields)
        return self.save(
            ticket_uuid,
            current.get("hypotheses") or [],
            current.get("selected_index", 0),
            current.get("reasoning_summary") or "",
            pipeline_state=state,
        )

    def select(self, ticket_uuid: str, index: int) -> dict[str, Any]:
        current = self.get(ticket_uuid) or {
            "hypotheses": [],
            "selected_index": 0,
            "reasoning_summary": "",
            "pipeline_state": {},
        }
        hypotheses = current.get("hypotheses") or []
        if hypotheses:
            index = max(0, min(index, len(hypotheses) - 1))
        return self.save(
            ticket_uuid,
            hypotheses,
            index,
            reasoning_summary=current.get("reasoning_summary") or "",
            pipeline_state=current.get("pipeline_state") or {},
        )
