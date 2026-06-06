from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import Settings


PRIORITY_MAP = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

PHOENIX_STATUS_TO_UI = {
    "OPEN": "Open",
    "PENDING": "Troubleshooting",
    "DONE": "Fixed",
}

UI_STATUS_TO_PHOENIX = {
    "Open": "OPEN",
    "Analyzing": "PENDING",
    "Troubleshooting": "PENDING",
    "Validating": "PENDING",
    "Fixed": "DONE",
}


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is required")
        key = settings.supabase_service_role_key or settings.supabase_publishable_key
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_PUBLISHABLE_KEY is required")
        self.client: Client = create_client(settings.supabase_url, key)

    def _maybe_one(self, query) -> dict[str, Any] | None:
        resp = query.limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None

    def get_ticket_by_code(self, ticket_code: str) -> dict[str, Any] | None:
        return self._maybe_one(self.client.table("tickets").select("*").eq("ticket_code", ticket_code))

    def get_ticket(self, ticket_uuid: str) -> dict[str, Any] | None:
        return self._maybe_one(self.client.table("tickets").select("*").eq("id", ticket_uuid))

    def list_commands(self, ticket_uuid: str) -> list[dict[str, Any]]:
        resp = (
            self.client.table("ai_commands")
            .select("*")
            .eq("ticket_id", ticket_uuid)
            .order("created_at")
            .execute()
        )
        return resp.data or []

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        return self._maybe_one(self.client.table("ai_commands").select("*").eq("id", command_id))

    def get_system_info(self, ticket_uuid: str) -> dict[str, Any] | None:
        return self._maybe_one(
            self.client.table("system_info")
            .select("*")
            .eq("ticket_id", ticket_uuid)
            .order("created_at", desc=True)
        )

    def list_tickets(self) -> list[dict[str, Any]]:
        resp = self.client.table("tickets").select("*").order("created_at", desc=True).execute()
        return resp.data or []

    def delete_tickets_not_in_codes(self, codes: set[str]) -> int:
        removed = 0
        for row in self.list_tickets():
            if row.get("ticket_code") not in codes:
                self.client.table("tickets").delete().eq("id", row["id"]).execute()
                removed += 1
        return removed

    def upsert_ticket_from_phoenix(self, phoenix_ticket: dict[str, Any]) -> dict[str, Any]:
        code = str(phoenix_ticket["id"])
        priority_raw = (phoenix_ticket.get("priority") or "medium").lower()
        priority = PRIORITY_MAP.get(priority_raw, priority_raw.title())
        phoenix_status = PHOENIX_STATUS_TO_UI.get(phoenix_ticket.get("status", "OPEN"), "Open")

        payload: dict[str, Any] = {
            "ticket_code": code,
            "title": phoenix_ticket.get("title", f"Ticket {code}"),
            "customer_name": phoenix_ticket.get("customer_name", "Unknown"),
            "priority": priority,
            "report_text": phoenix_ticket.get("description", ""),
        }

        existing = self.get_ticket_by_code(code)
        if existing:
            # Refresh ERP metadata but keep in-progress local workflow state.
            if existing.get("status") in ("Open", "Fixed"):
                payload["status"] = phoenix_status
            resp = self.client.table("tickets").update(payload).eq("id", existing["id"]).execute()
            row = resp.data[0] if resp.data else existing
        else:
            payload["status"] = phoenix_status
            payload["active_agent"] = "Problem Analyzer"
            resp = self.client.table("tickets").insert(payload).execute()
            row = resp.data[0]

        return row

    def upsert_system_info(self, ticket_uuid: str, system: dict[str, Any], connection_status: str = "Idle") -> dict[str, Any]:
        payload = {
            "ticket_id": ticket_uuid,
            "host_ip": system.get("ip", ""),
            "username": system.get("username", "azureuser"),
            "port": system.get("port", 22),
            "os_version": system.get("os", "Ubuntu"),
            "connection_status": connection_status,
        }
        notes = system.get("notes", "")
        if notes:
            payload["system_notes"] = notes

        existing = self.get_system_info(ticket_uuid)
        try:
            if existing:
                resp = self.client.table("system_info").update(payload).eq("id", existing["id"]).execute()
                return resp.data[0] if resp.data else existing
            resp = self.client.table("system_info").insert(payload).execute()
            return resp.data[0]
        except Exception as exc:
            if "system_notes" not in str(exc):
                raise
            payload.pop("system_notes", None)
            if existing:
                resp = self.client.table("system_info").update(payload).eq("id", existing["id"]).execute()
                return resp.data[0] if resp.data else existing
            resp = self.client.table("system_info").insert(payload).execute()
            return resp.data[0]

    def update_ticket(self, ticket_uuid: str, **fields: Any) -> None:
        self.client.table("tickets").update(fields).eq("id", ticket_uuid).execute()

    def insert_command(self, ticket_uuid: str, **fields: Any) -> dict[str, Any]:
        payload = {"ticket_id": ticket_uuid, **fields}
        resp = self.client.table("ai_commands").insert(payload).execute()
        return resp.data[0]

    def update_command(self, command_id: str, **fields: Any) -> dict[str, Any]:
        resp = self.client.table("ai_commands").update(fields).eq("id", command_id).execute()
        return resp.data[0]

    def upsert_activity(self, ticket_uuid: str, **fields: Any) -> None:
        payload = {"ticket_id": ticket_uuid, **fields}
        self.client.table("activities").upsert(payload, on_conflict="ticket_id").execute()

    def get_activity(self, ticket_uuid: str) -> dict[str, Any] | None:
        return self._maybe_one(self.client.table("activities").select("*").eq("ticket_id", ticket_uuid))

    def reset_workspace(self) -> None:
        self.client.table("ai_commands").update({"human_status": "Pending", "output_logs": ""}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        self.client.table("tickets").update({"status": "Open", "active_agent": "Problem Analyzer"}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        self.client.table("activities").update({"submitted_to_erp": False}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        self.client.table("system_info").update({"connection_status": "Idle"}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()

    def clear_ticket_run(self, ticket_uuid: str) -> None:
        self.client.table("ai_commands").delete().eq("ticket_id", ticket_uuid).execute()
        self.client.table("activities").delete().eq("ticket_id", ticket_uuid).execute()
