from app.agent.hackathon_commands import (
    is_hackathon_grading_ticket,
    next_hackathon_command,
    public_test_passed,
    resolve_service_name,
)
from app.safety.layer import SafetyLayer


def test_hackathon_progression_suggests_enable_after_diagnostics():
    ticket = {"ticket_code": "7001", "title": "Status API", "report_text": "down after reboot"}
    commands = [
        {"command_text": "uptime && hostname", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "systemctl --failed --no-pager", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "df -h", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "free -m", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "ss -tlnp | head -30", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "journalctl -p err -n 30 --no-pager", "human_status": "Approved", "output_logs": "exit code: 0"},
        {
            "command_text": "systemctl list-unit-files --type=service | grep -iE 'status|api|hackathon|metrics'",
            "human_status": "Approved",
            "output_logs": "status-api.service\nexit code: 0",
        },
        {
            "command_text": "cat /opt/hackathon/case.json",
            "human_status": "Approved",
            "output_logs": '{"service": "status-api.service"}\nexit code: 0',
        },
        {
            "command_text": "systemctl status status-api.service --no-pager -l",
            "human_status": "Approved",
            "output_logs": "Active: inactive\nexit code: 0",
        },
        {
            "command_text": "systemctl is-enabled status-api.service",
            "human_status": "Approved",
            "output_logs": "disabled\nexit code: 0",
        },
    ]

    proposal = next_hackathon_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "systemctl enable --now status-api.service" in proposal["command_text"]


def test_resolve_prefers_grading_target_over_case_json_decoy():
    ticket = {"ticket_code": "7001"}
    commands = [
        {
            "command_text": "cat /opt/hackathon/case.json",
            "human_status": "Approved",
            "output_logs": '{"service": "customer-status.service"}\nexit code: 0',
        },
    ]
    assert resolve_service_name(ticket, commands) == "status-api.service"


def test_hackathon_corrects_wrong_service_after_failed_public_test():
    ticket = {"ticket_code": "7001", "title": "Status API", "report_text": "down after reboot"}
    commands = [
        {
            "command_text": "systemctl list-unit-files --type=service | grep -iE 'status|api|hackathon|metrics'",
            "human_status": "Approved",
            "output_logs": "status-api.service disabled\nexit code: 0",
        },
        {
            "command_text": "sudo systemctl enable --now customer-status.service",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        },
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "FAIL: status API health check failed\nexit code: 1",
        },
    ]
    proposal = next_hackathon_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "status-api.service" in proposal["command_text"]
    assert "systemctl enable" in proposal["command_text"]


def test_hackathon_revalidates_after_fix_following_failed_public_test():
    ticket = {"ticket_code": "7001", "title": "Status API", "report_text": "wrong port"}
    commands = [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "FAIL\nexit code: 1",
        },
        {
            "command_text": "sudo sed -i 's/PORT=8008/PORT=8080/' /etc/customer-status.env && sudo systemctl restart customer-status.service",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        },
    ]
    proposal = next_hackathon_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "public-test.sh" in proposal["command_text"]


def test_public_test_passed_uses_latest_run_only():
    commands = [
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "OK: status API healthy\nexit code: 0",
        },
        {
            "command_text": "sudo /opt/hackathon/public-test.sh",
            "human_status": "Approved",
            "output_logs": "FAIL: status API health check failed\nexit code: 1",
        },
    ]
    assert not public_test_passed(commands)


def test_hackathon_skips_non_grading_tickets():
    ticket = {"ticket_code": "7003", "title": "ERP orders fail", "report_text": "database error"}
    proposal = next_hackathon_command(ticket, [], __import__("app.safety.layer", fromlist=["SafetyLayer"]).SafetyLayer())
    assert proposal is None
    assert not is_hackathon_grading_ticket(ticket)
    assert is_hackathon_grading_ticket({"ticket_code": "7001"})
