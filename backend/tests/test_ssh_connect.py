from app.ssh.connect import SSHError, is_ssh_auth_error, is_transient_ssh_error
from app.ssh.runner import classify_ssh_failure


def test_classify_auth_error():
    assert classify_ssh_failure(SSHError("SSH authentication failed — check key")) == "auth"
    assert is_ssh_auth_error(SSHError("SSH authentication failed — check key"))


def test_classify_transient_error():
    err = SSHError("SSH connection failed: Error reading SSH protocol banner")
    assert classify_ssh_failure(err) == "transient"
    assert is_transient_ssh_error(err)


def test_classify_timeout_error():
    err = SSHError("SSH connection to 20.229.240.134:22 timed out")
    assert classify_ssh_failure(err) == "transient"
