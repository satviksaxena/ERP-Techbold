from app.agent.pathway_commands import command_already_run, next_pathway_command
from app.safety.layer import SafetyLayer


def test_pathway_disk_suggests_mount_after_df():
    hypothesis = {
        "title": "Disk Space or Read-Only Filesystem",
        "likely_root_cause": "Root filesystem mounted read-only",
        "first_command": "df -h",
    }
    commands = [
        {"command_text": "df -h", "human_status": "Approved", "output_logs": "exit code: 0"},
        {"command_text": "free -m", "human_status": "Approved", "output_logs": "exit code: 0"},
    ]
    proposal = next_pathway_command(hypothesis, commands, SafetyLayer())
    assert proposal is not None
    assert "mount" in proposal["command_text"].lower()


def test_pathway_postgres_after_generic_diagnostics():
    hypothesis = {
        "title": "Database / connectivity",
        "likely_root_cause": "PostgreSQL not accepting connections",
        "first_command": "systemctl status postgresql",
    }
    commands = [
        {"command_text": "journalctl -p err -n 30 --no-pager", "human_status": "Approved", "output_logs": "exit code: 0"},
    ]
    proposal = next_pathway_command(hypothesis, commands, SafetyLayer())
    assert proposal is not None
    assert "postgresql" in proposal["command_text"].lower()


def test_pathway_disk_mount_command_valid():
    hypothesis = {
        "title": "Disk Space or Read-Only Filesystem",
        "likely_root_cause": "Root filesystem mounted read-only",
    }
    commands = [
        {"command_text": "df -h && df -i", "human_status": "Approved", "output_logs": "exit code: 0"},
    ]
    proposal = next_pathway_command(hypothesis, commands, SafetyLayer())
    assert proposal is not None
    assert proposal["command_text"].startswith("mount |")


def test_command_already_run_matches_partial():
    commands = [{"command_text": "df -h", "human_status": "Approved", "output_logs": "ok"}]
    assert command_already_run(commands, "df -h && df -i")
