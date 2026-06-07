"""SOP pipeline phases for the multi-agent troubleshooting workflow."""
from __future__ import annotations

from enum import Enum
from typing import Any


class PipelinePhase(str, Enum):
    INTAKE = "INTAKE"
    HYPOTHESIS_SELECTED = "HYPOTHESIS_SELECTED"
    DIAGNOSE = "DIAGNOSE"
    ROOT_CAUSE_CONFIRMED = "ROOT_CAUSE_CONFIRMED"
    FIX = "FIX"
    VALIDATE = "VALIDATE"
    DOCUMENT = "DOCUMENT"


def infer_phase(
    commands: list[dict[str, Any]],
    *,
    public_test_done: bool,
    needs_public_test: bool,
    verifier_recommend: str | None = None,
) -> PipelinePhase:
    if public_test_done:
        return PipelinePhase.DOCUMENT
    if needs_public_test:
        return PipelinePhase.VALIDATE

    executed = [c for c in commands if c.get("human_status") in ("Approved", "Edited")]
    if not executed:
        return PipelinePhase.HYPOTHESIS_SELECTED

    has_fix = any(_looks_like_fix(c.get("command_text") or "") for c in executed)
    if has_fix:
        return PipelinePhase.FIX

    if verifier_recommend == "apply_fix":
        return PipelinePhase.ROOT_CAUSE_CONFIRMED

    return PipelinePhase.DIAGNOSE


def agent_for_phase(phase: PipelinePhase) -> str:
    mapping = {
        PipelinePhase.INTAKE: "Problem Analyzer",
        PipelinePhase.HYPOTHESIS_SELECTED: "Problem Analyzer",
        PipelinePhase.DIAGNOSE: "Customer System Analyzer",
        PipelinePhase.ROOT_CAUSE_CONFIRMED: "Problem Solver",
        PipelinePhase.FIX: "Problem Solver",
        PipelinePhase.VALIDATE: "Problem Solver",
        PipelinePhase.DOCUMENT: "Activity Log Generator",
    }
    return mapping.get(phase, "Customer System Analyzer")


def _looks_like_fix(command_text: str) -> bool:
    t = command_text.lower().strip()
    if not t:
        return False
    markers = (
        "chmod",
        "chown",
        "systemctl restart",
        "systemctl start",
        "systemctl enable",
        "sed -i",
        "tee ",
        "mkdir -p",
    )
    return any(m in t for m in markers)
