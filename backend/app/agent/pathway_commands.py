"""Deterministic next commands for selected hypothesis pathways (non-hackathon tickets)."""
from __future__ import annotations

from typing import Any

from app.agent.command_validator import is_valid_shell_command
from app.safety.layer import SafetyLayer

PathwayStep = tuple[str, str, str]

# Ordered diagnostics then fixes per pathway theme.
PATHWAY_STEPS: dict[str, list[PathwayStep]] = {
    "disk": [
        (
            "Customer System Analyzer",
            "df -h && df -i",
            "+ check disk and inode usage on all mounts",
        ),
        (
            "Customer System Analyzer",
            "mount | grep -E ' on / | on /var '",
            "+ check if root or /var is read-only",
        ),
        (
            "Customer System Analyzer",
            "findmnt -no TARGET,OPTIONS / /var /var/lib/postgresql 2>/dev/null",
            "+ inspect mount options for postgres data paths",
        ),
        (
            "Problem Solver",
            "sudo mount -o remount,rw /",
            "+ remount root filesystem read-write",
        ),
    ],
    "postgres": [
        (
            "Customer System Analyzer",
            "systemctl status postgresql --no-pager -l",
            "+ inspect PostgreSQL service state",
        ),
        (
            "Customer System Analyzer",
            "journalctl -u postgresql -n 50 --no-pager",
            "+ recent PostgreSQL journal errors",
        ),
        (
            "Customer System Analyzer",
            "ss -tlnp | grep 5432",
            "+ confirm postgres listening on 5432",
        ),
        (
            "Problem Solver",
            "sudo systemctl restart postgresql",
            "+ restart PostgreSQL after fixing underlying issue",
        ),
    ],
    "permissions": [
        (
            "Customer System Analyzer",
            "namei -l /var/www 2>/dev/null || ls -la /var/www",
            "+ inspect web root permissions",
        ),
        (
            "Customer System Analyzer",
            "ls -la /var/www/uploads 2>/dev/null || ls -la /var/lib/postgresql",
            "+ inspect likely write directories",
        ),
    ],
    "service": [
        (
            "Customer System Analyzer",
            "systemctl --failed --no-pager",
            "+ list failed systemd units",
        ),
        (
            "Customer System Analyzer",
            "systemctl list-units --type=service --state=failed --no-pager",
            "+ enumerate failed services",
        ),
    ],
}


def _pathway_key(hypothesis: dict[str, Any]) -> str | None:
    text = " ".join(
        [
            hypothesis.get("title") or "",
            hypothesis.get("likely_root_cause") or "",
            hypothesis.get("summary") or "",
            hypothesis.get("fix_strategy") or "",
        ]
    ).lower()

    if any(k in text for k in ("disk", "read-only", "readonly", "filesystem", "space", "storage", "full")):
        return "disk"
    if any(k in text for k in ("postgres", "database", "db ", "sql", "5432")):
        return "postgres"
    if any(k in text for k in ("permission", "chown", "chmod", "denied", "upload")):
        return "permissions"
    if any(k in text for k in ("service", "systemd", "unit", "boot", "down")):
        return "service"
    return None


def command_already_run(commands: list[dict[str, Any]], command_text: str) -> bool:
    normalized = command_text.strip().lower()
    if not normalized:
        return False

    primary = normalized.split("|")[0].split("&&")[0].strip()

    for cmd in commands:
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        executed = (cmd.get("command_text") or "").strip().lower()
        if executed == normalized:
            return True
        if primary and primary in executed:
            return True
        if executed and executed in normalized:
            return True
    return False


def _proposal(agent: str, command: str, diff: str, safety: SafetyLayer) -> dict[str, str]:
    result = safety.evaluate(command)
    return {
        "agent_name": agent,
        "command_text": command,
        "script_diff": diff,
        "safety_status": result.status,
        "human_status": "Pending",
        "output_logs": "",
        "agent_reasoning": "Pathway progression fallback.",
    }


def next_pathway_command(
    hypothesis: dict[str, Any] | None,
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
) -> dict[str, str] | None:
    """Next diagnostic or fix step for the active hypothesis pathway."""
    from app.agent.plan_resolver import next_plan_step

    if not hypothesis:
        return None
    return next_plan_step(hypothesis, commands, safety)


def next_pathway_across_hypotheses(
    hypotheses: list[dict[str, Any]],
    selected_index: int,
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
    *,
    prefer_switch: bool = False,
) -> tuple[dict[str, str] | None, int | None]:
    from app.agent.plan_resolver import next_plan_across_hypotheses

    return next_plan_across_hypotheses(
        hypotheses,
        selected_index,
        commands,
        safety,
        prefer_switch=prefer_switch,
    )
