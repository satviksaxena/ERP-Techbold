"""Reflexion — avoid repeating failed commands; suggest alternatives."""
from __future__ import annotations

from typing import Any


def last_failed_command(commands: list[dict[str, Any]]) -> dict[str, Any] | None:
    for c in reversed(commands):
        if c.get("human_status") not in ("Approved", "Edited"):
            continue
        output = (c.get("output_logs") or "").lower()
        if "execution failed" in output:
            return c
        if "exit code:" in output and "exit code: 0" not in output:
            return c
        if "[exit " in output and "[exit 0]" not in output:
            return c
    return None


def command_already_failed(commands: list[dict[str, Any]], command_text: str) -> bool:
    normalized = command_text.strip()
    failed = last_failed_command(commands)
    if not failed:
        return False
    return (failed.get("command_text") or "").strip() == normalized


def reflexion_context(commands: list[dict[str, Any]]) -> str:
    failed = last_failed_command(commands)
    if not failed:
        return ""
    cmd = failed.get("command_text", "")
    output = (failed.get("output_logs") or "")[:800]
    return (
        f"\nREFLEXION — previous command FAILED, do NOT repeat it verbatim:\n"
        f"Failed command: {cmd}\nOutput excerpt:\n{output}\n"
        f"Propose a DIFFERENT diagnostic or fix approach.\n"
    )
