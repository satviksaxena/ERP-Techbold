"""Azure OpenAI agent — primary LLM for hackathon (gpt-5.4-nano)."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.agent.llm_schemas import (
    SYSTEM_INSTRUCTION,
    ActivityDraft,
    CommandProposal,
)
from app.config import Settings
from app.safety.layer import SafetyLayer

logger = logging.getLogger(__name__)


class AzureOpenAIAgent:
    def __init__(self, settings: Settings, safety: SafetyLayer | None = None):
        self.settings = settings
        self.safety = safety or SafetyLayer()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.azure_openai_api_key and self.settings.azure_openai_endpoint)

    def _chat_json(self, system: str, user: str, schema_model: type) -> dict[str, Any]:
        base = self.settings.azure_openai_endpoint.rstrip("/")
        url = f"{base}/openai/v1/chat/completions"
        payload = {
            "model": self.settings.azure_openai_deployment,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.15,
        }
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = client.post(
                url,
                headers={
                    "api-key": self.settings.azure_openai_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        schema_model.model_validate(parsed)
        return parsed

    def propose_next_command(
        self,
        ticket: dict[str, Any],
        existing_commands: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        hypothesis_context: str = "",
        **kwargs: Any,
    ) -> dict[str, str] | None:
        if not self.enabled:
            return None

        history = self._format_history(existing_commands)
        sys_block = ""
        if system_info:
            sys_block = (
                f"\nTarget: {system_info.get('host_ip')}:{system_info.get('port', 22)} "
                f"user={system_info.get('username', 'azureuser')} "
                f"({system_info.get('os_version', 'Linux')}) "
                f"SSH={system_info.get('connection_status', 'Unknown')}"
            )

        step = len([c for c in existing_commands if c.get("human_status") in ("Approved", "Edited")])
        target_agent = kwargs.get("target_agent") or "Customer System Analyzer"
        evidence_context = kwargs.get("evidence_context") or ""
        verifier_context = kwargs.get("verifier_context") or ""
        runbook_context = kwargs.get("runbook_context") or ""
        reflexion_context = kwargs.get("reflexion_context") or ""
        phase = kwargs.get("phase") or ""

        from app.agent.agent_prompts import get_system_instruction

        system_instruction = get_system_instruction(target_agent)

        prompt = f"""Ticket: {ticket.get('title')}
Customer report: {ticket.get('report_text')}
Priority: {ticket.get('priority')}{sys_block}
Pipeline phase: {phase or 'DIAGNOSE'}
{hypothesis_context}
{evidence_context}
{verifier_context}
{runbook_context}
{reflexion_context}

Approved commands so far: {step}
{history or '(none yet)'}

You are acting as: {target_agent}
Respond with JSON matching this schema:
{{"agent_name": "...", "command_text": "...", "script_diff": "+ ...", "reasoning": "...", "ready_for_activity": false}}"""

        try:
            data = self._chat_json(system_instruction, prompt, CommandProposal)
            proposal = CommandProposal.model_validate(data)
            safety = self.safety.evaluate(proposal.command_text)
            return {
                "agent_name": proposal.agent_name,
                "command_text": proposal.command_text,
                "script_diff": proposal.script_diff or f"+ {proposal.command_text}",
                "safety_status": safety.status,
                "human_status": "Pending",
                "output_logs": "",
                "agent_reasoning": proposal.reasoning or "",
                "_reasoning": proposal.reasoning,
                "_ready_for_activity": str(proposal.ready_for_activity),
            }
        except Exception as exc:
            logger.exception("Azure OpenAI proposal failed")
            raise RuntimeError(f"Azure OpenAI proposal failed: {exc}") from exc

    def generate_activity(
        self,
        ticket: dict[str, Any],
        commands: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        if not self.enabled:
            return None

        executed = [
            c
            for c in commands
            if c.get("human_status") in ("Approved", "Edited") and c.get("output_logs")
        ]
        if not executed:
            return None

        history = self._format_history(executed)
        prompt = f"""Write Phoenix ERP activity JSON for this incident.

Ticket: {ticket.get('title')}
Report: {ticket.get('report_text')}

Commands and outputs:
{history}

JSON fields: summary, root_cause, actions_taken, commands_summary, validation_result

Rules:
- Every single JSON field MUST be a flat string (do NOT use arrays, lists, or dictionary objects for any field).
- actions_taken: ONLY commands that appear above as Approved/Edited, formatted as a flat, newline-separated or bulleted string (no lists or arrays). Never invent steps not yet run.
- commands_summary: a flat comma-separated string listing only command names/classes (no nested JSON/lists).
- validation_result: cite public-test.sh if executed; else "Validation pending"
"""

        try:
            data = self._chat_json(
                "You write precise IT incident documentation for an ERP.",
                prompt,
                ActivityDraft,
            )
            return ActivityDraft.model_validate(data).model_dump()
        except Exception as exc:
            logger.warning("Azure activity generation failed: %s", exc)
            return None

    @staticmethod
    def _format_history(commands: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for c in commands:
            if c.get("human_status") == "Pending":
                continue
            lines.append(f"[{c.get('agent_name')}] $ {c.get('command_text')} ({c.get('human_status')})")
            if c.get("output_logs"):
                lines.append(str(c.get("output_logs"))[:2000])
            lines.append("")
        return "\n".join(lines)
