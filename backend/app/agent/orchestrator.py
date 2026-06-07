from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from app.agent.azure_agent import AzureOpenAIAgent
from app.agent.evidence import extract_from_output, format_evidence_for_llm, merge_evidence
from app.agent.gemini_agent import GeminiAgentService
from app.agent.hypothesis_generator import HypothesisGenerator
from app.agent.hypothesis_ranker import rerank_hypotheses
from app.agent.llm_schemas import PUBLIC_TEST_COMMAND
from app.agent.phases import PipelinePhase, agent_for_phase, infer_phase
from app.agent.reflexion import command_already_failed, reflexion_context
from app.agent.runbooks import retrieve_runbooks
from app.agent.verifier import VerifierService
from app.activity.generator import generate_activity_draft
from app.audit.log import AuditLog
from app.config import Settings
from app.phoenix.client import PhoenixClient
from app.safety.layer import SafetyLayer
from app.ssh.key_resolver import discover_ssh_key, resolve_ssh_key_path
from app.ssh.runner import SSHError, SSHRunner, classify_ssh_failure
from app.store.hypothesis_store import HypothesisStore
from app.store.supabase_store import SupabaseStore

logger = logging.getLogger(__name__)

_RESUME_COOLDOWN_SECONDS = 15.0
_last_resume_at: dict[str, float] = {}

AGENTS = [
    "Problem Analyzer",
    "Customer System Analyzer",
    "Problem Solver",
    "Activity Log Generator",
]

# Read-only diagnostics first, then common fix patterns (LLM can override)
DIAGNOSTIC_COMMANDS = [
    ("Problem Analyzer", "uptime && hostname", "+ gather host identity"),
    ("Problem Analyzer", "systemctl --failed --no-pager", "+ list failed systemd units"),
    ("Customer System Analyzer", "df -h", "+ check disk usage"),
    ("Customer System Analyzer", "free -m", "+ check memory"),
    ("Customer System Analyzer", "ss -tlnp | head -30", "+ inspect listening ports"),
    ("Customer System Analyzer", "journalctl -p err -n 30 --no-pager", "+ recent error logs"),
]


class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        store: SupabaseStore,
        phoenix: PhoenixClient | None,
        ssh: SSHRunner,
        safety: SafetyLayer,
        audit: AuditLog,
    ):
        self.settings = settings
        self.store = store
        self.phoenix = phoenix
        self.ssh = ssh
        self.safety = safety
        self.audit = audit
        self._run_started: dict[str, str] = {}
        self._ssh_key_by_ticket: dict[str, str] = {}
        self._system_notes_by_ticket: dict[str, str] = {}
        self.hypothesis_store = HypothesisStore(store)
        self.hypothesis_generator = HypothesisGenerator(settings, safety)
        self.azure = AzureOpenAIAgent(settings, safety)
        self.gemini = GeminiAgentService(settings, safety)
        self.verifier = VerifierService(settings)

    def sync_tickets(self) -> list[dict[str, Any]]:
        if not self.phoenix:
            raise RuntimeError("Phoenix client not configured")
        phoenix_tickets = sorted(self.phoenix.list_tickets(sort="date"), key=lambda t: int(t["id"]))
        synced: list[dict[str, Any]] = []
        for idx, pt in enumerate(phoenix_tickets):
            row = self.store.upsert_ticket_from_phoenix(pt)
            try:
                cs = self.phoenix.get_customer_system(int(pt["id"]))
                system = cs.get("system", cs)
                notes = system.get("notes", "") if isinstance(system, dict) else ""
                self._system_notes_by_ticket[row["id"]] = notes
                key_path = resolve_ssh_key_path(
                    self.settings,
                    ticket=row,
                    ticket_index=idx,
                    system_notes=notes,
                )
                self._ssh_key_by_ticket[row["id"]] = key_path
                self.store.upsert_system_info(row["id"], system)
            except Exception as exc:
                self.audit.record("sync_system_info_failed", ticket_id=row["id"], error=str(exc))
            synced.append(row)

        phoenix_codes = {str(pt["id"]) for pt in phoenix_tickets}
        removed = self.store.delete_tickets_not_in_codes(phoenix_codes)
        if removed:
            self.audit.record("sync_removed_stale_tickets", count=removed)

        self.audit.record("sync_tickets", count=len(synced), removed=removed)
        return synced

    def start_analysis(self, ticket_uuid: str) -> dict[str, Any]:
        ticket = self.store.get_ticket(ticket_uuid)
        if not ticket:
            raise ValueError("Ticket not found")

        existing_pending = [c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"]
        if existing_pending:
            return existing_pending[0]

        from datetime import datetime, timezone

        self._run_started[ticket_uuid] = datetime.now(timezone.utc).isoformat()

        self.store.update_ticket(ticket_uuid, status="Analyzing", active_agent="Problem Analyzer")
        self.audit.record("analysis_started", ticket_id=ticket_uuid, ticket_code=ticket["ticket_code"])

        sys_info = self.store.get_system_info(ticket_uuid)
        self._try_connect_ssh(ticket_uuid, ticket, sys_info)

        if not self.hypothesis_store.get(ticket_uuid):
            self.generate_hypotheses(ticket_uuid)

        proposal = self._next_proposal(ticket)
        cmd_row = self.store.insert_command(ticket_uuid, **proposal)
        self.store.update_ticket(ticket_uuid, status="Troubleshooting", active_agent=proposal["agent_name"])
        return cmd_row

    def generate_hypotheses(self, ticket_uuid: str) -> dict[str, Any]:
        ticket = self.store.get_ticket(ticket_uuid)
        if not ticket:
            raise ValueError("Ticket not found")
        sys_info = self.store.get_system_info(ticket_uuid)
        items = self.hypothesis_generator.generate(ticket, sys_info)
        saved = self.hypothesis_store.save(
            ticket_uuid,
            items["hypotheses"],
            selected_index=0,
            reasoning_summary=items.get("reasoning_summary") or "",
        )
        if items.get("reasoning_summary"):
            self.audit.record(
                "ticket_reasoning",
                ticket_id=ticket_uuid,
                model=items.get("thinking_model", ""),
                level=items.get("thinking_level", ""),
                summary=(items.get("reasoning_summary") or "")[:500],
            )
        return saved

    def get_hypotheses(self, ticket_uuid: str) -> dict[str, Any]:
        data = self.hypothesis_store.get(ticket_uuid)
        if data:
            return data
        return {
            "hypotheses": [],
            "selected_index": 0,
            "reasoning_summary": "",
            "pipeline_state": {},
        }

    def _selected_hypothesis(self, ticket_uuid: str) -> dict[str, Any] | None:
        data = self.hypothesis_store.get(ticket_uuid)
        if not data:
            return None
        hypotheses = data.get("hypotheses") or []
        idx = data.get("selected_index", 0)
        if not hypotheses or idx >= len(hypotheses):
            return None
        return hypotheses[idx]

    def _pipeline_evidence(self, ticket_uuid: str) -> dict[str, Any]:
        data = self.hypothesis_store.get(ticket_uuid) or {}
        state = data.get("pipeline_state") or {}
        return state.get("evidence") or {}

    def _post_command_pipeline_update(
        self,
        ticket_uuid: str,
        ticket: dict[str, Any],
        latest_command: dict[str, Any],
        all_commands: list[dict[str, Any]],
    ) -> None:
        """Extract evidence, verify, re-rank hypotheses, update pipeline phase."""
        if latest_command.get("human_status") not in ("Approved", "Edited"):
            return

        patch = extract_from_output(
            latest_command.get("command_text") or "",
            latest_command.get("output_logs") or "",
        )
        evidence = merge_evidence(self._pipeline_evidence(ticket_uuid), patch)

        data = self.hypothesis_store.get(ticket_uuid) or {}
        hypotheses = list(data.get("hypotheses") or [])
        selected_index = data.get("selected_index", 0)
        hypothesis = hypotheses[selected_index] if hypotheses and selected_index < len(hypotheses) else None

        if hypotheses:
            hypotheses = rerank_hypotheses(hypotheses, evidence, selected_index)
            self.hypothesis_store.save(
                ticket_uuid,
                hypotheses,
                selected_index,
                data.get("reasoning_summary") or "",
                pipeline_state={**(data.get("pipeline_state") or {}), "evidence": evidence},
            )

        verification = self.verifier.verify(ticket, hypothesis, evidence, all_commands)
        phase = infer_phase(
            all_commands,
            public_test_done=self._public_test_done(all_commands),
            needs_public_test=self._needs_public_test(all_commands),
            verifier_recommend=verification.recommend,
        )

        self.hypothesis_store.update_pipeline_state(
            ticket_uuid,
            evidence=evidence,
            phase=phase.value,
            verifier={
                "recommend": verification.recommend,
                "summary": verification.evidence_summary,
                "confidence": verification.confidence,
                "hypothesis_supported": verification.hypothesis_supported,
            },
        )
        self.audit.record(
            "pipeline_verified",
            ticket_id=ticket_uuid,
            phase=phase.value,
            recommend=verification.recommend,
            summary=(verification.evidence_summary or "")[:200],
        )
        self.store.update_ticket(ticket_uuid, active_agent=agent_for_phase(phase))

    def select_hypothesis(self, ticket_uuid: str, index: int) -> dict[str, Any]:
        data = self.hypothesis_store.select(ticket_uuid, index)
        cmd = self._sync_command_to_selected_path(ticket_uuid, data)
        result = {**data}
        if cmd:
            result["command"] = cmd
        return result

    def _sync_command_to_selected_path(
        self, ticket_uuid: str, hypothesis_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Align the pending human-in-the-loop command with the selected pathway."""
        hypotheses = hypothesis_data.get("hypotheses") or []
        idx = hypothesis_data.get("selected_index", 0)
        if not hypotheses or idx >= len(hypotheses):
            return None

        h = hypotheses[idx]
        first_cmd = (h.get("first_command") or "").strip()
        if not first_cmd:
            return None

        existing = self.store.list_commands(ticket_uuid)
        pending = [c for c in existing if c.get("human_status") == "Pending"]
        title = h.get("title") or f"path {idx + 1}"

        if pending:
            pending_cmd = pending[0]
            pending_text = (pending_cmd.get("command_text") or "").strip()
            if (
                pending_text != first_cmd
                and not self._is_public_test(pending_cmd)
                and any(
                    c.get("human_status") in ("Approved", "Edited", "Rejected")
                    for c in existing
                )
            ):
                # Gate already advanced past step 1 — don't rewind on resume/select.
                return pending_cmd

        # Don't rewind to the pathway's first diagnostic after it already ran.
        if self._command_text_executed(existing, first_cmd):
            ticket = self.store.get_ticket(ticket_uuid)
            if not ticket:
                return None
            proposal = self._propose_next_for_path(ticket, h, existing)
            if not proposal:
                return None
            cmd = self._upsert_pending_command(ticket_uuid, proposal, pending)
            if cmd:
                self.audit.record(
                    "hypothesis_advanced",
                    ticket_id=ticket_uuid,
                    index=idx,
                    title=title,
                    command=proposal.get("command_text"),
                )
            return cmd

        safety = self.safety.evaluate(first_cmd)
        if not safety.allowed:
            self.audit.record(
                "hypothesis_command_blocked",
                ticket_id=ticket_uuid,
                index=idx,
                command=first_cmd,
                reason=safety.reason,
            )
            return None

        proposal = {
            "agent_name": "Problem Solver",
            "command_text": first_cmd,
            "script_diff": f"+ {title}",
            "safety_status": safety.status,
            "human_status": "Pending",
            "output_logs": "",
        }
        cmd = self._upsert_pending_command(ticket_uuid, proposal, pending)
        self.audit.record(
            "hypothesis_selected",
            ticket_id=ticket_uuid,
            index=idx,
            title=title,
            command=first_cmd,
        )
        return cmd

    @staticmethod
    def _command_text_executed(commands: list[dict[str, Any]], command_text: str) -> bool:
        normalized = command_text.strip()
        return any(
            c.get("human_status") in ("Approved", "Edited")
            and (c.get("command_text") or "").strip() == normalized
            for c in commands
        )

    def _upsert_pending_command(
        self,
        ticket_uuid: str,
        proposal: dict[str, str],
        pending: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if pending is None:
            pending = [c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"]
        if pending:
            fields = {
                "agent_name": proposal["agent_name"],
                "command_text": proposal["command_text"],
                "script_diff": proposal["script_diff"],
                "safety_status": proposal["safety_status"],
            }
            if proposal.get("agent_reasoning"):
                fields["agent_reasoning"] = proposal["agent_reasoning"]
            return self.store.update_command(pending[0]["id"], **fields)
        cmd = self.store.insert_command(ticket_uuid, **proposal)
        self.store.update_ticket(
            ticket_uuid,
            status="Troubleshooting",
            active_agent=proposal["agent_name"],
        )
        return cmd

    def connect_ssh(self, ticket_uuid: str) -> dict[str, str]:
        ticket = self.store.get_ticket(ticket_uuid)
        if not ticket:
            raise ValueError("Ticket not found")
        sys_info = self.store.get_system_info(ticket_uuid)
        if not sys_info or not sys_info.get("host_ip"):
            raise ValueError("No system info for ticket")
        status = self._try_connect_ssh(ticket_uuid, ticket, sys_info)
        return {"connection_status": status}

    def _try_connect_ssh(
        self,
        ticket_uuid: str,
        ticket: dict[str, Any] | None,
        sys_info: dict[str, Any] | None,
    ) -> str:
        if not sys_info or not sys_info.get("host_ip"):
            return "Idle"

        host = sys_info["host_ip"]
        port = int(sys_info.get("port", 22))
        username = sys_info.get("username", "azureuser")
        preferred = self._ssh_key_for(ticket_uuid, ticket, sys_info)

        payload = {
            "ip": host,
            "username": username,
            "port": port,
            "os": sys_info.get("os_version", "Ubuntu"),
        }

        try:
            self.ssh.test_connection(host, port, key_path=preferred)
            self.store.upsert_system_info(ticket_uuid, payload, connection_status="Connected")
            return "Connected"
        except SSHError as exc:
            if classify_ssh_failure(exc) != "auth":
                self.store.upsert_system_info(ticket_uuid, payload, connection_status="Failed")
                self.audit.record("ssh_connect_failed", ticket_id=ticket_uuid, error=str(exc))
                return "Failed"
            try:
                discovered = discover_ssh_key(
                    self.settings,
                    host,
                    port,
                    username=username,
                    preferred_keys=[preferred],
                )
                self._ssh_key_by_ticket[ticket_uuid] = discovered
                self.ssh.test_connection(host, port, key_path=discovered)
                self.store.upsert_system_info(ticket_uuid, payload, connection_status="Connected")
                self.audit.record(
                    "ssh_key_discovered",
                    ticket_id=ticket_uuid,
                    host=host,
                    key=discovered,
                )
                return "Connected"
            except SSHError as exc:
                self.store.upsert_system_info(ticket_uuid, payload, connection_status="Failed")
                self.audit.record("ssh_connect_failed", ticket_id=ticket_uuid, error=str(exc))
                return "Failed"

    def _propose_for_hypothesis_path(
        self,
        ticket: dict[str, Any],
        hypothesis: dict[str, Any],
        existing: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        """Propose the next command for the selected pathway (not a generic pipeline step)."""
        hypothesis_ctx = (
            f"\nTechnician committed to pathway: {hypothesis.get('title')}\n"
            f"Likely root cause: {hypothesis.get('likely_root_cause')}\n"
            f"Fix strategy: {hypothesis.get('fix_strategy')}\n"
            f"Pathway first command: {hypothesis.get('first_command')}\n"
            "The first command may already be executed. Propose the NEXT single shell command "
            "that continues THIS pathway toward the fix strategy. Do not restart unrelated diagnostics."
        )
        sys_info = self.store.get_system_info(ticket["id"])
        return self._filter_proposal(
            self._llm_propose_next(ticket, existing, sys_info, hypothesis_ctx),
            existing,
        )

    def _propose_next_for_path(
        self,
        ticket: dict[str, Any],
        hypothesis: dict[str, Any],
        existing: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        proposal = self._propose_for_hypothesis_path(ticket, hypothesis, existing)
        if not proposal:
            proposal = self._command_from_fix_strategy(hypothesis)
        if not proposal:
            proposal = self._next_proposal(ticket)
        return proposal

    def _filter_proposal(
        self,
        proposal: dict[str, str] | None,
        existing: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        if not proposal:
            return None
        if self._is_public_test(proposal) and not self._needs_public_test(existing):
            return None
        if self._is_public_test(proposal) and self._public_test_done(existing):
            return None
        return proposal

    def _command_from_fix_strategy(self, hypothesis: dict[str, Any]) -> dict[str, str] | None:
        """Extract a concrete chown/chmod (etc.) command from pathway fix_strategy text."""
        import re

        strategy = hypothesis.get("fix_strategy") or ""
        title = hypothesis.get("title") or "path fix"
        candidates: list[str] = []
        candidates.extend(re.findall(r"`([^`]+)`", strategy))
        for line in strategy.splitlines():
            stripped = line.strip().lstrip("-•*").strip()
            if self._looks_like_fix(stripped):
                candidates.append(stripped)

        for raw in candidates:
            cmd = raw.strip()
            if not cmd:
                continue
            if not cmd.startswith("sudo") and any(
                token in cmd.lower() for token in ("chown", "chmod", "systemctl", "setfacl")
            ):
                cmd = f"sudo {cmd}"
            if not self._looks_like_fix(cmd):
                continue
            safety = self.safety.evaluate(cmd)
            if not safety.allowed:
                continue
            return {
                "agent_name": "Problem Solver",
                "command_text": cmd,
                "script_diff": f"+ {title}: apply fix from pathway strategy",
                "safety_status": safety.status,
                "human_status": "Pending",
                "output_logs": "",
            }
        return None

    def _next_proposal(self, ticket: dict[str, Any]) -> dict[str, str] | None:
        existing = self.store.list_commands(ticket["id"])
        if self._public_test_done(existing):
            return None

        sys_info = self.store.get_system_info(ticket["id"])
        hypothesis_ctx = self._selected_hypothesis_context(ticket["id"])

        if self._needs_public_test(existing):
            safety = self.safety.evaluate(PUBLIC_TEST_COMMAND)
            return {
                "agent_name": "Problem Solver",
                "command_text": PUBLIC_TEST_COMMAND,
                "script_diff": "+ hackathon validation (public-test.sh)",
                "safety_status": safety.status,
                "human_status": "Pending",
                "output_logs": "",
            }

        proposal = self._llm_propose_next(ticket, existing, sys_info, hypothesis_ctx)
        return self._filter_proposal(proposal, existing)

    def _llm_propose_next(
        self,
        ticket: dict[str, Any],
        existing: list[dict[str, Any]],
        sys_info: dict[str, Any] | None,
        hypothesis_ctx: str,
    ) -> dict[str, str] | None:
        ticket_uuid = ticket["id"]
        evidence = self._pipeline_evidence(ticket_uuid)
        data = self.hypothesis_store.get(ticket_uuid) or {}
        state = data.get("pipeline_state") or {}
        verifier_data = state.get("verifier") or {}
        hypothesis = self._selected_hypothesis(ticket_uuid)

        verification = self.verifier.verify(ticket, hypothesis, evidence, existing)
        phase = infer_phase(
            existing,
            public_test_done=self._public_test_done(existing),
            needs_public_test=self._needs_public_test(existing),
            verifier_recommend=verification.recommend,
        )
        target_agent = agent_for_phase(phase)

        ctx_kwargs = {
            "target_agent": target_agent,
            "evidence_context": f"\nStructured evidence:\n{format_evidence_for_llm(evidence)}",
            "verifier_context": (
                f"\nVerifier ({verification.confidence}): {verification.recommend} — "
                f"{verification.evidence_summary}"
            ),
            "runbook_context": retrieve_runbooks(ticket, hypothesis),
            "reflexion_context": reflexion_context(existing),
            "phase": phase.value,
        }

        primary = (self.settings.llm_primary or "gemini").lower()
        order = (
            [("gemini", self.gemini), ("azure", self.azure)]
            if primary == "gemini"
            else [("azure", self.azure), ("gemini", self.gemini)]
        )
        proposal: dict[str, str] | None = None
        for name, agent in order:
            if not agent.enabled:
                continue
            try:
                proposal = agent.propose_next_command(
                    ticket,
                    existing,
                    sys_info,
                    hypothesis_context=hypothesis_ctx,
                    **ctx_kwargs,
                )
                if proposal:
                    proposal.pop("_ready_for_activity", None)
                    proposal.pop("_reasoning", None)
                    break
            except Exception as exc:
                self.audit.record(f"{name}_proposal_failed", ticket_id=ticket["id"], error=str(exc))

        if not proposal and self.settings.openai_api_key:
            llm_cmd = self._openai_propose(ticket, existing)
            if llm_cmd:
                safety = self.safety.evaluate(llm_cmd["command_text"])
                proposal = {
                    "agent_name": llm_cmd.get("agent_name", target_agent),
                    "command_text": llm_cmd["command_text"],
                    "script_diff": llm_cmd.get("script_diff", f"+ {llm_cmd['command_text']}"),
                    "safety_status": safety.status,
                    "human_status": "Pending",
                    "output_logs": "",
                    "agent_reasoning": llm_cmd.get("reasoning", ""),
                }

        if not proposal:
            proposal = self._fallback_proposal(existing, phase, verification)
        if not proposal:
            return None

        enforced = self._enforce_verifier_and_reflexion(proposal, existing, verification, phase)
        if enforced:
            return enforced
        return self._fallback_proposal(existing, phase, verification)

    def _fallback_proposal(
        self,
        existing: list[dict[str, Any]],
        phase: PipelinePhase,
        verification: Any,
    ) -> dict[str, str] | None:
        if self._needs_public_test(existing):
            safety = self.safety.evaluate(PUBLIC_TEST_COMMAND)
            return {
                "agent_name": "Problem Solver",
                "command_text": PUBLIC_TEST_COMMAND,
                "script_diff": "+ hackathon validation (public-test.sh)",
                "safety_status": safety.status,
                "human_status": "Pending",
                "output_logs": "",
                "agent_reasoning": "Validation required after fix — run public-test.sh.",
            }

        pending_or_done = len([c for c in existing if c.get("human_status") in ("Approved", "Edited")])
        if pending_or_done < len(DIAGNOSTIC_COMMANDS) and phase in (
            PipelinePhase.DIAGNOSE,
            PipelinePhase.HYPOTHESIS_SELECTED,
        ):
            agent, command, diff = DIAGNOSTIC_COMMANDS[pending_or_done]
            if not command_already_failed(existing, command):
                safety = self.safety.evaluate(command)
                return {
                    "agent_name": agent,
                    "command_text": command,
                    "script_diff": diff,
                    "safety_status": safety.status,
                    "human_status": "Pending",
                    "output_logs": "",
                    "agent_reasoning": "Fallback diagnostic sequence.",
                }

        return None

    def _enforce_verifier_and_reflexion(
        self,
        proposal: dict[str, str],
        existing: list[dict[str, Any]],
        verification: Any,
        phase: PipelinePhase,
    ) -> dict[str, str] | None:
        cmd_text = (proposal.get("command_text") or "").strip()
        if not cmd_text:
            return None

        if command_already_failed(existing, cmd_text):
            self.audit.record(
                "reflexion_blocked_repeat",
                command=cmd_text,
            )
            return None

        is_fix = self._looks_like_fix(cmd_text)
        if is_fix and verification.recommend in ("continue_diagnose", "switch_path"):
            self.audit.record(
                "verifier_blocked_fix",
                command=cmd_text,
                recommend=verification.recommend,
            )
            return None

        if phase in (PipelinePhase.DIAGNOSE, PipelinePhase.HYPOTHESIS_SELECTED) and is_fix:
            if verification.recommend != "apply_fix":
                self.audit.record("verifier_blocked_premature_fix", command=cmd_text)
                return None

        proposal["agent_name"] = proposal.get("agent_name") or agent_for_phase(phase)
        return proposal

    @staticmethod
    def _is_public_test(cmd: dict[str, Any]) -> bool:
        return "public-test.sh" in (cmd.get("command_text") or "").lower()

    @staticmethod
    def _is_executed(cmd: dict[str, Any]) -> bool:
        return cmd.get("human_status") in ("Approved", "Edited")

    @staticmethod
    def _public_test_done(commands: list[dict[str, Any]]) -> bool:
        for c in commands:
            if not AgentOrchestrator._is_public_test(c) or not AgentOrchestrator._is_executed(c):
                continue
            output = (c.get("output_logs") or "").lower()
            if "exit code: 0" in output:
                return True
        return False

    @staticmethod
    def _looks_like_fix(command_text: str) -> bool:
        """True for mutating/repair commands — not read-only diagnostics."""
        t = (command_text or "").lower().strip()
        if not t:
            return False
        fix_markers = (
            "chmod",
            "chown",
            "chgrp",
            "setfacl",
            "restorecon",
            "systemctl restart",
            "systemctl start",
            "systemctl enable",
            "service ",
            " restart",
            " reload",
            "setval(",
            "sed -i",
            "tee ",
            "mkdir -p",
            "install -",
            "truncate",
            "kill ",
            "pkill ",
        )
        if any(m in t for m in fix_markers):
            return True
        if ">" in t and any(p in t for p in ("/etc/", "/var/", "/opt/")):
            return True
        return False

    def _executed_fix_commands(self, commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            c
            for c in commands
            if self._is_executed(c)
            and not self._is_public_test(c)
            and self._looks_like_fix(c.get("command_text") or "")
        ]

    def _needs_public_test(self, commands: list[dict[str, Any]]) -> bool:
        """Propose public-test only after a fix command, and not again until a new fix runs."""
        if self._public_test_done(commands):
            return False

        approved_fixes = self._executed_fix_commands(commands)
        if not approved_fixes:
            return False

        last_public_test: dict[str, Any] | None = None
        last_public_test_idx = -1
        for i, c in enumerate(commands):
            if self._is_public_test(c) and self._is_executed(c):
                last_public_test = c
                last_public_test_idx = i

        if last_public_test is None:
            return True

        output = (last_public_test.get("output_logs") or "").lower()
        if "exit code: 0" in output:
            return False

        # Failed validation — wait for a new fix command after the last public-test run.
        fixes_after_failure = [
            c
            for c in commands[last_public_test_idx + 1 :]
            if self._is_executed(c)
            and not self._is_public_test(c)
            and self._looks_like_fix(c.get("command_text") or "")
        ]
        return len(fixes_after_failure) >= 1

    def _selected_hypothesis_context(self, ticket_uuid: str) -> str:
        data = self.hypothesis_store.get(ticket_uuid)
        if not data:
            return ""
        hypotheses = data.get("hypotheses") or []
        idx = data.get("selected_index", 0)
        if not hypotheses or idx >= len(hypotheses):
            return ""
        h = hypotheses[idx]
        return (
            f"\nTechnician selected approach: {h.get('title')}\n"
            f"Hypothesis: {h.get('likely_root_cause')}\n"
            f"Strategy: {h.get('fix_strategy')}\n"
            f"Suggested first command for this path: {h.get('first_command')}"
        )

    def _openai_propose(self, ticket: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, str] | None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.settings.openai_api_key)
            history = [
                {
                    "role": "user" if c.get("human_status") != "Pending" else "assistant",
                    "content": f"{c.get('agent_name')}: {c.get('command_text')}\nOutput:\n{c.get('output_logs', '')}",
                }
                for c in existing[-8:]
            ]
            prompt = f"""You are an IT service desk AI assistant troubleshooting a Linux VM over SSH.
Ticket: {ticket.get('title')}
Customer report: {ticket.get('report_text')}

Propose ONE safe diagnostic or fix shell command. Never propose destructive commands (rm -rf /, chmod -R 777, DROP DATABASE, disable firewall).
Respond as JSON: {{"agent_name": "...", "command_text": "...", "script_diff": "+ ..."}}

Previous commands and outputs are in the conversation."""
            messages = [{"role": "system", "content": prompt}, *history]
            resp = client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            if data.get("command_text"):
                return data
        except Exception as exc:
            self.audit.record("llm_proposal_failed", ticket_id=ticket["id"], error=str(exc))
        return None

    def _approve_command_core(
        self,
        command_id: str,
        edited_command: str | None = None,
    ) -> tuple[dict[str, Any], str, bool]:
        cmd = self.store.get_command(command_id)
        if not cmd:
            raise ValueError("Command not found")
        if cmd.get("human_status") != "Pending":
            raise ValueError("Command already processed")

        command_text = (edited_command or cmd["command_text"]).strip()
        safety = self.safety.evaluate(command_text)
        if not safety.allowed:
            self.store.update_command(command_id, safety_status="Blocked", human_status="Rejected")
            raise ValueError(f"Command blocked: {safety.reason}")

        ticket_uuid = cmd["ticket_id"]
        ticket = self.store.get_ticket(ticket_uuid)
        sys_info = self.store.get_system_info(ticket_uuid)
        key_path = self._ssh_key_for(ticket_uuid, ticket, sys_info)

        human_status = "Edited" if edited_command and edited_command.strip() != cmd["command_text"].strip() else "Approved"

        output = ""
        if sys_info and sys_info.get("host_ip"):
            host = sys_info["host_ip"]
            port = int(sys_info.get("port", 22))
            username = sys_info.get("username", "azureuser")
            payload = {
                "ip": host,
                "username": username,
                "port": port,
                "os": sys_info.get("os_version", "Ubuntu"),
            }
            if sys_info.get("system_notes"):
                payload["notes"] = sys_info["system_notes"]
            try:
                result = self._run_ssh_command(
                    ticket_uuid, host, port, username, command_text, key_path
                )
                output = self.ssh.format_output(result)
                self.store.upsert_system_info(ticket_uuid, payload, connection_status="Connected")
                self.audit.record(
                    "command_executed",
                    ticket_id=ticket_uuid,
                    command=command_text,
                    exit_code=result.exit_code,
                )
            except (SSHError, Exception) as exc:
                output = f"+ execution failed\n{exc}"
                self.store.upsert_system_info(ticket_uuid, payload, connection_status="Failed")
                self.audit.record("command_failed", ticket_id=ticket_uuid, command=command_text, error=str(exc))
        else:
            output = f"+ SSH not connected — simulated output\n$ {command_text}\n[mock] command would run on {sys_info.get('host_ip') if sys_info else 'unknown'}"

        updated = self.store.update_command(
            command_id,
            command_text=command_text,
            human_status=human_status,
            safety_status=safety.status,
            output_logs=output,
        )

        all_commands = self.store.list_commands(ticket_uuid)
        validation_passed = self._public_test_done(all_commands)

        if ticket:
            self._post_command_pipeline_update(ticket_uuid, ticket, updated, all_commands)

        if validation_passed:
            self.store.update_ticket(ticket_uuid, status="Fixed", active_agent="Activity Log Generator")
            self.audit.record(
                "validation_passed",
                ticket_id=ticket_uuid,
                command=command_text,
            )
        else:
            self.store.update_ticket(ticket_uuid, status="Validating", active_agent="Activity Log Generator")

        return updated, ticket_uuid, validation_passed

    def _dedupe_pending_commands(self, ticket_uuid: str) -> None:
        """Keep only the newest pending command — stale duplicates confuse the command gate."""
        pending = [
            c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"
        ]
        if len(pending) <= 1:
            return
        pending.sort(key=lambda c: c.get("created_at") or "")
        for stale in pending[:-1]:
            self.store.update_command(stale["id"], human_status="Rejected")
            self.audit.record(
                "duplicate_pending_rejected",
                ticket_id=ticket_uuid,
                command=stale.get("command_text"),
            )

    def approve_followup(self, ticket_uuid: str, validation_passed: bool) -> None:
        """Regenerate activity draft and optionally queue the next command (slow LLM work)."""
        self._dedupe_pending_commands(ticket_uuid)
        ticket = self.store.get_ticket(ticket_uuid)
        self._refresh_activity_draft(ticket_uuid)
        if ticket and not validation_passed:
            all_commands = self.store.list_commands(ticket_uuid)
            if all_commands:
                last = all_commands[-1]
                if self._is_executed(last) and self._command_output_failed(last.get("output_logs")):
                    return
            next_cmd = self._next_proposal(ticket)
            next_cmd = self._filter_proposal(next_cmd, all_commands)
            existing_pending = [
                c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"
            ]
            if not existing_pending and next_cmd:
                self.store.insert_command(ticket_uuid, **next_cmd)
                self.store.update_ticket(ticket_uuid, active_agent=next_cmd["agent_name"])

    def resume_pipeline(self, ticket_uuid: str) -> dict[str, Any]:
        """Unstick workbench when follow-up was lost (e.g. uvicorn --reload during approve)."""
        now = time.monotonic()
        last = _last_resume_at.get(ticket_uuid, 0.0)
        if now - last < _RESUME_COOLDOWN_SECONDS:
            return {"resumed": False, "reason": "rate_limited"}
        _last_resume_at[ticket_uuid] = now

        self._dedupe_pending_commands(ticket_uuid)
        commands = self.store.list_commands(ticket_uuid)
        if not commands:
            return {"resumed": False, "reason": "no_commands"}

        validation_passed = self._public_test_done(commands)
        pending = [c for c in commands if c.get("human_status") == "Pending"]
        executed = [c for c in commands if self._is_executed(c)]

        if validation_passed and any(self._is_public_test(c) for c in pending):
            result = self.reconcile_validation_state(ticket_uuid)
            return {"resumed": True, "action": "reconcile_validation", **result}

        if pending and self._is_public_test(pending[0]) and not self._needs_public_test(commands):
            data = self.hypothesis_store.get(ticket_uuid)
            if data and data.get("hypotheses"):
                cmd = self._sync_command_to_selected_path(ticket_uuid, data)
                if cmd:
                    self.audit.record(
                        "premature_public_test_replaced",
                        ticket_id=ticket_uuid,
                        command=cmd.get("command_text"),
                    )
                    return {
                        "resumed": True,
                        "action": "replaced_premature_public_test",
                        "command": cmd.get("command_text"),
                    }

        if executed and not pending and not validation_passed:
            last = executed[-1]
            if self._command_output_failed(last.get("output_logs")):
                return {"resumed": False, "reason": "awaiting_retry_after_failure"}
            threading.Thread(
                target=self._approve_followup_background,
                args=(ticket_uuid, validation_passed),
                daemon=True,
            ).start()
            self.audit.record("pipeline_resumed", ticket_id=ticket_uuid)
            return {"resumed": True, "action": "approve_followup_async"}

        return {"resumed": False, "reason": "pipeline_ok"}

    def _approve_followup_background(self, ticket_uuid: str, validation_passed: bool) -> None:
        try:
            self.approve_followup(ticket_uuid, validation_passed)
        except Exception as exc:
            logger.warning("Background approve_followup failed for %s: %s", ticket_uuid, exc)
            self.audit.record("approve_followup_failed", ticket_id=ticket_uuid, error=str(exc))

    def approve_command(self, command_id: str, edited_command: str | None = None) -> dict[str, Any]:
        updated, ticket_uuid, validation_passed = self._approve_command_core(command_id, edited_command)
        if self._command_output_failed(updated.get("output_logs")):
            self._refresh_activity_draft(ticket_uuid)
            return updated
        self.approve_followup(ticket_uuid, validation_passed)
        return updated

    def reject_command(self, command_id: str) -> dict[str, Any]:
        cmd = self.store.get_command(command_id)
        if not cmd:
            raise ValueError("Command not found")
        updated = self.store.update_command(command_id, human_status="Rejected")
        self.audit.record("command_rejected", ticket_id=cmd["ticket_id"], command=cmd.get("command_text"))

        ticket_uuid = cmd["ticket_id"]
        ticket = self.store.get_ticket(ticket_uuid)
        if ticket:
            existing_pending = [
                c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"
            ]
            if not existing_pending:
                next_cmd = self._next_proposal(ticket)
                if next_cmd:
                    self.store.insert_command(ticket_uuid, **next_cmd)
                    self.store.update_ticket(ticket_uuid, active_agent=next_cmd["agent_name"])

        return updated

    @staticmethod
    def _command_output_failed(output_logs: str | None) -> bool:
        output = (output_logs or "").lower()
        if "execution failed" in output:
            return True
        if "exit code:" in output and "exit code: 0" not in output:
            return True
        if "[exit " in output and "[exit 0]" not in output:
            return True
        return False

    def retry_command(self, command_id: str) -> dict[str, Any]:
        """Re-queue a failed executed command for another human-approved attempt."""
        cmd = self.store.get_command(command_id)
        if not cmd:
            raise ValueError("Command not found")
        if cmd.get("human_status") not in ("Approved", "Edited"):
            raise ValueError("Only executed commands can be retried")
        if not self._command_output_failed(cmd.get("output_logs")):
            raise ValueError("Command did not fail — retry is not needed")

        ticket_uuid = cmd["ticket_id"]
        command_text = (cmd.get("command_text") or "").strip()
        if not command_text:
            raise ValueError("Empty command text")

        safety = self.safety.evaluate(command_text)
        if not safety.allowed:
            raise ValueError(f"Command blocked: {safety.reason}")

        proposal = {
            "agent_name": cmd.get("agent_name") or "Problem Solver",
            "command_text": command_text,
            "script_diff": f"+ retry: {command_text[:80]}",
            "safety_status": safety.status,
            "human_status": "Pending",
            "output_logs": "",
        }

        self._dedupe_pending_commands(ticket_uuid)
        pending = [c for c in self.store.list_commands(ticket_uuid) if c.get("human_status") == "Pending"]
        if pending:
            row = self.store.update_command(
                pending[0]["id"],
                agent_name=proposal["agent_name"],
                command_text=proposal["command_text"],
                script_diff=proposal["script_diff"],
                safety_status=proposal["safety_status"],
                output_logs="",
            )
        else:
            row = self.store.insert_command(ticket_uuid, **proposal)
            self.store.update_ticket(ticket_uuid, status="Troubleshooting", active_agent=proposal["agent_name"])

        self.audit.record(
            "command_retry_queued",
            ticket_id=ticket_uuid,
            source_command_id=command_id,
            command=command_text,
        )
        return row

    def reconcile_validation_state(self, ticket_uuid: str) -> dict[str, Any]:
        """Clear stale pending public-test commands after validation already passed."""
        commands = self.store.list_commands(ticket_uuid)
        if not self._public_test_done(commands):
            return {"reconciled": False}

        rejected_ids: list[str] = []
        for cmd in commands:
            if cmd.get("human_status") == "Pending" and self._is_public_test(cmd):
                self.store.update_command(cmd["id"], human_status="Rejected")
                rejected_ids.append(cmd["id"])
                self.audit.record(
                    "validation_reconciled",
                    ticket_id=ticket_uuid,
                    command=cmd.get("command_text"),
                )

        self.store.update_ticket(ticket_uuid, status="Fixed", active_agent="Activity Log Generator")
        self._refresh_activity_draft(ticket_uuid)
        return {"reconciled": True, "rejected_command_ids": rejected_ids}

    def _refresh_activity_draft(self, ticket_uuid: str) -> None:
        ticket = self.store.get_ticket(ticket_uuid)
        if not ticket:
            return
        commands = self.store.list_commands(ticket_uuid)
        audit_entries = self.audit.list_entries(ticket_uuid)

        draft = self._llm_generate_activity(ticket, commands, audit_entries)
        draft = self._apply_public_test_validation(commands, draft)
        self.store.upsert_activity(ticket_uuid, **draft, submitted_to_erp=False)

    def _llm_generate_activity(
        self,
        ticket: dict[str, Any],
        commands: list[dict[str, Any]],
        audit_entries: list[dict[str, Any]],
    ) -> dict[str, str]:
        primary = (self.settings.llm_primary or "gemini").lower()
        order = (
            [("gemini", self.gemini), ("azure", self.azure)]
            if primary == "gemini"
            else [("azure", self.azure), ("gemini", self.gemini)]
        )
        for name, agent in order:
            if not agent.enabled:
                continue
            try:
                draft = agent.generate_activity(ticket, commands)
                if draft:
                    return draft
            except Exception as exc:
                self.audit.record(f"{name}_activity_failed", ticket_id=ticket["id"], error=str(exc))

        return generate_activity_draft(ticket=ticket, commands=commands, audit_entries=audit_entries)

    def _apply_public_test_validation(
        self,
        commands: list[dict[str, Any]],
        draft: dict[str, str],
    ) -> dict[str, str]:
        if not self._public_test_done(commands):
            return draft
        for c in reversed(commands):
            if not self._is_public_test(c) or not self._is_executed(c):
                continue
            output = c.get("output_logs") or ""
            ok_lines = [ln.strip() for ln in output.split("\n") if "OK:" in ln or "ok:" in ln.lower()]
            detail = ok_lines[-1] if ok_lines else "All public-test checks passed."
            draft = {**draft, "validation_result": f"PASS — public-test.sh exit 0. {detail}"}
            break
        return draft

    def submit_activity(self, ticket_uuid: str) -> dict[str, Any]:
        ticket = self.store.get_ticket(ticket_uuid)
        activity = self.store.get_activity(ticket_uuid)
        if not ticket or not activity:
            raise ValueError("Ticket or activity not found")

        from datetime import datetime, timezone

        start = self._run_started.get(ticket_uuid) or datetime.now(timezone.utc).isoformat()
        end = datetime.now(timezone.utc).isoformat()

        if self.phoenix:
            phoenix_id = int(ticket["ticket_code"])
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            self.phoenix.create_activity(
                ticket_id=phoenix_id,
                start_datetime=start_dt,
                end_datetime=end_dt,
                summary=activity.get("summary", ""),
                root_cause=activity.get("root_cause", ""),
                actions_taken=activity.get("actions_taken", ""),
                commands_summary=activity.get("commands_summary", ""),
                validation_result=activity.get("validation_result", ""),
            )
            self.phoenix.set_ticket_status(phoenix_id, "DONE")

        self.store.upsert_activity(ticket_uuid, submitted_to_erp=True)
        self.store.update_ticket(ticket_uuid, status="Fixed", active_agent="Activity Log Generator")
        self.audit.record("activity_submitted", ticket_id=ticket_uuid, ticket_code=ticket["ticket_code"])
        return {"ok": True, "ticket_id": ticket_uuid}

    def reset_workspace(self) -> dict[str, Any]:
        """Clear Supabase immediately; reboot Phoenix VMs in the background."""
        try:
            self.store.reset_workspace()
        except Exception as exc:
            logger.exception("Local workspace reset failed")
            raise RuntimeError(f"Failed to clear local workspace: {exc}") from exc

        self.audit.clear()
        self._run_started.clear()
        self._ssh_key_by_ticket.clear()
        self._system_notes_by_ticket.clear()
        self.hypothesis_store.clear_all()
        self.audit.record("workspace_local_cleared")

        if self.phoenix:
            threading.Thread(target=self._phoenix_reset_background, daemon=True).start()

        return {
            "local_cleared": True,
            "phoenix_ok": True,
            "phoenix_message": "VM reboot started in background — wait ~2 min then Sync ERP",
        }

    def _phoenix_reset_background(self) -> None:
        if not self.phoenix:
            return
        try:
            self.phoenix.reset()
            for pt in self.phoenix.list_tickets(sort="date"):
                if pt.get("status") == "OPEN":
                    continue
                try:
                    self.phoenix.set_ticket_status(int(pt["id"]), "OPEN")
                except Exception as exc:
                    self.audit.record(
                        "reset_ticket_reopen_failed",
                        ticket_code=str(pt.get("id")),
                        error=str(exc),
                    )
            try:
                self.sync_tickets()
            except Exception as exc:
                self.audit.record("reset_sync_failed", error=str(exc))
            self.audit.record("phoenix_reset_complete")
        except Exception as exc:
            logger.warning("Phoenix background reset failed: %s", exc)
            self.audit.record("phoenix_reset_failed", error=str(exc))

    def _run_ssh_command(
        self,
        ticket_uuid: str,
        host: str,
        port: int,
        username: str,
        command: str,
        key_path: str,
    ):
        try:
            return self.ssh.run(host, port, command, key_path=key_path)
        except SSHError as exc:
            if "authentication failed" not in str(exc).lower():
                raise
            discovered = discover_ssh_key(
                self.settings,
                host,
                port,
                username=username,
                preferred_keys=[key_path],
            )
            self._ssh_key_by_ticket[ticket_uuid] = discovered
            return self.ssh.run(host, port, command, key_path=discovered)

    def _ssh_key_for(
        self,
        ticket_uuid: str,
        ticket: dict[str, Any] | None,
        sys_info: dict[str, Any] | None,
    ) -> str:
        if ticket_uuid in self._ssh_key_by_ticket:
            return self._ssh_key_by_ticket[ticket_uuid]
        notes = self._system_notes_by_ticket.get(ticket_uuid, "")
        if not notes and sys_info:
            notes = sys_info.get("system_notes", "") or ""
        if ticket:
            key_path = resolve_ssh_key_path(self.settings, ticket=ticket, system_notes=notes)
            self._ssh_key_by_ticket[ticket_uuid] = key_path
            return key_path
        return resolve_ssh_key_path(self.settings, system_notes=notes)
