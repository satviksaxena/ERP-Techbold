"""Extract structured evidence from SSH command outputs."""
from __future__ import annotations

import re
from typing import Any


def empty_evidence() -> dict[str, Any]:
    return {
        "failed_units": [],
        "disabled_units": [],
        "full_filesystems": [],
        "listening_ports": [],
        "error_lines": [],
        "service_states": {},
        "last_exit_code": None,
    }


def merge_evidence(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = empty_evidence()
    out.update(base or {})
    for key in ("failed_units", "disabled_units", "full_filesystems", "listening_ports", "error_lines"):
        merged = list(dict.fromkeys((out.get(key) or []) + (patch.get(key) or [])))
        out[key] = merged[:50]
    states = dict(out.get("service_states") or {})
    states.update(patch.get("service_states") or {})
    out["service_states"] = states
    if patch.get("last_exit_code") is not None:
        out["last_exit_code"] = patch["last_exit_code"]
    return out


def extract_from_output(command_text: str, output_logs: str) -> dict[str, Any]:
    patch = empty_evidence()
    output = output_logs or ""
    lower = output.lower()
    cmd_lower = (command_text or "").lower()

    exit_match = re.search(r"exit code:\s*(\d+)", lower)
    if exit_match:
        patch["last_exit_code"] = int(exit_match.group(1))
    elif "[exit 0]" in lower:
        patch["last_exit_code"] = 0

    if "systemctl" in cmd_lower or "failed" in lower:
        for unit in re.findall(r"([a-z0-9@._-]+\.service)\s+(?:loaded|not-found|failed)", lower):
            if unit not in patch["failed_units"]:
                patch["failed_units"].append(unit)
        for line in output.splitlines():
            if ".service" in line and ("failed" in line.lower() or "×" in line or "●" in line):
                for unit in re.findall(r"([a-z0-9@._-]+\.service)", line, re.I):
                    if unit not in patch["failed_units"]:
                        patch["failed_units"].append(unit)

    for line in output.splitlines():
        ll = line.lower()
        if "active:" in ll and ".service" in ll:
            unit_match = re.search(r"([a-z0-9@._-]+\.service)", line, re.I)
            if unit_match:
                unit = unit_match.group(1)
                state = "active" if "active: active" in ll else "inactive"
                if "enabled" in ll:
                    patch["service_states"][unit] = f"{state}, enabled"
                elif "disabled" in ll:
                    patch["service_states"][unit] = f"{state}, disabled"
                    if unit not in patch["disabled_units"]:
                        patch["disabled_units"].append(unit)
                else:
                    patch["service_states"][unit] = state

    if "df " in cmd_lower or "%" in output:
        for line in output.splitlines():
            if re.search(r"\b9[0-9]%\b|\b100%\b", line):
                patch["full_filesystems"].append(line.strip()[:120])

    if "ss " in cmd_lower or "listen" in lower:
        for line in output.splitlines():
            if "LISTEN" in line or "listen" in line.lower():
                port_match = re.search(r":(\d+)\s", line)
                if port_match:
                    entry = f":{port_match.group(1)}"
                    if entry not in patch["listening_ports"]:
                        patch["listening_ports"].append(entry)

    if "journalctl" in cmd_lower or "error" in lower or "err" in cmd_lower:
        for line in output.splitlines():
            ll = line.lower()
            if any(tok in ll for tok in ("error", "failed", "fatal", "denied", "cannot", "refused")):
                cleaned = line.strip()[:200]
                if cleaned and cleaned not in patch["error_lines"]:
                    patch["error_lines"].append(cleaned)

    return patch


def format_evidence_for_llm(evidence: dict[str, Any]) -> str:
    if not evidence:
        return "(no structured evidence yet)"
    lines: list[str] = []
    if evidence.get("failed_units"):
        lines.append(f"Failed systemd units: {', '.join(evidence['failed_units'][:10])}")
    if evidence.get("disabled_units"):
        lines.append(f"Disabled units: {', '.join(evidence['disabled_units'][:10])}")
    if evidence.get("service_states"):
        states = list(evidence["service_states"].items())[:8]
        lines.append("Service states: " + "; ".join(f"{u}={s}" for u, s in states))
    if evidence.get("full_filesystems"):
        lines.append("Full filesystems: " + "; ".join(evidence["full_filesystems"][:3]))
    if evidence.get("listening_ports"):
        lines.append("Listening ports: " + ", ".join(evidence["listening_ports"][:15]))
    if evidence.get("error_lines"):
        lines.append("Recent errors: " + " | ".join(evidence["error_lines"][:5]))
    if evidence.get("last_exit_code") is not None:
        lines.append(f"Last command exit code: {evidence['last_exit_code']}")
    return "\n".join(lines) if lines else "(no structured evidence yet)"
