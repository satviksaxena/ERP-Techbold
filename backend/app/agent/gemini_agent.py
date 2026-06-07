"""Gemini-powered multi-agent pipeline for IT service desk troubleshooting."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.agent_prompts import get_system_instruction, is_valid_agent
from app.agent.command_validator import is_valid_shell_command
from app.agent.llm_schemas import AGENT_ROLES, ActivityDraft, CommandProposal
from app.config import Settings
from app.safety.layer import SafetyLayer

logger = logging.getLogger(__name__)

PROPOSAL_SCHEMA = CommandProposal.model_json_schema()
ACTIVITY_SCHEMA = ActivityDraft.model_json_schema()


class GeminiAgentService:
    def __init__(self, settings: Settings, safety: SafetyLayer | None = None):
        self.settings = settings
        self.safety = safety or SafetyLayer()
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def propose_next_command(
        self,
        ticket: dict[str, Any],
        existing_commands: list[dict[str, Any]],
        system_info: dict[str, Any] | None = None,
        hypothesis_context: str = "",
        *,
        target_agent: str | None = None,
        evidence_context: str = "",
        verifier_context: str = "",
        runbook_context: str = "",
        reflexion_context: str = "",
        phase: str = "",
    ) -> dict[str, str] | None:
        if not self.enabled:
            return None

        from google.genai import types

        history_text = self._format_command_history(existing_commands)
        sys_block = ""
        if system_info:
            sys_block = (
                f"\nTarget system: {system_info.get('host_ip')}:{system_info.get('port', 22)} "
                f"({system_info.get('os_version', 'Linux')}), "
                f"SSH status: {system_info.get('connection_status', 'Unknown')}"
            )

        agent_name = target_agent if target_agent and is_valid_agent(target_agent) else AGENT_ROLES[0]
        system_instruction = get_system_instruction(agent_name)

        prompt = f"""Ticket: {ticket.get('title')}
Customer report (symptom only): {ticket.get('report_text')}
Priority: {ticket.get('priority')}{sys_block}
Pipeline phase: {phase or 'DIAGNOSE'}
{hypothesis_context}
{evidence_context}
{verifier_context}
{runbook_context}
{reflexion_context}

Commands executed so far:
{history_text or '(none yet)'}

You are acting as: {agent_name}
Suggest the NEXT single shell command for this phase.
command_text MUST be one executable shell line only — no English sentences, no placeholders like <service_name>.
If proposing a fix, use a concrete command such as: sudo systemctl enable --now status-api.service
If verifier says continue_diagnose, do NOT propose fix commands.
If proposing a fix, prefer systemctl enable --now for persistence."""

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.15,
                    response_mime_type="application/json",
                    response_json_schema=PROPOSAL_SCHEMA,
                ),
            )
            raw = (response.text or "").strip()
            data = json.loads(raw)
            proposal = CommandProposal.model_validate(data)

            if not is_valid_shell_command(proposal.command_text):
                logger.warning("Gemini returned invalid shell command: %s", proposal.command_text[:120])
                return None

            if not is_valid_agent(proposal.agent_name):
                proposal.agent_name = agent_name

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
            logger.exception("Gemini command proposal failed")
            raise RuntimeError(f"Gemini proposal failed: {exc}") from exc

    def generate_activity(
        self,
        ticket: dict[str, Any],
        commands: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        if not self.enabled:
            return None

        from google.genai import types

        executed = [
            c
            for c in commands
            if c.get("human_status") in ("Approved", "Edited") and c.get("output_logs")
        ]
        if not executed:
            return None

        history = self._format_command_history(executed)
        prompt = f"""Write a Phoenix ERP activity log for this resolved incident.

Ticket: {ticket.get('title')}
Customer report: {ticket.get('report_text')}

Executed commands and outputs:
{history}

Requirements:
- summary: one sentence on what was restored (or progress so far if not fixed)
- root_cause: TECHNICAL cause based on evidence in outputs — say "under investigation" if unclear
- actions_taken: ONLY steps whose commands appear below with Approved/Edited status — do NOT invent enable/restart/fix steps not yet executed
- commands_summary: command classes only, no secret output
- validation_result: cite public-test.sh output if run; otherwise state "Validation pending — public-test.sh not yet passed"
"""

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You write precise IT incident documentation for an ERP system.",
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_json_schema=ACTIVITY_SCHEMA,
                ),
            )
            draft = ActivityDraft.model_validate(json.loads(response.text or "{}"))
            return draft.model_dump()
        except Exception as exc:
            logger.warning("Gemini activity generation failed, falling back: %s", exc)
            return None

    @staticmethod
    def _format_command_history(commands: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for c in commands:
            status = c.get("human_status", "?")
            if status == "Pending":
                continue
            lines.append(f"[{c.get('agent_name')}] $ {c.get('command_text')} ({status})")
            output = (c.get("output_logs") or "")[:2000]
            if output:
                lines.append(output)
            lines.append("")
        return "\n".join(lines)
