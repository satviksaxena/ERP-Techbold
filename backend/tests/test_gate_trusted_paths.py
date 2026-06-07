from app.agent.orchestrator import AgentOrchestrator


class _StubStore:
    pass


class _StubAudit:
    def record(self, *args, **kwargs):
        return {}


def test_gate_proposal_allows_fast_path_fix_despite_verifier():
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.audit = _StubAudit()
    orch._filter_proposal = lambda p, _e: p
    orch._current_verifier_recommend = lambda _tid: "continue_diagnose"

    proposal = {
        "command_text": "sudo mount -o remount,rw /",
        "plan_intent": "fix",
        "_path_source": "fast_path",
        "agent_name": "Problem Solver",
    }
    result = orch._gate_proposal(proposal, "ticket-uuid", [])
    assert result is not None
    assert result["command_text"] == "sudo mount -o remount,rw /"


def test_gate_proposal_blocks_untrusted_fix_when_verifier_diagnosing():
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.audit = _StubAudit()
    orch._filter_proposal = lambda p, _e: p
    orch._current_verifier_recommend = lambda _tid: "continue_diagnose"

    proposal = {
        "command_text": "sudo mount -o remount,rw /",
        "plan_intent": "fix",
        "agent_name": "Problem Solver",
    }
    result = orch._gate_proposal(proposal, "ticket-uuid", [])
    assert result is None
