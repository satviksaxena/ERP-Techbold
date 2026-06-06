#!/usr/bin/env python3
"""Point backend + frontend at a Supabase project (e.g. Hack AI).

Usage:
  python scripts/configure_hack_ai_supabase.py \\
    --url https://YOUR_REF.supabase.co \\
    --anon-key eyJ... \\
    --service-role eyJ...   # optional but recommended for backend

Then run supabase/hack_ai_bootstrap.sql in that project's SQL editor if tables are missing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_ref(url: str) -> str:
    m = re.match(r"https://([a-z0-9]+)\.supabase\.co/?$", url.strip())
    if not m:
        raise SystemExit(f"Invalid Supabase URL: {url}")
    return m.group(1)


def patch_env_file(path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def verify(url: str, anon_key: str, service_role: str = "") -> None:
    try:
        from supabase import create_client
    except ImportError:
        print("Install supabase in backend venv to verify, skipping check.")
        return
    key = service_role or anon_key
    if key.startswith("PASTE_") or key.startswith("PLACEHOLDER"):
        print("⚠ Publishable key not set yet — paste it into .env after copying from dashboard")
        return
    client = create_client(url, key)
    try:
        client.table("tickets").select("id").limit(1).execute()
        print("✓ Connected — tickets table exists")
    except Exception as exc:
        msg = str(exc)
        if "Could not find the table" in msg or "PGRST205" in msg:
            print("⚠ Connected but tickets table missing — run supabase/hack_ai_bootstrap.sql in SQL editor")
        else:
            print(f"⚠ Connection check: {exc}")


def main() -> None:
    p = argparse.ArgumentParser(description="Configure Supabase env for Hack AI project")
    p.add_argument("--url", required=True, help="https://YOUR_REF.supabase.co")
    p.add_argument("--anon-key", required=True, help="anon / publishable key from Settings → API")
    p.add_argument("--service-role", default="", help="service_role key (backend, optional)")
    args = p.parse_args()

    url = args.url.rstrip("/")
    ref = project_ref(url)
    anon = args.anon_key.strip()

    root_updates = {
        "SUPABASE_URL": url,
        "SUPABASE_PUBLISHABLE_KEY": anon,
        "VITE_SUPABASE_URL": url,
        "VITE_SUPABASE_PUBLISHABLE_KEY": anon,
    }
    if args.service_role:
        root_updates["SUPABASE_SERVICE_ROLE_KEY"] = args.service_role.strip()

    fe_updates = {
        "SUPABASE_PROJECT_ID": ref,
        "SUPABASE_URL": url,
        "SUPABASE_PUBLISHABLE_KEY": anon,
        "VITE_SUPABASE_PROJECT_ID": ref,
        "VITE_SUPABASE_URL": url,
        "VITE_SUPABASE_PUBLISHABLE_KEY": anon,
    }

    patch_env_file(ROOT / ".env", root_updates)
    patch_env_file(ROOT / "frontend" / ".env", fe_updates)

    print(f"Updated .env and frontend/.env → project {ref}")
    print(f"Dashboard: https://supabase.com/dashboard/project/{ref}")
    verify(url, anon, args.service_role)


if __name__ == "__main__":
    main()
