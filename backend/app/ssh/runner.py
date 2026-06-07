from __future__ import annotations

from dataclasses import dataclass

import paramiko

from app.config import Settings
from app.safety.layer import SafetyLayer
from app.ssh.connect import SSHError, is_ssh_auth_error, is_transient_ssh_error
from app.ssh.session_pool import get_session_pool


@dataclass
class SSHResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


class SSHRunner:
    def __init__(self, settings: Settings, safety: SafetyLayer | None = None):
        self.settings = settings
        self.safety = safety or SafetyLayer()
        self._key_path = settings.ssh_private_key_path
        self._username = settings.ssh_username

    def _connect(self, host: str, port: int, key_path: str | None = None) -> paramiko.SSHClient:
        path = key_path or self._key_path
        pool = get_session_pool(self.settings)
        try:
            return pool.get_or_connect(host, port, self._username, path)
        except SSHError:
            raise
        except Exception as exc:
            raise SSHError(f"SSH connection failed: {exc}") from exc

    def test_connection(self, host: str, port: int = 22, key_path: str | None = None) -> None:
        """Verify SSH and keep session in pool for subsequent commands."""
        client = self._connect(host, port, key_path)
        if not client.get_transport() or not client.get_transport().is_active():
            raise SSHError(f"SSH connection to {host}:{port} failed: transport inactive")

    def run(self, host: str, port: int, command: str, key_path: str | None = None) -> SSHResult:
        safety = self.safety.evaluate(command)
        if not safety.allowed:
            raise SSHError(f"Command blocked by safety layer: {safety.reason}")

        import time

        start = time.monotonic()
        pool = get_session_pool(self.settings)
        try:
            client = self._connect(host, port, key_path)
            _, stdout, stderr = client.exec_command(
                command,
                timeout=self.settings.ssh_command_timeout,
            )
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
        except SSHError as exc:
            if is_ssh_auth_error(exc):
                pool.invalidate(host, port, self._username)
            elif is_transient_ssh_error(exc):
                pool.invalidate(host, port, self._username)
            raise
        except Exception as exc:
            pool.invalidate(host, port, self._username)
            raise SSHError(f"SSH command failed: {exc}") from exc

        duration_ms = int((time.monotonic() - start) * 1000)
        return SSHResult(
            command=command,
            stdout=self.safety.redact_secrets(out),
            stderr=self.safety.redact_secrets(err),
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    def format_output(self, result: SSHResult) -> str:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).isoformat()
        lines = [
            f"+ executing on {self._username}@{result.command[:40]}…",
            f"[{ts}] $ {result.command}",
        ]
        if result.stdout.strip():
            lines.append(result.stdout.rstrip())
        if result.stderr.strip():
            lines.append(f"stderr:\n{result.stderr.rstrip()}")
        lines.append(f"[{ts}] exit code: {result.exit_code} ({result.duration_ms}ms)")
        return "\n".join(lines)


def classify_ssh_failure(exc: SSHError) -> str:
    if is_ssh_auth_error(exc):
        return "auth"
    if is_transient_ssh_error(exc):
        return "transient"
    return "other"
