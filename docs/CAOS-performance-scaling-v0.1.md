# Performance & Scaling — Practice Automation Platform
### v0.1

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial targets: current-scale assumptions, API/OCR/queue performance targets, database indexing for reconciliation matching, and concrete scaling triggers — all scoped per-deployment, per ADR 0009's single-tenant model. |
| v0.1 (extracted) | 2026-08-22 | Extracted from the consolidated internal PDF into its own standalone file. No content changes — ADR 0011 (multi-backend bookkeeping connector) doesn't alter these targets: both the Tally and Zoho adapters are I/O-bound external calls handled through the same async/queue architecture (ADR 0003, ADR 0007), so no new performance target category was needed. Worth noting for future revisions: §5's indexing guidance is written against Tally's purchase-register/voucher table shape specifically and should be revisited once real Zoho-adapter query patterns exist post-Sprint 5. |

## 1. Scale assumptions (per deployment)

Per ADR 0009, every deployment is single-tenant — these targets are per practice, not aggregated across future customers. A second practice's deployment gets its own instance and its own performance profile, not a shared pool that needs to account for combined load.

For this first deployment specifically:
- ~100 clients today, target ~500 within 6 months (per the proposal's central goal)
- ~10 concurrent staff users at peak
- Document volume: moderate — a few thousand documents/month at 500-client scale, not industrial batch volume

These numbers matter because they justify not over-engineering for scale that doesn't exist yet — CPU-only OCR (ADR 0008) and a lightweight hosting footprint (ADR 0007/0009) are correct choices at this scale, not premature economizing.

## 2. API response time targets

| Endpoint class | Target (P95) | Rationale |
|---|---|---|
| Dashboard/task-list reads | < 500ms | Staff check this frequently through the day; sluggish reads erode trust in the tool |
| Voucher/reconciliation review actions (approve, reject) | < 1s | Needs to feel responsive during active review sessions |
| Document upload → OCR trigger acknowledgment | < 2s (the OCR itself runs async, per ADR 0003's queue pattern) | The user-facing action is "acknowledged," not "OCR complete" |
| Report/working paper generation | < 5s | Less frequent, less latency-sensitive action |

These are targets for a lightly-loaded single-deployment instance, not aspirational figures for a system under heavy concurrent load that doesn't exist at this scale.

## 3. OCR throughput

Per ADR 0008: PaddleOCR runs CPU-first, since processing is async (queue-based, per ADR 0003) with no real-time latency requirement.

- **Target:** process a typical invoice document within 30 seconds of being picked up from the queue, on CPU.
- **Scaling trigger:** if the document processing queue's backlog regularly exceeds a few hundred pending items (i.e., processing can't keep pace with intake even during normal hours, not just a temporary morning spike), that's the signal to provision GPU — not before. Don't provision GPU based on projected volume; provision it based on observed queue backlog.

## 4. Background job / queue sizing

Celery + Redis (per ADR 0007) handles: Dropbox webhook processing, OCR jobs, GSP API calls, email intake processing, and — per ADR 0011 — Zoho Books API calls (extraction and posting), which follow the same async pattern as Tally's XML-over-HTTP calls rather than a separate queue.

- Start with a small worker pool (2-4 workers) sized for the current document volume — this is not a number to over-provision for hypothetical future load, per the same reasoning as §3.
- Queue depth is a monitored signal (ties to the still-open observability tooling decision) — sustained queue growth over time, not point-in-time spikes, is what triggers adding worker capacity.

## 5. Database performance — reconciliation matching is the hot path

The Reconciliation Agent's core operation (RC-02: match purchase register line items against GSTR-2A/2B by GSTIN + invoice number + amount) is the platform's most query-intensive operation at scale, since it runs across potentially thousands of line items per client per period, regardless of which books-system adapter supplied the purchase register.

- Index `(client_id, vendor_gstin, invoice_number)` on the purchase register / voucher table — this is the primary lookup path for matching and for the duplicate-prevention check (CG7).
- Avoid N+1 query patterns in the matching logic — batch-fetch GSTR-2B line items for a period once, match in memory or via a single set-based query, not one query per purchase register line.
- Revisit indexing once real volume from Phase 0/1 usage is available — designing the "correct" index set against assumed access patterns before real query logs exist is guesswork; this is a starting point, not a final answer. **Also revisit once real Zoho-adapter query patterns exist post-Sprint 5** — the index above was designed against Tally's data shape specifically; confirm it still holds once entries sourced from Zoho Books are flowing through the same table at volume.

## 6. PWA load performance

Per ADR 0006 (desktop-first PWA):

- **Initial load target:** interactive within 2-3 seconds on a typical office broadband connection — this is a desk-based tool, not a mobile app optimized for constrained networks, so the bar is "doesn't feel slow," not "works on 2G."
- No specific bundle-size budget is set yet — revisit once the frontend build exists and a real baseline can be measured, rather than guessing a number now.

## 7. Scaling triggers — a summary table

| Signal | Action |
|---|---|
| OCR queue backlog sustained > few hundred items | Provision GPU for PaddleOCR |
| Celery queue depth trending up over days, not just spiking | Add worker capacity |
| API P95 response time exceeding targets in §2 under normal (not peak) load | Investigate query performance before scaling hardware |
| A second practice signs on | New deployment (per ADR 0009) — not a capacity question for this instance at all |

## 8. What this doesn't cover

Formal load testing tooling and process aren't specified yet — this document sets targets; the Dev Readiness Checklist includes setting up actual load-testing tooling as a task (item RB-03), once there's a working system to test against rather than a specification to guess load-test scenarios for.
