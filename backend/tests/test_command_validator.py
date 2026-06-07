from app.agent.command_validator import is_valid_shell_command


def test_rejects_prose_command():
    bad = (
        "sudo Enable the systemd service using 'sudo systemctl enable <service_name>' "
        "so that it persists across reboots."
    )
    assert not is_valid_shell_command(bad)


def test_accepts_systemctl_fix():
    assert is_valid_shell_command("sudo systemctl enable --now status-api.service")


def test_accepts_mount_and_findmnt():
    assert is_valid_shell_command("mount | grep -E ' on / | on /var '")
    assert is_valid_shell_command("findmnt -no TARGET,OPTIONS / /var /var/lib/postgresql 2>/dev/null")


def test_rejects_placeholder():
    assert not is_valid_shell_command("sudo systemctl enable --now <service_name>")
