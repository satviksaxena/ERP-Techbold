"""Reuse SSH sessions per VM to avoid repeated handshakes and flaky reconnects."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import paramiko

from app.config import Settings
from app.ssh.connect import open_ssh_client

logger = logging.getLogger(__name__)


@dataclass
class _Session:
    client: paramiko.SSHClient
    last_used: float


class SSHSessionPool:
    """Thread-safe pool of open Paramiko clients keyed by host:port:username."""

    def __init__(self, settings: Settings, *, ttl_seconds: float = 300.0):
        self.settings = settings
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(host: str, port: int, username: str) -> str:
        return f"{username}@{host}:{port}"

    def _is_alive(self, client: paramiko.SSHClient) -> bool:
        transport = client.get_transport()
        return bool(transport and transport.is_active())

    def _configure_keepalive(self, client: paramiko.SSHClient) -> None:
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)

    def get_or_connect(
        self,
        host: str,
        port: int,
        username: str,
        key_path: str,
    ) -> paramiko.SSHClient:
        key = self._key(host, port, username)
        now = time.monotonic()

        with self._lock:
            self._evict_stale(now)
            existing = self._sessions.get(key)
            if existing and self._is_alive(existing.client):
                existing.last_used = now
                return existing.client

            if existing:
                try:
                    existing.client.close()
                except Exception:
                    pass
                self._sessions.pop(key, None)

        client = open_ssh_client(self.settings, host, port, username, key_path)
        self._configure_keepalive(client)

        with self._lock:
            self._sessions[key] = _Session(client=client, last_used=time.monotonic())
        return client

    def invalidate(self, host: str, port: int, username: str) -> None:
        key = self._key(host, port, username)
        with self._lock:
            session = self._sessions.pop(key, None)
        if session:
            try:
                session.client.close()
            except Exception:
                pass

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            try:
                session.client.close()
            except Exception:
                pass

    def _evict_stale(self, now: float) -> None:
        stale_keys = [
            k for k, s in self._sessions.items() if now - s.last_used > self.ttl_seconds
        ]
        for k in stale_keys:
            session = self._sessions.pop(k, None)
            if session:
                try:
                    session.client.close()
                except Exception:
                    pass


_global_pool: SSHSessionPool | None = None
_pool_lock = threading.Lock()


def get_session_pool(settings: Settings) -> SSHSessionPool:
    global _global_pool
    with _pool_lock:
        if _global_pool is None:
            _global_pool = SSHSessionPool(settings)
        return _global_pool
