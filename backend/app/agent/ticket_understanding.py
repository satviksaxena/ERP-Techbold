"""Deep ticket understanding via Gemini thinking models (hypothesis generation only)."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agent.llm_schemas import HypothesisItem, HypothesisList
from app.config import Settings
from app.safety.layer import SafetyLayer

logger = logging.getLogger(__name__)

UNDERSTANDING_PROMPT = """You are the Problem Analyzer for an IT service desk autopilot.

Carefully reason about this incident before proposing solution paths. Consider:
- What the customer symptom implies vs what might actually be broken on the Linux VM
- Which subsystems are involved (systemd, nginx, filesystem, database, network)
- What safe read-only diagnostics would disambiguate each theory

Ticket title: {title}
Customer report: {report}
Priority: {priority}
{system_block}

After your analysis, return JSON only:
{{"hypotheses": [
  {{"title": "short tab label", "summary": "...", "likely_root_cause": "...",
    "confidence": "high|medium|low", "first_command": "safe read-only shell cmd",
    "fix_strategy": "what we'd do if this hypothesis is correct",
    "steps": [
      {{"agent_name": "Customer System Analyzer", "command_text": "...", "script_diff": "+ ...", "intent": "diagnostic"}},
      {{"agent_name": "Problem Solver", "command_text": "sudo ...", "script_diff": "+ ...", "intent": "fix"}}
    ]}}
]}}

Rules:
- Propose 2–3 DISTINCT ranked hypotheses (different solution paths, not rewordings)
- first_command must be safe diagnostics (no destructive ops)
- steps: 3–6 ordered commands per hypothesis (diagnostics first, then fix)
- Ground every hypothesis in the customer symptom and your reasoning
- Include at least one service/config hypothesis and one resource/permission hypothesis when plausible"""


def parse_thinking_response(response: Any) -> tuple[str, str]:
    """Split Gemini response into thought summary text and final answer text."""
    thought_parts: list[str] = []
    answer_parts: list[str] = []

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            text = (getattr(part, "text", None) or "").strip()
            if not text:
                continue
            if getattr(part, "thought", False):
                thought_parts.append(text)
            else:
                answer_parts.append(text)

    if not answer_parts:
        answer_parts.append((getattr(response, "text", None) or "").strip())

    return "\n\n".join(thought_parts).strip(), "\n".join(answer_parts).strip()


class TicketUnderstandingService:
    """Uses a thinking-capable Gemini model for ticket comprehension and hypothesis paths."""

    def __init__(self, settings: Settings, safety: SafetyLayer | None = None):
        self.settings = settings
        self.safety = safety or SafetyLayer()
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key and self.settings.gemini_ticket_thinking_enabled)

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def analyze(
        self,
        ticket: dict[str, Any],
        system_info: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return {reasoning_summary, hypotheses} or None if thinking is unavailable."""
        if not self.enabled:
            return None

        from google.genai import types

        system_block = ""
        if system_info:
            system_block = (
                f"Target: {system_info.get('host_ip')}:{system_info.get('port', 22)} "
                f"({system_info.get('os_version', 'Linux')})"
            )

        prompt = UNDERSTANDING_PROMPT.format(
            title=ticket.get("title", ""),
            report=ticket.get("report_text", "")[:3000],
            priority=ticket.get("priority", "Medium"),
            system_block=system_block,
        )

        level = (self.settings.gemini_thinking_level or "high").lower()
        model = self.settings.gemini_thinking_model or self.settings.gemini_model

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_json_schema=HypothesisList.model_json_schema(),
                    thinking_config=types.ThinkingConfig(
                        thinking_level=level,
                        include_thoughts=True,
                    ),
                ),
            )
            reasoning_summary, answer_text = parse_thinking_response(response)
            items = HypothesisList.model_validate(json.loads(answer_text or "{}")).hypotheses
            hypotheses = [self._sanitize_item(h) for h in items]
            return {
                "reasoning_summary": reasoning_summary,
                "hypotheses": hypotheses,
                "thinking_model": model,
                "thinking_level": level,
            }
        except Exception as exc:
            logger.warning("Gemini thinking ticket analysis failed (%s): %s", model, exc)
            return None

    def _sanitize_item(self, item: HypothesisItem) -> dict[str, Any]:
        from app.agent.plan_resolver import ensure_plan

        safety = self.safety.evaluate(item.first_command)
        data = ensure_plan(item.model_dump())
        data["safety_status"] = safety.status
        return data
