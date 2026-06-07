from app.agent.phases import PipelinePhase, agent_for_phase, infer_phase


def test_infer_phase_diagnose():
    phase = infer_phase([], public_test_done=False, needs_public_test=False)
    assert phase == PipelinePhase.HYPOTHESIS_SELECTED


def test_infer_phase_validate():
    phase = infer_phase(
        [{"command_text": "sudo chown x", "human_status": "Approved"}],
        public_test_done=False,
        needs_public_test=True,
    )
    assert phase == PipelinePhase.VALIDATE


def test_agent_for_phase_fix():
    assert agent_for_phase(PipelinePhase.FIX) == "Problem Solver"
