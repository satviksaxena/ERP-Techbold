from app.agent.fast_paths import has_fast_path, next_fast_path_command
from app.safety.layer import SafetyLayer


def test_has_fast_path_for_hackathon_codes():
    assert has_fast_path({"ticket_code": "7001"})
    assert has_fast_path({"ticket_code": "7005"})
    assert not has_fast_path({"ticket_code": "9999"})


def test_7001_starts_with_is_enabled_check():
    ticket = {"ticket_code": "7001", "title": "Status API", "report_text": "down"}
    proposal = next_fast_path_command(ticket, [], SafetyLayer())
    assert proposal is not None
    assert "is-enabled status-api.service" in proposal["command_text"]
    assert proposal.get("plan_intent") == "diagnostic"


def test_7001_proposes_enable_after_diagnostic():
    ticket = {"ticket_code": "7001", "title": "Status API", "report_text": "down"}
    commands = [
        {
            "command_text": "systemctl is-enabled status-api.service",
            "human_status": "Approved",
            "output_logs": "disabled\nexit code: 0",
        }
    ]
    proposal = next_fast_path_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "systemctl enable" in proposal["command_text"]
    assert proposal.get("plan_intent") == "fix"


def test_7002_upload_path_chown():
    ticket = {
        "ticket_code": "7002",
        "title": "Document uploads fail with permission denied",
        "report_text": "permission denied",
    }
    commands = [
        {
            "command_text": "stat /srv/customer-portal/uploads",
            "human_status": "Approved",
            "output_logs": "root:root /srv/customer-portal/uploads\nexit code: 0",
        }
    ]
    proposal = next_fast_path_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "chown" in proposal["command_text"]


def test_7002_public_test_after_chown():
    ticket = {
        "ticket_code": "7002",
        "title": "Document uploads fail with permission denied",
        "report_text": "permission denied",
    }
    commands = [
        {
            "command_text": "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        }
    ]
    proposal = next_fast_path_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "public-test.sh" in proposal["command_text"]
