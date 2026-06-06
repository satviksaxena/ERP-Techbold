"""Gemini-powered multi-agent pipeline for IT service desk troubleshooting."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.safety.layer import SafetyLayer

logger = logging.getLogger(__name__)

AGENT_ROLES = [
    "Problem Analyzer",
    "Customer System Analyzer",
    "Problem Solver",
    "Activity Log Generator",
]

SYSTEM_INSTRUCTION = """You are part of an AI Service Desk Autopilot for Linux VMs (Ubuntu).
You work in a team of specialized agents. A human technician MUST approve every shell command
before it runs — you only PROPOSE commands, never execute them.

Agents and responsibilities:
- Problem Analyzer: interpret the ticket symptom, propose initial read-only diagnostics
- Customer System Analyzer: inspect system state (services, disk, memory, ports, logs)
- Problem Solver: propose minimal, targeted fixes once root cause is likely known
- Activity Log Generator: propose validation commands to prove the fix worked

Rules:
- Propose ONE shell command at a time
- Prefer read-only diagnostics before fixes
- Never propose: rm -rf on system paths, chmod -R 777, DROP DATABASE, disable firewall,
  delete logs/history, run as unrestricted superuser
- Keep commands minimal — no unnecessary package installs
- Base proposals on ticket text AND prior command outputs
- If enough evidence exists, move to validation (curl, systemctl status, health checks)
- When proposing a fix, explain briefly in script_diff what will change"""


class CommandProposal(BaseModel):
    agent_name: str = Field(description="One of the four agent roles")
    command_text: str = Field(description="Single shell command for SSH execution")
    script_diff: str = Field(description="Human-readable diff starting with + or -")
    reasoning: str = Field(default="", description="Why this command is the next best step")
    ready_for_activity: bool = Field(
        default=False,
        description="True if troubleshooting appears complete and validation passed",
    )


class ActivityDraft(BaseModel):
    summary: str
    root_cause: str
    actions_taken: str
    commands_summary: str
    validation_result: str


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

        step = len([c for c in existing_commands if c.get("human_status") in ("Approved", "Edited")])
        suggested_agent = AGENT_ROLES[min(step, len(AGENT_ROLES) - 1)]

        prompt = f"""Ticket: {ticket.get('title')}
Customer report (symptom only): {ticket.get('report_text')}
Priority: {ticket.get('priority')}{sys_block}
{hypothesis_context}

Commands executed so far ({step} approved):
{history_text or '(none yet)'}

Suggest the NEXT single command. Current pipeline stage hint: {suggested_agent}.
If prior outputs show the issue is fixed, propose a validation command instead of more changes."""

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.15,
                    response_mime_type="application/json",
                    response_json_schema=PROPOSAL_SCHEMA,
                ),
            )
            raw = (response.text or "").strip()
            data = json.loads(raw)
            proposal = CommandProposal.model_validate(data)

            if proposal.agent_name not in AGENT_ROLES:
                proposal.agent_name = suggested_agent

            safety = self.safety.evaluate(proposal.command_text)
            return {
                "agent_name": proposal.agent_name,
                "command_text": proposal.command_text,
                "script_diff": proposal.script_diff or f"+ {proposal.command_text}",
                "safety_status": safety.status,
                "human_status": "Pending",
                "output_logs": "",
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
