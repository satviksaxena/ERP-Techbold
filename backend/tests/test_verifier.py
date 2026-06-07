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


def test_verifier_validate_after_fix():
    result = verify_rule_based(None, {}, diagnostic_count=3, has_fix=True)
    assert result.recommend == "validate"
