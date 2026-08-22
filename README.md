# CAOS — Practice Automation Platform

Internal task-engine + automation-agent platform for Venture Assist /
Srivatsan & Associates. See the full documentation package for context:
PRD, ADRs, Sprint Plan, API Spec, Coding Guidelines, Security Standard,
Testing Strategy, Logging Standard, Performance & Scaling, and the Dev
Readiness Checklist.

## Claude Code setup

This repo includes Claude Code project conventions, configured for
**Windows + PowerShell** development:

- **`CLAUDE.md`** — read automatically every session; the non-negotiable
  conventions (CG1–CG11 summarized), the Books Connector architecture rule
  (never import `TallyAdapter`/`ZohoAdapter` directly outside the resolver),
  and commands (PowerShell).
- **`.claude/settings.json` + `.claude/hooks/`** — two enforcement hooks,
  both run via PowerShell (`"shell": "powershell"` in `settings.json`) and
  invoked with `python` (not `python3` — use the standard python.org
  installer, which puts `python.exe` on `PATH`, not `python3.exe`):
  - `post_edit_python.py` runs `ruff` on every edited Python file under
    `services/api` (blocking on failure, per CG1), blocks any `TODO`/`FIXME`/
    `HACK`/`XXX`/`NotImplementedError` that doesn't carry a tracked
    `STUB(#123)` or `STUB(PENDING:NNN)` marker (see `docs/STUB_ISSUES.md`),
    and additionally runs the model tests + reminds about Alembic migrations
    when a file under `app/models/` changes. Resolves the venv's `ruff.exe`/
    `pytest.exe` under `.venv\Scripts\` (Windows layout), falling back to
    `PATH` if no venv exists yet.
  - `guard_dangerous_bash.py` blocks a short list of repo-specific footguns,
    matched against **either** the Bash or PowerShell tool (whichever Claude
    actually used): force-push (`git push --force`/`-f`/`--force-with-lease`),
    deleting `.git` (`rm -rf`, PowerShell's `Remove-Item -Recurse -Force`, or
    `rd /s`), and `alembic downgrade base`.
- **`.claude/agents/`** — two subagents: `books-connector-adapter` (scoped
  to `app/books_connector/`, knows ADR 0011's interface-boundary rule and
  CG7's duplicate-check contract) and `migration-reviewer` (reviews a new
  Alembic migration against the ER diagram and CG5 before it's applied).

If you want to use Claude Code's native PowerShell tool (rather than the
default Bash tool running under Git Bash), set
`CLAUDE_CODE_USE_POWERSHELL_TOOL=1` — the hooks above already match either
tool name, so this works whichever way you have it configured.

## What's in this repo right now

This is the **repo scaffold and basic setup** ahead of Sprint 1-2 — not
Sprint 1-2 itself. It covers what can be built and verified without a
live AWS account, Tally Cloud connection, or Zoho/GSP sandbox credentials:

- ✅ Repo structure (`services/api`, `services/web`) per Coding Guidelines
- ✅ `ruff` configured, zero warnings (CG1)
- ✅ Core SQLAlchemy models for all 9 core-platform entities, matching
  `audit-platform-ER-core.mermaid` v0.2 exactly
- ✅ Alembic configured async; initial migration generated **and verified
  to run** against SQLite (`d5a6e6feba43_initial_core_schema.py`)
- ✅ `BooksConnector` interface + `TallyAdapter`/`ZohoAdapter` stubs +
  resolver, per ADR 0011 — the adapters raise `NotImplementedError` with
  clear TODOs; the interface boundary, resolver dispatch, and
  duplicate-prevention call site (CG7) are real and tested
- ✅ Task Engine service (create / reassign / complete / escalate), per
  ADR 0005 — TE-01, TE-03, TE-04, TE-06
- ✅ Auth (JWT login), Tasks, Health API routes wired into FastAPI, with
  the standard error shape from the API Spec
- ✅ 14 tests passing, 85%+ coverage (CG10's gate)
- ✅ Frontend scaffold: React + Vite + TypeScript + Tailwind (Design B
  palette), typechecks and builds clean, proves it can reach the backend
- ✅ GitHub Actions CI: lint + test (backend), typecheck + build (frontend)

## What's genuinely NOT done — blocked on real infrastructure/accounts

These need things this environment doesn't have (a live AWS account,
real Tally Cloud access, Zoho/GSP developer accounts) — see the **Dev
Readiness Checklist** for the exact items:

- AWS infrastructure (ENV-01, ENV-02, ENV-03) — no cloud account provisioned
- Real `TallyAdapter` HTTP/XML calls (blocked on P0-02, ENV-05)
- Real `ZohoAdapter` OAuth2/API calls (blocked on P0-06, ENV-07)
- GSP integration (blocked on P0-04, ENV-06)
- Dropbox webhook wiring (blocked on ENV-08)
- Secrets Manager wiring (currently reads from `.env` — fine for local
  dev, not for production per Security Standard §3)
- Every agent beyond the Task Engine skeleton (Bookkeeping, Reconciliation,
  Validation, TDS, Bank Reconciliation, Working Paper, Client Communication,
  Client Profiling & Billing, Practice Management) — these are Sprint 3
  onward per the Sprint Plan
- Real screens beyond a health-check placeholder — the actual 9 screens +
  4 admin sub-screens exist as wireframes (`audit-platform-wireframes-v0.2.html`)
  but aren't built as React components yet

## Running locally

**All commands below are PowerShell.** Run `pwsh` (PowerShell 7+, recommended)
or Windows PowerShell 5.1 — either works, but `.claude/hooks` assume `python`
is on `PATH` (the standard python.org installer name; not `python3`).

### Backend

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env     # defaults to SQLite, no real credentials needed
alembic upgrade head            # creates caos_dev.db with all 9 tables
uvicorn app.main:app --reload   # http://localhost:8000
```

> If `Activate.ps1` is blocked by execution policy, run once per session:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

```powershell
ruff check . --no-fix                                                    # CG1
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=85    # CG10
```

### Frontend

```powershell
cd services/web
npm install
npm run dev      # http://localhost:5173, proxies /api to :8000
```

## Repo structure

```
services/
  api/
    app/
      models/            # SQLAlchemy models — ER Diagram v0.2 core entities
      books_connector/    # BooksConnector interface + Tally/Zoho adapters (ADR 0011)
      task_engine/         # Task Engine service (ADR 0005)
      agents/               # Empty — Bookkeeping, Reconciliation, etc. land Sprint 3+
      routers/                # FastAPI route handlers
      config.py                 # Centralized settings (CG4)
      db.py                       # Async SQLAlchemy engine/session
      main.py                       # FastAPI app entrypoint
    practices/            # Extension-point directory (CG11, ADR 0010) — empty by design
    alembic/               # Migrations
    tests/                    # pytest suite
  web/
    src/                      # React + Vite + TypeScript frontend
.github/workflows/ci.yml    # Lint + test + build, on every push/PR
```

## Next steps

Work through the **Dev Readiness Checklist** (`CAOS-dev-readiness-checklist-v0.1.xlsx`)
— specifically the Phase 0 Spikes and Environment & Tooling sections —
before starting Sprint 1-2 for real. Several items in this scaffold
(the two adapters, Secrets Manager wiring, Dropbox webhook) are
deliberately stubbed pending those spikes' results.
