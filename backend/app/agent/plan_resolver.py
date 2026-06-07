"""Unified hypothesis plan — one progression engine for all ticket types."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agent.command_intent import intent_from_command, is_fix_command
from app.agent.command_validator import is_valid_shell_command
from app.agent.pathway_commands import PATHWAY_STEPS, _pathway_key, command_already_run
from app.safety.layer import SafetyLayer

# Safe read-only commands usable on any Linux VM when nothing else is queued.
UNIVERSAL_BASELINE: list[tuple[str, str, str]] = [
    ("Problem Analyzer", "uptime && hostname", "+ gather host identity"),
    ("Problem Analyzer", "systemctl --failed --no-pager", "+ list failed systemd units"),
    ("Customer System Analyzer", "df -h", "+ check disk usage"),
    ("Customer System Analyzer", "free -m", "+ check memory"),
    ("Customer System Analyzer", "ss -tlnp | head -30", "+ inspect listening ports"),
    ("Customer System Analyzer", "journalctl -p err -n 30 --no-pager", "+ recent error logs"),
    ("Customer System Analyzer", "journalctl -p err -n 50 --no-pager", "+ extended error log scan"),
    ("Customer System Analyzer", "systemctl list-units --state=failed --no-pager", "+ enumerate failed units"),
]

_FIX_CMD_RE = re.compile(
    r"(?:sudo\s+)?(?:systemctl\s+(?:enable|restart|start)\s+(?:--now\s+)?[\w@.-]+\.service|"
    r"chmod\s+[\dugo+-]+|chown\s+[\w:.-]+|mount\s+-o\s+remount[^\n;|&]+)",
    re.I,
)


@dataclass(frozen=True)
class PlanStep:
    agent_name: str
    command_text: str
    script_diff: str
    intent: str  # diagnostic | fix | validate


def _extract_fix_commands(fix_strategy: str) -> list[str]:
    if not fix_strategy:
        return []
    found: list[str] = []
    for match in _FIX_CMD_RE.finditer(fix_strategy):
        cmd = match.group(0).strip().rstrip(".")
        if cmd and cmd not in found:
            found.append(cmd)
    for raw in re.findall(r"`([^`]+)`", fix_strategy):
        cmd = raw.strip()
        if is_fix_command(cmd) and cmd not in found:
            if not cmd.startswith("sudo") and any(
                token in cmd.lower() for token in ("chown", "chmod", "systemctl", "mount")
            ):
                cmd = f"sudo {cmd}"
            found.append(cmd)
    return found


def build_plan(hypothesis: dict[str, Any]) -> list[PlanStep]:
    """Build an ordered command plan for any hypothesis (stored steps or synthesized)."""
    stored = hypothesis.get("steps") or []
    if stored:
        plan: list[PlanStep] = []
        for step in stored:
            cmd = (step.get("command_text") or step.get("command") or "").strip()
            if not cmd:
                continue
            plan.append(
                PlanStep(
                    agent_name=step.get("agent_name") or "Customer System Analyzer",
                    command_text=cmd,
                    script_diff=step.get("script_diff") or f"+ {hypothesis.get('title', 'path')}",
                    intent=step.get("intent") or intent_from_command(cmd),
                )
            )
        if plan:
            return plan

    plan = []
    seen: set[str] = set()

    def add(agent: str, command: str, diff: str, intent: str | None = None) -> None:
        cmd = command.strip()
        if not cmd or cmd.lower() in seen:
            return
        seen.add(cmd.lower())
        plan.append(
            PlanStep(
                agent_name=agent,
                command_text=cmd,
                script_diff=diff,
                intent=intent or intent_from_command(cmd),
            )
        )

    first = (hypothesis.get("first_command") or "").strip()
    if first:
        add("Problem Analyzer", first, f"+ first diagnostic: {hypothesis.get('title', 'path')}")

    key = _pathway_key(hypothesis)
    for agent, command, diff in PATHWAY_STEPS.get(key or "", []):
        add(agent, command, diff)

    for fix_cmd in _extract_fix_commands(hypothesis.get("fix_strategy") or ""):
        add("Problem Solver", fix_cmd, f"+ fix: {hypothesis.get('title', 'path')}", "fix")

    if not any(s.intent == "validate" for s in plan):
        validate_cmd = (
            first
            if first and is_valid_shell_command(first)
            else "systemctl --failed --no-pager"
        )
        add(
            "Problem Solver",
            validate_cmd,
            "+ verify fix resolved the symptom",
            "validate",
        )

    return plan


def ensure_plan(hypothesis: dict[str, Any]) -> dict[str, Any]:
    """Attach a steps[] plan to a hypothesis dict when missing (runtime enrichment)."""
    if hypothesis.get("steps"):
        return hypothesis
    out = dict(hypothesis)
    out["steps"] = [
        {
            "agent_name": s.agent_name,
            "command_text": s.command_text,
            "script_diff": s.script_diff,
            "intent": s.intent,
        }
        for s in build_plan(hypothesis)
    ]
    return out


def _proposal_from_step(step: PlanStep, safety: SafetyLayer) -> dict[str, str]:
    result = safety.evaluate(step.command_text)
    return {
        "agent_name": step.agent_name,
        "command_text": step.command_text,
        "script_diff": step.script_diff,
        "safety_status": result.status,
        "human_status": "Pending",
        "output_logs": "",
        "agent_reasoning": "Hypothesis plan progression.",
        "plan_intent": step.intent,
    }


def _step_allowed(
    step: PlanStep,
    verifier_recommend: str | None,
) -> bool:
    if step.intent != "fix":
        return True
    return verifier_recommend in ("apply_fix", "validate", None)


def _command_succeeded(output_logs: str | None) -> bool:
    output = (output_logs or "").lower()
    if "execution failed" in output:
        return False
    if "exit code:" in output and "exit code: 0" not in output:
        return False
    if "[exit " in output and "[exit 0]" not in output:
        return False
    return True


def last_fix_index(commands: list[dict[str, Any]]) -> int:
    for i in range(len(commands) - 1, -1, -1):
        cmd = commands[i]
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        if is_fix_command(cmd.get("command_text") or "") and _command_succeeded(cmd.get("output_logs")):
            return i
    return -1


def validation_step(hypothesis: dict[str, Any]) -> PlanStep:
    hyp = ensure_plan(hypothesis)
    for step in build_plan(hyp):
        if step.intent == "validate":
            return step
    first = (hypothesis.get("first_command") or "").strip()
    cmd = first if first and is_valid_shell_command(first) else "systemctl --failed --no-pager"
    return PlanStep(
        "Problem Solver",
        cmd,
        "+ verify fix resolved the symptom",
        "validate",
    )


def validation_attempted_after_fix(
    commands: list[dict[str, Any]],
    hypothesis: dict[str, Any],
) -> bool:
    fix_idx = last_fix_index(commands)
    if fix_idx < 0:
        return False
    target = validation_step(hypothesis).command_text.strip().lower()
    for cmd in commands[fix_idx + 1 :]:
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        if (cmd.get("command_text") or "").strip().lower() == target:
            return True
        if command_already_run([cmd], validation_step(hypothesis).command_text):
            return True
    return False


def validation_succeeded_after_fix(
    commands: list[dict[str, Any]],
    hypothesis: dict[str, Any],
) -> bool:
    fix_idx = last_fix_index(commands)
    if fix_idx < 0:
        return False
    target = validation_step(hypothesis).command_text.strip().lower()
    for cmd in reversed(commands[fix_idx + 1 :]):
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        text = (cmd.get("command_text") or "").strip().lower()
        if text == target or command_already_run([cmd], validation_step(hypothesis).command_text):
            return _command_succeeded(cmd.get("output_logs"))
    return False


def needs_validation(
    commands: list[dict[str, Any]],
    hypothesis: dict[str, Any] | None,
) -> bool:
    if not hypothesis:
        return False
    if last_fix_index(commands) < 0:
        return False
    return not validation_succeeded_after_fix(commands, hypothesis)


def next_validation_step(
    hypothesis: dict[str, Any],
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
) -> dict[str, str] | None:
    """Queue a post-fix verification command (re-check symptom or health)."""
    if not needs_validation(commands, hypothesis):
        return None
    if validation_attempted_after_fix(commands, hypothesis):
        return None
    step = validation_step(hypothesis)
    if not is_valid_shell_command(step.command_text):
        return None
    result = safety.evaluate(step.command_text)
    if not result.allowed:
        return None
    return _proposal_from_step(step, safety)


def next_plan_step(
    hypothesis: dict[str, Any],
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
    *,
    verifier_recommend: str | None = None,
) -> dict[str, str] | None:
    """Next unrun step on the selected hypothesis plan."""
    hyp = ensure_plan(hypothesis)
    for step in build_plan(hyp):
        if step.intent == "validate":
            continue
        if command_already_run(commands, step.command_text):
            continue
        if not is_valid_shell_command(step.command_text):
            continue
        if not _step_allowed(step, verifier_recommend):
            continue
        result = safety.evaluate(step.command_text)
        if not result.allowed:
            continue
        return _proposal_from_step(step, safety)
    return None


def next_plan_across_hypotheses(
    hypotheses: list[dict[str, Any]],
    selected_index: int,
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
    *,
    verifier_recommend: str | None = None,
    prefer_switch: bool = False,
) -> tuple[dict[str, str] | None, int | None]:
    if not hypotheses:
        return None, None

    indices = list(range(len(hypotheses)))
    if prefer_switch and len(indices) > 1:
        indices = [i for i in indices if i != selected_index] + [selected_index]

    for idx in indices:
        proposal = next_plan_step(
            hypotheses[idx],
            commands,
            safety,
            verifier_recommend=verifier_recommend,
        )
        if proposal:
            return proposal, idx
    return None, None


def next_universal_baseline(
    commands: list[dict[str, Any]],
    safety: SafetyLayer,
) -> dict[str, str] | None:
    """Last-resort safe diagnostics that work on any Linux VM."""
    for agent, command, diff in UNIVERSAL_BASELINE:
        if command_already_run(commands, command):
            continue
        if not is_valid_shell_command(command):
            continue
        result = safety.evaluate(command)
        if not result.allowed:
            continue
        return {
            "agent_name": agent,
            "command_text": command,
            "script_diff": diff,
            "safety_status": result.status,
            "human_status": "Pending",
            "output_logs": "",
            "agent_reasoning": "Universal baseline diagnostic (pipeline fallback).",
            "plan_intent": "diagnostic",
        }
    return None
