from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config import Settings


class PhoenixError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PhoenixClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.phoenix_api_base_url.rstrip("/")
        self.token = settings.phoenix_api_token
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise PhoenixError("Phoenix API request timed out") from exc
        except httpx.RequestError as exc:
            raise PhoenixError(f"Phoenix API unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise PhoenixError("Phoenix API unauthorized — check PHOENIX_API_TOKEN", 401)
        if resp.status_code == 404:
            raise PhoenixError("Phoenix resource not found", 404)
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise PhoenixError(f"Phoenix API error {resp.status_code}: {detail}", resp.status_code)

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/me")

    def list_tickets(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        sort: str = "date",
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"sort": sort}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        return self._request("GET", "/api/v1/me/tickets", params=params)

    def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/tickets/{ticket_id}")

    def get_customer_system(self, ticket_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/tickets/{ticket_id}/customer-system")

    def set_ticket_status(self, ticket_id: int, status: str) -> dict[str, Any]:
        return self._request("PATCH", f"/api/v1/tickets/{ticket_id}/status", json={"status": status})

    def create_activity(
        self,
        *,
        ticket_id: int,
        start_datetime: datetime,
        end_datetime: datetime,
        summary: str,
        root_cause: str,
        actions_taken: str,
        commands_summary: str,
        validation_result: str,
    ) -> dict[str, Any]:
        payload = {
            "ticket_id": ticket_id,
            "start_datetime": start_datetime.isoformat().replace("+00:00", "Z"),
            "end_datetime": end_datetime.isoformat().replace("+00:00", "Z"),
            "summary": summary,
            "root_cause": root_cause,
            "actions_taken": actions_taken,
            "commands_summary": commands_summary,
            "validation_result": validation_result,
        }
        return self._request("POST", "/api/v1/activities/create", json=payload)

    def reset(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/me/reset")
