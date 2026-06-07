from app.agent.runbook_paths import (
    has_runbook_path,
    next_runbook_path_command,
)
from app.agent.runbooks import (
    classify_incident,
    hybrid_search_runbooks,
    retrieve_runbooks,
    symptom_fingerprint,
)
from app.safety.layer import SafetyLayer


def test_classify_permission_upload():
    ticket = {
        "ticket_code": "8100",
        "title": "Document uploads fail with permission denied",
        "report_text": "Customer cannot upload files to portal — permission denied on uploads",
    }
    assert classify_incident(ticket) == "permission_upload"
    assert has_runbook_path(ticket)


def test_classify_readonly_filesystem():
    ticket = {
        "ticket_code": "8101",
        "title": "ERP sync failing",
        "report_text": "Read-only filesystem — cannot write to /var",
    }
    assert classify_incident(ticket) == "filesystem_readonly"


def test_hackathon_fast_path_not_runbook_path():
    ticket = {"ticket_code": "7001", "title": "Status API down", "report_text": "service inactive"}
    assert not has_runbook_path(ticket)


def test_runbook_path_starts_with_diagnostic():
    ticket = {
        "ticket_code": "8100",
        "title": "Upload permission denied",
        "report_text": "permission denied on customer portal uploads",
    }
    proposal = next_runbook_path_command(ticket, [], SafetyLayer())
    assert proposal is not None
    assert proposal.get("plan_intent") == "diagnostic"
    assert "stat" in proposal["command_text"] or "ls -ld" in proposal["command_text"]


def test_runbook_path_proposes_chown_after_stat():
    ticket = {
        "ticket_code": "8100",
        "title": "Upload permission denied",
        "report_text": "permission denied uploads",
    }
    commands = [
        {
            "command_text": "stat /srv/customer-portal/uploads 2>/dev/null || ls -ld /srv/customer-portal/uploads",
            "human_status": "Approved",
            "output_logs": "root:root /srv/customer-portal/uploads\nexit code: 0",
        }
    ]
    proposal = next_runbook_path_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert proposal.get("plan_intent") == "fix"
    assert "chown" in proposal["command_text"]


def test_idempotency_skips_chown_when_www_data():
    ticket = {
        "ticket_code": "8100",
        "title": "Upload permission denied",
        "report_text": "permission denied uploads",
    }
    commands = [
        {
            "command_text": "stat /srv/customer-portal/uploads",
            "human_status": "Approved",
            "output_logs": "www-data:www-data /srv/customer-portal/uploads\nexit code: 0",
        }
    ]
    proposal = next_runbook_path_command(ticket, commands, SafetyLayer())
    assert proposal is None or "chown" not in (proposal.get("command_text") or "")


def test_verify_gate_after_remount_fix():
    ticket = {
        "ticket_code": "8102",
        "title": "Cannot write files",
        "report_text": "read-only filesystem root mount ro",
    }
    commands = [
        {
            "command_text": "df -h && mount | grep -E ' on / | on /var '",
            "human_status": "Approved",
            "output_logs": "/dev/sda1 on / type ext4 (ro,relatime)\nexit code: 0",
        },
        {
            "command_text": "sudo mount -o remount,rw /",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        },
    ]
    proposal = next_runbook_path_command(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert proposal.get("plan_intent") == "validate"
    assert "mount" in proposal["command_text"] or "df -h" in proposal["command_text"]


def test_hybrid_retrieve_includes_class():
    ticket = {
        "title": "PostgreSQL connection errors",
        "report_text": "database sync fails — postgres not responding",
    }
    ctx = retrieve_runbooks(ticket)
    assert "Database connectivity" in ctx
    assert "Incident class:" in ctx


def test_symptom_fingerprint_stable():
    t1 = {"title": "Upload fail", "report_text": "permission denied on 10.0.0.5 at 2026-06-06"}
    t2 = {"title": "Upload fail", "report_text": "permission denied on 192.168.1.1 at 2026-06-07"}
    assert symptom_fingerprint(t1) == symptom_fingerprint(t2)


def test_unclassified_ticket_no_runbook_path():
    ticket = {"ticket_code": "9999", "title": "Misc", "report_text": "something vague happened"}
    assert classify_incident(ticket) is None
    assert not has_runbook_path(ticket)
    assert next_runbook_path_command(ticket, [], SafetyLayer()) is None


def test_hybrid_search_ranks_permission_above_postgres():
    ticket = {
        "title": "Upload errors",
        "report_text": "permission denied when uploading documents to portal",
    }
    results = hybrid_search_runbooks(ticket, limit=2)
    assert results
    assert results[0][1]["id"] == "permission_upload"
