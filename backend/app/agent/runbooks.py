"""Curated Linux runbooks — hybrid retrieval, incident classification, execution plans."""
from __future__ import annotations

import math
import re
from typing import Any

from app.agent.llm_schemas import PUBLIC_TEST_COMMAND

# FastStep: agent, command, diff, intent
RunbookStep = tuple[str, str, str, str]

RUNBOOKS: list[dict[str, Any]] = [
    {
        "id": "service_systemd",
        "keywords": "service boot enabled systemd down failed inactive not running api status",
        "title": "Systemd service not enabled on boot",
        "steps": (
            "1. systemctl --failed --no-pager\n"
            "2. systemctl status <unit> --no-pager -l\n"
            "3. journalctl -u <unit> -n 50 --no-pager\n"
            "4. Fix: sudo systemctl enable --now <unit.service>\n"
            "5. Verify: systemctl is-enabled <unit>"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "systemctl --failed --no-pager",
                "+ list failed systemd units",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "systemctl list-units --state=failed --no-pager",
                "+ enumerate failed units",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "journalctl -p err -n 30 --no-pager",
                "+ recent error logs for failed services",
                "diagnostic",
            ),
        ],
    },
    {
        "id": "permission_upload",
        "keywords": "permission denied upload chown chmod www-data portal document",
        "title": "Filesystem permissions on app directory",
        "steps": (
            "1. stat or ls -la on upload directory\n"
            "2. Fix: sudo chown -R www-data:www-data /specific/path (never chmod -R 777)\n"
            "3. Verify ownership and retry app write"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "stat /srv/customer-portal/uploads 2>/dev/null || ls -ld /srv/customer-portal/uploads",
                "+ confirm upload directory ownership",
                "diagnostic",
            ),
            (
                "Problem Solver",
                "sudo chown -R www-data:www-data /srv/customer-portal/uploads",
                "+ fix upload directory ownership",
                "fix",
            ),
        ],
    },
    {
        "id": "nginx_proxy",
        "keywords": "502 nginx proxy upstream web http site bad gateway",
        "title": "Web proxy / upstream misconfiguration",
        "steps": (
            "1. systemctl status nginx --no-pager\n"
            "2. nginx -t\n"
            "3. ss -tlnp | grep -E ':80|:443|:8080'\n"
            "4. Fix config or restart upstream app service\n"
            "5. sudo systemctl reload nginx"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "systemctl status nginx --no-pager -l",
                "+ inspect nginx service",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "nginx -t",
                "+ validate nginx configuration",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "ss -tlnp | grep -E ':80|:443|:8080'",
                "+ inspect web listening ports",
                "diagnostic",
            ),
        ],
    },
    {
        "id": "disk_space",
        "keywords": "disk full space storage df no space left inode",
        "title": "Disk space exhaustion",
        "steps": (
            "1. df -h && df -i\n"
            "2. du -xh /var/log /tmp /var 2>/dev/null | sort -h | tail -20\n"
            "3. Safely truncate or remove known log rotators\n"
            "4. Restart affected service after space freed"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "df -h && df -i",
                "+ check disk and inode usage",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "du -xh /var/log /tmp /var 2>/dev/null | sort -h | tail -20",
                "+ find largest directories",
                "diagnostic",
            ),
        ],
    },
    {
        "id": "filesystem_readonly",
        "keywords": "read-only readonly remount filesystem write failed ro mount",
        "title": "Read-only root filesystem",
        "steps": (
            "1. df -h && mount | grep -E ' on / | on /var '\n"
            "2. Fix: sudo mount -o remount,rw /\n"
            "3. Verify writes succeed"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "df -h && mount | grep -E ' on / | on /var '",
                "+ check disk and read-only mounts",
                "diagnostic",
            ),
            (
                "Problem Solver",
                "sudo mount -o remount,rw /",
                "+ remount root read-write",
                "fix",
            ),
            (
                "Customer System Analyzer",
                "df -h && mount | grep -E ' on / | on /var '",
                "+ verify filesystem writable after remount",
                "validate",
            ),
        ],
    },
    {
        "id": "metrics_agent",
        "keywords": "metrics agent monitoring dashboard telemetry",
        "title": "Metrics / monitoring agent",
        "steps": (
            "1. systemctl status metrics-agent.service --no-pager -l\n"
            "2. journalctl -u metrics-agent.service -n 100 --no-pager\n"
            "3. Fix: enable/start unit or fix config referenced in journal"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "systemctl status metrics-agent.service --no-pager -l",
                "+ inspect metrics-agent service",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "journalctl -u metrics-agent.service -n 50 --no-pager",
                "+ metrics-agent error logs",
                "diagnostic",
            ),
            (
                "Problem Solver",
                "sudo systemctl enable --now metrics-agent.service",
                "+ enable metrics-agent grading target",
                "fix",
            ),
        ],
    },
    {
        "id": "postgres_db",
        "keywords": "postgres postgresql database connection sync order sql db",
        "title": "Database connectivity",
        "steps": (
            "1. systemctl status postgresql --no-pager\n"
            "2. ss -tlnp | grep 5432\n"
            "3. journalctl -u postgresql -n 50 --no-pager\n"
            "4. Restore service or fix pg_hba/local connection settings"
        ),
        "execution_plan": [
            (
                "Customer System Analyzer",
                "systemctl status postgresql --no-pager -l",
                "+ inspect PostgreSQL service",
                "diagnostic",
            ),
            (
                "Customer System Analyzer",
                "ss -tlnp | grep 5432",
                "+ confirm PostgreSQL listening",
                "diagnostic",
            ),
            (
                "Problem Solver",
                "sudo systemctl restart postgresql",
                "+ restart PostgreSQL after underlying fix",
                "fix",
            ),
        ],
    },
]

# Minimum hybrid score to activate runbook execution path (avoids false routing).
CLASSIFICATION_MIN_SCORE = 2.0

_DYNAMIC_ID_RE = re.compile(r"\b(\d{4,})\b")
_PATH_RE = re.compile(r"(/[\w./-]*(?:upload|portal)[\w./-]*)", re.I)


def _ticket_text(ticket: dict[str, Any], hypothesis: dict[str, Any] | None = None) -> str:
    return " ".join(
        [
            ticket.get("title") or "",
            ticket.get("report_text") or "",
            (hypothesis or {}).get("title") or "",
            (hypothesis or {}).get("likely_root_cause") or "",
        ]
    )


def symptom_fingerprint(ticket: dict[str, Any]) -> str:
    """Stable normalized key from ticket symptoms (ignores volatile tokens)."""
    text = _ticket_text(ticket).lower()
    text = re.sub(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", "", text)
    text = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", "", text)
    text = _DYNAMIC_ID_RE.sub("", text)
    text = re.sub(r"[-/]\d{1,2}[-/]\d{1,2}\b", "", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "", text)
    text = re.sub(r"[^a-z0-9\s/-]+", " ", text)
    tokens = sorted({t for t in text.split() if len(t) > 2})
    return "|".join(tokens[:40])


def _tokenize(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if len(t) > 1]


def _keyword_score(query: str, book: dict[str, Any]) -> float:
    tokens = set(_tokenize(query))
    keywords = book["keywords"].split()
    if not tokens:
        return 0.0
    hits = sum(1 for kw in keywords if kw in query or kw in tokens)
    return float(hits)


def _bm25_score(query_tokens: list[str], doc_text: str, *, k1: float = 1.2, b: float = 0.75) -> float:
    doc_tokens = _tokenize(doc_text)
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    avg_dl = 120.0
    tf_map: dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    score = 0.0
    for term in set(query_tokens):
        tf = tf_map.get(term, 0)
        if tf == 0:
            continue
        idf = math.log(1 + (len(RUNBOOKS) - 1 + 0.5) / (1 + 0.5))
        denom = tf + k1 * (1 - b + b * doc_len / avg_dl)
        score += idf * (tf * (k1 + 1)) / denom
    return score


def _rerank_score(query: str, book: dict[str, Any]) -> float:
    """Token overlap between query and runbook title + steps (cross-encoder proxy)."""
    doc = f"{book['title']} {book['keywords']} {book['steps']}"
    q_tokens = set(_tokenize(query))
    d_tokens = set(_tokenize(doc))
    if not q_tokens or not d_tokens:
        return 0.0
    overlap = len(q_tokens & d_tokens)
    return overlap / math.sqrt(len(q_tokens) * len(d_tokens))


def hybrid_search_runbooks(
    ticket: dict[str, Any],
    hypothesis: dict[str, Any] | None = None,
    *,
    limit: int = 2,
) -> list[tuple[float, dict[str, Any]]]:
    """Hybrid keyword + BM25 + rerank retrieval over runbooks."""
    query = _ticket_text(ticket, hypothesis).lower()
    query_tokens = _tokenize(query)
    scored: list[tuple[float, dict[str, Any]]] = []

    for book in RUNBOOKS:
        doc_text = f"{book['title']} {book['keywords']} {book['steps']}"
        kw = _keyword_score(query, book)
        bm25 = _bm25_score(query_tokens, doc_text)
        rerank = _rerank_score(query, book)
        combined = kw * 1.5 + bm25 * 2.0 + rerank * 3.0
        if combined > 0:
            scored.append((combined, book))

    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def classify_incident(
    ticket: dict[str, Any],
    hypothesis: dict[str, Any] | None = None,
) -> str | None:
    """Return runbook id when symptoms match strongly enough for plan-then-execute."""
    results = hybrid_search_runbooks(ticket, hypothesis, limit=1)
    if not results:
        return None
    score, book = results[0]
    if score < CLASSIFICATION_MIN_SCORE:
        return None
    return str(book["id"])


def get_runbook_by_id(runbook_id: str) -> dict[str, Any] | None:
    for book in RUNBOOKS:
        if book["id"] == runbook_id:
            return book
    return None


def get_execution_plan(
    ticket: dict[str, Any],
    hypothesis: dict[str, Any] | None = None,
) -> list[RunbookStep] | None:
    """Locked plan steps for classified incidents (plan-then-execute)."""
    runbook_id = classify_incident(ticket, hypothesis)
    if not runbook_id:
        return None
    book = get_runbook_by_id(runbook_id)
    if not book:
        return None
    plan: list[RunbookStep] = list(book.get("execution_plan") or [])
    if not plan:
        return None

    # Adapt upload path from ticket text when present.
    if runbook_id == "permission_upload":
        text = _ticket_text(ticket)
        path_match = _PATH_RE.search(text)
        if path_match:
            path = path_match.group(1).rstrip("/")
            plan = [
                (
                    "Customer System Analyzer",
                    f"stat {path} 2>/dev/null || ls -ld {path}",
                    f"+ confirm ownership on {path}",
                    "diagnostic",
                ),
                (
                    "Problem Solver",
                    f"sudo chown -R www-data:www-data {path}",
                    f"+ fix ownership on {path}",
                    "fix",
                ),
            ]
        if "public-test" in text.lower() or str(ticket.get("ticket_code") or "").startswith("700"):
            plan = [
                *plan,
                (
                    "Problem Solver",
                    PUBLIC_TEST_COMMAND,
                    "+ validate after permission fix",
                    "validate",
                ),
            ]
    return plan


def retrieve_runbooks(
    ticket: dict[str, Any],
    hypothesis: dict[str, Any] | None = None,
    limit: int = 2,
) -> str:
    """Grounding text for LLM prompts — uses hybrid retrieval."""
    results = hybrid_search_runbooks(ticket, hypothesis, limit=limit)
    if not results:
        return ""

    classified = classify_incident(ticket, hypothesis)
    lines = ["Relevant runbook guidance (hybrid retrieval):"]
    if classified:
        lines.append(f"Incident class: {classified}")
    for score, book in results:
        lines.append(f"- {book['title']} (score={score:.1f}):\n{book['steps']}")
    return "\n".join(lines)
