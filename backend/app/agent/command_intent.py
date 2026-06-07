"""Classify proposed commands — prefer explicit plan intent over substring heuristics."""
from __future__ import annotations

from app.agent.command_validator import is_valid_shell_command

_FIX_MARKERS = (
    "chmod",
    "chown",
    "systemctl restart",
    "systemctl start",
    "systemctl enable",
    "mount -o remount",
    "sed -i",
    "setfacl",
    "useradd",
    "groupadd",
)


def intent_from_command(command_text: str) -> str:
    """Return diagnostic | fix | validate for a shell command."""
    t = (command_text or "").strip().lower()
    if not t:
        return "diagnostic"
    if "public-test" in t or t.startswith("curl ") and "health" in t:
        return "validate"
    if any(m in t for m in _FIX_MARKERS):
        return "fix"
    return "diagnostic"


def is_fix_command(command_text: str, *, plan_intent: str | None = None) -> bool:
    if plan_intent:
        return plan_intent == "fix"
    return intent_from_command(command_text) == "fix"


def is_validate_command(command_text: str, *, plan_intent: str | None = None) -> bool:
    if plan_intent:
        return plan_intent == "validate"
    return intent_from_command(command_text) == "validate"


def is_valid_proposal_command(text: str) -> bool:
    return is_valid_shell_command(text)
