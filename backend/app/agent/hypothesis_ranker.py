"""Re-rank and eliminate hypothesis paths based on structured evidence."""
from __future__ import annotations

from typing import Any


def rerank_hypotheses(
    hypotheses: list[dict[str, Any]],
    evidence: dict[str, Any],
    selected_index: int,
) -> list[dict[str, Any]]:
    if not hypotheses:
        return hypotheses

    failed = evidence.get("failed_units") or []
    disabled = evidence.get("disabled_units") or []
    full_fs = evidence.get("full_filesystems") or []
    errors = evidence.get("error_lines") or []

    updated: list[dict[str, Any]] = []
    for i, h in enumerate(hypotheses):
        item = dict(h)
        title = (item.get("title") or "").lower()
        root = (item.get("likely_root_cause") or "").lower()
        eliminated = bool(item.get("eliminated"))

        service_path = any(k in title + root for k in ("service", "systemd", "boot", "enabled", "unit"))
        disk_path = any(k in title + root for k in ("disk", "space", "full", "storage", "resource"))
        perm_path = any(k in title + root for k in ("permission", "chown", "chmod", "owner"))

        if service_path and failed:
            item["confidence"] = "high"
            item["eliminated"] = False
        elif service_path and disabled and not failed:
            item["confidence"] = "high"
            item["eliminated"] = False
        elif disk_path and full_fs:
            item["confidence"] = "high"
            item["eliminated"] = False
        elif perm_path and errors and any("denied" in e.lower() for e in errors):
            item["confidence"] = "high"
            item["eliminated"] = False
        elif i != selected_index and failed and service_path and not any(
            u in (title + root) for u in failed
        ):
            if len(failed) >= 1 and not disk_path and not perm_path:
                item["confidence"] = "low"
                item["eliminated"] = True
                item["elimination_reason"] = f"Evidence shows failed units {failed[:3]} — path mismatch"

        if disk_path and not full_fs and len(failed) >= 1 and not service_path:
            item["confidence"] = "low"
            item["eliminated"] = True
            item["elimination_reason"] = "Disk full not observed; failed units point elsewhere"

        updated.append(item)
    return updated
