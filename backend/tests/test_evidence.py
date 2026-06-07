from app.agent.evidence import extract_from_output, format_evidence_for_llm, merge_evidence


def test_extract_failed_units():
    output = "customer-status.service loaded failed failed\n× customer-status.service"
    patch = extract_from_output("systemctl --failed", output)
    assert any("customer-status.service" in u for u in patch["failed_units"])


def test_extract_exit_code():
    patch = extract_from_output("df -h", "Filesystem\n/dev/sda1 100%\nexit code: 0")
    assert patch["last_exit_code"] == 0


def test_merge_evidence_deduplicates():
    base = {"failed_units": ["a.service"], "disabled_units": [], "full_filesystems": [], "listening_ports": [], "error_lines": [], "service_states": {}, "last_exit_code": None}
    patch = extract_from_output("systemctl --failed", "b.service failed")
    merged = merge_evidence(base, patch)
    assert "a.service" in merged["failed_units"]
    assert any("b.service" in u for u in merged["failed_units"])


def test_format_evidence_for_llm():
    text = format_evidence_for_llm({"failed_units": ["x.service"], "last_exit_code": 1})
    assert "x.service" in text
    assert "exit code: 1" in text
