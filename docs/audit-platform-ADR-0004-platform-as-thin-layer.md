# ADR 0004 — Platform as a Thin Layer Over Tally and Dropbox

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

DPDP Act obligations and data-residency questions were raised as open items. Tally and Dropbox are already the practice’s systems of record and already carry whatever data- handling posture the practice and its clients have accepted.

## Decision

The platform does not introduce a new consolidated store of full financial records or documents. Tally (via the Connector) and Dropbox remain the systems of record. The platform’s own database holds only derived/operational data: task metadata, client profile and billing data, communication logs, and reconciliation/validation results. Source documents and ledger data are read on demand and written back, not duplicated into a separate permanent store.

## Consequences

- Narrows the DPDP Act surface considerably — most obligations are already covered by the practice’s existing use of Tally and Dropbox; what’s new is the platform’s own metadata layer plus transient OCR/LLM processing.

- Still requires a decision on which OCR/LLM vendor processes documents in transit, and whether that vendor retains anything even temporarily — this is a smaller, specific decision rather than a broad open question.
- Any future feature that seems to want a “local copy” of source documents or full ledgers should be treated as a deviation from this ADR and revisited explicitly, not built by default.

## Alternatives considered

- Full data warehouse mirroring Tally + Dropbox into the platform’s own store — rejected; unnecessary duplication, expands the DPDP surface significantly, and adds sync-consistency risk for no clear benefit given Tally/Dropbox already serve as reliable sources of truth.
