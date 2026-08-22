# Sprint Plan — Practice Automation Platform
### 12 Sprints × 2 Weeks = 24 Weeks (+ Phase 0 Baseline) | v0.2

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial plan: Phase 0 baseline + 12 sprints, sequencing the Feature Backlog's 102 features against the module dependency order established across the ADRs. |
| v0.2 | 2026-08-22 | Added P0-06 (Zoho Books sandbox spike) to Phase 0. Expanded Sprint 1-2 (Foundation) deliverables to build both the Tally and Zoho adapters behind the new Books Connector interface, per ADR 0011, plus the Admin — Connections screen's Zoho OAuth status. **Flagged: the Sprint 1-2 timeline needs explicit reconfirmation once P0-06 reports back** — see the note at the end of Sprint 1-2 below. Sprint 4-5's critical end-to-end test now runs against both adapters, not just Tally. |

## Sequencing logic

Sprints follow the same dependency order the ADRs and Feature Backlog already established: foundation before agents (a task can't route anywhere without the Task Engine; an entry can't post without the Books Connector), Bookkeeping before Reconciliation (the majority-path data has to exist in the books system before it can be reconciled), and Billing after enough agents exist to generate real billable events. The customer's own two highest-priority pain points — bookkeeping volume and client follow-up — land in Sprints 4–6, not at the end.

Per ADR 0011, both the Tally and Zoho adapters must exist before the Bookkeeping Agent build begins in Sprint 4-5, since ~20-40% of clients need Zoho from day one — this is why both adapters are now scoped into Sprint 1-2 rather than Tally-first with Zoho following later.

## Phase 0 — Baseline (Weeks -3 to 0, pre-sprint)

Not a build sprint — a measurement and validation phase before any application code is written.

- Use existing task-sheet data to measure real time-per-task (P0-01)
- Confirm Tally Cloud access method with the provider — port 9000 reachability (P0-02)
- Map shared inbox (work@xyz.com) routing logic to clients/staff (P0-03)
- WhiteBooks GSP sandbox spike — validate GSTR-2B fetch + GSTR-1/3B filing endpoints (P0-04)
- PaddleOCR accuracy validation against 20–50 real sample invoices (P0-05)
- **Zoho Books sandbox spike — validate the OAuth2 authorization flow, Bill/Journal-posting API shape, and current published rate limits before Sprint 1 begins (P0-06, per ADR 0011)**
- IaC tooling decision made (Terraform, per the still-open ADR item) — this needs resolving before Sprint 1 begins, since Sprint 1 provisions infrastructure

## Sprint 1–2 (Weeks 1–4) — Foundation

**Sprint goal:** Repo scaffolded, infrastructure provisioned, auth working, Task Engine operational, Books Connector reading real data from both a Tally and a Zoho Books client.

**ADRs exercised:** 0001 (Tally adapter), 0004 (thin-layer architecture), 0005 (Task Engine), 0007 (Python/FastAPI stack), 0009 (deployment model), 0010 (extension-point scaffold), **0011 (multi-backend Books Connector)**

**Deliverables:**
- Repo scaffolded per Coding Guidelines: ruff config, pytest, CI pipeline (Testing Strategy §6)
- Infrastructure provisioned via IaC on AWS ap-south-1 (ADR 0007/0009)
- `practices/{practice_slug}/` extension-point directory scaffolded, empty but structurally in place (CG11)
- Postgres schema for core-platform entities: Client, User, Task, Document, ExtractedData, `BooksConnection` (generalized from TallyCompany, per ADR 0011), Voucher, VendorMapping, EmailSenderMap, AuditEvent (per the ER diagram v0.2)
- Auth: JWT login/logout, role-based access control enforced server-side (ID-01 to ID-05, Security Standard §1–2)
- Secrets management wired to AWS Secrets Manager, including Zoho OAuth client credentials and per-client refresh tokens (Security Standard §3, amended)
- Task Engine: creation, routing rules, status lifecycle, auto-escalation (TE-01 to TE-09)
- **`BooksConnector` interface defined; `TallyAdapter` implemented and tested against the TallyPrime API Explorer sandbox, then the practice's real Tally Cloud (TC-01 to TC-05)**
- **`ZohoAdapter` implemented and tested against the Zoho Books developer sandbox — OAuth2 authorization flow, token refresh, and read extraction (ZB-01, ZB-02, ZB-04)**
- Dashboard API + Dashboard screen wired to real Task Engine data (PM-01)
- Admin — Connections screen includes Zoho OAuth status alongside Tally/GSP health (ZB-05, TC-05, TC-08)

> **Timeline flag:** This sprint's scope grew with the addition of the Zoho adapter. The original 2-sprint (4-week) estimate was set before ADR 0011. **Re-confirm this estimate once the Phase 0 Zoho spike (P0-06) reports back** — if the OAuth/posting work proves heavier than expected, Foundation may need to become a 3-sprint phase rather than 2, which would shift the whole ~27-week plan by roughly two weeks. This is called out explicitly rather than silently absorbed into the existing estimate; see Dev Readiness Checklist item GO-03.

## Sprint 3 (Weeks 5–6) — Intake Pipeline

**Sprint goal:** Documents flow automatically from email and Dropbox into the platform, with OCR extraction running.

**ADRs exercised:** 0003 (Dropbox webhooks + async queue), 0008 (PaddleOCR)

**Deliverables:**
- Email Intake Agent: shared inbox monitoring, sender-to-client mapping, auto-file to Dropbox (EI-01 to EI-06)
- Document Intake: Dropbox webhook + `list_folder/continue` pattern, async queue processing respecting the 10-second response constraint (DI-01, DI-01a, DI-01b)
- PaddleOCR (PP-StructureV3) pipeline live, validated against the Phase 0 sample set (DI-02, DI-03)
- Document checklist tracking, missing-item flagging (DI-04, DI-05)
- My Tasks screen wired to real data (TE-07)

## Sprint 4–5 (Weeks 7–10) — Bookkeeping Agent

**Sprint goal:** The highest-leverage agent, per the customer's own stated priority — documents become staged, reviewable, postable entries, for both Tally and Zoho Books clients.

**ADRs exercised:** CG5 (Decimal precision), CG7 (duplicate-prevention, amended for both adapters)

**Deliverables:**
- Line-item extraction from OCR output — vendor, date, amount, GST, HSN (BK-01)
- Fuzzy vendor-to-ledger matching engine (BK-02)
- New-ledger-creation task flow — flagged, not auto-created (BK-03)
- Draft entry generation with correct tax split, dispatched through the Books Connector to the client's configured adapter (BK-04)
- Confidence scoring, auto-stage vs. flag logic (BK-05)
- Bookkeeping Review screen wired to real staged entries, document preview alongside, with a Books System column so staff can see which backend each row targets (BK-06)
- Entry posting via the Books Connector — Tally voucher or Zoho Bill/Journal Entry — with the duplicate-prevention check running before every post, regardless of adapter (BK-07, BK-08)
- Client Workspace screen wired to real per-client module status

> **Testing note:** Per the Testing Strategy addendum, critical end-to-end flow #1 ("Document intake → bookkeeping → entry posted") must be run twice before this sprint closes — once against the Tally adapter, once against the Zoho adapter. Passing on one gives no assurance about the other, since the two adapters differ meaningfully in auth model and write shape.

## Sprint 6 (Weeks 11–12) — Client Communication

**Sprint goal:** Follow-up automation live — the practice's stated #1 pain point.

**Deliverables:**
- Template library + scheduled auto-send for routine reminders (CC-01, CC-02)
- Judgment-required communication drafting + proprietor approval queue (CC-03)
- Communication log (CC-04)
- Priority flagging for time-sensitive, client-dependent actions like OTP submission (CC-05)
- Client Communication screen wired to real data (approval queue + log)

## Sprint 7 (Weeks 13–14) — Reconciliation Agent

**Sprint goal:** GSTR-2A/2B reconciliation running through a direct GSP integration, with Winman removed from the critical path. Pulls purchase register data via the Books Connector, so it works identically for Tally and Zoho clients.

**ADRs exercised:** 0002 (GSP integration, bypassing Winman)

**Deliverables:**
- GSP integration (WhiteBooks or the vendor confirmed during Phase 0's sandbox spike) — GSTR-2B fetch (RC-01)
- Matching engine: GSTIN + invoice number + amount (RC-02)
- Auto-confirm for matched items, ITC claim summary (RC-03, RC-05)
- Mismatch queue with reason codes, routed as tasks (RC-04)
- Reconciliation Review screen wired to real data

## Sprint 8 (Weeks 15–16) — Validation/Compliance + TDS/TCS

**Sprint goal:** Pre-filing checks and TDS reconciliation, reusing the matching patterns built in Sprint 7.

**Deliverables:**
- GSTR-1 vs. 3B, HSN code, tax rate, and TDS-vs-26AS checks (VC-01 to VC-05)
- Per-client filing-readiness status (VC-06)
- TDS deduction-vs-deposit matching (TDS-01 to TDS-03)
- Draft quarterly TDS return generation (TDS-04)

## Sprint 9 (Weeks 17–18) — Bank Reconciliation + Working Paper

**Sprint goal:** Round out the compliance layer; auto-assemble the factual backbone of every engagement's working paper.

**Deliverables:**
- Bank account/transaction management, auto-matching by date/amount/reference (BR-01 to BR-04)
- Working paper auto-population from Reconciliation and Validation output (WP-01, WP-02)
- Judgment-notes field + finalization workflow, filed to Dropbox (WP-03, WP-04)
- Reports & Working Papers screen wired to real data

## Sprint 10 (Weeks 19–20) — Client Profiling & Billing

**Sprint goal:** Billing automation, built from scratch since no rate card exists today.

**Deliverables:**
- Client master profile CRUD, add/edit/deactivate, including the `books_system` field (CB-01)
- Service catalog + categories, reflecting the practice's actual service lines (CB-02)
- Per-client price overrides with recorded reason/approval (CB-03)
- Billing-trigger mapping from task/agent completion events (CB-04)
- Draft invoice generation, GST-compliant (GSTIN, HSN/SAC, tax breakup) (CB-05, CB-09)
- Invoice approval flow (CB-06)
- Invoice history (CB-07)
- Admin — Clients (with the Books system selector) and Service Catalog screens wired to real data; Billing screen wired

## Sprint 11 (Weeks 21–22) — Practice Management + Admin Completion

**Sprint goal:** Give the proprietor full practice-wide visibility; close out the remaining Admin screens.

**Deliverables:**
- Staff workload view, capacity indicator, deadline calendar (PM-02 to PM-04)
- Time-per-task tracking, extending the practice's existing task-sheet habit (PM-05)
- Outstanding invoice visibility on the dashboard (PM-06)
- Admin — Assignment Rules screen wired to the real routing rule table (TE-02)
- Admin — Connections screen wired to real Tally, Zoho, and GSP connection health (TC-05, TC-08, ZB-05)
- Tier reassignment workflow (CB-08)

## Sprint 12 (Weeks 23–24) — Hardening & Launch Preparation

**Sprint goal:** Production-ready. Every critical flow verified end-to-end, security and performance validated against their respective standards, not just assumed.

**Deliverables:**
- All 4 critical end-to-end flows tested against staging, including both adapter variants of flow #1 (Testing Strategy §3)
- Security review against the Security Standard checklist — auth, secrets (including Zoho OAuth token storage), encryption, audit-trail immutability, GSP call rate limiting
- Performance validated against targets in Performance & Scaling §2 and §5, under realistic (not synthetic) data volume
- Credential-rotation runbook written, covering Tally/GSP's fixed schedule and Zoho's revocation-triggered model (Security Standard §3, amended)
- Load-testing tooling set up (Performance & Scaling §8, still-pending task)
- DPDP legal review checkpoint — routed to the practice's legal/compliance contact, not resolved by engineering (still-open item)
- ADR review: confirm all 11 ADRs still reflect what was actually built; update any that drifted
- Staging → production deployment on AWS ap-south-1

## Summary

| Sprint | Weeks | Focus | Key modules |
|---|---|---|---|
| Phase 0 | -3–0 | Baseline measurement (incl. Zoho spike) | — |
| 1–2 | 1–4 | Foundation | Identity, Task Engine, Books Connector (Tally + Zoho adapters) |
| 3 | 5–6 | Intake pipeline | Email Intake, Document Intake |
| 4–5 | 7–10 | Bookkeeping | Bookkeeping Agent (both adapters) |
| 6 | 11–12 | Follow-up automation | Client Communication |
| 7 | 13–14 | GST reconciliation | Reconciliation Agent |
| 8 | 15–16 | Compliance checks | Validation, TDS/TCS |
| 9 | 17–18 | Remaining compliance | Bank Reconciliation, Working Paper |
| 10 | 19–20 | Billing | Client Profiling & Billing |
| 11 | 21–22 | Practice visibility | Practice Management, Admin |
| 12 | 23–24 | Hardening | Security, performance, launch prep |

**Total: ~27 weeks including Phase 0**, pending reconfirmation of the Sprint 1-2 estimate once the Zoho spike (P0-06) reports back — see the timeline flag under Sprint 1-2 above.
