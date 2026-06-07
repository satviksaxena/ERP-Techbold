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


def test_failed_fix_step_is_not_plan_done():
    from app.agent.plan_resolver import PlanStep, plan_step_done

    step = PlanStep(
        "Problem Solver",
        "sudo chown -R www-data:root /var/lib/nginx",
        "+ fix",
        "fix",
    )
    commands = [
        {
            "command_text": "sudo chown -R www-data:root /var/lib/nginx",
            "human_status": "Approved",
            "output_logs": "cannot access\nexit code: 1",
        }
    ]
    assert not plan_step_done(commands, step)


def test_permission_fixup_from_stat_evidence():
    from app.agent.plan_resolver import permission_fixup_fallback

    ticket = {"title": "Document uploads fail with permission denied", "report_text": ""}
    commands = [
        {
            "command_text": "sudo -n stat -c '%A %U:%G %n' /srv/customer-portal/uploads",
            "human_status": "Approved",
            "output_logs": "drwxr-xr-x root:root /srv/customer-portal/uploads\nexit code: 0",
        },
        {
            "command_text": "sudo chown -R www-data:root /var/lib/nginx",
            "human_status": "Approved",
            "output_logs": "exit code: 1",
        },
    ]
    proposal = permission_fixup_fallback(ticket, commands, SafetyLayer())
    assert proposal is not None
    assert "/srv/customer-portal/uploads" in proposal["command_text"]
    assert "www-data:www-data" in proposal["command_text"]


def test_switch_path_proposes_fix_when_alt_diagnostics_done():
    from app.agent.plan_resolver import diagnostics_complete, next_plan_across_hypotheses

    upload_path = {
        "title": "Upload Directory Permissions",
        "likely_root_cause": "wrong owner on upload dir",
        "first_command": "sudo find /var/www -type d -name upload -exec ls -ld {} +",
        "fix_strategy": "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
        "steps": [
            {
                "agent_name": "Customer System Analyzer",
                "command_text": "sudo find /var/www -type d -name upload -exec ls -ld {} +",
                "intent": "diagnostic",
            },
            {
                "agent_name": "Problem Solver",
                "command_text": "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
                "intent": "fix",
            },
        ],
    }
    disk_path = {
        "title": "Disk Space",
        "likely_root_cause": "disk full",
        "first_command": "df -h",
        "fix_strategy": "sudo apt-get clean",
    }
    commands = [
        {
            "command_text": "sudo find /var/www -type d -name upload -exec ls -ld {} +",
            "human_status": "Approved",
            "output_logs": "exit code: 0",
        },
        {"command_text": "df -h", "human_status": "Approved", "output_logs": "exit code: 0"},
    ]
    assert diagnostics_complete(upload_path, commands)
    proposal, idx = next_plan_across_hypotheses(
        [upload_path, disk_path],
        selected_index=1,
        commands=commands,
        safety=SafetyLayer(),
        verifier_recommend="switch_path",
        prefer_switch=True,
    )
    assert idx == 0
    assert proposal is not None
    assert proposal.get("plan_intent") == "fix"
    assert "chown" in proposal["command_text"]
