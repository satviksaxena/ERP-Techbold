# Experiential auto-learning — design & roadmap

**Status:** In active development (hackathon + post-hackathon roadmap)

## Idea

Every resolved incident is more than an ERP activity — it is **training signal** for the next incident. When ticket 7002 fails again with “permission denied on uploads”, the system should remember that a targeted `chown` on `/srv/customer-portal/uploads` plus `public-test.sh` worked last time — not re-discover the fix through 20 exploratory commands.

## What we capture today (foundation)

| Source | Table / file | Contents |
|--------|----------------|----------|
| Audit trail | `audit_events` (Supabase), `audit.jsonl` | Sync, SSH, command executed/failed/rejected, pathway switches, validation, activity submit |
| Commands | `ai_commands` | Proposed/approved commands + full SSH output |
| Analysis | `ticket_hypotheses` | Ranked pathways, selected path, verifier pipeline state |
| Resolution | `activities` | `summary`, `root_cause`, `actions_taken`, `commands_summary`, `validation_result` |

The workbench **Audit Trail** panel reads this via `GET /api/audit?ticket_id=…` (Supabase-first, durable across backend restarts).

## Learning Agent (roadmap)

After a ticket reaches **Fixed** and activity is committed to Phoenix ERP:

1. **Compile incident bundle** — audit events + commands + hypothesis + activity for that `ticket_id`
2. **Extract patterns** — symptom keywords → root cause → minimal command chain → validation proof
3. **Update system knowledge** — without bypassing human approval or safety rules:
   - Extend **`fast_paths.py`** with new ticket-class shortcuts
   - Enrich **`runbooks.py`** and agent prompts with proven sequences
   - Tune **hypothesis ranker** weights for recurring failure modes
4. **Replay on similar tickets** — orchestrator prefers fast path / runbook before generic LLM + universal baseline diagnostics

```
  Resolved case                    New similar case
  ─────────────                    ────────────────
  audit_events  ──┐
  ai_commands   ──┼──► Learning Agent ──► fast_paths / runbooks / prompts
  hypotheses    ──┤                              │
  activities    ──┘                              ▼
                                    Orchestrator → fewer, correct commands
```

## Principles (aligned with judging rubric)

- **Human-in-the-loop always** — learning improves *proposals*; technicians still slide-to-authorize fixes
- **Safety layer unchanged** — learned commands must pass the same blocks (no chmod 777, no DROP DATABASE, etc.)
- **No secrets in learning store** — SSH keys and tokens never enter audit or activity fields; outputs are redacted
- **Minimal changes** — learning reinforces *targeted* fixes (e.g. one `chown` path), not broad filesystem sweeps

## Current implementation

- ✅ Persistent audit (`audit_events` migration)
- ✅ Per-ticket fast paths for cases **7001–7005** (`backend/app/agent/fast_paths.py`)
- ✅ Fast path priority in orchestrator resolver (before LLM / universal baseline)
- 🚧 Automated Learning Agent loop (post-incident compile + prompt/runbook update)
- 🚧 Cross-ticket similarity matching (symptom → past case retrieval)

## For judges / demo

Point to the **Audit Trail** sidebar during the loop: every step is recorded for transparency (category **C**) and feeds the learning pipeline described above.
