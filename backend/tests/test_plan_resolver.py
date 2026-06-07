from app.agent.plan_resolver import build_plan, ensure_plan, next_plan_step, next_universal_baseline
from app.safety.layer import SafetyLayer


def test_build_plan_from_first_command_and_pathway():
    hypothesis = {
        "title": "Disk Space or Read-Only Filesystem",
        "likely_root_cause": "Root filesystem mounted read-only",
        "first_command": "df -h",
        "fix_strategy": "Run `sudo mount -o remount,rw /` to restore writes.",
    }
    plan = build_plan(hypothesis)
    commands = [s.command_text for s in plan]
    assert "df -h" in commands
    assert any("mount" in c for c in commands)
    assert any("remount" in c for c in commands)


def test_ensure_plan_attaches_steps():
    hypothesis = {
        "title": "Service down",
        "first_command": "systemctl --failed --no-pager",
        "likely_root_cause": "systemd unit failed",
        "fix_strategy": "sudo systemctl restart nginx.service",
    }
    enriched = ensure_plan(hypothesis)
    assert len(enriched["steps"]) >= 2


def test_next_plan_step_skips_fix_when_verifier_says_diagnose():
    hypothesis = {
        "title": "Disk read-only",
        "likely_root_cause": "filesystem read-only",
        "first_command": "df -h",
        "fix_strategy": "sudo mount -o remount,rw /",
    }
    commands = [
        {"command_text": "df -h", "human_status": "Approved"},
        {"command_text": "mount | grep -E ' on / | on /var '", "human_status": "Approved"},
    ]
    proposal = next_plan_step(
        hypothesis,
        commands,
        SafetyLayer(),
        verifier_recommend="continue_diagnose",
    )
    assert proposal is None or proposal.get("plan_intent") != "fix"


def test_validation_after_fix():
    from app.agent.plan_resolver import last_fix_index, next_validation_step, validation_succeeded_after_fix

    hypothesis = {
        "title": "Disk read-only",
        "likely_root_cause": "filesystem read-only",
        "first_command": "df -h",
        "fix_strategy": "sudo mount -o remount,rw /",
    }
    commands = [
        {"command_text": "df -h", "human_status": "Approved", "output_logs": "exit code: 0"},
        {
            "command_text": "sudo mount -o remount,rw /",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        },
    ]
    assert last_fix_index(commands) == 1
    proposal = next_validation_step(hypothesis, commands, SafetyLayer())
    assert proposal is not None
    assert proposal["command_text"] == "df -h"

    commands.append(
        {"command_text": "df -h", "human_status": "Approved", "output_logs": "exit code: 0"}
    )
    assert validation_succeeded_after_fix(commands, hypothesis)
    assert next_validation_step(hypothesis, commands, SafetyLayer()) is None


def test_remount_is_fix():
    from app.agent.command_intent import is_fix_command

    assert is_fix_command("sudo mount -o remount,rw /")
