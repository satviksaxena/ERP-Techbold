#!/usr/bin/env python3
"""Validate Hack AI database + backend API after migration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx

from app.config import get_settings
from app.phoenix.client import PhoenixClient
from app.store.supabase_store import SupabaseStore

HACK_AI = "cpobgjkowqlqmogmuelk"
OLD_UUID = "c0eb5a41-d48b-4fab-9b1c-e469a6502ea4"


def main() -> int:
    get_settings.cache_clear()
    s = get_settings()
    errors = 0

    print("\n=== Hack AI validation ===\n")

    # 1. Env points to Hack AI
    if HACK_AI not in (s.supabase_url or ""):
        print(f"  ✗ SUPABASE_URL not Hack AI: {s.supabase_url}")
        errors += 1
    else:
        print(f"  ✓ SUPABASE_URL → Hack AI ({HACK_AI})")

    if not s.supabase_service_role_key and not s.supabase_publishable_key:
        print("  ✗ No Supabase keys configured")
        errors += 1
    else:
        print("  ✓ Supabase keys configured")

    # 2. Tables + tickets
    store = SupabaseStore(s)
    tables = ["tickets", "system_info", "ai_commands", "activities", "ticket_hypotheses"]
    for t in tables:
        try:
            store.client.table(t).select("*").limit(1).execute()
            print(f"  ✓ table {t}")
        except Exception as exc:
            print(f"  ✗ table {t}: {exc}")
            errors += 1

    tickets = store.client.table("tickets").select("id,ticket_code").order("ticket_code").execute()
    codes = [r["ticket_code"] for r in (tickets.data or [])]
    print(f"  ✓ tickets in DB: {codes}")

    if len(codes) < 5:
        print("  ⚠ fewer than 5 tickets — syncing from Phoenix…")
        try:
            r = httpx.post("http://localhost:8000/api/sync/tickets", timeout=60)
            r.raise_for_status()
            synced = r.json()
            print(f"  ✓ synced {synced.get('count', 0)} tickets")
            tickets = store.client.table("tickets").select("id,ticket_code").order("ticket_code").execute()
            codes = [r["ticket_code"] for r in (tickets.data or [])]
        except Exception as exc:
            print(f"  ✗ sync failed: {exc}")
            errors += 1

    # 3. Old UUID gone
    old = store.client.table("tickets").select("id").eq("id", OLD_UUID).execute()
    if old.data:
        print(f"  ✗ stale old Lovable UUID still present: {OLD_UUID}")
        errors += 1
    else:
        print("  ✓ old Lovable UUID not in Hack AI")

    # 4. Phoenix
    try:
        phoenix = PhoenixClient(s)
        erp = phoenix.list_tickets(sort="date")
        print(f"  ✓ Phoenix ERP: {len(erp)} tickets")
        phoenix.close()
    except Exception as exc:
        print(f"  ✗ Phoenix: {exc}")
        errors += 1

    # 5. Backend API on current 7001
    t7001 = store.get_ticket_by_code("7001")
    if not t7001:
        print("  ✗ ticket 7001 missing")
        errors += 1
    else:
        uid = t7001["id"]
        print(f"  ✓ ticket 7001 UUID: {uid}")
        try:
            h = httpx.get(f"http://localhost:8000/health", timeout=5).json()
            print(f"  ✓ backend health: {h.get('status')}")
            r = httpx.post(f"http://localhost:8000/api/tickets/{uid}/connect-ssh", timeout=30)
            if r.status_code == 200:
                print(f"  ✓ SSH connect: {r.json().get('connection_status')}")
            else:
                print(f"  ⚠ SSH connect HTTP {r.status_code}: {r.text[:120]}")
        except Exception as exc:
            print(f"  ✗ backend API: {exc}")
            errors += 1

    print(f"\n=== Result: {errors} error(s) ===\n")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
