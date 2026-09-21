# Documentation index

What each file in `docs/` is. Markdown lives here so `CLAUDE.md` and Claude
Code can read it directly in-repo.

**This index deliberately carries no version numbers.** A document's version
lives in its own changelog, which is the single source of truth for it.
Repeating versions here would create a second place to update and a second
place to go stale — the failure this index is being rebuilt to correct.

New to the repo? Read `../README.md` for what is built vs. stubbed, then
`context.md` for current status, then the doc you actually need.

## Status and process

| File | What it is |
|---|---|
| `context.md` | Living status doc — current state, blockers, recent merges. Updated by `/wrapup` at the end of every session (mandatory, not optional). **Read this first in any new session** before re-deriving status. |
| `STUB_ISSUES.md` | Stub / incomplete-code tracker. Every `STUB(...)` marker in the codebase resolves to a GitHub issue or a `PENDING:NNN` row here. |
| `CAOS-prompt-conventions.md` | How requests to Claude Code get phrased and how output gets prepared for merge. |

## Core specifications

| File | What it is |
|---|---|
| `CAOS-PRD-v0.2.md` | Product Requirements Document — 14 modules, requirement IDs (`BK-01`, `ZB-03`, …), KPIs. §3 is the documentation roadmap. |
| `CAOS-sprint-plan-v0.2.md` | Sprint Plan — Phase 0 baseline + 12 sprints. |
| `CAOS-api-spec-v0.2.md` | API Specification — endpoints across 12 domains, traced to PRD requirement IDs and ER entities. |
| `CAOS-coding-guidelines-v0.2.md` | CG1–CG11. Non-negotiable unless a rule says otherwise. |
| `CAOS-security-standard-v0.2.md` | Auth, secrets, encryption, audit-trail immutability, rate limiting. |
| `CAOS-testing-strategy-v0.2.md` | Test pyramid, external-service mock boundary, critical flows, CI gates. |
| `CAOS-logging-standard-v0.1.md` | Structured logging, correlation fields, the audit-trail boundary, PII masking. |
| `CAOS-performance-scaling-v0.1.md` | Performance targets, indexing guidance, scaling triggers. |

## Architecture decisions

| File | What it is |
|---|---|
| `ADR-INDEX.md` | **The authoritative ADR table** — every ADR 0001–0014 plus both 0011 amendments, with status and filename. Start here rather than reading filenames. |
| `audit-platform-ADR-*.md` | The ADRs themselves, one per file. Indexed above; not re-listed here, so the index stays the only place status is stated. |
| `audit-platform-ADR-0001-0010-open-items.md` | What was left undecided when the original 0001–0010 set was written. Check each against later ADRs before assuming it is still open. |

## Data model

| File | What it is |
|---|---|
| `audit-platform-ER-diagram-v0.1.md` | ER diagram companion doc — entity descriptions and changelog. |
| `audit-platform-ER-core.mermaid` | Core platform ER diagram. Models in `services/api/app/models/` match it, with one documented exception: `created_at` is deliberately omitted from the diagrams. |
| `audit-platform-ER-compliance-billing.mermaid` | Compliance & billing ER diagram. |

## Phase 0 spike runbooks

Runbooks — what to run and what to look for — live here. The **results** of
running them (`FINDINGS.md`, scripts, captured request/response logs) live in
`spikes/` at the repo root, one directory per spike. The two are easy to
confuse: `docs/spikes/P0-06-zoho-api-runbook.md` is the plan,
`spikes/p0-06-zoho/FINDINGS.md` is what happened.

| File | What it is |
|---|---|
| `spikes/P0-02-api-explorer-runbook.md` | TallyPrime API Explorer — payload builders and test sequence. |
| `spikes/P0-04-whitebooks-gsp-runbook.md` | WhiteBooks GSP — request builders and test sequence. |
| `spikes/P0-06-zoho-api-runbook.md` | Zoho Books API — request builders and test sequence. |
| `spikes/p0-04-whitebooks-gsp/whitebooks-api-reference.md` | WhiteBooks GSP API reference, distilled from five vendor-supplied documents. |
| `spikes/p0-04-whitebooks-gsp/reference/` | Those five source documents, as supplied, plus the TLS certificate. |
| `spikes/*.py` | Pre-spike request/payload builders (`gsp_requests.py`, `tally_payloads.py`, `zoho_requests.py`). Superseded by the executed spikes under the root `spikes/`. |
| `CAOS-tally-integration-schema-reference.md` | TallyPrime XML schema reference compiled from P0-02. Point-in-time, not a living spec. |

## Binary deliverables, committed here

| File | What it is |
|---|---|
| `CAOS_Internal_Development_Readiness_v0_1_1.pdf` | The original consolidated readiness package. ADRs 0001–0010 were extracted from it into individual files; it is kept for provenance, not as the current source. |
| `CAOS_Feature_Documentation_v0_6.docx` | Customer-facing process flows per module. |
| `CAOS_Presentation_v0_2.pptx` | Customer-facing presentation deck. |
| `CAOS_Integration_Testing_v0_1.docx` | Customer-facing deliverable prepared for Venture Assist / Srivatsan & Associates, September 2026 — the integration testing approach, reporting what was tested against real systems. |
| `CAOS_Tally_Integration_Capabilities_v0_1.docx` | Customer-facing deliverable prepared for Venture Assist / Srivatsan & Associates, September 2026 — Tally integration capabilities: what works today against a live Tally system, and what does not yet. |
| `CAOS_Software_Development_Proposal_v0_3.docx` | Customer-facing commercial proposal — scope, timeline, fixed price against milestones, warranty, training, and the licence model. **Not yet sent to the practice:** §9's recurring-cost estimate is still priced on Supabase/Railway, against ADR 0007/0009 — see `PENDING:038`. |
| `CAOS_Software_Development_Proposal_v0_2.docx` | The pre-commercial-terms version, kept as the source of record for what changed in v0.3. Superseded — read v0.3. |
| `audit-platform-wireframes-v0_2.html` | 9 screens + 4 admin sub-screens, Design B (Capacity). |

## Delivered separately, genuinely not in this repo

- **Dev Readiness Checklist** (`CAOS-dev-readiness-checklist-v0.1.xlsx`) — 44 items across 6 categories.
- **Feature Backlog** (`.xlsx`) — MoSCoW-tagged, phase-mapped.

The checklist is the one that matters day to day. Its item IDs — `P0-*`
(Phase 0 spikes), `ENV-*`, `RB-*` (runbooks), `OQ-*` (open questions), `GO-*`
— are cited **throughout this repo**, in docs, ADRs, spike runbooks, code
comments, `.env.example` and CI config, with **no in-repo source for what any
of those items actually says.** Anyone reading `ENV-05` or `OQ-07` here has to
ask someone for the spreadsheet. PRD §3's Dev Readiness Checklist row carries
the current citation count and the method used to produce it.

Note `PM-*` is **not** one of those prefixes, despite appearing alongside
them: `PM-01`–`PM-06` are the PRD's own Practice Management requirement IDs
(§5.14), which share the shape.
