import pytest

from app.safety.layer import SafetyLayer


@pytest.fixture
def safety():
    return SafetyLayer()


def test_blocks_chmod_777(safety):
    r = safety.evaluate("chmod -R 777 /var")
    assert r.allowed is False
    assert r.status == "Blocked"


def test_blocks_drop_database(safety):
    r = safety.evaluate("psql -c 'DROP DATABASE prod'")
    assert r.allowed is False


def test_allows_df(safety):
    r = safety.evaluate("df -h")
    assert r.allowed is True
    assert r.status == "Safe"


def test_warns_sudo(safety):
    r = safety.evaluate("sudo systemctl restart nginx")
    assert r.allowed is True
    assert r.status == "Warning"


def test_redacts_secrets(safety):
    text = "password=supersecret123"
    assert "[REDACTED]" in safety.redact_secrets(text)
