"""Generate ranked troubleshooting hypotheses (multiple solution paths)."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.llm_schemas import HypothesisItem, HypothesisList
from app.agent.azure_agent import AzureOpenAIAgent
from app.agent.gemini_agent import GeminiAgentService
from app.config import Settings
from app.safety.layer import SafetyLayer

logger = logging.getLogger(__name__)

HYPOTHESIS_PROMPT = """Given this IT incident ticket, propose 2–3 DISTINCT ranked hypotheses for the root cause.
Each hypothesis is a different solution path the technician could pursue.

Ticket title: {title}
Customer report: {report}
Priority: {priority}
{system_block}

Return JSON: {{"hypotheses": [
  {{"title": "short tab label", "summary": "...", "likely_root_cause": "...",
    "confidence": "high|medium|low", "first_command": "safe read-only shell cmd",
    "fix_strategy": "what we'd do if this hypothesis is correct"}}
]}}

Rules:
- Hypotheses must be meaningfully different (not rewordings)
- first_command must be safe diagnostics (no destructive ops)
- Prefer hypotheses grounded in the customer symptom
- Include at least one service/config hypothesis and one resource/permission hypothesis when plausible"""


def _fallback_hypotheses(ticket: dict[str, Any]) -> list[dict[str, Any]]:
    report = (ticket.get("report_text") or "").lower()
    items: list[dict[str, Any]] = []

    if any(k in report for k in ("502", "8080", "http", "api", "down", "unavailable")):
        items.append(
            {
                "title": "Service down",
                "summary": "The application service may be stopped or not listening on the expected port.",
                "likely_root_cause": "Systemd unit failed or not enabled after reboot.",
                "confidence": "high",
                "first_command": "systemctl --failed --no-pager",
                "fix_strategy": "Identify failed unit, inspect logs, restart/reload service.",
            }
        )
        items.append(
            {
                "title": "Misconfiguration",
                "summary": "Service runs but proxy/port/config points to wrong upstream.",
                "likely_root_cause": "Config drift or bad reload after change.",
                "confidence": "medium",
                "first_command": "ss -tlnp | head -30",
                "fix_strategy": "Validate config files and nginx/app bindings.",
            }
        )

    if any(k in report for k in ("permission", "upload", "denied", "chmod")):
        items.append(
            {
                "title": "Permissions",
                "summary": "Filesystem permissions may block the application write path.",
                "likely_root_cause": "Wrong owner/mode on upload or data directory.",
                "confidence": "high",
                "first_command": "namei -l /var/www 2>/dev/null || ls -la /var/www",
                "fix_strategy": "Targeted chown/chmod on specific directory only.",
            }
        )

    if any(k in report for k in ("database", "postgres", "order", "sync", "partner")):
        items.append(
            {
                "title": "Database / connectivity",
                "summary": "Database or upstream dependency unreachable or rejecting connections.",
                "likely_root_cause": "Service down, wrong credentials, or network/DNS issue.",
                "confidence": "medium",
                "first_command": "systemctl status postgresql 2>/dev/null || systemctl --failed --no-pager",
                "fix_strategy": "Restore DB service or fix connection string/firewall.",
            }
        )

    if len(items) < 2:
        items.extend(
            [
                {
                    "title": "Failed service",
                    "summary": "A systemd service required by the app may have failed.",
                    "likely_root_cause": "Unit crash loop or dependency failure.",
                    "confidence": "medium",
                    "first_command": "systemctl --failed --no-pager",
                    "fix_strategy": "Inspect journalctl, restart affected service.",
                },
                {
                    "title": "Resource exhaustion",
                    "summary": "Disk or memory pressure may prevent normal operation.",
                    "likely_root_cause": "Full disk or OOM killing processes.",
                    "confidence": "low",
                    "first_command": "df -h && free -m",
                    "fix_strategy": "Free safe space or raise limits, then restart service.",
                },
            ]
        )

    return items[:3]


class HypothesisGenerator:
    def __init__(self, settings: Settings, safety: SafetyLayer | None = None):
        self.settings = settings
        self.safety = safety or SafetyLayer()
        self.azure = AzureOpenAIAgent(settings, safety)
        self.gemini = GeminiAgentService(settings, safety)

    def generate(
        self,
        ticket: dict[str, Any],
        system_info: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        system_block = ""
        if system_info:
            system_block = (
                f"Target: {system_info.get('host_ip')}:{system_info.get('port', 22)} "
                f"({system_info.get('os_version', 'Linux')})"
            )

        prompt = HYPOTHESIS_PROMPT.format(
            title=ticket.get("title", ""),
            report=ticket.get("report_text", "")[:3000],
            priority=ticket.get("priority", "Medium"),
            system_block=system_block,
        )

        primary = (self.settings.llm_primary or "gemini").lower()
        if primary == "gemini" and self.gemini.enabled:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.settings.gemini_api_key)
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        response_json_schema=HypothesisList.model_json_schema(),
                    ),
                )
                items = HypothesisList.model_validate(json.loads(response.text or "{}")).hypotheses
                return [self._sanitize_item(h) for h in items]
            except Exception as exc:
                logger.warning("Gemini hypothesis generation failed: %s", exc)

        if self.azure.enabled:
            try:
                data = self.azure._chat_json(
                    "You are an expert Linux SRE proposing distinct diagnostic hypotheses.",
                    prompt,
                    HypothesisList,
                )
                items = HypothesisList.model_validate(data).hypotheses
                return [self._sanitize_item(h) for h in items]
            except Exception as exc:
                logger.warning("Azure hypothesis generation failed: %s", exc)

        if primary != "gemini" and self.gemini.enabled:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.settings.gemini_api_key)
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        response_json_schema=HypothesisList.model_json_schema(),
                    ),
                )
                items = HypothesisList.model_validate(json.loads(response.text or "{}")).hypotheses
                return [self._sanitize_item(h) for h in items]
            except Exception as exc:
                logger.warning("Gemini hypothesis generation failed: %s", exc)

        return _fallback_hypotheses(ticket)

    def _sanitize_item(self, item: HypothesisItem) -> dict[str, Any]:
        safety = self.safety.evaluate(item.first_command)
        data = item.model_dump()
        data["safety_status"] = safety.status
        return data
