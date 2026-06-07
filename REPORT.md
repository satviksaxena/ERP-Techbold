# AI Service Desk Autopilot — Technical Report

**Track:** techbold · START Hack Vienna '26  
**Project:** Human-in-the-loop AI technician workspace for Phoenix ERP + Linux VMs

---

## 1. Problem

Managed service desk technicians spend significant time on repetitive Linux incident work. Knowledge from fixes is often lost because activity logs in the ERP are generic. This project automates **diagnosis, controlled remediation, validation, and documentation** while keeping a human in the loop for every shell action.

## 2. Solution overview

A three-tier system:

1. **React workbench** — ticket matrix, live terminal, hypothesis pathways, command gate, audit trail, activity draft  
2. **FastAPI backend** — Phoenix ERP sync, SSH execution, Gemini multi-agent orchestration, safety layer, audit log  
3. **Supabase** — realtime UI state (tickets, commands, system info, activities, audit_events, hypotheses)

Every proposed command passes through a **slide-to-authorize gate**. The safety layer blocks hard-fail patterns from the rubric before SSH runs.

## 2b. Experiential auto-learning (in progress)

We are extending the platform so **past incidents teach future ones**:

1. Each case generates a **persistent audit trail** (`audit_events`), command transcripts, hypothesis analysis, and a structured ERP activity.
2. A **Learning Agent** (roadmap) will consume closed incidents and update fast paths, runbooks, and agent prompts.
3. The **orchestrator** already prioritizes **fast paths** (`fast_paths.py`) — minimal command chains for tickets 7001–7005 — before exploratory LLM diagnostics.

Outcome: similar symptoms → **shorter resolution** with **correct commands**, while humans retain approval control.

Details: [`docs/EXPERIENTIAL_LEARNING.md`](./docs/EXPERIENTIAL_LEARNING.md)

## 3. Architecture

```
Phoenix ERP  ←→  FastAPI (:8000)  ←→  Supabase (realtime)
                      ↓ SSH (paramiko)
                 Customer VMs 7001–7005
                      ↓ Gemini (primary) / Azure OpenAI (fallback)
                 Multi-agent pipeline
```

### Agent pipeline

| Agent | Role |
|-------|------|
| Problem Analyzer | Initial host / systemd diagnostics |
| Customer System Analyzer | Disk, memory, ports, logs |
| Problem Solver | Fix commands + `public-test.sh` validation |
| Activity Log Generator | ERP activity draft from executed commands |

### Hypothesis-first UX

Gemini generates **three ranked pathways** (title, root cause, fix strategy, first command). The technician picks one; the command gate syncs to that path. This matches the case brief’s “diagnosis first” pattern.

## 4. Human-in-the-loop flow

1. **Sync ERP** — pull tickets + customer-system SSH metadata  
2. **Open workbench** — read customer report, system info, agent stepper  
3. **Connect SSH** — handshake test with multi-key resolver  
4. **Start Analysis** — generate hypotheses + first proposed command  
5. **Pick pathway** — command gate updates to selected approach  
6. **Slide to authorize** — edit, reject, or retry on failure  
7. **Validate** — `sudo /opt/hackathon/public-test.sh` must exit 0  
8. **Commit activity** — all five ERP fields submitted; ticket → DONE  

## 5. Safety & audit

- **SafetyLayer** blocks: recursive chmod 777, DROP DATABASE, firewall disable, log wiping, secret patterns  
- **AuditLog** records: sync, SSH, command executed/failed/rejected/retry, hypothesis selection, activity submit  
- **Persistence:** `audit_events` in Supabase + `audit.jsonl` on disk (survives backend restart)  
- **Audit Trail panel** in workbench (`GET /api/audit`) — jury-visible, feeds experiential learning pipeline  
- Secrets: `.env` and `*.pem` gitignored; service role key backend-only  

## 6. ERP integration

| Endpoint | Usage |
|----------|--------|
| `GET /api/v1/me/tickets` | Sync assigned cases |
| `GET /api/v1/tickets/{id}/customer-system` | SSH target + notes (key hints) |
| `POST /api/v1/activities/create` | Submit completed activity |
| `POST /api/v1/me/reset` | Reset VMs + clear team activities |

Activity fields populated: `summary`, `root_cause`, `actions_taken`, `commands_summary`, `validation_result`.

## 7. Validation strategy

- Per-ticket fixes guided by LLM + selected hypothesis  
- Mandatory **`public-test.sh`** after fix commands (orchestrator enforces sequencing)  
- Grader persistence/reboot checks run on hidden VMs — we avoid fragile workarounds and destructive commands  

## 8. Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TanStack Router/Query, Tailwind, Supabase realtime |
| Backend | FastAPI, Paramiko, Google Gemini, Supabase Python client |
| Data | Supabase Postgres (Hack AI project) |
| Infra | Docker Compose for reproducible demo |

## 9. Testing

```bash
# Unit tests (safety + orchestrator helpers)
cd backend && .venv312/bin/pytest tests/ -v

# Post-migration validation
python scripts/validate_hack_ai.py

# VM connectivity
python scripts/test_all_vms.py

# Docker smoke (another machine)
cp .env.example .env   # fill credentials
./scripts/docker-smoke.sh
```

## 10. Assumptions & limits

- VMs 7002/7003/7005 may be intermittently unreachable (organiser network)  
- LLM proposals can be wrong — human gate is the correctness backstop  
- Audit is **persisted** in Supabase; Learning Agent auto-update loop is roadmap (fast paths shipped)  
- UI targets desktop technicians; mobile is out of scope  

## 11. Demo script (3–4 min)

1. `docker compose up --build` → http://localhost:5173  
2. Sync ERP → open ticket **7001**  
3. Connect SSH → Start Analysis → show **3 hypothesis cards**  
4. Pick path → show **command gate sync**  
5. Authorize diagnostic → terminal output → **audit trail updates**  
6. Authorize fix → authorize **public-test.sh** → `[exit 0]`  
7. Review activity draft → **Validate & Commit to Phoenix ERP**  
8. Show audit trail + ticket status Fixed  

## 12. Team

| Member | Role |
|--------|------|
| _[Your name]_ | Full-stack / AI orchestration |
| _[Teammate]_ | Frontend / UX |
| _[Teammate]_ | Backend / infra |

_Update before Tally submission._

---

See also: [SUBMISSION.md](./SUBMISSION.md) for the official checklist and Tally form fields.
