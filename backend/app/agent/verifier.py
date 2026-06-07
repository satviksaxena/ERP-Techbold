"""Verifier agent — independent check before fix commands (Plan-Execute-Verify)."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.command_validator import is_valid_shell_command
from app.agent.evidence import format_evidence_for_llm
from app.config import Settings

logger = logging.getLogger(__name__)


class VerifierResult(BaseModel):
    hypothesis_supported: bool = False
    recommend: str = Field(
        description="continue_diagnose | apply_fix | switch_path | validate | escalate"
    )
    evidence_summary: str = ""
    confidence: str = "low"


VERIFIER_SCHEMA = VerifierResult.model_json_schema()


def _mount_diagnostics_executed(commands: list[dict[str, Any]] | None) -> bool:
    for cmd in commands or []:
        if cmd.get("human_status") not in ("Approved", "Edited"):
            continue
        text = (cmd.get("command_text") or "").lower()
        if text.startswith("mount ") or "mount |" in text or "findmnt" in text:
            return True
    return False


def verify_rule_based(
    hypothesis: dict[str, Any] | None,
    evidence: dict[str, Any],
    *,
    diagnostic_count: int,
    has_fix: bool,
    report_text: str = "",
    commands: list[dict[str, Any]] | None = None,
) -> VerifierResult:
    """Fast deterministic verifier — no LLM required."""
    failed = evidence.get("failed_units") or []
    disabled = evidence.get("disabled_units") or []
    full_fs = evidence.get("full_filesystems") or []
    readonly = evidence.get("readonly_mounts") or []
    errors = evidence.get("error_lines") or []

    title = (hypothesis or {}).get("title", "").lower()
    root = (hypothesis or {}).get("likely_root_cause", "").lower()

    if has_fix:
        return VerifierResult(
            hypothesis_supported=True,
            recommend="validate",
            evidence_summary="Fix command already executed — proceed to validation.",
            confidence="high",
        )

    if diagnostic_count < 1:
        return VerifierResult(
            hypothesis_supported=False,
            recommend="continue_diagnose",
            evidence_summary="Need at least one diagnostic before applying a fix.",
            confidence="low",
        )

    service_hypothesis = any(
        k in title + root for k in ("service", "systemd", "boot", "enabled", "unit", "down")
    )
    perm_hypothesis = any(k in title + root for k in ("permission", "chown", "chmod", "owner"))
    disk_hypothesis = any(
        k in title + root
        for k in ("disk", "space", "full", "storage", "read-only", "readonly", "filesystem")
    )

    if service_hypothesis and (failed or disabled):
        units = failed or disabled
        return VerifierResult(
            hypothesis_supported=True,
            recommend="apply_fix",
            evidence_summary=f"Failed/disabled units detected: {', '.join(units[:5])}",
            confidence="high",
        )

    if disk_hypothesis and full_fs:
        return VerifierResult(
            hypothesis_supported=True,
            recommend="apply_fix",
            evidence_summary=f"Filesystem pressure: {full_fs[0][:80]}",
            confidence="medium",
        )

    if disk_hypothesis and readonly:
        return VerifierResult(
            hypothesis_supported=True,
            recommend="apply_fix",
            evidence_summary=f"Read-only mount detected: {readonly[0][:80]}",
            confidence="high",
        )

    if perm_hypothesis and errors and any("denied" in e.lower() or "permission" in e.lower() for e in errors):
        return VerifierResult(
            hypothesis_supported=True,
            recommend="apply_fix",
            evidence_summary="Permission errors in logs support this path.",
            confidence="medium",
        )

    if diagnostic_count >= 3 and not (failed or disabled or full_fs):
        report = (report_text or "").lower()
        if service_hypothesis and any(
            k in report for k in ("reboot", "boot", "unavailable", "8080", "enable", "restart")
        ):
            return VerifierResult(
                hypothesis_supported=True,
                recommend="apply_fix",
                evidence_summary=(
                    "Boot/reboot service symptom after diagnostics — apply systemctl enable --now fix."
                ),
                confidence="medium",
            )
        if disk_hypothesis and not readonly and not _mount_diagnostics_executed(commands):
            return VerifierResult(
                hypothesis_supported=False,
                recommend="continue_diagnose",
                evidence_summary="Disk/read-only path — inspect mount options before switching paths.",
                confidence="medium",
            )
        return VerifierResult(
            hypothesis_supported=False,
            recommend="switch_path",
            evidence_summary="Multiple diagnostics found no failed units or disk issues — consider another path.",
            confidence="medium",
        )

    return VerifierResult(
        hypothesis_supported=False,
        recommend="continue_diagnose",
        evidence_summary="Insufficient evidence to apply a fix yet.",
        confidence="low",
    )


class VerifierService:
    """Optional LLM-enhanced verifier on top of rule-based checks."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def llm_enabled(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def verify(
        self,
        ticket: dict[str, Any],
        hypothesis: dict[str, Any] | None,
        evidence: dict[str, Any],
        commands: list[dict[str, Any]],
    ) -> VerifierResult:
        executed = [c for c in commands if c.get("human_status") in ("Approved", "Edited")]
        diagnostic_count = len(
            [c for c in executed if not _looks_like_fix(c.get("command_text") or "")]
        )
        has_fix = any(
            _looks_like_fix(c.get("command_text") or "")
            and not _command_output_failed(c.get("output_logs") or "")
            for c in executed
        )
        public_test_failed = any(
            "public-test.sh" in (c.get("command_text") or "").lower()
            and c.get("human_status") in ("Approved", "Edited")
            and _command_output_failed(c.get("output_logs") or "")
            for c in commands
        )
        public_test_passed = any(
            "public-test.sh" in (c.get("command_text") or "").lower()
            and c.get("human_status") in ("Approved", "Edited")
            and not _command_output_failed(c.get("output_logs") or "")
            for c in commands
        )
        if public_test_failed and not public_test_passed:
            has_fix = False

        baseline = verify_rule_based(
            hypothesis,
            evidence,
            diagnostic_count=diagnostic_count,
            has_fix=has_fix,
            report_text=(ticket.get("report_text") or ""),
            commands=commands,
        )

        if not self.llm_enabled or baseline.confidence in ("high", "medium"):
            return baseline

        try:
            from google.genai import types

            prompt = f"""You are an independent Verifier agent. Do NOT propose shell commands.
Ticket: {ticket.get('title')}
Customer report: {(ticket.get('report_text') or '')[:1500]}
Selected hypothesis: {hypothesis.get('title') if hypothesis else 'none'}
Likely root cause: {hypothesis.get('likely_root_cause') if hypothesis else 'unknown'}

Structured evidence:
{format_evidence_for_llm(evidence)}

Rule-based recommendation: {baseline.recommend} ({baseline.evidence_summary})

Return JSON with: hypothesis_supported (bool), recommend (continue_diagnose|apply_fix|switch_path|validate|escalate),
evidence_summary (short), confidence (high|medium|low).
Only recommend apply_fix when evidence clearly supports the hypothesis."""

            client = self._get_client()
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_json_schema=VERIFIER_SCHEMA,
                ),
            )
            result = VerifierResult.model_validate(json.loads(response.text or "{}"))
            if result.recommend == "apply_fix" and not result.hypothesis_supported:
                result.recommend = "continue_diagnose"
            return result
        except Exception as exc:
            logger.warning("LLM verifier failed, using rules: %s", exc)
            return baseline


def _command_output_failed(output_logs: str | None) -> bool:
    output = (output_logs or "").lower()
    if "execution failed" in output:
        return True
    if "exit code:" in output and "exit code: 0" not in output:
        return True
    if "[exit " in output and "[exit 0]" not in output:
        return True
    return False


def _looks_like_fix(command_text: str) -> bool:
    from app.agent.command_intent import is_fix_command

    return is_fix_command(command_text) and is_valid_shell_command(command_text)
