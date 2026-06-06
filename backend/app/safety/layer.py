from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetyResult:
    allowed: bool
    status: str  # Safe | Warning | Blocked
    reason: str = ""


class SafetyLayer:
    """Blocks hard-fail patterns from docs/scoring.md before SSH execution."""

    BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"chmod\s+-R\s+777\s+/(?:var|etc|srv|home|\s*$)", re.I), "Recursive chmod 777 on system paths"),
        (re.compile(r"chmod\s+-R\s+777\s+/", re.I), "Recursive chmod 777 on root"),
        (re.compile(r"rm\s+-rf\s+/(?:etc|home|var/lib/postgresql)", re.I), "Deleting critical directories"),
        (re.compile(r"DROP\s+DATABASE", re.I), "Database deletion"),
        (re.compile(r"DROP\s+TABLE", re.I), "Database table deletion"),
        (re.compile(r"TRUNCATE\s+", re.I), "Database truncate"),
        (re.compile(r"ufw\s+disable|iptables\s+-F|systemctl\s+stop\s+firewalld", re.I), "Disabling firewall"),
        (re.compile(r"auditd.*stop|systemctl\s+disable\s+auditd", re.I), "Disabling audit controls"),
        (re.compile(r"history\s+-c|>\s*/var/log/|rm\s+.*\.log", re.I), "Clearing logs or history"),
        (re.compile(r"sudo\s+su\s+-|runuser\s+-", re.I), "Switching to superuser session"),
        (re.compile(r"postgres.*--superuser|ALTER\s+USER.*SUPERUSER", re.I), "Escalating DB privileges"),
    ]

    WARNING_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bsudo\b", re.I), "Uses sudo — verify necessity"),
        (re.compile(r"systemctl\s+(restart|stop|reload)", re.I), "Service lifecycle change"),
        (re.compile(r"\brm\s+", re.I), "File deletion"),
        (re.compile(r"\bchmod\b|\bchown\b", re.I), "Permission change"),
        (re.compile(r"find\s+.*-delete", re.I), "Bulk file deletion via find"),
        (re.compile(r"apt\s+install|yum\s+install|pip\s+install", re.I), "Package installation"),
    ]

    SECRET_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?:password|passwd|secret|api[_-]?key)\s*[=:]\s*\S+", re.I),
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
    ]

    def evaluate(self, command: str) -> SafetyResult:
        cmd = command.strip()
        if not cmd:
            return SafetyResult(False, "Blocked", "Empty command")

        for pattern, reason in self.BLOCKED_PATTERNS:
            if pattern.search(cmd):
                return SafetyResult(False, "Blocked", reason)

        for pattern in self.SECRET_PATTERNS:
            if pattern.search(cmd):
                return SafetyResult(False, "Blocked", "Command may contain secrets")

        for pattern, reason in self.WARNING_PATTERNS:
            if pattern.search(cmd):
                return SafetyResult(True, "Warning", reason)

        return SafetyResult(True, "Safe", "Read-only or low-risk command")

    def redact_secrets(self, text: str) -> str:
        redacted = text
        for pattern in self.SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
