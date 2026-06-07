from app.agent.orchestrator import AgentOrchestrator


def test_command_output_failed_detects_ssh_error():
    assert AgentOrchestrator._command_output_failed("+ execution failed\nSSH timeout")


def test_command_output_failed_detects_nonzero_exit():
    assert AgentOrchestrator._command_output_failed("stdout\nexit code: 1")


def test_command_output_failed_ignores_success():
    assert not AgentOrchestrator._command_output_failed("ok\nexit code: 0")
    assert not AgentOrchestrator._command_output_failed("metrics loaded\n[exit 0]")


def test_public_test_done_uses_latest_run_only():
    commands = [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "OK\nexit code: 0",
        },
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "FAIL\nexit code: 1",
        },
    ]
    assert not AgentOrchestrator._public_test_done(commands)


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


def test_looks_like_fix_ignores_find_with_dev_null():
    cmd = 'sudo find /var/www /opt /srv -type d -name "*upload*" -exec ls -ld {} + 2>/dev/null'
    assert not AgentOrchestrator._looks_like_fix(cmd)


def test_looks_like_fix_detects_file_redirect():
    assert AgentOrchestrator._looks_like_fix("echo foo > /etc/customer-status.env")


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


def test_needs_public_test_after_upload_chown_fix():
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    ticket = {
        "ticket_code": "7002",
        "title": "Document uploads fail with permission denied",
        "report_text": "permission denied",
    }
    fix = {
        "command_text": "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    assert orch._needs_public_test(ticket, [fix])


def test_filter_proposal_allows_validate_intent_after_fix():
    fix = {
        "command_text": "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
        "ticket_id": "ticket-upload",
    }
    proposal = {
        "agent_name": "Problem Solver",
        "command_text": "sudo /opt/hackathon/public-test.sh",
        "script_diff": "+ validate",
        "safety_status": "Safe",
        "human_status": "Pending",
        "output_logs": "",
        "plan_intent": "validate",
    }

    class FakeStore:
        def get_ticket(self, ticket_id):
            return {
                "ticket_code": "7002",
                "title": "Document uploads fail with permission denied",
                "report_text": "permission denied",
            }

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.store = FakeStore()
    assert orch._filter_proposal(proposal, [fix]) is not None


def test_needs_public_test_not_after_diagnostics_only():
    diagnostic = {
        "command_text": "ps aux | grep nginx; find /var/www -name upload",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    assert not AgentOrchestrator._looks_like_fix(diagnostic["command_text"])
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    ticket = {"ticket_code": "7001"}
    assert not orch._needs_public_test(ticket, [diagnostic])


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


def test_enforce_verifier_blocks_premature_fix():
    from app.agent.phases import PipelinePhase
    from app.agent.verifier import VerifierResult

    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.audit = type("A", (), {"record": lambda *a, **k: None})()
    verification = VerifierResult(recommend="continue_diagnose", evidence_summary="need more")
    proposal = {
        "agent_name": "Problem Solver",
        "command_text": "sudo systemctl enable --now foo.service",
        "script_diff": "+ fix",
        "safety_status": "Safe",
        "human_status": "Pending",
        "output_logs": "",
    }
    result = orch._enforce_verifier_and_reflexion(proposal, [], verification, PipelinePhase.DIAGNOSE)
    assert result is None


def test_should_hold_for_retry_false_after_public_test_fail():
    cmd = {
        "command_text": "sudo /opt/hackathon/public-test.sh",
        "human_status": "Approved",
        "output_logs": "FAIL\nexit code: 1",
    }
    assert not AgentOrchestrator._should_hold_for_retry(cmd)


def test_should_hold_for_retry_false_for_diagnostic_grep():
    cmd = {
        "command_text": "systemctl list-unit-files --type=service | grep -iE 'status|api'",
        "human_status": "Approved",
        "output_logs": "exit code: 1",
    }
    assert not AgentOrchestrator._should_hold_for_retry(cmd)


def test_realign_pending_replaces_diagnostic_with_public_test():
    from app.agent.llm_schemas import PUBLIC_TEST_COMMAND

    class FakeStore:
        def __init__(self):
            self.commands = [
                {
                    "id": "fix-1",
                    "ticket_id": "t1",
                    "command_text": "sudo systemctl enable --now customer-status.service",
                    "human_status": "Approved",
                    "output_logs": "exit code: 0",
                    "created_at": "1",
                },
                {
                    "id": "pending-1",
                    "ticket_id": "t1",
                    "command_text": "sudo systemctl status nginx --no-pager -l || true",
                    "human_status": "Pending",
                    "output_logs": "",
                    "created_at": "2",
                },
            ]
            self.ticket = {
                "id": "t1",
                "ticket_code": "7001",
                "title": "Status API intermittently unavailable",
                "report_text": "down after reboot",
            }

        def list_commands(self, ticket_id):
            return self.commands

        def get_ticket(self, ticket_id):
            return self.ticket

        def update_command(self, command_id, **fields):
            for cmd in self.commands:
                if cmd["id"] == command_id:
                    cmd.update(fields)

    store = FakeStore()
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    orch.store = store
    orch.audit = type("A", (), {"record": lambda *a, **k: None})()
    orch.safety = __import__("app.safety.layer", fromlist=["SafetyLayer"]).SafetyLayer()
    orch.hypothesis_store = type(
        "H",
        (),
        {
            "get": lambda self, tid: {
                "hypotheses": [
                    {
                        "title": "Systemd Service Not Enabled",
                        "fix_strategy": "Enable status-api.service",
                        "steps": [
                            {
                                "command_text": PUBLIC_TEST_COMMAND,
                                "intent": "validate",
                                "agent_name": "Problem Solver",
                            }
                        ],
                    }
                ],
                "selected_index": 0,
                "pipeline_state": {},
            }
        },
    )()

    assert orch._realign_pending_gate("t1")
    pending = [c for c in store.commands if c.get("human_status") == "Pending"]
    assert not pending
    rejected = [c for c in store.commands if c.get("human_status") == "Rejected"]
    assert rejected and "nginx" in rejected[0]["command_text"]


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
        "command_text": "sudo systemctl enable --now status-api.service",
        "human_status": "Approved",
        "output_logs": "exit code: 0",
    }
    assert AgentOrchestrator._looks_like_fix(fix["command_text"])
    orch = AgentOrchestrator.__new__(AgentOrchestrator)
    ticket = {"ticket_code": "7001"}
    assert orch._needs_public_test(ticket, [fix])


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


