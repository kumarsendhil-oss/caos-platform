# Architecture Decision Records — Index

All ADRs for the CAOS platform, in one place. ADRs 0001–0010 were extracted
from the original consolidated *Internal Development Readiness Package* PDF
(kept in this folder as `CAOS_Internal_Development_Readiness_v0_1_1.pdf`);
0011 onward were written directly as standalone files.

| ADR | Title | Status | File |
|---|---|---|---|
| 0001 | Tally Integration via XML-over-HTTP | Accepted, amended by 0011 | `audit-platform-ADR-0001-tally-integration-xml-over-http.md` |
| 0002 | GST Data Access via Direct GSP Integration (Bypassing Winman) | Accepted | `audit-platform-ADR-0002-gst-data-access-via-gsp.md` |
| 0003 | Document Intake via Dropbox Webhooks with Async Processing | Accepted | `audit-platform-ADR-0003-document-intake-dropbox-webhooks.md` |
| 0004 | Platform as a Thin Layer Over Tally and Dropbox | Accepted | `audit-platform-ADR-0004-platform-as-thin-layer.md` |
| 0005 | Task Engine as the Shared Backbone | Accepted | `audit-platform-ADR-0005-task-engine-shared-backbone.md` |
| 0006 | App Form Factor: Desktop-First PWA | Accepted | `audit-platform-ADR-0006-app-form-factor-desktop-first-pwa.md` |
| 0007 | Technology Stack | Accepted (revised) | `audit-platform-ADR-0007-technology-stack.md` |
| 0008 | Self-Hosted OCR Engine: PaddleOCR (PP-StructureV3) | Accepted | `audit-platform-ADR-0008-self-hosted-ocr-paddleocr.md` |
| 0009 | Deployment Model: Single-Tenant, Per-Customer Instances | Accepted | `audit-platform-ADR-0009-deployment-model-single-tenant.md` |
| 0010 | Base Product with Per-Practice Customization and Upstream Promotion | Accepted | `audit-platform-ADR-0010-base-product-per-practice-customization.md` |
| 0011 | Multi-Backend Bookkeeping Connector (Tally + Zoho Books) | Accepted | `audit-platform-ADR-0011-addendum.md` |
| 0011-A1 | Amendment 1: Tax Modelling in `DraftEntry` | Accepted | `audit-platform-ADR-0011-amendment-1-tax-modelling.md` |
| 0011-A2 | Amendment 2: Canonical State Representation and Shared Tax-Jurisdiction Determination | Accepted | `audit-platform-ADR-0011-amendment-2-state-representation.md` |
| 0012 | Cost-Optimized Agent LLM Usage | Accepted (pending re-metering) | `audit-platform-ADR-0012-cost-optimization.md` |
| 0013 | HRMS Integration for Internal Staff Management (Frappe HR) | Superseded by 0016 | `audit-platform-ADR-0013-hrms-integration.md` |
| 0014 | Infrastructure-as-Code Scope: Terraform Without Fargate | Accepted | `audit-platform-ADR-0014-iac-scope-terraform-without-fargate.md` |
| 0015 | Engagement and Task Model Redesign | Accepted | `audit-platform-ADR-0015-engagement-and-task-model.md` |
| 0016 | Attendance, Payroll and Performance: Native Capture with RazorpayX Payroll | Accepted | `audit-platform-ADR-0016-attendance-and-payroll-integration.md` |
| — | Open items carried from ADRs 0001–0010 | — | `audit-platform-ADR-0001-0010-open-items.md` |

## Notes

- **0007 was Accepted on 2026-09-17.** The open question was never the analysis but whether the team building this is comfortable in Python rather than Node; confirmed, and the codebase (`services/api/app/` — FastAPI, async SQLAlchemy, Alembic) had already implemented the choice. Its Dev Readiness Checklist item is closed.
- **0014 unbundles ADR 0007's "Fargate/Terraform-level complexity" phrase.** That parenthetical read as a rejection of Terraform itself, which contradicted 0009's "adopt IaC from the first deployment" consequence and left the IaC tooling choice open on the Phase 0 list. 0014 reaffirms the **Fargate** rejection unchanged and adopts **Terraform** at the scope 0007 already specified. Nothing 0007 decided is overturned.
- **0003 is Accepted but doc-verified only; live verification is pending via P0-07.** Its webhook design was checked against Dropbox's documentation and never against a real app. The flag is on the ADR itself. Same annotation pattern as the open-question note carried on **0002** pending #51's resolution — a flag on an Accepted decision, not a status change. Three specifics are unobserved: the cursor pattern, the 10-second window, and "App folder" scope behaviour.
- **0001 is amended by 0011.** Its technical content stands, but it now describes the *Tally adapter* specifically rather than the whole bookkeeping integration.
- **0011 Amendment 1 changes `DraftEntry`'s shape.** It must land before either adapter's `post_entry` is implemented (issues #2 and #5) — free now, a migration later.
- **0011 Amendment 2 settles how state is represented, and corrects one consequence of Amendment 1.** The two-digit statutory numeric code (`33`) is canonical; each adapter translates at its own edge; and the intra- vs inter-state determination moves *out* of the adapters into one shared function above them. Amendment 1's core decision stands — only its "`TallyAdapter` decides intra/inter" addition is superseded, because P0-06 finding #9 showed Zoho validates that choice rather than making it. Resolves issue #50. Same timing argument as A1: free now, expensive after either adapter is written.
- **0015 is the first ADR whose provenance is customer feedback rather than a spike finding, discovery work, or a contradiction between existing ADRs.** Its own Context says so explicitly and asks future sessions to weigh it accordingly — it rests on a reading of what the practice said it wants, which is more revisable than a reproducible sandbox observation. Two parts of it are worth knowing about from here:
  - **It carves out an exception to 0005**, which is *Accepted*. A "buzz" (asking a colleague for status) becomes a `TASK_NUDGE` row plus a `status_requested_at` flag on `TASK` that surfaces in the task queue — **not** a Task. The carve-out is argued against 0005's Context ("not a generic notification or flag") and its Alternatives rationale ("fragment task visibility"), not against the Decision clause's narrower agent-raised scope. It carries a stated falsification condition: **if a buzz turns out to need its own due date and escalation path, it is a Task and the carve-out is wrong.** Revisit on evidence — repeat nudges per task, or anyone asking for a report of unanswered buzzes — rather than re-arguing it from first principles.
  - **It narrowly reverses a PRD §6 deferral.** §6 deferred a Knowledge Base/Query Assistant; 0015 argues a versioned Dropbox pointer per service (`SERVICE_RESOURCE`, `storage_ref` only, never file content, per 0004) is a materially smaller thing. **§6's deferral of the Query Assistant itself stands unchanged.**
- **0015 supplies the data ADR 0013 presupposes — and concludes 0013 must be superseded.** 0013 commits to computing per-employee billable utilization "from task-engine data it already owns"; no time data exists today. 0015 adds `TIME_ENTRY`, `TASK.work_class` and `TASK.engagement_id`, which is what that commitment needs. But its Decision 7 goes further: the customer has **dropped Frappe HR**, attendance is captured natively in CAOS and exported to **RazorpayX Payroll**, and performance measurement is **quantitative only** — so 0013's integration target inverts and one of its three pillars (the Goal/KRA push) is deleted rather than changed. 0015's assessment is therefore that **0013 must be SUPERSEDED by a new ADR rather than amended**. **0016 is that supersession.**
- **0016 declares `P0-08` and has not run it.** Every RazorpayX capability in 0016 — PF, ESI, PT, LWF, salary TDS, Form 24Q, Form 16, shift rules, auto-attendance, payroll linkage — is marked **unverified**, and its T1–T9 list is questions the spike must answer, not findings. **Read nothing in 0016 as a vendor capability claim.** Two things hang off it: **leave placement** (T2 — the holiday calendar is decided as CAOS's, leave is not), and the **TDS agent's scope** (T4 — 0013 narrowed it to 26Q/27EQ because Frappe filed 24Q; if RazorpayX does not, that narrowing reverses). `P0-08` is **not yet on the sprint plan's Phase 0 list**, which still ends at P0-07.
- **0016 corrects a stack error in 0013 rather than carrying it.** 0013 refers twice to a "Supabase/Postgres/Railway" stack, contradicting 0007's revision **away from Railway** to **AWS ap-south-1 (Mumbai)**, 0009's per-deployment AWS Mumbai, and 0014's Terraform. 0016 states the correct stack and says so explicitly. **0013's own file is left as written** — a superseded document is not edited.
- **0015 makes no sprint decisions.** It flags that Sprint 10's catalog work grows under its Decision 2 and that PM-05's Sprint 11 placement is questionable, and explicitly defers both as a separate decision — tracked as `PENDING:027` in `STUB_ISSUES.md`, along with `PENDING:024`–`026` (invoice due-date/overdue states, annual billing frequency, `BILLABLE_EVENT` WIP status).
- The **open-items file** lists what was undecided when the original set was written. Check each against 0011/0012 and the Dev Readiness Checklist before assuming it's still open.

## Gaps worth knowing about

~~There is a reference elsewhere to an **ADR 0013** that is not in this folder.~~ **Resolved 2026-09-17: it was in the folder all along.** `audit-platform-ADR-0013-hrms-integration.md` exists and is complete — it was simply never added to the table above, and this note went stale rather than the ADR going missing. It is now indexed, at the status its own file states (*Proposed*), which nothing here changes. The highest-numbered ADR on record is **0016**.
