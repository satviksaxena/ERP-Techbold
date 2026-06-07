from app.agent.command_intent import can_auto_approve, intent_from_command


def test_intent_classifies_diagnostics():
    assert intent_from_command("df -h") == "diagnostic"
    assert intent_from_command("systemctl status nginx") == "diagnostic"


def test_intent_classifies_fixes():
    assert intent_from_command("sudo systemctl enable --now status-api.service") == "fix"
    assert intent_from_command("sudo sed -i 's/a/b/' file") == "fix"


def test_can_auto_approve_read_only_diagnostics():
    assert can_auto_approve("df -h")
    assert can_auto_approve("journalctl -p err -n 30 --no-pager")
    assert can_auto_approve("sudo systemctl status customer-status.service --no-pager -l")
    assert can_auto_approve("cat /opt/hackathon/case.json")


def test_can_auto_approve_blocks_fixes_and_validation():
    assert not can_auto_approve("sudo systemctl enable --now status-api.service")
    assert not can_auto_approve("sudo sed -i 's/PORT=8008/PORT=8080/' /etc/customer-status.env")
    assert not can_auto_approve("sudo /opt/hackathon/public-test.sh")
    assert not can_auto_approve("curl -s http://localhost:8080/health")
    assert not can_auto_approve("", safety_allowed=True)
    assert not can_auto_approve("df -h", safety_allowed=False)
