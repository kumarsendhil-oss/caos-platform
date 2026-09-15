# ADR 0012 — Cost-Optimized Agent LLM Usage

**Status:** Accepted (pending Phase 0/1 re-metering — see Consequences)

## Context

The recurring operating cost model (built separately, in the pricing/proposal work) priced AI/LLM agent reasoning at roughly ₹28,500–47,500/month at target scale (~500 clients), modeled across nine agent types: Document Intake, Bookkeeping, Reconciliation, Validation, TDS/TCS, Client Communication, Bank Reconciliation, Working Papers, and Practice Management. That model assumed, implicitly, that every agent action on every document for every client every month triggers an LLM call — which makes the cost scale linearly with document volume, and therefore with client count.

Reviewing the actual module descriptions against that assumption surfaces a mismatch: several of the nine agents perform deterministic matching, comparison, or lookup operations that don't require LLM reasoning at all — and were already specified elsewhere in this documentation set to use non-LLM tooling. Meanwhile, the agents that do genuinely need an LLM (primarily Bookkeeping's unstructured document extraction) were not designed to reuse anything learned about a client from one month to the next, so the same reasoning gets re-derived from scratch every period.

Neither of these is a new architectural decision so much as a gap between what was already decided (ADR 0007's tech stack, ADR 0008's `invoice2data` fast-path) and what the cost model assumed. This ADR makes the distinction explicit and formalizes the caching/reuse pattern that closes the gap.

## Decision

### 1. Agents are classified by whether they need an LLM call at all

| Agent | Core operation | LLM required? |
|---|---|---|
| Reconciliation (RC-02) | Match GSTIN + invoice number + amount across two structured datasets | **No** — deterministic/fuzzy string matching (`rapidfuzz`, already the ADR 0007 tech stack choice) |
| Validation (VC-01–VC-04) | Compare GSTR-1 vs GSTR-3B totals, check HSN presence, look up the standard tax rate table, check TDS vs 26AS | **No** — arithmetic comparison and table lookup |
| TDS/TCS matching (TDS-02) | Match deductions against deposits and due dates | **No** — same matching logic as RC-02 |
| Bank Reconciliation (BR-02) | Match entries by date, amount, reference | **No** — deterministic matching |
| Document Intake classification (DI, EI-02/EI-06) | Classify document type; route by sender | **Only on first encounter** — a learned sender-to-client mapping table handles every repeat sender via lookup, not a fresh classification call |
| Bookkeeping extraction (BK-01, BK-02, BK-04) | Extract line items from an unstructured invoice; match vendor to ledger | **Yes, on first encounter per vendor layout** — this is the genuine unstructured-extraction problem; see the caching pattern below for repeat encounters |
| Client Communication (CC-01–CC-03) | Draft a reminder or a judgment-requiring message | **Only for judgment-requiring content** — routine reminders are template fills (CC-02), never an LLM call; only content requiring interpretation or tone (CC-03) reaches the LLM |
| Working Papers (WP-01, WP-02) | Assemble the factual backbone from Reconciliation/Validation output | **No** — template population from already-structured data |

Core modules (`app/agents/`, per the existing Coding Guidelines CG11 boundary) must not default to an LLM call as the implementation of a matching, comparison, or lookup operation. An LLM call is justified only where the input is genuinely unstructured (a scanned invoice, free-text client correspondence) or the output requires judgment a lookup table can't encode (drafting tone, escalation wording).

### 2. Vendor template caching for Bookkeeping (formalizes ADR 0008's `invoice2data` fast-path)

The first invoice from a given vendor, in a given layout, gets a full LLM extraction pass. Once that extraction is human-approved (per BK-06), the field-position template is cached, keyed by `(client_id, vendor_id, layout_fingerprint)`. Every subsequent invoice matching that fingerprint is extracted via the cached template — a deterministic field read, not an LLM call — and only escalates back to the LLM if the layout changes or the template match's own confidence score drops below threshold (reusing the existing BK-05 confidence-scoring mechanism, not a new one).

This means Bookkeeping's LLM volume is driven by *new vendors and layout changes*, not by total invoice count. For a client base where most vendors repeat monthly — the normal case — LLM volume per client should fall substantially after the first one to two months, independent of how many documents that client generates thereafter.

### 3. Prompt caching for LLM calls that remain

Where an LLM call is genuinely needed, the static context accompanying it — a client's chart of accounts, vendor mapping table, the standard GST rate table — is identical across every call for that client within a period. This context is sent using Anthropic's prompt caching, so it is billed in full once and at a fraction of the cost on every subsequent call that reuses it within the cache TTL. This requires no change to agent logic, only to how the API call is constructed.

### 4. Model routing stays as originally specified, with a tighter escalation boundary

Haiku remains the default model for classification and extraction; Sonnet is reserved for genuinely ambiguous cases — specifically, only extractions that fall below BK-05's confidence threshold, or communications that CC-03 already flags as requiring judgment. This was implied by the original cost model's Haiku/Sonnet split but is stated here as a hard rule: a call does not escalate to Sonnet by default, only on an explicit confidence or judgment flag.

## Consequences

- **The recurring cost model needs re-running**, not just re-labeled. Removing four of nine agents from the LLM line entirely, and modeling Bookkeeping's LLM volume as new-vendor-driven rather than document-count-driven, changes the shape of the cost curve, not just its magnitude — it should be re-flattened against client count rather than assumed linear. This ADR does not replace that cost model; it supplies the assumptions the next revision of it should use.
- **A template cache layer is new engineering scope**, not covered in the original Sprint Plan. It belongs in the Bookkeeping Agent's build (Sprint 4-5), alongside BK-05's confidence scoring, since the two mechanisms share the same escalation path. Flag this as added scope when the Sprint Plan is next revised.
- **Layout-fingerprinting needs a concrete definition** — what constitutes "the same layout" for a given vendor (field positions? a hash of the document structure? something coarser?) is an open design question, not yet specified. This should be resolved during the Bookkeeping Agent's build, not assumed here.
- **Prompt caching has a TTL and a minimum-reuse threshold** to actually save money — caching context that's reused only once doesn't pay for the cache write. This needs validating against real call patterns once agents are live, not assumed to be a free win in every case.
- **The four "no LLM needed" agents still need a fallback path.** Deterministic matching will have its own miss rate (a genuine edge case a rule doesn't cover); this ADR doesn't argue for zero LLM involvement ever in those agents, only that the default path is deterministic and an LLM (or a human task, per the existing Task Engine pattern) is the exception path, not the default.
- **This should be verified, not assumed, in Phase 0/1.** The pricing conversation already flagged actual LLM call volume as "the single biggest lever in either direction" on the cost model. This ADR changes what should be metered — not just total calls, but the split between deterministic-eligible and genuinely-LLM-requiring calls, and the vendor-repeat rate that determines how fast Bookkeeping's cache hit rate climbs.

## Alternatives considered

- **Leave all nine agents on a uniform LLM-call-per-action model, and rely on lower per-token pricing over time to control cost.** Rejected — this bets on external price trends rather than an architectural choice available now, and doesn't address that four of the nine agents are solving problems (structured matching, table lookups) that a lookup or a matching library solves more reliably than an LLM call, independent of cost.
- **Fine-tune a smaller model on this practice's own vendor/document data instead of template caching.** Rejected for now — meaningfully more upfront engineering and data-collection effort than a template cache, and per ADR 0009's single-tenant model, a fine-tuned model would need re-deriving per practice deployment rather than reusing the same base logic. Worth reconsidering only if template caching's hit rate proves insufficient once real usage data exists.
- **Cache LLM outputs directly (memoize the full extraction result) rather than caching the template/context.** Rejected as the primary mechanism — a full-output cache only helps on an exact repeat of the same document, which doesn't happen; caching the *template* (which fields sit where, how tax splits are structured) is what actually recurs month to month, since the invoice's amounts and dates change even when its layout doesn't.
