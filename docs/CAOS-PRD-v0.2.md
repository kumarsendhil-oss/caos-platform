# Practice Automation Platform — Product Requirements Document
### Prepared for Venture Assist / Srivatsan & Associates | v0.2.5

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial draft: 13 modules, requirements, user stories, KPIs. Open questions resolved iteratively: Tally access method, Winman/GSP integration approach, Dropbox API constraints, DPDP/data-residency architecture principle, billing module added. Still open: GSP vendor pricing confirmation, DPDP specifics. Not yet at v1.0 — pending ADRs. |
| v0.2 | 2026-08-22 | Discovery found ~20-40% of clients maintain books in Zoho Books rather than Tally, requiring full read/write parity (not a reduced experience). §5.3 retitled and restructured from "Tally Connector" to "Books Connector," covering both a Tally adapter and a new Zoho adapter, per ADR 0011. CB-01 gains a `books_system` field. §2's data-sources row and §8's open questions updated accordingly. |
| v0.2.1 | 2026-09-15 | BK-04 reworded per **ADR 0011 Amendment 1**. The P0-06 Zoho spike found that Tally and Zoho model GST incompatibly — Tally takes explicit CGST/SGST/IGST ledger lines, Zoho takes a per-line tax reference and *decomposes* it into components itself. **Tax selection remains the caller's responsibility on both backends** (corrected in v0.2.2 — the original wording, "computes the split itself," read as though handing Zoho the state codes were sufficient; it is not): the adapter must still choose an intra-state tax group or an IGST tax from place of supply and supplier state, and Zoho only *validates* that choice against them. So `DraftEntry` now carries tax determinants (taxable amount, tax rate, place of supply, supplier state) and each adapter derives its own backend's representation. BK-04 previously assigned the split to the Bookkeeping Agent, which is no longer where it happens. This also widens BK-01's extraction scope: place of supply and supplier state are two new fields to read off the invoice, and absent or unreadable values route through the Task Engine like any other low-confidence extraction rather than being guessed. |
| v0.2.2 | 2026-09-16 | Three lines corrected against live P0-06 results — each had been written from Zoho's documentation or from a reasonable inference, and each was settled by an actual API response. **ZB-03** (finding #12): Journal Entries cannot carry tax at all — a line-level `tax_id` is rejected with code 110942 ("Tax not supported"), and `source_of_supply`/`destination_of_supply` are accepted with HTTP 201 and then silently dropped, absent from the read-back. Any tax-bearing entry must route to Bills specifically; Journals are for tax-free entries only. **BK-04** carried the same now-wrong claim ("a Zoho Bill/Journal Entry with a tax-rate reference") and is corrected to match, same finding. **v0.2.1's own changelog line** (findings #8, #9): "Zoho takes a per-line tax reference and computes the split itself" was true of the decomposition (`GST18` in, `CGST9`+`SGST9` out) but misleading as a whole — Zoho *validates* the caller's tax choice against the two state codes rather than deriving it, rejecting a mismatch in either direction with code 3032. Tax *selection* stays with the caller. **BK-08** (finding #10): "neither Tally's XML import nor Zoho's write API prevents duplicate entries on its own" is wrong for Zoho — it enforces case-insensitive, whitespace-trimmed uniqueness on (vendor, `bill_number`), code 13011. CG7 is unchanged and still required: Zoho's guard is keyed on the contact rather than the GSTIN, ignores the date, and matches the invoice number literally. Full evidence in `spikes/p0-06-zoho/FINDINGS.md`. |
| v0.2.3 | 2026-09-18 | Resolved an apparent self-contradiction between §3's roadmap table ("Dev Readiness Checklist — Complete") and §10.5 ("Complete the Dev Readiness Checklist before Sprint 1 begins"). Both were true but read as conflicting: §3 tracks whether each *document* was authored, §10 tracks outstanding *work*. Neither status was wrong, so neither was downgraded. §3's row now names the artifact (`CAOS-dev-readiness-checklist-v0.1.xlsx`, delivered separately per `docs/README.md`), states that "Complete" means authored, and records the six category prefixes its item IDs use (`P0`, `ENV`, `RB`, `OQ`, `GO`, `PM`) — these are cited in **sixteen** other documents under `docs/` and in ten further files outside it — code, tests, CI config and agent definitions (e.g. `P0-02`/`ENV-05` in `docs/STUB_ISSUES.md`, `RB-01`/`OQ-05`/`OQ-06` in the Security Standard, `RB-03` in Performance & Scaling, `GO-03` in the Sprint Plan, `ENV-05`/`ENV-06`/`ENV-07` in `.github/workflows/ci.yml`). Counted by matching `\b(P0\|ENV\|RB\|OQ\|GO)-[0-9]{2}\b` over tracked files, excluding this document itself and the root `spikes/` execution directories; `PM` is deliberately outside that pattern, because `PM-01`–`PM-06` in §5.14 are this PRD's own Practice Management requirement IDs and match the same shape. §10.5 is reworded to ask for the items to be worked through rather than for the checklist to be written. The `CAOS_Internal_Development_Readiness_v0_1_1.pdf` snapshot (2026-08-16) showing the checklist "Not started" is not evidence against this — it predates the 2026-08-22 authoring date by six days. |
| v0.2.4 | 2026-09-19 | **§3's Documentation Roadmap rebuilt against actual state, and §2's architecture row corrected.** Anchored to the 2026-09-19 documentation-currency audit. Every §3 row was re-derived from its source artifact rather than the named ones being patched — the audit's first pass, which patched only what it had already spotted, missed four further errors. **Two rows were wrong on status:** the ADR row still listed **IaC tooling as open** after ADR 0014 closed it on 2026-09-17, and omitted 0012, 0013, 0014 and both 0011 amendments; the Tech Stack row still listed ADR 0007 as **Proposed** when it was Accepted on 2026-09-17 (`5ad7db5`). **Five were wrong on version or date:** Sprint Plan, Security Standard (v0.2.1), Performance & Scaling (v0.1 rev), ER Diagram (the core `.mermaid` carries v0.2.1), and this PRD's own row. **One row was missing entirely** — `CAOS_Feature_Documentation_v0_5.docx` is tracked in the repo and was absent from a table describing itself as "the master index across all artifacts"; an omitted artifact is the same defect as a wrong version, so it was added rather than deferred. Seven rows were checked and confirmed already correct (Feature Backlog, API Spec, Coding Guidelines, Logging Standard, Testing Strategy, Wireframes, Visual Design Directions) and are unchanged. `docs/ADR-INDEX.md` was confirmed current through 0014 including 0011-A2 and deliberately not touched. Known-unverifiable, left alone: the Sprint Plan's v0.1 row cites **102** features against this table's **107** — consistent with growth between backlog v0.1 and v0.2, but nothing in-repo records that transition and the Feature Backlog xlsx is delivered separately, like the readiness checklist. |
| v0.2.5 | 2026-09-19 | **§3 no longer carries version numbers for documents that have their own changelog.** Eleven rows now point — ten documents at their changelogs, the ADR and Tech Stack rows at `docs/ADR-INDEX.md` — and the `Last Updated` column is gone, folded into the one remaining `Version` cell for the artifacts that still need it. **Five rows keep a version**: the Feature Backlog and Dev Readiness Checklist spreadsheets, the customer-facing Feature Documentation, the wireframes and the Visual Design Directions, none of which has an in-repo changelog, so for those this table *is* the single place — the rule is one place, not never here. **Why, concretely:** v0.2.4 rebuilt this table's version columns on 2026-09-19 and they were stale the same day — PR #73 took the Coding Guidelines to v0.2.1 and the row here still read v0.2, unnoticed across two further PRs. Copying a version into a second table reproduces that indefinitely; pointing makes it structurally impossible. Status stays here in full, being the column that is not derivable from any file. Enforced by `scripts/check_doc_versions.py` per `CAOS-prompt-conventions.md` §9. |

## 1. Executive Summary

This PRD defines the requirements for an internal practice-automation platform: a task-engine-driven system with a set of purpose-built agents that automate document intake, bookkeeping, GST/TDS reconciliation, compliance validation, client communication, and practice-wide workload visibility for a CA practice currently servicing ~100 GST returns/month with a target of ~500/month within 6 months, without adding headcount.

This is an internal operations platform, not a client-facing product — client acquisition stays personal-connect only, per the practice's stated preference. Every module exists to remove manual, repetitive work from the 10-person team while keeping the proprietor and senior staff in control of every judgment call.

## 2. Platform at a Glance

| Dimension | Detail |
|---|---|
| Platform type | Internal task-engine + automation-agent platform for a CA/audit practice |
| App form factor | PWA (installable) and regular full-browser access — same app, no separate desktop-only build. Designed desktop-first with responsive breakpoints, since staff primarily work at a desktop monitor; mobile is a secondary, fully-functional but reflowed layout, not the primary design target |
| Primary users | Proprietor, senior staff (paid assistants), junior staff (article clerks) |
| External users | None — no client-facing portal in this phase |
| Data sources | Tally Cloud and/or Zoho Books (books — per client, see §5.3), Dropbox (documents), shared inbox work@xyz.com (email), Winman (filing utility), GSTN portal (GSTR-2A/2B) |
| Geography / compliance | India — GST, Income Tax, TDS/TCS, ROC |
| Language | English (staff-facing; no multi-language requirement identified) |
| Architecture | See Architecture Decision Records (ADRs 0001-0014, plus two amendments to ADR 0011) |
| Modules | 14 (13 functional + 1 integration layer) |
| Build plan | Phased (Phase 0–4, per prior roadmap discussion) — broken into a 12-sprint plan, see Sprint Plan v0.2 |

## 3. Documentation Roadmap

Tracking status of the full readiness package — this table is the master index across all artifacts.

**Status is tracked here; versions are not, for anything that carries its own
changelog.** A document's changelog is the single source of truth for its
version (`docs/CAOS-prompt-conventions.md` §9), so those rows point rather than
copy. This table previously copied them and went stale the same day it was
rebuilt — the Coding Guidelines row still read v0.2 after PR #73 took the file
to v0.2.1. The five rows that still carry a version are artifacts with no
in-repo changelog, for which this table *is* the one place.

| Document | Status | Version |
|---|---|---|
| PRD (this document) | In progress | See this document's changelog |
| Feature Backlog (MoSCoW + phase mapping) | Complete (107 features, xlsx with Summary sheet) | v0.2 (2026-08-22) |
| Feature Documentation (customer-facing) | Complete — process flows per module; "Why This Matters — In Numbers" reframed per the P0-01 finding that no existing task-sheet baseline exists to measure against. Committed as `CAOS_Feature_Documentation_v0_5.docx` | v0.5 (2026-09-18) |
| Architecture Decision Records | In progress — 14 ADRs (0001–0014) plus two amendments to 0011. **0013 (HRMS) is Proposed; all others Accepted**, several with a flag on their own file (0011 pending Zoho sandbox spike, 0012 pending re-metering, 0003 doc-verified only pending P0-07). Still open: DPDP legal specifics, PaddleOCR accuracy validation against real documents, and the extension-point pattern (`OQ-07`). **IaC tooling is no longer open** — closed 2026-09-17 by ADR 0014 (lightweight Terraform; Fargate stays rejected). See `docs/ADR-INDEX.md` for the authoritative table | See `docs/ADR-INDEX.md` |
| ER Diagram | Complete (2 diagrams: core platform, compliance & billing — BOOKS_CONNECTION generalized per ADR 0011; `ROUTING_RULE` added and `TASK` gains `assigned_role`) | See `audit-platform-ER-diagram-v0.1.md`'s changelog |
| API Spec | Complete — endpoints across 12 domains, Books Connections retitled and Zoho OAuth endpoints added | See its changelog |
| Coding Guidelines | Complete — CG1–CG11, CG7 generalized across both adapters | See its changelog |
| Logging Standard | Complete — no changes required by ADR 0011 | See its changelog |
| Testing Strategy | Complete — mock boundary and critical flow #1 extended to cover the Zoho adapter | See its changelog |
| Security Standard | Complete — Zoho OAuth credential storage and rotation-model note added; §4 gains external-TLS-certificate tracking, with the WhiteBooks GSP certificate's 11 Nov 2026 expiry as the first recorded instance | See its changelog |
| Performance & Scaling | Complete — §3 carries the first **real** OCR throughput measurement (~243 s/document on CPU, from P0-05). The original 30 s target is **not met** and is retained alongside the measurement rather than rewritten; §4's 2–4 worker range was rechecked against it and stands | See its changelog |
| Wireframes / Mockups | Complete — Design B (Capacity) applied across all 9 screens + 4 Admin sub-screens; Books system field, Zoho Connections table, and Bookkeeping Review updates added | v0.2 (2026-08-22) |
| Visual Design Directions | Resolved — customer selected Design B (Capacity) | v0.1 (2026-08-16) |
| Tech Stack Decision | **Accepted** as ADR 0007 (revised) — Python/FastAPI backend, AWS ap-south-1 (Mumbai) hosting. The open question was never the analysis but whether the team is comfortable in Python rather than Node; confirmed, and the codebase had already implemented the choice. Fargate remains rejected; Terraform adopted at ADR 0007's scope per ADR 0014 | See `docs/ADR-INDEX.md` |
| Sprint Plan | Complete — Phase 0 (+ Zoho spike) + 12 sprints (~27 weeks, timeline pending Phase 0 spike confirmation). P0-07 (Dropbox webhook live verification) added; P0-01 marked not executable and deferred to PM-05 (Sprint 11) | See its changelog |
| Dev Readiness Checklist | Complete — 44 items across 6 categories. Delivered separately as `CAOS-dev-readiness-checklist-v0.1.xlsx`, not committed to git (see `docs/README.md`, "Delivered separately"). "Complete" here means the checklist is **authored**, not that its items are all done — item IDs cited across this repo use six prefixes: `P0` (Phase 0 spikes), `ENV` (environment & tooling), `RB` (runbooks), `OQ` (open questions), `GO` (go/no-go), `PM`. | v0.1 (2026-08-22) |

## 4. Users & Roles

| Role | Who | Primary use of the platform |
|---|---|---|
| Proprietor (SV) | Practice owner | Cross-client/cross-staff dashboard, escalations, final sign-off on judgment calls, capacity view for taking on new work |
| Senior staff (paid assistants) | 6 | Reconciliation/TDS/validation review, voucher approval, client communication approval, task assignment to juniors |
| Junior staff (article clerks) | 4 | Document classification exceptions, staged voucher review, routine task execution, follow-up calls |

Note: all three roles were confirmed as day-to-day users during discovery (Q19) — this isn't a tool for one persona, it's used practice-wide.

## 5. Modules & Requirements

### 5.0 Architecture Principle: Platform as a Thin Layer, Not a New System of Record

Tally and Zoho Books (via the Books Connector) and Dropbox remain the systems of record for financial data and documents respectively — both are already in use today, and both already carry whatever data-handling posture the practice and its clients have accepted. The platform does not introduce a new consolidated store of full financial records or documents.

What the platform's own database does hold: task metadata, client profile/billing data, communication logs, and reconciliation/validation results (derived data, not source documents). Source documents and ledger data are read from Dropbox/Tally/Zoho Books on demand, processed, and written back — not duplicated into a separate permanent store.

This narrows the DPDP Act surface considerably (§8, item 4): the practice's existing obligations for Tally, Zoho Books, and Dropbox already cover the bulk of the data; what's new is the platform's own metadata layer, plus any transient processing (OCR/LLM) in between.

### 5.1 Identity & Access (ID)

Role-based access and accountability across the practice.

- ID-01 Role-based login (Proprietor / Senior staff / Junior staff)
- ID-02 Each user sees a personal task queue scoped to what's assigned to them
- ID-03 Proprietor has cross-client, cross-staff visibility by default
- ID-04 Session handling appropriate for shared office devices (auto-logout, no persistent shared sessions)
- ID-05 Audit log of who took what action, when — supports accountability and DPDP Act alignment

### 5.2 Task Engine (TE)

The shared layer every other module writes to and every user reads from.

- TE-01 Any agent exception or judgment call creates a task record: type, linked record/context, client, due date
- TE-02 Task routing via a configurable assignment rule table (task type → default role/person)
- TE-03 Manual reassignment available to senior staff and proprietor
- TE-04 Auto-escalation when a task passes its due date/threshold — escalates to senior staff or proprietor depending on task type
- TE-05 Task status lifecycle: Open → In Progress → Completed / Escalated
- TE-06 Completing a task requires a recorded outcome (approved / rejected / edited), not just "marked done"
- TE-07 Personal "My Tasks" view, sorted by due date and priority
- TE-08 Notification on new assignment and on escalation
- TE-09 Full task history retained per client, for audit trail and time-per-task measurement

### 5.3 Books Connector (BC) — integration layer, not user-facing

*Retitled from "Tally Connector" — per ADR 0011, discovery found ~20-40% of clients maintain books in Zoho Books rather than Tally, requiring the same full read/write automation as Tally, not a reduced experience. The platform now defines a `BooksConnector` interface with two adapters. No agent module (Bookkeeping, Reconciliation, Working Paper) contains backend-specific logic — every agent is built against the interface's normalized schema.*

Which adapter a given client uses is per-client configuration (`books_system`: `tally` | `zoho_books`, recorded on the client master profile — see CB-01), not a code fork.

#### 5.3.1 Tally Adapter

Confirmed: books for the large majority of clients are maintained by the practice's own staff in the practice's own Tally Cloud (multi-company subscription) — this is the practice's environment, not each client's. Only a small percentage of clients maintain their own Tally and hand over a backup/exported ledger instead. This means two distinct data paths, not one.

**Primary path — practice-maintained companies (majority of clients)**
- TC-01 Connect to the practice's own Tally Cloud subscription, across all client companies hosted within it, via TallyPrime's built-in XML-over-HTTP interface (default port 9000). Verified against Tally Solutions' own documentation: this is a native, built-in capability of TallyPrime — enabling it is a configuration step (Advanced Configuration → HTTP Server), not a separate purchasable license. TallyPrime can act as an HTTP server, accepting XML/JSON requests and returning both read data and accepting writes (voucher/master creation) over the same interface. The real open item isn't licensing — it's whether the practice's Tally Cloud provider allows this port/configuration to be reached from outside their hosted environment.
- TC-01a ODBC is also available on TallyPrime (as both ODBC server and client) but is read-only — no INSERT/UPDATE support. Suitable for simple reporting-style extraction if useful as a secondary/reporting path, but the Bookkeeping Agent's voucher push (TC-04) must go through the XML/HTTP interface, not ODBC.
- TC-01b Development/testing note: Tally Solutions provides an official sandbox — the TallyPrime API Explorer — for sending live XML/JSON requests and inspecting responses without a real Tally company connected. Use this to validate the exact payload shapes for TC-02 (extract) and TC-04 (voucher push) before writing Connector code against any live client data. The TallyPrime Developer IDE (includes a Tally Connector component) is the tool for the actual build; it has a 90-day free evaluation, after which a Tally Software Services (TSS) subscription is needed.
- TC-02 Extract purchase register, sales register, bank book, and ledgers in structured form, per client company
- TC-03 Normalize data across Tally versions/company-specific customizations into one standard schema — this is the same normalization principle the Zoho adapter's output (§5.3.2) is held to, so downstream agents never see backend-specific shapes
- TC-04 Push draft vouchers (from the Bookkeeping Agent) into the correct client company via import
- TC-05 Per-client-company connection/sync health surfaced on the Practice Management dashboard

**Secondary path — client-maintained books (small percentage of clients)**
- TC-06 Accept a client-provided Tally backup file as the input — confirmed this is the actual format used, and it can be restored/imported directly into the practice's own Tally environment
- TC-07 Once restored, the same primary-path extraction (TC-01–TC-03) applies — no separate parser needed, just an operational step (restore backup → company appears in Tally → primary pipeline runs against it) with its own scheduling/freshness profile
- TC-08 Flag clients on this path distinctly on the dashboard, since data freshness depends on how often the client sends an updated backup

#### 5.3.2 Zoho Adapter

*New per ADR 0011.* Confirmed: roughly 20-40% of clients keep their books in Zoho Books directly (their own subscription/organization, not practice-hosted), and need the same level of Bookkeeping Agent automation as Tally clients — extraction, fuzzy vendor matching, draft posting, duplicate prevention.

- ZB-01 Per-client-organization OAuth2 authorization-code flow against Zoho Books; refresh-token storage in Secrets Manager (CG4, Security Standard §3) with automated token refresh. Unlike Tally's practice-wide credential, this is a per-client consent — closer to the GSP's per-GSTIN OTP/consent model (ADR 0002) than to Tally's single practice-wide connection.
- ZB-02 Extract the equivalent purchase register, sales register, bank book, and ledgers from Zoho Books via its REST API v3, normalized to the same standard schema the Tally adapter produces (TC-03).
- ZB-03 Push approved draft entries (from the Bookkeeping Agent) into Zoho Books. **Any tax-bearing entry must post as a Bill, not a Journal Entry** — Zoho's Bills carry the CGST/SGST/IGST breakdown in their own tax-component fields (the functional equivalent of a Tally voucher's ledger split), whereas Journal Entries reject a line-level tax reference outright and silently discard the place-of-supply fields, so a Journal cannot represent a taxable purchase at all. Journal Entries remain available for tax-free entries only (reclassifications, accruals, adjustments). Per P0-06 finding #12. The same duplicate-prevention check (CG7) runs before this write, identical in principle to the Tally path.
- ZB-04 Client master profile records which bookkeeping system (Tally or Zoho Books) a client is on (`books_system`, per CB-01), driving which adapter every downstream agent uses for that client.
- ZB-05 Per-client OAuth connection status, token health, and re-consent flow surfaced on the Admin — Connections screen, alongside Tally/GSP health — a stale Tally sync and an expired Zoho token are different failure modes needing different remediation, so they're tracked as separate tables, not one generic "connected/disconnected" status.

### 5.4 Email Intake Agent (EI)

Automates the manual email-to-Dropbox filing step confirmed as a real, unautomated pain point.

- EI-01 Monitor the shared inbox (work@xyz.com) for incoming client emails
- EI-02 Identify the client from sender address/domain, using a learned mapping table
- EI-03 Classify the attachment type (invoice, bank statement, GSTR filing, other)
- EI-04 High-confidence match → auto-file to the correct Dropbox folder
- EI-05 Low-confidence or unrecognized sender → creates a task for staff to confirm client/folder manually
- EI-06 Sender-to-client mapping is viewable and editable by staff

### 5.5 Document Intake / Dropbox Sync (DI)

Verified against Dropbox's own API documentation.

- DI-01 Watch the defined Dropbox folder structure (client/period/doc-type) via webhook. Verified: Dropbox webhooks notify only that an account has changes — not which files. The confirmed pattern is: webhook fires → app calls `/files/list_folder/continue` with a stored cursor → app filters the returned changes for relevant folders.
- DI-01a Hard constraint: the webhook endpoint must respond within 10 seconds. Actual processing (fetching changes, downloading the file, triggering OCR) must happen asynchronously via a queue/background worker — never inline in the webhook handler.
- DI-01b Recommended scope decision: request Dropbox "App folder" access rather than "Full Dropbox" access, per the data-minimization principle.
- DI-02 OCR + data extraction for PDF documents (amounts, dates, GSTIN, vendor name)
- DI-03 Excel parsing with per-client template detection, since formats vary by client
- DI-04 Checklist of expected vs. received documents per client per period
- DI-05 Missing-item reminder routed through the Client Communication Agent once a document is overdue

### 5.6 Bookkeeping / Voucher Entry Agent (BK)

Flagged directly by the customer as the area with the most automation need — this is the highest-leverage module. Applies identically regardless of which adapter (Tally or Zoho) a client is on, per §5.3.

- BK-01 Extract line items from intake documents: vendor, date, amount, GST, HSN
- BK-02 Fuzzy-match vendor/customer name to an existing ledger (Tally or Zoho Books, per the client's configured `books_system`)
- BK-03 No match found → create a task for new-ledger creation rather than auto-creating
- BK-04 Generate a draft entry carrying the tax *determinants* — taxable amount, tax rate, place of supply, and supplier state — rather than a computed tax split. The Books Connector adapter derives its own backend's representation from these: a Tally voucher with its CGST/SGST/IGST ledger split, or — for Zoho, where a tax-bearing entry must be a Bill and never a Journal Entry (P0-06 finding #12, see ZB-03) — a Zoho Bill with a tax-rate reference, depending on the client's backend. Per ADR 0011 Amendment 1
- BK-05 Confidence scoring: high-confidence entries auto-stage, low-confidence ones are flagged for review
- BK-06 Staff review/approval screen for staged entries before posting
- BK-07 Approved entries post via the Books Connector — to Tally or Zoho Books, whichever the client uses
- BK-08 Duplicate-prevention check runs before posting. Tally's XML import does not prevent duplicate entries on its own. Zoho's write API enforces a case-insensitive, whitespace-trimmed uniqueness constraint on (vendor, `bill_number`) and rejects violations with code 13011 — but that constraint is narrower than this check's dedup key (vendor GSTIN + invoice number + date) in every dimension that matters: it is keyed on the contact record rather than the GSTIN, it ignores the date entirely, and it matches the invoice number literally rather than semantically (`INV-001` and `INV001` are two different bills to Zoho). The platform's own check (CG7) therefore remains necessary on both backends and must run first, normalising the invoice number before comparing; Zoho's guard is a backstop against exact repeats, not a dedup implementation. A bill that passes CG7 but is rejected by Zoho as a duplicate is a genuine conflict and becomes a Task. Per P0-06 finding #10

### 5.7 Reconciliation Agent (RC)

- RC-01 Pull purchase register (via the Books Connector — either adapter) and GSTR-2A/2B via a direct GSP (GST Suvidha Provider) API integration — this replaces the Winman-dependent path entirely. GSTN licenses GSPs to provide programmatic API access to the same underlying data Winman itself uses internally. Shortlist of GSTN-licensed GSPs with developer-facing APIs worth evaluating: WhiteBooks (has a free sandbox and a purpose-built GSTR-2B fetch/reconciliation API — good first candidate to prototype against), GSTHero, Adaequare, GSPIndia, MasterGST, Cygnet, IRIS GST.
- RC-01a Note on what doesn't go away: GSTN requires an OTP/consent step per client GSTIN as part of its own security model, regardless of which GSP is used. This becomes a scriptable, automated authentication step within the platform rather than a manual per-client action in Winman.
- RC-01b GSP API access has its own cost (typically per-call or subscription-tier pricing) — a new line item to include in the investment conversation, similar to the Zoho API tier cost note (§5.3.2, ADR 0011).
- RC-01c Strategic scope note: Winman covers three distinct compliance areas (GST, Income Tax/ITR, TDS), and they don't have equivalent replacement paths. GST filing and reconciliation have solid API-first alternatives — the same GSP relationship used for GSTR-2A/2B (RC-01) can likely also handle GSTR-1/3B filing itself. Income Tax (ITR) and TDS filing run through separate government systems (Income Tax Department e-filing infrastructure, TRACES) — replacing Winman there would need its own integration effort (e.g., ERI registration), not a simple vendor swap. Recommendation: scope this build to replacing Winman's GST role only, for now.
- RC-01d WhiteBooks technical spike details (verified, safe to act on): sandbox at apisandbox.whitebooks.in/gst (free, no card required), production at api.whitebooks.in/gst, OAuth 2.0 bearer auth, relevant endpoints for GSTR-1/GSTR-3B filing and GSTR-2B fetch, SDKs in Java/Node.js/Python, OpenAPI 3.0 spec available. Caveat: WhiteBooks' own pricing page shows internally inconsistent numbers — treat the sandbox/technical details as safe to prototype against immediately; do not use any pricing figures from their site in the investment conversation without a direct sales quote.
- RC-02 Match line items by GSTIN, invoice number, and amount
- RC-03 Auto-confirm matched items and include in the ITC claim summary
- RC-04 Mismatches (timing difference, vendor not filed, amount mismatch, duplicate) become a task with reason
- RC-05 Generate the final reconciliation statement for filing

### 5.8 Validation / Compliance Agent (VC)

Verified: Winman is a desktop application with no open third-party API. GSTR-2A/2B data now flows through a direct GSP integration instead (§5.7, RC-01), bypassing Winman entirely for that step. Winman remains relevant for filing itself: it supports Excel export, and import via JSON or Excel — but only per individual head of income, not as a holistic single import.

- VC-01 GSTR-1 output tax vs. GSTR-3B output tax cross-check
- VC-02 HSN code presence and correctness check
- VC-03 Tax rate applied vs. standard rate table
- VC-04 TDS in Form 26AS vs. books cross-check
- VC-05 Any discrepancy becomes a task with the specific line item and variance amount, ahead of the filing deadline
- VC-06 Per-client filing-readiness status (cleared / blocked)

### 5.9 Client Communication Agent (CC)

Addresses the #1 stated pain point — follow-up.

- CC-01 Template library for routine reminders (deadline approaching, document pending)
- CC-02 Routine reminders sent automatically on a configured schedule
- CC-03 Communication requiring judgment is drafted and routed as a task for approval before sending
- CC-04 All sent/received communication logged per client
- CC-05 Time-sensitive, client-dependent actions (e.g. OTP-based steps) flagged with higher priority

### 5.10 TDS/TCS Return Automation (TDS)

- TDS-01 Pull TDS deducted (books) and Form 26AS/TRACES data
- TDS-02 Match deductions against deposits and due dates
- TDS-03 Short deduction, late deposit, or mismatch becomes a task with the specific entry
- TDS-04 Prepare the draft quarterly return (24Q/26Q/27EQ) for review and filing

### 5.11 Bank Reconciliation Agent (BR)

- BR-01 Pull bank statement data and books bank book, across all client accounts
- BR-02 Auto-match entries by date, amount, and reference
- BR-03 Unmatched entries become a task for staff review
- BR-04 Generate a reconciliation statement per account, per period

### 5.12 Working Paper Agent (WP)

- WP-01 Auto-populate the standard working paper template from reconciliation and validation output
- WP-02 Generate a draft working paper per engagement
- WP-03 Task routed to the auditor to add professional judgment notes
- WP-04 Finalized working paper filed to the client's Dropbox record

### 5.13 Client Profiling & Billing (CB)

Confirmed: billing today is informal — based on individual job description and client, done ad hoc in Excel, with no existing tier or rate-card structure. This module is being designed from scratch, not digitizing an existing system. Invoices must be GST-compliant (GSTIN, HSN/SAC codes for professional services, CGST/SGST/IGST breakup).

- CB-01 Client master profile: entity type, services subscribed (GST / IT / Statutory Audit / ROC / Advisory), **books system** (`tally` \| `zoho_books` — per ADR 0011, drives which Books Connector adapter this client's downstream agents use), linked Tally company or Zoho organization, primary contact, billing cycle (monthly/quarterly)
- CB-02 Service catalog: each billable service type defined with standard price tiers — built from scratch, since no rate card exists today. Category structure drawn from the practice's own two websites: GST, Income Tax, Accounting Services, Statutory Audit, Entity Setup & Registration, Corporate/ROC Compliance, Corporate Finance & Advisory, Services for Non-Residents.
- CB-03 Per-client price override — a specific client's rate can be set to override the tier default, with the reason and who approved it recorded
- CB-04 Billing-trigger mapping: which completed agent/task event generates a billable line item
- CB-05 Auto-generate a draft invoice per client per billing cycle, built from services actually rendered and the applicable tier/override pricing
- CB-06 Draft invoice routed as a task for proprietor/senior staff review and approval before it's sent
- CB-07 Invoice history per client: sent, outstanding, paid status
- CB-08 Tier reassignment workflow for when a client's volume or complexity changes — flagged as a task rather than silently auto-changing a client's pricing
- CB-09 Invoice format is GST-compliant: GSTIN, HSN/SAC code for professional services, and CGST/SGST/IGST tax breakup on every generated invoice

### 5.14 Practice Management Dashboard (PM)

- PM-01 Cross-client, cross-staff task dashboard for the proprietor
- PM-02 Per-staff workload view: open, overdue, and completed tasks
- PM-03 Capacity indicator — surfaces available bandwidth for new client work
- PM-04 Deadline calendar across all clients and all compliance types (GST, IT, TDS, ROC)
- PM-05 Time-per-task tracking — extends the practice's existing task-sheet habit rather than replacing it outright
- PM-06 Outstanding/overdue invoice visibility, sourced from the Client Profiling & Billing module (§5.13)

## 6. Deferred to Later Phases (Out of Scope for This PRD)

Confirmed low-priority or explicitly deprioritized during discovery:

- Notice / Scrutiny Tracker Agent — notices are "negligible" per discovery; revisit if that changes
- AI-assisted audit tooling — explicitly flagged as not relevant at current client scale
- Client-facing portal — client acquisition is personal-connect only; no external-facing surface planned
- Financial Statement Analysis/Ratio Agent, ROC Tracker, Fixed Asset Register, Audit Sampling & Risk-Scoring, Knowledge Base/Query Assistant — all previously identified as potential value-adds, not core to the 500-returns goal

## 7. Key User Stories

- As a junior staff member, I want one queue of tasks assigned to me with due dates, so I know exactly what to work on without checking multiple channels.
- As the proprietor, I want to see which clients are at risk of missing a filing deadline, so I can step in before it becomes urgent.
- As a senior staff member, I want to review only the flagged reconciliation mismatches instead of the full ledger, so I save review time on every client.
- As a staff member, I want client documents to be filed to the right Dropbox folder automatically, so I stop spending time on manual email filing.
- As the proprietor, I want an overdue task to escalate to me automatically, so a missed internal deadline doesn't go unnoticed the way it can today.
- As the proprietor, I want invoices to be drafted automatically from services actually delivered, so billing doesn't depend on someone remembering to work it out manually each cycle.
- As a staff member, I want the platform to work the same way whether a client's books are in Tally or Zoho Books, so I don't need to think about which system I'm dealing with.

## 8. Open Questions (Before Architecture Decisions)

| # | Question | Answer | Status |
|---|---|---|---|
| 1 | Tally Cloud access method | Browser-based access, from anywhere, with username/password. Verified: TallyPrime's XML-over-HTTP interface (port 9000) and ODBC are both built-in, native capabilities — not separate licenses. | Resolved (technical approach confirmed), one item to reconfirm — re-ask the provider specifically: "can the HTTP server on port 9000 be reached from outside your hosted environment, or can a small service be deployed on the same host to reach it locally?" |
| 1a | Format for the small percentage of clients on their own Tally | Native Tally backup file, importable directly into Tally | Resolved |
| 2 | Does Winman have export/API capability? | Yes — exports to Excel; import via JSON or Excel, but only per individual head of income, not holistically | Resolved |
| 3 | How is GSTR-2A/2B data accessed? | Bypass Winman for this data pull; register the practice directly with a GSTN-licensed GSP for programmatic, multi-client API access | Resolved (new approach) |
| 4 | DPDP Act obligations for storing/processing client financial data | Tally, Zoho Books, and Dropbox are the systems of record and already carry the practice's existing data-handling posture; the platform doesn't introduce a new consolidated store | Largely resolved — narrowed to: what DPDP obligations apply specifically to the platform's own metadata layer and to transient OCR/LLM processing |
| 5 | Where does OCR/LLM processing run, and what data leaves the practice's environment? | Documents stay in Dropbox as the system of record. What's still open: which OCR/LLM vendor processes documents in transit, and whether that vendor retains any data even transiently | Partially resolved |
| 6 | What does client billing look like today? | Informal/ad hoc, per job and per client, currently done in Excel; invoices must be GST-compliant | Resolved — Billing module (§5.13) designed from scratch |
| 7 | What proportion of clients are on Zoho Books vs. Tally, and does the Zoho population need full read/write parity? | Confirmed ~20-40% of clients on Zoho Books, full read/write parity required (same as Tally) | **Resolved** — see ADR 0011, §5.3 |

## 9. Success Metrics (KPIs)

| Metric | Today | 6-Month Target |
|---|---|---|
| GST returns serviced/month | ~100 | ~500 |
| Reconciliation time per client | 1–2 hrs/month | <15 min (review only) |
| Tasks completed before due date | Not tracked | Target: >90% |
| Documents auto-filed without manual intervention | 0% (fully manual) | Majority, exceptions only |
| Vouchers/entries auto-staged with high confidence | 0% | Target set after Phase 0 baseline |
| Follow-up handled without manual chasing | 0% (fully manual, #1 pain point) | Majority automated, exceptions only |
| Invoices auto-drafted from rendered services | 0% (manual/ad hoc) | Majority auto-drafted, exceptions reviewed only |

These metrics apply uniformly across the client base regardless of which books system a client uses — a Zoho-backed client should hit the same targets as a Tally-backed one, not a reduced bar.

## 10. Next Steps

1. Resolve the open questions in §8 that block architecture decisions — Tally Cloud access method (item 1) and the DPDP metadata-layer question (item 4) are the most urgent.
2. Write the remaining Architecture Decision Records covering: task engine data model, offline/PWA sync strategy, and OCR/document-processing approach (see ADRs 0001–0011 for what's already decided).
3. Confirm the Feature Backlog v0.2's phase mapping against the Sprint Plan v0.2.
4. Confirm the ER diagram v0.2's `BOOKS_CONNECTION` generalization against the actual Zoho Books API response shapes once the Phase 0 spike (P0-06) reports back.
5. Work through the Dev Readiness Checklist's **items** before Sprint 1 begins — principally the Phase 0 Spikes (`P0-*`) and Environment & Tooling (`ENV-*`) sections. The checklist document itself is authored and complete (§3); this item is open *work*, not open *documentation*.
