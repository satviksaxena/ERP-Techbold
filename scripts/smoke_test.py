#!/usr/bin/env python3
"""Smoke test against hackathon requirements (techbold-case.pdf)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run from repo root: python3.12 scripts/smoke_test.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.safety.layer import SafetyLayer
from app.ssh.key_resolver import resolve_ssh_key_path


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def main() -> int:
    get_settings.cache_clear()
    s = get_settings()
    errors = 0

    print("\n=== techbold Service Desk Autopilot — smoke test ===\n")

    # A. Credentials present
    print("1. Credentials")
    if s.phoenix_api_token:
        ok(f"Phoenix token set ({s.phoenix_api_token[:20]}…)")
    else:
        fail("PHOENIX_API_TOKEN missing")
        errors += 1

    if s.phoenix_api_base_url:
        ok(f"Phoenix URL: {s.phoenix_api_base_url}")
    else:
        fail("PHOENIX_API_BASE_URL missing — get from Builder Base / Discord")
        errors += 1

    if s.azure_openai_api_key and s.azure_openai_endpoint:
        ok(f"Azure OpenAI: {s.azure_openai_deployment}")
    else:
        fail("Azure OpenAI not configured")
        errors += 1

    if s.supabase_url:
        ok(f"Supabase: {s.supabase_url}")
    else:
        fail("SUPABASE_URL missing")
        errors += 1

    # SSH keys
    print("\n2. SSH keys (5 VMs)")
    keys_dir = Path(s.ssh_keys_dir)
    for i in range(1, 6):
        p = keys_dir / f"case{i}_key.pem"
        if p.is_file():
            ok(f"case{i}_key.pem found")
        else:
            fail(f"case{i}_key.pem missing at {p}")
            errors += 1

    # C. Safety layer
    print("\n3. Safety layer (category C)")
    safety = SafetyLayer()
    if not safety.evaluate("chmod -R 777 /var").allowed:
        ok("Blocks chmod -R 777 /var")
    else:
        fail("Safety: should block chmod -R 777")
        errors += 1
    if safety.evaluate("df -h").allowed:
        ok("Allows df -h")
    else:
        fail("Safety: should allow df -h")
        errors += 1

    # Azure LLM live call
    print("\n4. Azure OpenAI live call")
    try:
        from app.agent.azure_agent import AzureOpenAIAgent

        agent = AzureOpenAIAgent(s, safety)
        proposal = agent.propose_next_command(
            {
                "title": "Nginx 502 errors",
                "report_text": "API returns 502 since morning",
                "priority": "High",
                "id": "test",
            },
            [],
            {"host_ip": "10.0.0.1", "port": 22, "username": "azureuser", "connection_status": "Idle"},
        )
        if proposal and proposal.get("command_text"):
            ok(f"Proposed: {proposal['command_text'][:60]}…")
        else:
            fail("Azure returned empty proposal")
            errors += 1
    except Exception as exc:
        fail(f"Azure OpenAI: {exc}")
        errors += 1

    # Supabase
    print("\n5. Supabase connectivity")
    try:
        from app.store.supabase_store import SupabaseStore

        store = SupabaseStore(s)
        tickets = store.client.table("tickets").select("id,ticket_code,title").limit(3).execute()
        ok(f"Supabase tickets readable ({len(tickets.data or [])} rows)")
    except Exception as exc:
        fail(f"Supabase: {exc}")
        errors += 1

    # Phoenix ERP
    print("\n6. Phoenix ERP")
    if s.phoenix_api_base_url:
        try:
            from app.phoenix.client import PhoenixClient

            phoenix = PhoenixClient(s)
            me = phoenix.get_me()
            ok(f"Authenticated as {me.get('firstname')} {me.get('lastname')} ({me.get('teamname')})")
            tickets = phoenix.list_tickets(sort="date")
            ok(f"Loaded {len(tickets)} ticket(s) from ERP")
            if tickets:
                t0 = tickets[0]
                cs = phoenix.get_customer_system(int(t0["id"]))
                sys_info = cs.get("system", cs)
                ok(f"Customer system: {sys_info.get('ip')} user={sys_info.get('username')}")
            phoenix.close()
        except Exception as exc:
            fail(f"Phoenix: {exc}")
            errors += 1
    else:
        print("  (skipped — set PHOENIX_API_BASE_URL)")

    # SSH to first Phoenix VM if available
    print("\n7. SSH to customer VM")
    if s.phoenix_api_base_url:
        try:
            from app.phoenix.client import PhoenixClient
            from app.ssh.runner import SSHRunner

            phoenix = PhoenixClient(s)
            tickets = phoenix.list_tickets(sort="date")
            if tickets:
                t0 = sorted(tickets, key=lambda t: int(t["id"]))[0]
                cs = phoenix.get_customer_system(int(t0["id"]))
                sys_info = cs.get("system", cs)
                key_path = resolve_ssh_key_path(
                    s,
                    ticket={"ticket_code": str(t0["id"])},
                    ticket_index=0,
                    system_notes=sys_info.get("notes", ""),
                )
                ssh = SSHRunner(s, safety)
                ssh.test_connection(sys_info["ip"], int(sys_info.get("port", 22)), key_path=key_path)
                ok(f"SSH OK → {sys_info['ip']} with {Path(key_path).name}")
            phoenix.close()
        except Exception as exc:
            fail(f"SSH: {exc}")
            errors += 1
    else:
        print("  (skipped — need Phoenix URL + tickets)")

    # Backend health
    print("\n8. Backend API (if running)")
    try:
        import httpx

        r = httpx.get("http://localhost:8000/health", timeout=3)
        if r.status_code == 200:
            ok(f"/health → {json.dumps(r.json())}")
        else:
            fail(f"/health returned {r.status_code}")
    except Exception:
        print("  (backend not running — start with: cd backend && uvicorn app.main:app --reload)")

    print(f"\n=== Result: {errors} error(s) ===\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
