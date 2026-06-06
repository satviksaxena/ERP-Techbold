from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def generate_activity_draft(
    *,
    ticket: dict[str, Any],
    commands: list[dict[str, Any]],
    audit_entries: list[dict[str, Any]],
) -> dict[str, str]:
    """Build Phoenix ERP activity fields from executed commands and audit trail."""
    executed = [
        c
        for c in commands
        if c.get("human_status") in ("Approved", "Edited") and c.get("output_logs")
    ]

    actions_lines: list[str] = []
    cmd_classes: list[str] = []
    for i, cmd in enumerate(executed, 1):
        actions_lines.append(f"{i}. [{cmd.get('agent_name')}] {cmd.get('command_text')}")
        first_word = (cmd.get("command_text") or "").split()[0] if cmd.get("command_text") else ""
        if first_word and first_word not in cmd_classes:
            cmd_classes.append(first_word)

    validation = _validation_from_commands(executed)

    root_hints = _infer_root_cause(ticket.get("report_text", ""), executed)

    return {
        "summary": _build_summary(ticket, executed),
        "root_cause": root_hints,
        "actions_taken": "\n".join(actions_lines) if actions_lines else "No commands executed yet.",
        "commands_summary": ", ".join(cmd_classes) if cmd_classes else "diagnostic shell commands",
        "validation_result": validation or "Pending validation — run a service check after fix.",
    }


def _validation_from_commands(executed: list[dict[str, Any]]) -> str:
    for cmd in reversed(executed):
        text = (cmd.get("command_text") or "").lower()
        if "public-test" not in text:
            continue
        output = cmd.get("output_logs") or ""
        if "exit code: 0" in output.lower():
            ok_lines = [ln.strip() for ln in output.split("\n") if "OK:" in ln or "ok:" in ln.lower()]
            detail = ok_lines[-1] if ok_lines else "All public-test checks passed."
            return f"PASS — public-test.sh exit 0. {detail}"
        if output:
            return "FAIL — public-test.sh did not pass. Review terminal output for details."

    validation_cmds = [
        c
        for c in executed
        if "curl" in (c.get("command_text") or "")
        or "systemctl status" in (c.get("command_text") or "")
    ]
    if validation_cmds:
        return validation_cmds[-1].get("output_logs", "")[-500:]
    if executed:
        return executed[-1].get("output_logs", "")[-500:]
    return ""


def _build_summary(ticket: dict[str, Any], executed: list[dict[str, Any]]) -> str:
    title = ticket.get("title", "Incident")
    if not executed:
        return f"Investigation in progress for: {title}"
    last = executed[-1]
    status = "resolved" if last.get("output_logs", "").find("exit code: 0") >= 0 else "mitigated"
    return f"{title} — incident {status} after {len(executed)} approved SSH action(s)."


def _infer_root_cause(report: str, executed: list[dict[str, Any]]) -> str:
    report_lower = report.lower()
    if any(k in report_lower for k in ("disk", "space", "full", "storage")):
        return "Disk space exhaustion on critical filesystem preventing service operation."
    if any(k in report_lower for k in ("502", "nginx", "web", "http", "site down")):
        return "Web service misconfiguration or upstream failure causing HTTP errors."
    if any(k in report_lower for k in ("database", "postgres", "mysql", "connection refused")):
        return "Database service unavailable or rejecting connections."
    if any(k in report_lower for k in ("ssl", "certificate", "tls", "expired")):
        return "TLS certificate expired or misconfigured."
    if any(k in report_lower for k in ("permission", "denied", "upload")):
        return "Incorrect filesystem permissions blocking application write access."
    if executed:
        return "Root cause identified during SSH diagnostics — see actions taken for evidence."
    return "Under investigation — symptom reported: " + (report[:200] if report else "unknown")
