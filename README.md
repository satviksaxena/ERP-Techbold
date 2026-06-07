# AI Service Desk Autopilot — techbold track

AI-assisted technician workspace for **START Hack Vienna '26** ([techbold track](https://github.com/START-Vienna/techbold_track_template)). Loads tickets from the **Phoenix ERP** mock, connects to customer Linux VMs over **SSH** under human approval, troubleshoots with AI agents, and writes activities back to the ERP.

## Architecture

```
Phoenix ERP (Bearer token)  ←→  FastAPI Backend  ←→  Supabase (realtime UI state)
                                      ↓
                              SSH (paramiko) → Customer VMs
                                      ↓
                              OpenAI (optional BYO LLM)
```

| Layer | Role |
|-------|------|
| **Frontend** | Lovable React workbench — ticket matrix, command gate, activity draft |
| **Backend** | ERP client, SSH runner, safety layer, agent orchestrator, audit log |
| **Supabase** | Realtime state for tickets, commands, system info, activities, **audit_events** |

### Experiential learning (in progress)

We are building an **experiential auto-learning layer** on top of the audit trail. Each resolved case produces structured experience:

- **Audit events** — every command, approval, failure, pathway switch, and validation (`audit_events` in Supabase + `audit.jsonl`)
- **Command history** — full SSH transcripts per ticket (`ai_commands`)
- **Analysis artifacts** — ranked hypotheses, verifier outcomes, root-cause notes (`ticket_hypotheses`)
- **ERP activities** — final summary, technical root cause, ordered actions, validation proof (`activities`)

A dedicated **Learning Agent** (roadmap) will ingest closed incidents and update:

- **Fast paths** — minimal command sequences per ticket class (see `agent/fast_paths.py`)
- **Runbooks & prompts** — refined diagnostics/fix patterns for Problem Analyzer, Customer System Analyzer, and Problem Solver
- **Orchestrator policy** — prefer proven command chains over exploratory LLM loops on similar symptoms

Goal: when a new issue resembles a past case, the system proposes the **correct fix in fewer commands** and less time — while humans still approve every mutating action.

See [`docs/EXPERIENTIAL_LEARNING.md`](docs/EXPERIENTIAL_LEARNING.md) for the full design.

### Human-in-the-loop flow

1. **Sync ERP** — pull assigned tickets + customer system info into Supabase  
2. **Open ticket** → **Connect SSH** → **Start AI Analysis**  
3. Agent proposes a command → technician **slides to authorize** (or edit/reject)  
4. Backend runs command through **safety layer** over SSH  
5. Activity draft auto-updates → **Validate & Commit to Phoenix ERP**

## Prerequisites

- Docker Desktop (recommended) **or** Python 3.11+, Bun/Node 20+
- Phoenix ERP URL + team token (from Builder Base / Discord)
- SSH `.pem` key for customer VMs
- Supabase project (from Lovable UI) with migration applied
- Optional: OpenAI API key for smarter diagnostics

## Setup

```bash
git clone <your-repo>
cd Hackathon

cp .env.example .env
# Fill in PHOENIX_*, SUPABASE_*, VITE_* vars

cp /path/from/builder-base/your-key.pem keys/your-key.pem
# Set SSH_PRIVATE_KEY_PATH=/keys/your-key.pem in .env
```

Apply Supabase schema (if not already):

```bash
# In Supabase SQL Editor, run in order:
#   supabase/hack_ai_bootstrap.sql          (full schema)
#   supabase/migrations/20260607120000_audit_events.sql   (if bootstrap already applied)
```

## Run with Docker (recommended for judges / another machine)

```bash
cp .env.example .env
# Fill PHOENIX_*, SUPABASE_*, GEMINI_*, VITE_* (see .env.example)

# Place SSH keys in tb-hackathon-ssh/ (case1_key.pem … case5_key.pem)
docker compose up --build
```

Or use the smoke script:

```bash
chmod +x scripts/docker-smoke.sh
./scripts/docker-smoke.sh
```

- Frontend: http://localhost:5173  
- Backend: http://localhost:8000/health  
- API docs: http://localhost:8000/docs  

The stack mounts `tb-hackathon-ssh/` as `/keys` inside the backend container. Set `SSH_PRIVATE_KEY_PATH=/keys/case1_key.pem` in `.env` (default in compose).

## Run locally (without Docker)

```bash
# Backend (use stable script for demos — --reload restarts mid-SSH and sticks the UI)
./scripts/dev-backend.sh
# Or with auto-reload while editing code only:
# cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
bun install && bun run dev
```

## Environment variables

See [`.env.example`](.env.example). **Never commit** `.env` or SSH keys.

| Variable | Where | Purpose |
|----------|-------|---------|
| `PHOENIX_API_BASE_URL` | Backend | Phoenix mock base URL |
| `PHOENIX_API_TOKEN` | Backend | Team bearer token |
| `SSH_PRIVATE_KEY_PATH` | Backend | Path to `.pem` |
| `SUPABASE_URL` | Backend | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend only | Sync + command updates |
| `VITE_SUPABASE_*` | Frontend | Browser Supabase client |
| `VITE_API_BASE` | Frontend | Backend URL |
| `GEMINI_API_KEY` | Backend | **Primary LLM** — multi-agent command proposals |
| `GEMINI_MODEL` | Backend | Default: `gemini-3.5-flash` (latest GA agentic model) |
| `LLM_PRIMARY` | Backend | Always `gemini` (Docker enforces this; Azure is not used as fallback) |

## Backend modules

```
backend/app/
  phoenix/client.py       # ERP API (tickets, customer-system, activities, reset)
  ssh/runner.py           # Paramiko SSH with timeouts
  safety/layer.py         # Blocks hard-fail commands (scoring.md)
  agent/gemini_agent.py   # Gemini multi-agent pipeline
  agent/orchestrator.py   # Human-in-the-loop orchestration
  agent/fast_paths.py     # Minimal proven command chains (7001–7005)
  activity/generator.py   # Draft Phoenix activity from commands + audit
  audit/log.py            # Persistent audit trail (Supabase + file)
  store/supabase_store.py # Supabase read/write
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/sync/tickets` | Pull tickets from Phoenix → Supabase |
| POST | `/api/tickets/{id}/analyze` | Start agent analysis, propose first command |
| POST | `/api/tickets/{id}/connect-ssh` | Test SSH connection |
| POST | `/api/commands/{id}/approve` | Execute approved command over SSH |
| POST | `/api/commands/{id}/reject` | Reject proposed command |
| POST | `/api/commands/{id}/retry` | Re-queue a failed executed command |
| POST | `/api/tickets/{id}/submit-activity` | Submit activity to Phoenix ERP |
| POST | `/api/workspace/reset` | Phoenix reset + clear local state |
| GET | `/api/audit?ticket_id=` | Audit trail (for demo / jury) |

## Tests

```bash
cd backend && .venv/bin/pytest tests/ -v
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| 401 from Phoenix | Check `PHOENIX_API_TOKEN` and Bearer header |
| Empty ticket list | Click **Sync ERP** in header |
| SSH connect fails | Key at `SSH_PRIVATE_KEY_PATH`, user `azureuser`, VM reachable |
| Backend can't reach Phoenix in Docker | Use `host.docker.internal` in `PHOENIX_API_BASE_URL` |
| Supabase errors | Verify migration applied + service role key on backend; run `20260607120000_audit_events.sql` for persisted audit |

## Submission

- Track: **techbold · AI Service Desk Autopilot**
- MIT License — see [LICENSE](LICENSE)
- Full rubric: [`docs/scoring.md`](docs/scoring.md)
- Experiential learning design: [`docs/EXPERIENTIAL_LEARNING.md`](docs/EXPERIENTIAL_LEARNING.md)
- Technical report: [`REPORT.md`](REPORT.md)
- Tally checklist: [`SUBMISSION.md`](SUBMISSION.md)
- ERP contract: [`docs/phoenix-openapi.yaml`](docs/phoenix-openapi.yaml)

## Team

| Member | Role |
|--------|------|
| _[Name]_ | _[e.g. Backend / AI orchestration]_ |
| _[Name]_ | _[e.g. Frontend / UX]_ |

_Update this table before the Tally submission (Sun Jun 7, 14:00)._
