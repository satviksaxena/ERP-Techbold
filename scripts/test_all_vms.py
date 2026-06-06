#!/usr/bin/env python3
"""Test Phoenix ERP + SSH reachability for all 5 hackathon VMs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.phoenix.client import PhoenixClient
from app.safety.layer import SafetyLayer
from app.ssh.key_resolver import discover_ssh_key, resolve_ssh_key_path
from app.ssh.runner import SSHError, SSHRunner
from app.store.supabase_store import SupabaseStore

PUBLIC_TEST = "sudo /opt/hackathon/public-test.sh"


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    safety = SafetyLayer()
    phoenix = PhoenixClient(settings)
    ssh = SSHRunner(settings, safety)

    print("\n=== Hackathon connectivity — 5/5 check ===\n")

    # Phoenix
    print("Phoenix ERP (68.210.101.85:8000)")
    try:
        me = phoenix.get_me()
        tickets = sorted(phoenix.list_tickets(sort="date"), key=lambda t: int(t["id"]))
        print(f"  ✓ API OK — team {me.get('teamname')}, {len(tickets)} ticket(s)\n")
    except Exception as exc:
        print(f"  ✗ Phoenix failed: {exc}\n")
        return 1

    # Supabase
    print(f"Supabase ({settings.supabase_url})")
    db_ok = False
    try:
        store = SupabaseStore(settings)
        rows = store.client.table("tickets").select("id").limit(1).execute()
        print(f"  ✓ DB OK — tickets table exists ({len(rows.data or [])} sample row(s))\n")
        db_ok = True
    except Exception as exc:
        print(f"  ✗ DB not ready: {exc}")
        print("  → Run supabase/hack_ai_bootstrap.sql in Hack AI SQL editor\n")

    # SSH all 5
    print("SSH + public-test.sh (all 5 VMs)")
    ssh_ok = 0
    results: list[tuple[int, str, str, str]] = []

    for idx, pt in enumerate(tickets):
        tid = int(pt["id"])
        try:
            cs = phoenix.get_customer_system(tid)
            system = cs.get("system", cs)
            ip = system.get("ip")
            port = int(system.get("port", 22))
            user = system.get("username", "azureuser")
            notes = system.get("notes", "")

            key_path = resolve_ssh_key_path(
                settings,
                ticket={"ticket_code": str(tid)},
                ticket_index=idx,
                system_notes=notes,
            )
            ssh.test_connection(ip, port, key_path=key_path)

            discovered = discover_ssh_key(
                settings,
                host=ip,
                port=port,
                username=user,
                preferred_keys=[key_path],
            )
            key_used = Path(discovered or key_path).name

            result = ssh.run(ip, port, PUBLIC_TEST, key_path=discovered or key_path)
            status = "PASS" if result.exit_code == 0 else f"FAIL (exit {result.exit_code})"
            line = f"  ✓ {tid} {ip} SSH OK — public-test {status} [{key_used}]"
            print(line)
            ssh_ok += 1
            results.append((tid, ip, "ssh_ok", status))
        except SSHError as exc:
            print(f"  ✗ {tid} SSH failed: {exc}")
            results.append((tid, ip if "ip" in dir() else "?", "ssh_fail", str(exc)[:80]))
        except Exception as exc:
            print(f"  ✗ {tid} error: {exc}")
            results.append((tid, "?", "error", str(exc)[:80]))

    phoenix.close()

    print(f"\n=== Summary ===")
    print(f"  Phoenix ERP:     ✓ ({len(tickets)}/5 tickets)")
    print(f"  Hack AI DB:      {'✓ ready' if db_ok else '✗ run bootstrap SQL first'}")
    print(f"  SSH reachable:   {ssh_ok}/5")
    print(f"  public-test PASS: {sum(1 for r in results if 'PASS' in r[3])}/5")
    print()
    return 0 if ssh_ok == 5 and db_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
