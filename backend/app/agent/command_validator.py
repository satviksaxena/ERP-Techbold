"""Validate LLM-proposed shell commands before SSH execution."""
from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"<[^>]+>")

_PROSE_MARKERS = (
    " so that ",
    " using '",
    " using \"",
    " persists across",
    "enable the systemd service using",
    "identify ",
    "inspect ",
    "the next step",
    "you should",
    "recommend",
)

_SHELL_PREFIXES = (
    "sudo ",
    "systemctl ",
    "cat ",
    "ls ",
    "df ",
    "mount ",
    "findmnt ",
    "free ",
    "ss ",
    "journalctl ",
    "uptime",
    "hostname",
    "ps ",
    "curl ",
    "grep ",
    "find ",
    "namei ",
    "head ",
    "tail ",
    "echo ",
    "/opt/",
    "/usr/",
    "pg_isready",
    "test ",
    "wc ",
    "stat ",
)


def is_valid_shell_command(text: str) -> bool:
    """Reject natural-language or placeholder-filled pseudo commands."""
    t = (text or "").strip()
    if not t or len(t) > 400:
        return False
    if _PLACEHOLDER.search(t):
        return False
    lower = t.lower()
    if any(marker in lower for marker in _PROSE_MARKERS):
        return False
    # Multiple sentences → likely prose, not a shell line.
    if t.count(". ") >= 1 and not t.startswith("./"):
        return False
    if not any(lower.startswith(prefix) for prefix in _SHELL_PREFIXES):
        return False
    return True
