from app.agent.verifier import verify_rule_based


def test_verifier_continue_diagnose_without_evidence():
    result = verify_rule_based(
        {"title": "Service down", "likely_root_cause": "systemd unit failed"},
        {},
        diagnostic_count=0,
        has_fix=False,
    )
    assert result.recommend == "continue_diagnose"


def test_verifier_apply_fix_on_failed_units():
    result = verify_rule_based(
        {"title": "Service not enabled", "likely_root_cause": "systemd unit disabled on boot"},
        {"failed_units": ["customer-status.service"], "disabled_units": []},
        diagnostic_count=2,
        has_fix=False,
    )
    assert result.recommend == "apply_fix"
    assert result.hypothesis_supported is True


def test_verifier_apply_fix_after_reboot_diagnostics():
    result = verify_rule_based(
        {"title": "Service down", "likely_root_cause": "systemd unit not enabled on boot"},
        {},
        diagnostic_count=4,
        has_fix=False,
        report_text="Status API unavailable after reboot until manual restart",
    )
    assert result.recommend == "apply_fix"


def test_verifier_apply_fix_on_readonly_mount():
    result = verify_rule_based(
        {"title": "Disk read-only", "likely_root_cause": "filesystem mounted read-only"},
        {"readonly_mounts": ["/dev/sda1 on / type ext4 (ro,relatime)"]},
        diagnostic_count=3,
        has_fix=False,
    )
    assert result.recommend == "apply_fix"

def test_verifier_continue_diagnose_disk_before_mount_check():
    result = verify_rule_based(
        {"title": "Disk read-only", "likely_root_cause": "filesystem mounted read-only"},
        {},
        diagnostic_count=4,
        has_fix=False,
        commands=[
            {"command_text": "df -h", "human_status": "Approved"},
            {"command_text": "ss -tlnp | head -30", "human_status": "Approved"},
        ],
    )
    assert result.recommend == "continue_diagnose"

    result = verify_rule_based(None, {}, diagnostic_count=3, has_fix=True)
    assert result.recommend == "validate"
