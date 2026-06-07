"""Curated Linux runbook snippets — keyword retrieval for agent grounding."""
from __future__ import annotations

RUNBOOKS: list[dict[str, str]] = [
    {
        "keywords": "service boot enabled systemd down failed inactive",
        "title": "Systemd service not enabled on boot",
        "steps": (
            "1. systemctl --failed --no-pager\n"
            "2. systemctl status <unit> --no-pager -l\n"
            "3. journalctl -u <unit> -n 50 --no-pager\n"
            "4. Fix: sudo systemctl enable --now <unit.service>\n"
            "5. Verify: systemctl is-enabled <unit> && public-test.sh"
        ),
    },
    {
        "keywords": "permission denied upload chown chmod www-data",
        "title": "Filesystem permissions on app directory",
        "steps": (
            "1. namei -l /path/to/dir or ls -la\n"
            "2. Fix: sudo chown -R www-data:www-data /specific/path (never chmod -R 777)\n"
            "3. Verify ownership and retry app write"
        ),
    },
    {
        "keywords": "502 nginx proxy upstream web http site",
        "title": "Web proxy / upstream misconfiguration",
        "steps": (
            "1. systemctl status nginx --no-pager\n"
            "2. nginx -t\n"
            "3. ss -tlnp | grep -E ':80|:443|:8080'\n"
            "4. Fix config or restart upstream app service\n"
            "5. sudo systemctl reload nginx"
        ),
    },
    {
        "keywords": "disk full space storage df no space left",
        "title": "Disk space exhaustion",
        "steps": (
            "1. df -h && df -i\n"
            "2. du -xh /var/log /tmp /var 2>/dev/null | sort -h | tail -20\n"
            "3. Safely truncate or remove known log rotators — never rm -rf /var\n"
            "4. Restart affected service after space freed"
        ),
    },
    {
        "keywords": "metrics agent monitoring dashboard",
        "title": "Metrics / monitoring agent",
        "steps": (
            "1. systemctl status metrics-agent.service --no-pager -l\n"
            "2. journalctl -u metrics-agent.service -n 100 --no-pager\n"
            "3. Fix: enable/start unit or fix config referenced in journal\n"
            "4. public-test.sh for hackathon validation"
        ),
    },
    {
        "keywords": "postgres database connection sync order",
        "title": "Database connectivity",
        "steps": (
            "1. systemctl status postgresql --no-pager\n"
            "2. ss -tlnp | grep 5432\n"
            "3. journalctl -u postgresql -n 50 --no-pager\n"
            "4. Restore service or fix pg_hba/local connection settings"
        ),
    },
]


def retrieve_runbooks(ticket: dict[str, Any], hypothesis: dict[str, Any] | None = None, limit: int = 2) -> str:
    text = " ".join(
        [
            ticket.get("title") or "",
            ticket.get("report_text") or "",
            (hypothesis or {}).get("title") or "",
            (hypothesis or {}).get("likely_root_cause") or "",
        ]
    ).lower()

    scored: list[tuple[int, dict[str, str]]] = []
    tokens = set(text.split())
    for book in RUNBOOKS:
        keywords = book["keywords"].split()
        score = sum(1 for kw in keywords if kw in text or kw in tokens)
        if score > 0:
            scored.append((score, book))

    scored.sort(key=lambda x: -x[0])
    if not scored:
        return ""

    lines = ["Relevant runbook guidance:"]
    for _, book in scored[:limit]:
        lines.append(f"- {book['title']}:\n{book['steps']}")
    return "\n".join(lines)
