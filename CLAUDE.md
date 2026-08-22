# CAOS — Practice Automation Platform

**Development platform: Windows, PowerShell.** All commands in this file
and in `README.md` are PowerShell, not bash — this repo's `.claude/hooks/`
are also configured to run via PowerShell (`"shell": "powershell"` in
`.claude/settings.json`), matching either the Bash or PowerShell tool
depending on which one actually executed a given command. If this ever
becomes a cross-platform team, revisit `.claude/settings.json` and the
hook scripts' venv-path resolution (`venv_exe()` in `post_edit_python.py`
already handles both Windows and Unix venv layouts, but the shell
commands themselves currently assume PowerShell).

Internal task-engine + automation-agent platform for Venture Assist /
Srivatsan & Associates. Read `README.md` first for what's built vs. stubbed.
Full docs are in `docs/` — read the relevant one before assuming a rule from
memory, especially `docs/CAOS-coding-guidelines-v0.2.md` (CG1–CG11) and
`docs/audit-platform-ADR-0011-addendum.md` (the Books Connector architecture).

## What this platform does

Task-engine-driven system automating document intake, bookkeeping, GST/TDS
reconciliation, compliance validation, client communication, and billing for
a CA practice scaling from ~100 to ~500 GST returns/month without adding
headcount. Every judgment call an agent can't make becomes a Task, assigned
to a specific person, escalating if it's not resolved in time.

## Non-negotiable conventions (CG1–CG11, full detail in docs/)

- **Ruff, zero warnings before commit.** `ruff check . --no-fix` must exit 0.
- **Type hints on every function signature.** `from __future__ import annotations` at the top of every file.
- **50-line function limit.** Extract helpers, especially in agent logic (extraction, matching, posting are three functions, not one).
- **Settings only through `app/config.py`.** Never call `os.environ` directly anywhere else.
- **Money is `Decimal`, never `float`.** Sourced from strings, never float arithmetic.
- **External API calls need explicit timeout + bounded retry + failure-into-a-Task.** Never let an external call crash a request or a worker silently.
- **CG7 — duplicate-prevention check before ANY books-system write**, Tally or Zoho, no exceptions. Runs once against the platform's own `Voucher` table before either adapter is called.
- **Human-judgment paths go through the Task Engine (`app/task_engine`), never ad hoc.** No agent sends its own notification or writes its own "pending review" flag.
- **Pydantic models for every request/response shape.** No route handler accepts or returns a raw dict.
- **pytest, ≥85% coverage, all external services mocked.** Tally, Zoho, GSP, and OCR are mocked at the client boundary in every unit test.
- **`app/practices/{slug}/` is the only place practice-specific customization goes** — core modules (`app/agents/`, `app/task_engine/`, `app/books_connector/`) never branch on which practice is running. Check whether something is actually *configuration* (a client's `books_system`, service catalog pricing) before reaching for a practice-specific file.
- **Every stub, hardcoded placeholder, or intentionally incomplete implementation must be tracked.** No `TODO`, `FIXME`, `HACK`, `XXX`, or `raise NotImplementedError` may exist without a `STUB(...)` marker on the same line — see "Stub tracking" below. A hook enforces this; it will block the edit if it's missing.

## Stub tracking

Any code that stands in for something not yet built — a `NotImplementedError`,
a hardcoded value doing the job of real logic, a genuinely incomplete
function — must carry a comment in this exact form:

```python
# STUB(#123): short description          # once a real GitHub issue exists
# STUB(PENDING:007): short description    # before this repo has a GitHub remote / gh auth
```

**Workflow:**
1. If this repo has a GitHub remote and `gh` is authenticated, run
   `gh issue create --title "..." --body "..." --label stub` and use the
   real issue number: `STUB(#123)`.
2. If not, use the next unused `PENDING:NNN` number and add a row to
   `docs/STUB_ISSUES.md` describing it (location, title, what it's
   blocked on). Don't reuse a `PENDING:NNN` number already in that file.
3. When a real issue eventually gets filed for a `PENDING` entry,
   find-and-replace `STUB(PENDING:NNN)` → `STUB(#<real number>)` at every
   occurrence and update that row's Status in `docs/STUB_ISSUES.md` to Filed.

`.claude/hooks/post_edit_python.py` blocks (exit 2) any edited file under
`services/api` containing a `TODO`/`FIXME`/`HACK`/`XXX`/`NotImplementedError`
with no `STUB(...)` marker on the same line. This is a mechanical
same-line check, not a guarantee the marker is *meaningful* — still write
a real description, not just `STUB(PENDING:1): x`.

See `docs/STUB_ISSUES.md` for the current list — as of this writing, all
of the `BooksConnector` adapters' unimplemented methods and the Task
Engine's not-yet-role-aware escalation.

## Architecture — read before touching books_connector/ or agents/

Per ADR 0011: the platform supports two bookkeeping backends (Tally and
Zoho Books) behind one `BooksConnector` interface (`app/books_connector/base.py`).
**No agent should ever import `TallyAdapter` or `ZohoAdapter` directly** —
resolve the right adapter via `get_adapter_for_connection()` and depend on
the `BooksConnector` interface from there. This is the single most
important architectural rule in this codebase; violating it is exactly the
kind of thing CG11's "core must never branch on a specific backend" rule
exists to prevent, generalized from practices to books-systems.

The two adapters (`tally_adapter.py`, `zoho_adapter.py`) currently raise
`NotImplementedError` — see the `TODO(Sprint 1-2)` comments for what's
blocked on which Dev Readiness Checklist item (`P0-02`/`ENV-05` for Tally,
`P0-06`/`ENV-07` for Zoho). Don't implement the real HTTP/OAuth calls
without those sandbox credentials actually configured — stub work that
*looks* wired but silently no-ops is worse than an honest `NotImplementedError`.

## Repo structure

```
services/api/app/
  models/            SQLAlchemy models — matches docs' ER diagram exactly
  books_connector/   BooksConnector interface + Tally/Zoho adapters + resolver (ADR 0011)
  task_engine/       Task Engine service (ADR 0005)
  agents/            Empty — Bookkeeping, Reconciliation, etc. land Sprint 3+
  routers/           FastAPI route handlers
  config.py          Settings (CG4) — the only file that reads env vars
  db.py              Async SQLAlchemy engine/session
  main.py            FastAPI entrypoint
services/api/practices/   Extension-point dir (CG11) — empty by design
services/api/alembic/     Migrations
services/api/tests/       pytest suite
services/web/src/         React + Vite + TypeScript frontend
docs/                      PRD, Sprint Plan, API Spec, Coding Guidelines, etc.
```

## Commands (PowerShell)

```powershell
# Backend — run from services/api, with .venv activated
ruff check . --no-fix                                                    # CG1
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=85    # CG10
alembic revision --autogenerate -m "description"                         # after any model change
alembic upgrade head
uvicorn app.main:app --reload

# Frontend — run from services/web
npm run dev
npx tsc -b; npx vite build
```

## When adding a new model

1. Add the model in `app/models/`, import it in `app/models/__init__.py`.
2. Trace it back to an ER diagram entity in `docs/audit-platform-ER-*.mermaid` — if it's genuinely new, note that explicitly, don't assume.
3. Run `alembic revision --autogenerate -m "..."` and **read the generated migration** before running `alembic upgrade head` — autogenerate gets foreign keys and index names right more often than it gets column types and defaults right.
4. Add a roundtrip test in `tests/test_models.py`.

## When adding a new agent (Sprint 3+)

Every agent (Bookkeeping, Reconciliation, Validation, TDS, Bank Reconciliation,
Working Paper, Client Communication) follows the same shape, per the PRD's
module descriptions: extract → match/validate → stage a decision → either
auto-confirm or create a Task via `TaskEngine.create_task()`. Read the
matching PRD section (`docs/CAOS-PRD-v0.2.md` §5) for the specific
requirement IDs (e.g. BK-01 to BK-08) before writing the agent, and cite
them in docstrings the way the existing scaffold does — it's how a reviewer
traces code back to a requirement without re-reading the whole PRD.
