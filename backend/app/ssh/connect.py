from __future__ import annotations

import socket
import time
from pathlib import Path

import paramiko

from app.config import Settings


class SSHError(Exception):
    pass


def is_ssh_auth_error(exc: BaseException) -> bool:
    if isinstance(exc, paramiko.AuthenticationException):
        return True
    if isinstance(exc, SSHError):
        return "authentication failed" in str(exc).lower()
    return False


def is_transient_ssh_error(exc: BaseException) -> bool:
    if isinstance(exc, socket.timeout):
        return True
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, OSError):
        return True
    if isinstance(exc, SSHError):
        msg = str(exc).lower()
        return any(
            token in msg
            for token in ("timed out", "timeout", "banner", "connection reset", "connection refused")
        )
    if isinstance(exc, paramiko.SSHException):
        msg = str(exc).lower()
        return "banner" in msg or "timeout" in msg
    return False


def load_private_key(path: str) -> paramiko.PKey:
    try:
        return paramiko.RSAKey.from_private_key_file(path)
    except FileNotFoundError as exc:
        raise SSHError(f"SSH key not found at {path}") from exc
    except paramiko.SSHException as exc:
        raise SSHError(f"Invalid SSH key: {exc}") from exc


def open_ssh_client(
    settings: Settings,
    host: str,
    port: int,
    username: str,
    key_path: str,
    *,
    retries: int | None = None,
) -> paramiko.SSHClient:
    """Connect with retries on transient VM/network errors."""
    attempts = retries if retries is not None else settings.ssh_connect_retries
    key = load_private_key(key_path)
    last_exc: BaseException | None = None

    for attempt in range(attempts):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=username,
                pkey=key,
                timeout=settings.ssh_connect_timeout,
                banner_timeout=settings.ssh_connect_timeout,
                auth_timeout=settings.ssh_connect_timeout,
            )
            return client
        except paramiko.AuthenticationException as exc:
            client.close()
            raise SSHError("SSH authentication failed — check key and username") from exc
        except socket.timeout as exc:
            client.close()
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(settings.ssh_retry_delay_seconds)
                continue
            raise SSHError(f"SSH connection to {host}:{port} timed out") from exc
        except paramiko.SSHException as exc:
            client.close()
            last_exc = exc
            if is_transient_ssh_error(exc) and attempt + 1 < attempts:
                time.sleep(settings.ssh_retry_delay_seconds)
                continue
            raise SSHError(f"SSH connection failed: {exc}") from exc
        except OSError as exc:
            client.close()
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(settings.ssh_retry_delay_seconds)
                continue
            raise SSHError(f"SSH connection to {host}:{port} failed: {exc}") from exc

    raise SSHError(f"SSH connection to {host}:{port} failed: {last_exc}")

def tcp_ping(host: str, port: int, timeout: float = 5.0) -> tuple[int | None, str | None]:
    """Perform a fast TCP connection to measure latency and check reachability without full SSH auth."""
    import socket
    import time
    start = time.perf_counter()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        latency = int((time.perf_counter() - start) * 1000)
        return latency, None
    except socket.timeout:
        return None, "Timeout"
    except ConnectionRefusedError:
        return None, "Connection Refused"
    except Exception as e:
        return None, str(e)
