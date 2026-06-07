"""Plan-then-execute runbook paths for classified incidents (non-hackathon fast-path tickets)."""
from __future__ import annotations

from typing import Any

from app.agent.command_validator import is_valid_shell_command
from app.agent.fast_paths import has_fast_path
from app.agent.hackathon_commands import command_succeeded
from app.agent.llm_schemas import PUBLIC_TEST_COMMAND
from app.agent.plan_resolver import last_fix_index
from app.agent.reflexion import command_already_failed
from app.agent.runbooks import RunbookStep, classify_incident, get_execution_plan
from app.safety.layer import SafetyLayer


def has_runbook_path(ticket: dict[str, Any]) -> bool:
    """True when ticket classifies to a runbook with an executable plan."""
    if has_fast_path(ticket):
        return False
    return classify_incident(ticket) is not None


def _proposal(step: RunbookStep, safety: SafetyLayer) -> dict[str, str]:
    agent, command, diff, intent = step
    result = safety.evaluate(command)
    if not result.allowed:
        return {}
    return {
        "agent_name": agent,
        "command_text": command,
        "script_diff": diff,
        "safety_status": result.status,
        "human_status": "Pending",
        "output_logs": "",
        "agent_reasoning": "Classified runbook path (plan-then-execute).",
        "plan_intent": intent,
        "_path_source": "runbook_path",
    }


def _step_succeeded(
    commands: list[dict[str, Any]],
    command: str,
    *,
    after_index: int = -1,
) -> bool:
    normalized = command.strip().lower()
    for i, cmd in enumerate(commands):
        if after_index >= 0 and i <= after_index:
            continue
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        executed = (cmd.get("command_text") or "").strip().lower()
        if executed == normalized or normalized in executed or executed in normalized:
            if command_succeeded(cmd.get("output_logs")):
                return True
            if PUBLIC_TEST_COMMAND in command and "exit code: 0" in (cmd.get("output_logs") or "").lower():
                return True
    return False


def _step_executed(
    commands: list[dict[str, Any]],
    command: str,
    *,
    after_index: int = -1,
) -> bool:
    normalized = command.strip().lower()
    for i, cmd in enumerate(commands):
        if after_index >= 0 and i <= after_index:
            continue
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        executed = (cmd.get("command_text") or "").strip().lower()
        if executed == normalized:
            return True
        if normalized in executed or executed in normalized:
            return True
    return False


def _fix_state_already_satisfied(commands: list[dict[str, Any]], command: str) -> bool:
    """Idempotency — skip fix when prior diagnostics show desired state."""
    cmd_lower = command.lower()
    if "chown" in cmd_lower and "www-data" in cmd_lower:
        for cmd in commands:
            if cmd.get("human_status") not in ("Approved", "Edited"):
                continue
            text = (cmd.get("command_text") or "").lower()
            if not any(k in text for k in ("stat", "ls -l", "ls -ld")):
                continue
            output = (cmd.get("output_logs") or "").lower()
            if "www-data:www-data" in output or "www-data www-data" in output:
                return True
    if "systemctl enable" in cmd_lower or "systemctl restart" in cmd_lower:
        for cmd in commands:
            if cmd.get("human_status") not in ("Approved", "Edited"):
                continue
            text = (cmd.get("command_text") or "").lower()
            if "is-enabled" not in text and "is-active" not in text:
                continue
            output = (cmd.get("output_logs") or "").lower()
            if "enabled" in output and "disabled" not in output:
                return True
            if "active (running)" in output:
                return True
    if "remount,rw" in cmd_lower:
        for cmd in commands:
            if cmd.get("human_status") not in ("Approved", "Edited"):
                continue
            text = (cmd.get("command_text") or "").lower()
            if "remount" not in text:
                continue
            if command_succeeded(cmd.get("output_logs")):
                return True
    return False


def _pending_validate_after_fix(
    steps: list[RunbookStep],
    commands: list[dict[str, Any]],
) -> RunbookStep | None:
    """Mandatory verify gate — queue validate before another fix."""
    fix_idx = last_fix_index(commands)
    if fix_idx < 0:
        return None
    for step in steps:
        if step[3] != "validate":
            continue
        if _step_succeeded(commands, step[1], after_index=fix_idx):
            return None
        if _step_executed(commands, step[1], after_index=fix_idx):
            return None
        return step
    return None


def next_runbook_path_command(
    ticket: dict[str, Any],
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
    *,
    hypothesis: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Next step from classified runbook plan, or None to fall through to existing resolver."""
    if has_fast_path(ticket):
        return None

    steps = get_execution_plan(ticket, hypothesis)
    if not steps:
        return None

    validate_pending = _pending_validate_after_fix(steps, commands)
    if validate_pending:
        proposal = _proposal(validate_pending, safety)
        if proposal:
            return proposal

    has_fix = last_fix_index(commands) >= 0
    fix_idx = last_fix_index(commands)
    for step in steps:
        intent = step[3]
        command = step[1]

        if intent == "validate" and not has_fix:
            continue
        if not is_valid_shell_command(command):
            continue
        if command_already_failed(commands, command):
            continue
        if intent == "validate":
            if _step_succeeded(commands, command, after_index=fix_idx):
                continue
            if _step_executed(commands, command, after_index=fix_idx):
                continue
        elif _step_succeeded(commands, command):
            continue
        if intent == "fix" and _fix_state_already_satisfied(commands, command):
            continue
        if intent == "fix" and has_fix and validate_pending is None:
            # Another fix attempted — require validate between fixes when plan defines it.
            has_validate = any(s[3] == "validate" for s in steps)
            if has_validate and not any(
                _step_succeeded(commands, s[1], after_index=fix_idx) for s in steps if s[3] == "validate"
            ):
                continue

        proposal = _proposal(step, safety)
        if proposal:
            return proposal

    return None
