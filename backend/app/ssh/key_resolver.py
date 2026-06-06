from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.config import Settings
from app.ssh.connect import is_ssh_auth_error, is_transient_ssh_error, open_ssh_client


def list_available_keys(settings: Settings) -> list[str]:
    keys_dir = Path(settings.ssh_keys_dir)
    keys = sorted(keys_dir.glob("case*_key.pem"))
    if keys:
        return [str(p) for p in keys]
    default = Path(settings.ssh_private_key_path)
    return [str(default)] if default.is_file() else []


def resolve_ssh_key_path(
    settings: Settings,
    *,
    ticket: dict[str, Any] | None = None,
    ticket_index: int | None = None,
    system_notes: str = "",
) -> str:
    """Map a ticket to case1_key.pem … case5_key.pem from tb-hackathon-ssh."""
    keys_dir = Path(settings.ssh_keys_dir)
    default = Path(settings.ssh_private_key_path)

    match = re.search(r"-(\d+)\s+public", system_notes)
    if match:
        n = int(match.group(1)) + 1
        if 1 <= n <= 5:
            candidate = keys_dir / f"case{n}_key.pem"
            if candidate.is_file():
                return str(candidate)

    if ticket:
        code = str(ticket.get("ticket_code", ""))
        tail = re.search(r"(\d)$", code)
        if tail:
            n = int(tail.group(1))
            if 1 <= n <= 5:
                candidate = keys_dir / f"case{n}_key.pem"
                if candidate.is_file():
                    return str(candidate)

    if ticket_index is not None:
        n = (ticket_index % 5) + 1
        candidate = keys_dir / f"case{n}_key.pem"
        if candidate.is_file():
            return str(candidate)

    for i in range(1, 6):
        candidate = keys_dir / f"case{i}_key.pem"
        if candidate.is_file():
            return str(candidate)

    return str(default)


def discover_ssh_key(
    settings: Settings,
    host: str,
    port: int = 22,
    username: str | None = None,
    preferred_keys: list[str] | None = None,
) -> str:
    """Try each .pem until one authenticates. Network errors fail fast (wrong key ≠ timeout)."""
    from app.ssh.runner import SSHError

    user = username or settings.ssh_username
    candidates = preferred_keys or []
    seen = set(candidates)
    for path in list_available_keys(settings):
        if path not in seen:
            candidates.append(path)
            seen.add(path)

    if not candidates:
        raise SSHError(f"SSH key discovery failed for {host}: no keys available")

    last_error = "no keys available"
    for path in candidates:
        try:
            client = open_ssh_client(settings, host, port, user, path)
            client.close()
            return path
        except SSHError as exc:
            last_error = str(exc)
            if is_transient_ssh_error(exc):
                raise SSHError(f"SSH key discovery failed for {host}: {last_error}") from exc
            if is_ssh_auth_error(exc):
                last_error = f"auth failed for {Path(path).name}"
                continue
            raise

    raise SSHError(f"SSH key discovery failed for {host}: {last_error}")
