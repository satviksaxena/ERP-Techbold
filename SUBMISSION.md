# Submission checklist — techbold track

**Code freeze:** Sunday, June 7, 2026 — **14:00 sharp** (CET)  
**Form:** START Hack Tally link (shared on Discord)

---

## Before you submit

### GitHub repository

- [ ] Public repo in **START Hack Vienna '26** org → `techbold/` → your team folder  
- [ ] **MIT LICENSE** at repo root  
- [ ] **README.md** with setup, run, architecture, troubleshooting  
- [ ] **`.env.example`** — no real secrets committed  
- [ ] **`docker compose up --build`** works on a clean machine (use `./scripts/docker-smoke.sh`)

### Demo video (~3 minutes)

Record the **full loop live** (not slides):

- [ ] Load ticket from ERP (Sync)  
- [ ] Analyse + hypothesis paths  
- [ ] Human confirmations (slide gate)  
- [ ] SSH command output in terminal  
- [ ] **Audit trail panel** visible  
- [ ] Fix + `public-test.sh` validation  
- [ ] Submit activity to Phoenix ERP  

Upload to YouTube/Loom and paste URL in Tally.

### Tally form fields (copy/paste drafts)

**Project title:**  
`AI Service Desk Autopilot`

**One-line pitch:**  
`Gemini-powered technician workbench that fixes Linux incidents over SSH under human approval and writes precise activities back to Phoenix ERP.`

**Team & members:**  
_List all 2–4 members with roles._

**Problem:**  
Technicians manually SSH into customer VMs, troubleshoot ad hoc, and leave vague ERP activity logs — losing reusable knowledge.

**Solution overview:**  
Multi-agent AI copilot with ranked hypothesis paths, slide-to-authorize command gate, safety layer, live audit trail, and auto-generated Phoenix activities. Human approves every shell action.

**Tech stack:**  
React, TanStack, Supabase, FastAPI, Paramiko, Google Gemini, Docker Compose, Phoenix ERP mock.

**Links:**

| Field | URL |
|-------|-----|
| GitHub repo | `https://github.com/START-Vienna/techbold/…` |
| Demo video | _your upload_ |
| Live demo (optional) | `http://your-host:5173` |

### Optional attachments

- [ ] **REPORT.md** (technical write-up — included in repo)  
- [ ] Pitch deck PDF (optional)

---

## Judging categories — quick self-check

| Category | What judges look for | Your demo moment |
|----------|---------------------|------------------|
| A (20) | ERP load, list, activity submit | Sync + commit activity |
| B (35) | Hidden VM fixes, public-test | Full loop on fresh VM |
| C (20) | Safety, audit, no secrets | Audit panel + reject blocked cmd |
| D (10) | UX, human control | Hypotheses + slide gate + retry |
| E (15) | README, tests, docker | `pytest` + `docker-smoke.sh` |

---

## Day-of demo tips

1. Run **Reset Workspace** before each jury run for a clean VM  
2. Use ticket **7001** if others are unreachable  
3. Keep **Audit Trail** expanded in the right sidebar  
4. Ensure **`public-test.sh` shows exit 0** before committing  
5. Do not commit `.env`, PEM keys, or API keys  

Good luck.
