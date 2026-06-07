from app.agent.orchestrator import AgentOrchestrator


def test_command_output_failed_detects_ssh_error():
    assert AgentOrchestrator._command_output_failed("+ execution failed\nSSH timeout")


def test_command_output_failed_detects_nonzero_exit():
    assert AgentOrchestrator._command_output_failed("stdout\nexit code: 1")


def test_command_output_failed_ignores_success():
    assert not AgentOrchestrator._command_output_failed("ok\nexit code: 0")
    assert not AgentOrchestrator._command_output_failed("metrics loaded\n[exit 0]")


def test_public_test_done_detects_exit_zero():
    commands = [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "OK: monitoring dashboard is healthy\nexit code: 0 (700ms)",
        }
    ]
    assert AgentOrchestrator._public_test_done(commands)


def test_public_test_done_ignores_pending():
    commands = [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Pending",
            "output_logs": "",
        }
    ]
    assert not AgentOrchestrator._public_test_done(commands)


def test_next_proposal_stops_after_public_test_passes():
    class FakeStore:
        def list_commands(self, ticket_id):
            return [
                {
                    "command_text": "sudo systemctl restart metrics-agent.service",
                    "human_status": "Approved",
                    "output_logs": "exit code: 0",
                },
                {
                    "command_text": "sudo /opt/hackathon/public-test.sh",
                    "human_status": "Approved",
                    "output_logs": "OK: metrics updating\nexit code: 0 (700ms)",
                },
            ]

        def get_system_info(self, ticket_id):
            return None

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.store = FakeStore()
    orch.hypothesis_store = type("H", (), {"get": lambda self, tid: None})()

    assert orch._next_proposal({"id": "ticket-1"}) is None


def test_needs_public_test_not_after_diagnostics_only():
    diagnostic = {
        "command_text": "ps aux | grep nginx; find /var/www -name upload",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    assert not AgentOrchestrator._looks_like_fix(diagnostic["command_text"])
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    assert not orch._needs_public_test([diagnostic])


def test_filter_proposal_blocks_premature_public_test():
    diagnostic = {
        "command_text": "ps aux | grep nginx",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    proposal = {
        "agent_name": "Problem Solver",
        "command_text": "sudo /opt/hackathon/public-test.sh",
        "script_diff": "+ test",
        "safety_status": "Safe",
        "human_status": "Pending",
        "output_logs": "",
    }
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    assert orch._filter_proposal(proposal, [diagnostic]) is None


def test_command_from_fix_strategy_extracts_chown():
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.safety = __import__("app.safety.layer", fromlist=["SafetyLayer"]).SafetyLayer()
    hypothesis = {
        "title": "Directory Permissions",
        "fix_strategy": "Run `chown -R www-data:www-data /var/www/uploads` to fix ownership.",
    }
    cmd = orch._command_from_fix_strategy(hypothesis)
    assert cmd is not None
    assert "chown" in cmd["command_text"]

    fix = {
        "command_text": "sudo chown -R www-data:www-data /var/www/uploads",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    assert AgentOrchestrator._looks_like_fix(fix["command_text"])
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    assert orch._needs_public_test([fix])


def test_sync_command_stops_after_public_test_passes():
    class FakeStore:
        def list_commands(self, ticket_id):
            return [
                {
                    "command_text": "sudo /opt/hackathon/public-test.sh",
                    "human_status": "Approved",
                    "output_logs": "OK\nexit code: 0",
                }
            ]
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.store = FakeStore()
    assert orch._sync_command_to_selected_path("ticket-1", {"hypotheses": [{"first_command": "ls"}], "selected_index": 0}) is None


def test_propose_next_for_path_stops_after_public_test_passes():
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    assert orch._propose_next_for_path({"id": "ticket-1"}, {}, [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "OK\nexit code: 0",
        }
    ]) is None


