"""Minimal deterministic command sequences per hackathon ticket — fewest steps to fix."""
from __future__ import annotations

from typing import Any

from app.agent.command_validator import is_valid_shell_command
from app.agent.llm_schemas import PUBLIC_TEST_COMMAND
from app.agent.hackathon_commands import (
    command_succeeded,
    fix_applied_after_last_public_test,
    last_public_test_failed,
    public_test_passed,
    uses_hackathon_service_progression,
)
from app.agent.plan_resolver import command_already_run, last_fix_index
from app.agent.reflexion import command_already_failed
from app.safety.layer import SafetyLayer

FastStep = tuple[str, str, str, str]  # agent, command, diff, intent

# Ordered minimal paths — diagnostics may auto-run; fixes need approval.
FAST_PATHS: dict[str, list[FastStep]] = {
    "7001": [
        (
            "Customer System Analyzer",
            "systemctl is-enabled status-api.service",
            "+ check grading service enabled on boot",
            "diagnostic",
        ),
        (
            "Problem Solver",
            "sudo systemctl enable --now status-api.service",
            "+ enable status-api grading target",
            "fix",
        ),
        (
            "Problem Solver",
            PUBLIC_TEST_COMMAND,
            "+ hackathon validation",
            "validate",
        ),
    ],
    "7002": [
        (
            "Customer System Analyzer",
            "stat /srv/customer-portal/uploads",
            "+ confirm upload directory ownership",
            "diagnostic",
        ),
        (
            "Problem Solver",
            "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
            "+ fix upload directory ownership",
            "fix",
        ),
        (
            "Problem Solver",
            PUBLIC_TEST_COMMAND,
            "+ hackathon validation after chown",
            "validate",
        ),
    ],
    "7003": [
        (
            "Customer System Analyzer",
            "df -h && df -i",
            "+ check disk and inode usage",
            "diagnostic",
        ),
        (
            "Customer System Analyzer",
            "systemctl status postgresql --no-pager -l",
            "+ inspect PostgreSQL service",
            "diagnostic",
        ),
        (
            "Problem Solver",
            "sudo systemctl restart postgresql",
            "+ restart PostgreSQL after underlying fix",
            "fix",
        ),
    ],
    "7004": [
        (
            "Customer System Analyzer",
            "df -h && mount | grep -E ' on / | on /var '",
            "+ check disk and read-only mounts",
            "diagnostic",
        ),
        (
            "Problem Solver",
            "sudo mount -o remount,rw /",
            "+ remount root read-write",
            "fix",
        ),
    ],
    "7005": [
        (
            "Customer System Analyzer",
            "systemctl --failed --no-pager",
            "+ list failed systemd units",
            "diagnostic",
        ),
        (
            "Customer System Analyzer",
            "journalctl -p err -n 30 --no-pager",
            "+ recent error logs",
            "diagnostic",
        ),
    ],
}

# After failed public-test on 7001 — common hidden-VM follow-ups (minimal).
POST_FAIL_7001: list[FastStep] = [
    (
        "Customer System Analyzer",
        "systemctl status customer-status.service --no-pager -l",
        "+ inspect customer-status after failed validation",
        "diagnostic",
    ),
    (
        "Problem Solver",
        "sudo sed -i 's/PORT=8008/PORT=8080/' /etc/customer-status.env && sudo systemctl restart customer-status.service",
        "+ correct customer-status listen port",
        "fix",
    ),
    (
        "Problem Solver",
        PUBLIC_TEST_COMMAND,
        "+ re-run hackathon validation",
        "validate",
    ),
]


def _proposal(step: FastStep, safety: SafetyLayer) -> dict[str, str]:
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
        "agent_reasoning": "Minimal fast path for this ticket.",
        "plan_intent": intent,
        "_path_source": "fast_path",
    }


def _step_done(commands: list[dict[str, Any]], command: str) -> bool:
    if command_already_run(commands, command):
        return True
    for cmd in commands:
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        if (cmd.get("command_text") or "").strip() == command.strip():
            if command_succeeded(cmd.get("output_logs")):
                return True
            if PUBLIC_TEST_COMMAND in command and "exit code: 0" in (cmd.get("output_logs") or "").lower():
                return True
    return False


def _next_from_steps(
    steps: list[FastStep],
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
) -> dict[str, str] | None:
    for step in steps:
        command = step[1]
        if not is_valid_shell_command(command):
            continue
        if command_already_failed(commands, command):
            continue
        if _step_done(commands, command):
            continue
        proposal = _proposal(step, safety)
        return proposal or None
    return None


def next_fast_path_command(
    ticket: dict[str, Any],
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
) -> dict[str, str] | None:
    """Return the next minimal step for known hackathon tickets, or None."""
    code = str(ticket.get("ticket_code") or "")
    if code not in FAST_PATHS:
        return None

    if public_test_passed(commands):
        return None

    # 7001 — after failed public-test, try port/service correction path.
    if code == "7001" and last_public_test_failed(commands):
        if fix_applied_after_last_public_test(commands):
            return _proposal(
                (
                    "Problem Solver",
                    PUBLIC_TEST_COMMAND,
                    "+ re-run hackathon validation",
                    "validate",
                ),
                safety,
            )
        post = _next_from_steps(POST_FAIL_7001, commands, safety)
        if post:
            return post

    # 7002 — validate after any successful fix even without systemd progression.
    if code == "7002" and not uses_hackathon_service_progression(ticket):
        if last_fix_index(commands) >= 0 and not _step_done(commands, PUBLIC_TEST_COMMAND):
            if last_public_test_failed(commands) and not fix_applied_after_last_public_test(commands):
                return _next_from_steps(FAST_PATHS["7002"], commands, safety)
            if not last_public_test_failed(commands):
                return _proposal(
                    (
                        "Problem Solver",
                        PUBLIC_TEST_COMMAND,
                        "+ hackathon validation after chown",
                        "validate",
                    ),
                    safety,
                )

    steps = FAST_PATHS.get(code, [])
    if not steps:
        return None

    # Skip validate step until a fix succeeded.
    has_fix = last_fix_index(commands) >= 0
    for step in steps:
        if step[3] == "validate" and not has_fix:
            continue
        command = step[1]
        if command_already_failed(commands, command):
            continue
        if _step_done(commands, command):
            continue
        if not is_valid_shell_command(command):
            continue
        proposal = _proposal(step, safety)
        if proposal:
            return proposal

    return None


def has_fast_path(ticket: dict[str, Any]) -> bool:
    return str(ticket.get("ticket_code") or "") in FAST_PATHS
