"""FastAPI backend for techbold AI Service Desk Autopilot."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.orchestrator import AgentOrchestrator
from app.audit.log import AuditLog
from app.config import Settings, get_settings
from app.phoenix.client import PhoenixClient, PhoenixError
from app.safety.layer import SafetyLayer
from app.ssh.runner import SSHRunner
from app.store.supabase_store import SupabaseStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

audit_log = AuditLog()
_safety = SafetyLayer()


class ApproveBody(BaseModel):
    command_text: str | None = None


class ActivityBody(BaseModel):
    summary: str = ""
    root_cause: str = ""
    actions_taken: str = ""
    commands_summary: str = ""
    validation_result: str = ""


class HypothesisSelectBody(BaseModel):
    index: int = Field(ge=0)


def _build_orchestrator(settings: Settings) -> AgentOrchestrator:
    store = SupabaseStore(settings)
    phoenix = None
    if settings.phoenix_api_base_url and settings.phoenix_api_token:
        phoenix = PhoenixClient(settings)
    ssh = SSHRunner(settings, _safety)
    return AgentOrchestrator(settings, store, phoenix, ssh, _safety, audit_log)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    settings = get_settings()
    if settings.phoenix_api_base_url:
        try:
            client = PhoenixClient(settings)
            client.close()
        except Exception:
            pass


app = FastAPI(
    title="techbold AI Service Desk Autopilot",
    description="Backend orchestrating Phoenix ERP, SSH, AI agents, and Supabase state.",
    lifespan=lifespan,
)

settings = get_settings()
origins = ["*"] if settings.cors_origins == "*" else [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_orchestrator() -> AgentOrchestrator:
    return _build_orchestrator(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    s = get_settings()
    return {
        "status": "ok",
        "mock_mode": str(s.mock_mode),
        "phoenix_configured": str(bool(s.phoenix_api_base_url and s.phoenix_api_token)),
        "supabase_configured": str(
            bool(s.supabase_url and (s.supabase_service_role_key or s.supabase_publishable_key))
        ),
        "gemini_configured": str(bool(s.gemini_api_key)),
        "gemini_model": s.gemini_model if s.gemini_api_key else "",
        "gemini_thinking_model": s.gemini_thinking_model if s.gemini_api_key else "",
        "gemini_thinking_level": s.gemini_thinking_level if s.gemini_api_key else "",
        "gemini_ticket_thinking_enabled": str(s.gemini_ticket_thinking_enabled),
        "azure_openai_configured": str(bool(s.azure_openai_api_key and s.azure_openai_endpoint)),
        "azure_openai_deployment": s.azure_openai_deployment,
        "llm_primary": s.llm_primary,
    }


@app.post("/api/sync/tickets")
def sync_tickets(orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        tickets = orch.sync_tickets()
        return {"ok": True, "count": len(tickets), "tickets": tickets, "source": "phoenix_erp"}
    except PhoenixError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/analyze")
def start_analysis(ticket_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        cmd = orch.start_analysis(ticket_id)
        hypotheses = orch.get_hypotheses(ticket_id)
        return {"ok": True, "command": cmd, "hypotheses": hypotheses}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/tickets/{ticket_id}/hypotheses")
def get_hypotheses(ticket_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return orch.get_hypotheses(ticket_id)


@app.post("/api/tickets/{ticket_id}/hypotheses/generate")
def generate_hypotheses(ticket_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        data = orch.generate_hypotheses(ticket_id)
        return {"ok": True, **data}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/hypotheses/select")
def select_hypothesis(
    ticket_id: str,
    body: HypothesisSelectBody,
    orch: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    try:
        data = orch.select_hypothesis(ticket_id, body.index)
        return {"ok": True, **data}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/commands/{command_id}/approve")
def approve_command(
    command_id: str,
    body: ApproveBody = ApproveBody(),
    orch: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    try:
        cmd = orch.approve_command(command_id, body.command_text)
        return {"ok": True, "command": cmd}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/resume-pipeline")
def resume_pipeline(
    ticket_id: str,
    orch: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Recover activity draft / next command after a dev-server reload interrupted follow-up."""
    try:
        return orch.resume_pipeline(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/commands/{command_id}/reject")
def reject_command(command_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        cmd = orch.reject_command(command_id)
        return {"ok": True, "command": cmd}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/commands/{command_id}/retry")
def retry_command(command_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        cmd = orch.retry_command(command_id)
        return {"ok": True, "command": cmd}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/submit-activity")
def submit_activity(
    ticket_id: str,
    body: ActivityBody | None = None,
    orch: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    try:
        if body:
            store = SupabaseStore(get_settings())
            store.upsert_activity(
                ticket_id,
                summary=body.summary,
                root_cause=body.root_cause,
                actions_taken=body.actions_taken,
                commands_summary=body.commands_summary,
                validation_result=body.validation_result,
            )
        result = orch.submit_activity(ticket_id)
        return result
    except PhoenixError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/reconcile-validation")
def reconcile_validation(
    ticket_id: str,
    orch: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    try:
        return orch.reconcile_validation_state(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/connect-ssh")
def connect_ssh(ticket_id: str, orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        result = orch.connect_ssh(ticket_id)
        audit_log.record("ssh_connected", ticket_id=ticket_id, status=result["connection_status"])
        if result["connection_status"] != "Connected":
            raise HTTPException(status_code=502, detail="SSH connection failed — tried all available keys")
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/audit")
def get_audit(ticket_id: str | None = None) -> dict[str, Any]:
    entries = audit_log.list_entries(ticket_id)
    return {"entries": entries}


@app.post("/api/workspace/reset")
def reset_workspace(orch: AgentOrchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    try:
        result = orch.reset_workspace()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": "true",
        "message": "Local workspace cleared — VMs rebooting in background (~2 min)",
        **result,
    }


class SafetyCheckBody(BaseModel):
    command: str = Field(..., min_length=1)


@app.post("/api/safety/check")
def safety_check(body: SafetyCheckBody) -> dict[str, Any]:
    result = _safety.evaluate(body.command)
    return {"allowed": result.allowed, "status": result.status, "reason": result.reason}
