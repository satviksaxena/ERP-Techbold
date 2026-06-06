#!/usr/bin/env python3
"""End-to-end test: sync ERP, SSH all 5 cases, analyze + validate flow."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx

from app.agent.orchestrator import AgentOrchestrator
from app.audit.log import AuditLog
from app.config import get_settings
from app.phoenix.client import PhoenixClient
from app.safety.layer import SafetyLayer
from app.ssh.key_resolver import discover_ssh_key, resolve_ssh_key_path
from app.ssh.runner import SSHError, SSHRunner
from app.store.supabase_store import SupabaseStore

PUBLIC_TEST = "sudo /opt/hackathon/public-test.sh"


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    safety = SafetyLayer()
    store = SupabaseStore(settings)
    phoenix = PhoenixClient(settings)
    ssh = SSHRunner(settings, safety)
    orch = AgentOrchestrator(settings, store, phoenix, ssh, safety, AuditLog())

    errors = 0
    section("1. Backend API")
    try:
        r = httpx.get("http://localhost:8000/health", timeout=5)
        health = r.json()
        print(f"  ✓ /health {health}")
    except Exception as exc:
        print(f"  ✗ Backend not running: {exc}")
        return 1

    section("2. Sync Phoenix → Supabase")
    try:
        synced = orch.sync_tickets()
        print(f"  ✓ Synced {len(synced)} ticket(s)")
        for t in synced:
            print(f"    - {t['ticket_code']}: {t['title'][:50]}")
    except Exception as exc:
        print(f"  ✗ Sync failed: {exc}")
        return 1

    section("3. Per-case: customer-system + SSH + AI + public-test")
    phoenix_tickets = sorted(phoenix.list_tickets(sort="date"), key=lambda t: int(t["id"]))

    for idx, pt in enumerate(phoenix_tickets):
        tid = int(pt["id"])
        local = store.get_ticket_by_code(str(tid))
        if not local:
            print(f"  ✗ {tid}: not in Supabase after sync")
            errors += 1
            continue

        print(f"\n--- Case {tid}: {pt.get('title', '')[:55]} ---")
        cs = phoenix.get_customer_system(tid)
        system = cs.get("system", cs)
        ip = system.get("ip")
        port = int(system.get("port", 22))
        user = system.get("username", "azureuser")
        notes = system.get("notes", "")
        print(f"  VM: {user}@{ip}:{port}")
        print(f"  notes: {notes[:70]}…")

        preferred = resolve_ssh_key_path(
            settings,
            ticket=local,
            ticket_index=idx,
            system_notes=notes,
        )
        key_used = preferred
        ssh_ok = False
        try:
            ssh.test_connection(ip, port, key_path=preferred)
            ssh_ok = True
            print(f"  ✓ SSH with {Path(preferred).name}")
        except SSHError:
            try:
                key_used = discover_ssh_key(
                    settings, ip, port, username=user, preferred_keys=[preferred]
                )
                ssh.test_connection(ip, port, key_path=key_used)
                ssh_ok = True
                print(f"  ✓ SSH after key discovery → {Path(key_used).name}")
            except SSHError as exc:
                print(f"  ✗ SSH failed: {exc}")
                errors += 1

        if ssh_ok:
            try:
                result = ssh.run(ip, port, "hostname && uptime", key_path=key_used)
                print(f"  ✓ hostname: {result.stdout.strip()[:80]}")
            except SSHError as exc:
                print(f"  ✗ Command run failed: {exc}")
                errors += 1

            try:
                test = ssh.run(ip, port, PUBLIC_TEST, key_path=key_used)
                status = "PASS" if test.exit_code == 0 else f"FAIL(exit {test.exit_code})"
                snippet = (test.stdout or test.stderr or "")[:200].replace("\n", " ")
                print(f"  {'✓' if test.exit_code == 0 else '⚠'} public-test.sh → {status}")
                if snippet:
                    print(f"    output: {snippet}")
            except SSHError as exc:
                print(f"  ⚠ public-test.sh blocked/failed: {exc}")

        # AI analysis via API
        try:
            r = httpx.post(
                f"http://localhost:8000/api/tickets/{local['id']}/analyze",
                timeout=120,
            )
            if r.status_code == 200:
                body = r.json()
                cmd = body.get("command", {})
                hypos = body.get("hypotheses", {}).get("hypotheses", [])
                print(f"  ✓ Analyze → command: {cmd.get('command_text', '')[:70]}")
                print(f"  ✓ Hypotheses: {len(hypos)} path(s)")
                for i, h in enumerate(hypos[:3]):
                    print(f"      [{i}] {h.get('title')} ({h.get('confidence')})")
            else:
                print(f"  ✗ Analyze HTTP {r.status_code}: {r.text[:200]}")
                errors += 1
        except Exception as exc:
            print(f"  ✗ Analyze failed: {exc}")
            errors += 1

        time.sleep(0.5)

    section("4. API sync endpoint")
    try:
        r = httpx.post("http://localhost:8000/api/sync/tickets", timeout=60)
        body = r.json()
        print(f"  ✓ POST /api/sync/tickets → count={body.get('count')}")
    except Exception as exc:
        print(f"  ✗ {exc}")
        errors += 1

    phoenix.close()
    section(f"RESULT: {errors} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
