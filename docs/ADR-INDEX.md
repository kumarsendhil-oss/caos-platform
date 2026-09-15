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
| 0007 | Technology Stack | **Proposed** (revised) | `audit-platform-ADR-0007-technology-stack.md` |
| 0008 | Self-Hosted OCR Engine: PaddleOCR (PP-StructureV3) | Accepted | `audit-platform-ADR-0008-self-hosted-ocr-paddleocr.md` |
| 0009 | Deployment Model: Single-Tenant, Per-Customer Instances | Accepted | `audit-platform-ADR-0009-deployment-model-single-tenant.md` |
| 0010 | Base Product with Per-Practice Customization and Upstream Promotion | Accepted | `audit-platform-ADR-0010-base-product-per-practice-customization.md` |
| 0011 | Multi-Backend Bookkeeping Connector (Tally + Zoho Books) | Accepted | `audit-platform-ADR-0011-addendum.md` |
| 0011-A1 | Amendment 1: Tax Modelling in `DraftEntry` | Accepted | `audit-platform-ADR-0011-amendment-1-tax-modelling.md` |
| 0012 | Cost-Optimized Agent LLM Usage | Accepted (pending re-metering) | `audit-platform-ADR-0012-cost-optimization.md` |
| — | Open items carried from ADRs 0001–0010 | — | `audit-platform-ADR-0001-0010-open-items.md` |

## Notes

- **0007 is still Proposed**, not Accepted. It needs confirmation from whoever actually builds the platform, since team familiarity with Python vs. Node weighs as heavily as the analysis in it. Tracked as an item on the Dev Readiness Checklist.
- **0001 is amended by 0011.** Its technical content stands, but it now describes the *Tally adapter* specifically rather than the whole bookkeeping integration.
- **0011 Amendment 1 changes `DraftEntry`'s shape.** It must land before either adapter's `post_entry` is implemented (issues #2 and #5) — free now, a migration later.
- The **open-items file** lists what was undecided when the original set was written. Check each against 0011/0012 and the Dev Readiness Checklist before assuming it's still open.

## Gaps worth knowing about

There is a reference elsewhere to an **ADR 0013** that is not in this folder and was not part of the original PDF. If it exists, it should be added here and this index updated. Until then, 0012 is the highest-numbered ADR on record.
