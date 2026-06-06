from __future__ import annotations

from dataclasses import dataclass

import paramiko

from app.config import Settings
from app.safety.layer import SafetyLayer
from app.ssh.connect import SSHError, is_ssh_auth_error, is_transient_ssh_error, open_ssh_client


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
        try:
            return open_ssh_client(
                self.settings,
                host,
                port,
                self._username,
                path,
            )
        except SSHError:
            raise
        except Exception as exc:
            raise SSHError(f"SSH connection failed: {exc}") from exc

    def test_connection(self, host: str, port: int = 22, key_path: str | None = None) -> None:
        client = self._connect(host, port, key_path)
        client.close()

    def run(self, host: str, port: int, command: str, key_path: str | None = None) -> SSHResult:
        safety = self.safety.evaluate(command)
        if not safety.allowed:
            raise SSHError(f"Command blocked by safety layer: {safety.reason}")

        import time

        start = time.monotonic()
        client = self._connect(host, port, key_path)
        try:
            _, stdout, stderr = client.exec_command(
                command,
                timeout=self.settings.ssh_command_timeout,
            )
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
        finally:
            client.close()

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
