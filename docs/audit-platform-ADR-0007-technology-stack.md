# ADR 0007 — Technology Stack

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted (revised)

**Accepted 2026-09-17.** The open question was never the analysis — it was
whether the team that actually builds this is comfortable in Python rather
than Node. Confirmed: they are. The formal status now matches a choice the
codebase has already implemented — `services/api/app/` is FastAPI with async
SQLAlchemy and Alembic, and `app/books_connector/` is built on it. This
records reality rather than authorising a change.

Note that acceptance covers the stack, not every aside in the Decision
table. The hosting row's parenthetical rejection of "Fargate/Terraform-level
complexity" bundles two separable things; **ADR 0014** unbundles them,
reaffirming the Fargate rejection and adopting Terraform at the scope this
ADR already specified.

## Context

No tech stack had been decided yet. The reference project (COCA) used NestJS + PostgreSQL/PostGIS + Redis/BullMQ + AWS ECS Fargate + Turborepo — but COCA had three separate user-facing surfaces (offline-first mobile field app, ops dashboard, client portal) and a VC-backed team with dedicated DevOps. This project has a single user-facing surface (one desktop-first PWA, per ADR 0006, no client portal per §6 of the PRD) and a cost-sensitive, payback-justified budget (no dedicated technology line item per discovery). Revision note: the initial draft weighted this decision toward the webhook/integration workload and assumed OCR/matching would be a thin wrapper around external APIs. On reconsideration, the document-extraction and ledger/reconciliation-matching engine (BK-02, RC-02) is the actual differentiator the solution’s success depends on — not the webhook plumbing — and that changes the calculus materially.

## Decision

| Layer | Choice | Rationale |
|---|---|---|
| Backend framework | **Python (FastAPI)** — revised from NestJS | The extraction/matching engine is the differentiator, not a peripheral concern. Python's ecosystem (rapidfuzz, pandas for reconciliation logic, a real path to embedding-based matching later, and mature self-hosted OCR options if cloud OCR raises data-residency concerns per ADR 0004) is meaningfully stronger here than Node's equivalents. FastAPI's async support handles the webhook/I/O workload adequately even though it isn't Python's traditional strength. One language throughout avoids the operational overhead of a Node+Python hybrid for a small team. |
| Database | PostgreSQL | Unchanged — ACID guarantees for financial/task data |
| ORM | SQLAlchemy (async) + Alembic for migrations | Python-native equivalent of the Prisma/NestJS pairing |
| Queue | Redis + Celery (or RQ for lighter weight) | Required by ADR 0003 for async webhook processing; Python-native equivalent of BullMQ |
| Frontend | React + Vite + TypeScript | Unchanged — desktop-first PWA per ADR 0006; frontend language choice is independent of backend language |
| UI | shadcn/ui + Tailwind CSS | Unchanged |
| PWA layer | Workbox (service worker) + Web Push API | Unchanged |
| OCR | Evaluate self-hosted (Tesseract/PaddleOCR) vs. cloud API (Claude/GPT-4V/Document AI) | Ties directly to the open OCR/LLM vendor item, as part of the still-open OCR vendor decision — Python backend keeps both options equally viable, which a Node backend would not |
| Hosting | **AWS ap-south-1 (Mumbai)** — revised from Railway | Revision: Railway was the original recommendation for its lighter operational footprint vs. COCA's full AWS Fargate + Terraform setup, but Railway has no India region (closest is Singapore). Once DPDP-driven self-hosted OCR became the decision (ADR 0008), hosting also needs to be India-resident for that principle to actually hold — self-hosted OCR running outside India doesn't meaningfully improve on a cloud API with India-region processing. AWS Mumbai keeps the practice's data in-country, matches the region COCA also used for the same reason, and still allows a lightweight setup (a single EC2 instance or small ECS setup) without Fargate/Terraform-level complexity — the "lighter than COCA" principle still holds, just not via Railway specifically. |
| Repo structure | Single repo, two packages (api, web) | Unchanged — frontend (TS) and backend (Python) naturally separate packages regardless |
| CI/CD | GitHub Actions | Unchanged |

## Consequences

- Frontend (TypeScript/React) and backend (Python) are now different languages — loses the “one language across the stack” simplicity the original NestJS recommendation offered, in exchange for materially better tooling on the part of the system that determines whether the product actually works well.

- Type-sharing between frontend and

backend requires either a generated OpenAPI client or manual type definitions — FastAPI’s automatic OpenAPI generation makes this workable, but it’s an explicit trade-off to note, not a wash.

- Keeps self-hosted OCR genuinely viable as an option, which matters if the OCR vendor decision leans toward data-residency concerns over convenience.
- Still Proposed, not Accepted — same caveat as before: needs confirmation from whoever actually builds this, since team familiarity with Python vs. Node matters as much as this analysis.

## Alternatives considered

- NestJS (original recommendation) — superseded by this revision; was reasonable when the webhook/integration workload was weighted as primary, less so once the matching engine is recognized as the differentiator.

- Hybrid: NestJS app layer + Python matching microservice — genuinely viable, best-of-both technically, but adds a second runtime/deployment unit that’s real overhead for a small team. Worth reconsidering if the team ends up being large enough to support polyglot services comfortably.
- Full COCA- equivalent stack (AWS ECS Fargate + Terraform + Turborepo) — still rejected as disproportionate to this project’s scale and budget.

## Status note

This ADR changed direction once between drafts based on which workload was weighted as primary — a useful reminder to lock down “what actually determines success” before finalizing stack decisions, not after.
