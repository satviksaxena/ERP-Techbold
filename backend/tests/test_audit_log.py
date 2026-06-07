from app.audit.log import AuditLog


def test_audit_persists_via_callback():
    saved: list[dict] = []

    log = AuditLog(persist_fn=lambda entry: saved.append(entry))
    log.record("command_executed", ticket_id="tid-1", command="df -h", exit_code=0)
    assert len(saved) == 1
    assert saved[0]["action"] == "command_executed"
    assert saved[0]["ticket_id"] == "tid-1"


def test_audit_list_by_ticket():
    log = AuditLog()
    log.record("sync_tickets", count=5)
    log.record("command_executed", ticket_id="a", command="uptime")
    log.record("command_executed", ticket_id="b", command="df -h")
    assert len(log.list_entries("a")) == 1
    assert log.list_entries("a")[0]["command"] == "uptime"
