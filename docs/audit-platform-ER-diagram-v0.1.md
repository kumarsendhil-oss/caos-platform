# ER Diagram — Practice Automation Platform
### Prepared for Venture Assist / Srivatsan & Associates | Draft v0.1 (reconstructed)

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial entity model, split into two diagrams (core platform, compliance & billing) per the PRD's 14 modules. |
| v0.1 (reconstructed) | 2026-08-22 | Recreated from the CAOS Internal Development Readiness Package narrative, since the original `.mermaid` source files were not recovered. One entity — `AUDIT_EVENT` — added to Diagram 1 to account for ID-05's audit-log requirement and the Security Standard's `AuditTrailService`, bringing the total to 23 entities as originally documented. |
| v0.2 | 2026-08-22 | Per ADR 0011 (multi-backend bookkeeping connector): `TALLY_COMPANY` generalized to `BOOKS_CONNECTION` with a `books_system` field (`tally` \| `zoho_books`), and `VOUCHER` updated to reference it via `books_connection_id` with a `posting_system` field. Reflects ~20-40% of clients maintaining books in Zoho Books rather than Tally, with full read/write parity required. |

**Sources:** `audit-platform-ER-core.mermaid`, `audit-platform-ER-compliance-billing.mermaid`

## Why two diagrams, not one

23 entities is more than fits legibly in a single diagram. Split by the same logical boundary the PRD already uses: the **core platform** (identity, tasks, documents, bookkeeping) that most agents write to, and **compliance & billing** (reconciliation, validation, TDS, bank, working papers, notices, communication, billing) that mostly reads from the core and writes its own domain-specific records. `CLIENT` is the shared anchor entity across both.

This mirrors the PRD's own module grouping (§5) and keeps each diagram traceable back to a specific set of requirement IDs.

## Diagram 1 — Core Platform

**Source:** `audit-platform-ER-core.mermaid`
**Covers:** Identity & Access (ID), Task Engine (TE), Tally Connector (TC), Email Intake (EI), Document Intake (DI), Bookkeeping/Voucher Entry (BK)

| Entity | Purpose | Key PRD traceability |
|---|---|---|
| CLIENT | Master client record — anchor entity for the whole system | ID, CB |
| USER | Staff member (Proprietor / Senior / Junior) | ID-01 |
| TASK | Every human-touch item any agent raises, per ADR 0005 | TE-01 to TE-09 |
| DOCUMENT | A file received via email/Dropbox, before extraction | EI, DI-01 to DI-04 |
| EXTRACTED_DATA | OCR/parsing output from a document (PaddleOCR per ADR 0008) | DI-02, DI-03 |
| BOOKS_CONNECTION | A client's connection to their bookkeeping system — either a Tally company within the practice's Tally Cloud (or the secondary backup-import path), or an OAuth-connected Zoho Books organization, per ADR 0011 | TC-01 to TC-08, ADR 0011 |
| VOUCHER | A draft or posted Tally voucher, with confidence score | BK-01 to BK-08 |
| VENDOR_MAPPING | Learned vendor-name-to-ledger matches, used by the fuzzy-matching engine | BK-02 |
| EMAIL_SENDER_MAP | Learned sender-address-to-client mapping | EI-02, EI-06 |
| AUDIT_EVENT | Immutable, append-only record of approvals, overrides, and reassignments — written by `AuditTrailService`, never the logger | ID-05, Security Standard §5 |

**Notable relationships:**
- `DOCUMENT → EXTRACTED_DATA` is 1:1 — each document produces one extraction result (which may be low-confidence and routed to a task).
- `EXTRACTED_DATA → VOUCHER` is 1:many — a single document (e.g. a multi-line invoice) can generate multiple draft vouchers.
- `TASK.assignee_id` references `USER`, but `TASK` itself is not tied to a single entity type — it links to whichever record raised it (document, voucher, reconciliation item, etc.) via a generic polymorphic reference, kept out of this diagram for clarity, since the whole point of the Task Engine (ADR 0005) is that any module can raise one.
- `AUDIT_EVENT.actor_id` references `USER`; `AUDIT_EVENT.subject_id` is a polymorphic reference to whatever record was acted on, mirroring `TASK`'s pattern.

## Diagram 2 — Compliance & Billing

**Source:** `audit-platform-ER-compliance-billing.mermaid`
**Covers:** Reconciliation (RC), Validation/Compliance (VC), TDS/TCS (TDS), Bank Reconciliation (BR), Working Paper (WP), Notice/Scrutiny Tracker (NT, future), Client Communication (CC), Client Profiling & Billing (CB)

| Entity | Purpose | Key PRD traceability |
|---|---|---|
| CLIENT | Shared anchor with Diagram 1 | — |
| RECONCILIATION | A GSTR-2A/2B match result for a client/period | RC-01 to RC-05 |
| VALIDATION_CHECK | A pre-filing check result (GSTR-1 vs 3B, HSN, TDS) | VC-01 to VC-06 |
| TDS_RECORD | A TDS deduction/deposit match for a client/period | TDS-01 to TDS-04 |
| BANK_ACCOUNT / BANK_TXN | A client's bank account and its transactions | BR-01 to BR-04 |
| WORKING_PAPER | An engagement's working paper, draft or finalized | WP-01 to WP-04 |
| NOTICE | A GST/IT notice — future scope, deprioritized per discovery | NT-01 to NT-04 |
| COMMUNICATION | A logged client communication (reminder, query) | CC-01 to CC-05 |
| SERVICE_CATALOG | The practice's service/price-tier definitions | CB-02 |
| SERVICE_OVERRIDE | A client-specific price override against the catalog | CB-03 |
| INVOICE | A billing-cycle invoice, GST-compliant | CB-05, CB-09 |
| BILLABLE_EVENT | A single billable line item, generated from a task/agent event | CB-04 |
| GSP_CREDENTIAL | Per-client GSTIN authorization with the chosen GSP (WhiteBooks or similar) | RC-01, ADR 0002 |

**Notable relationships:**
- `INVOICE → BILLABLE_EVENT` is 1:many, and each `BILLABLE_EVENT` optionally links back to the `TASK` that generated it (via `task_id`) — this is what makes CB-04 (billing-trigger mapping) traceable, rather than a black box.
- `SERVICE_OVERRIDE` sits between `CLIENT` and `SERVICE_CATALOG` as a many-to-one bridge — a client can have multiple overrides (one per service type), each referencing the standard catalog item it overrides.
- `GSP_CREDENTIAL` is 1:1 with `CLIENT` in this diagram, reflecting that GSTN's OTP/consent step (ADR 0002) is per-GSTIN, not shared across clients.

## What's deliberately not modeled yet

- Full column-level schema (types, constraints, indexes) — this is an entity-relationship model for architecture review, not a migration script. That level of detail belongs in the actual SQLAlchemy schema once development starts.
- The generic `TASK → source-record` link (and `AUDIT_EVENT → subject`) is left as a conceptual polymorphic reference rather than drawn out, since forcing it into a rigid ER relationship would either require a separate join table per source-entity type (cluttering both diagrams) or misrepresent the Task Engine's actual flexibility.
- `NOTICE` is included for schema completeness even though it's explicitly future/deprioritized scope, so the model doesn't need revisiting if the practice's notice volume changes later.
