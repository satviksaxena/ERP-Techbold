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


_AUTO_BLOCK_MARKERS = (
    "systemctl enable",
    "systemctl disable",
    "systemctl restart",
    "systemctl start",
    "systemctl stop",
    "mount -o remount",
    "sed -i",
    "chmod ",
    "chown ",
    "chgrp ",
    "setfacl",
    "useradd",
    "groupadd",
    "public-test",
    "apt-get clean",
    "journalctl --vacuum",
    "-exec chown",
    "-exec chmod",
)


def can_auto_approve(
    command_text: str,
    *,
    plan_intent: str | None = None,
    safety_allowed: bool = True,
) -> bool:
    """Read-only diagnostics may run without human slide-to-authorize when auto-run is enabled."""
    if not safety_allowed:
        return False
    text = (command_text or "").strip()
    if not text or not is_valid_shell_command(text):
        return False
    if plan_intent in ("fix", "validate"):
        return False
    if is_fix_command(text, plan_intent=plan_intent):
        return False
    if is_validate_command(text, plan_intent=plan_intent):
        return False
    lower = text.lower()
    if any(marker in lower for marker in _AUTO_BLOCK_MARKERS):
        return False
    return intent_from_command(text) == "diagnostic"
