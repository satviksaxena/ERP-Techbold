from __future__ import annotations

from pydantic import BaseModel, Field


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


class HypothesisItem(BaseModel):
    title: str = Field(description="Short tab label, e.g. 'Service not running'")
    summary: str = Field(description="One paragraph explaining this approach")
    likely_root_cause: str = Field(description="Technical hypothesis, not symptom")
    confidence: str = Field(description="high, medium, or low")
    first_command: str = Field(description="Safe first diagnostic command for this approach")
    fix_strategy: str = Field(description="What fix steps would follow if confirmed")


class HypothesisList(BaseModel):
    hypotheses: list[HypothesisItem] = Field(min_length=2, max_length=4)


PUBLIC_TEST_COMMAND = "sudo /opt/hackathon/public-test.sh"


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
