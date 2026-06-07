from app.agent.reflexion import command_already_failed, last_failed_command


def test_last_failed_command_detects_ssh_error():
    cmds = [
        {
            "command_text": "sudo ss -tulpn",
            "human_status": "Approved",
            "output_logs": "+ execution failed\nSSH timeout",
        }
    ]
    assert last_failed_command(cmds) is not None
    assert command_already_failed(cmds, "sudo ss -tulpn")


def test_last_failed_command_ignores_success():
    cmds = [
        {
            "command_text": "df -h",
            "human_status": "Approved",
            "output_logs": "ok\nexit code: 0",
        }
    ]
    assert last_failed_command(cmds) is None
