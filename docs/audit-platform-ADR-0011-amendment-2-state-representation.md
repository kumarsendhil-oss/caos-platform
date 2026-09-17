# ADR 0011 — Amendment 2: Canonical State Representation and Shared Tax-Jurisdiction Determination

**Status:** Accepted
**Amends:** ADR 0011 (Multi-Backend Bookkeeping Connector), and corrects part of ADR 0011 Amendment 1
**Date:** 2026-09-17
**Raised by:** the P0-06 Zoho spike, live — findings #8 and #9 (`spikes/p0-06-zoho/FINDINGS.md`)
**Resolves:** issue #50 (`PENDING:018` — three unreconciled state representations)
**Blocks:** issues #2 (`TallyAdapter.post_entry`) and #5 (`ZohoAdapter.post_entry`)

> This is the revisit Amendment 1 asked for. Its **Open** section said: *"Not validated against either API. Both spikes remain unrun; this decision is reasoned from the two APIs' documented models. If Test 5 in the P0-06 runbook reveals Zoho behaves differently than documented, revisit."* The spike ran, and Zoho does behave differently. Amendment 1's core decision — `DraftEntry` carries determinants, not computed amounts — **stands unchanged**. One of its consequences does not.

## Context

### Problem 1 — three incompatible state representations, no canonical mapping

Three spellings of "which state" are in play across the platform, and nothing converts between any pair of them or declares which is authoritative:

| Representation | Example | Where it appears |
|---|---|---|
| **Two-digit statutory numeric** | `33` | The GST state code assigned by the GST registry. Already present in the codebase *implicitly*, as `vendor_gstin[:2]` — a field both `DraftEntry` and `VOUCHER` carry |
| Two-letter alpha | `TN` | What `DraftEntry` currently documents, and what Zoho echoes on the wire as `source_of_supply` / `destination_of_supply` (confirmed live, P0-06 finding #8) |
| Full state name | `Tamil Nadu` | Tally's `STATENAME` — a name, not a code, and it carries sentinel values such as `<EOT> Any` (seen live, P0-02 findings #18/#20). GST rates are scoped by it, so `TallyAdapter` must produce it exactly |

### Problem 2 — the same mismatch fails differently on each backend, and only one is loud

This is what makes the mismatch dangerous rather than merely untidy. Per P0-06 finding #9:

- **On Zoho it is loud.** Zoho *validates* the CGST/SGST-vs-IGST choice against the two supply states rather than deriving it, rejecting a wrong-direction tax **symmetrically** with error code **3032** — `TN→KA` with a CGST/SGST group ("IGST has to be applied as this is an interstate transaction") and `TN→TN` with `IGST18` ("IGST cannot be applied as this is an intrastate transaction"). The result is a **failed posting**.
- **On Tally it is silent.** Intra- vs inter-state is decided by comparing the two values. A comparison across two *different representations* does not raise — `"TN" != "Tamil Nadu"` is simply unequal, so it picks IGST where CGST/SGST was correct and posts a **wrong-but-plausible** split, which per P0-02 finding #2 the backend will not complain about.

Same root cause, same line of logic, two failure modes — and the one that corrupts the books is the one that stays quiet.

### Problem 3 — Amendment 1 assigned the determination to the adapters

Amendment 1 ended with: *"`TallyAdapter` becomes responsible for computing the CGST/SGST/IGST split from `tax_rate`, `place_of_supply` and `supplier_state`, and for selecting the correct tax ledger names."*

That was reasonable when written, on the documented premise that **Zoho decides** the split server-side. Finding #9 falsified the premise: Zoho does not decide, it *checks*. So **tax selection is the caller's job on both backends** — and Amendment 1's structure has each adapter making the same intra/inter determination independently.

Two copies of one decision, where only one copy's mistakes are ever reported, is a design that drifts silently in the direction of the silent backend.

## Options considered

**A — Alpha (`TN`) canonical.** Closest to `DraftEntry`'s current comment, and to Zoho's wire format, so it minimises immediate edits. **Rejected:** two-letter alpha state codes have no fixed, enforced vocabulary in the GST system. They are a convenience notation; nothing government-assigned guarantees a stable set or the spelling of any member. Choosing it makes the adapter boundary depend on an informal convention.

**B — Full state name (`Tamil Nadu`) canonical.** Matches the representation Tally actually requires, so `TallyAdapter` would need no translation. **Rejected:** free-form spelling is the worst possible canonical form. It is case- and punctuation-sensitive, varies between sources, and Tally's own vocabulary includes sentinels (`<EOT> Any`) that are not state names at all. It also privileges one backend, which is the failure ADR 0011 exists to prevent — and Amendment 1 explicitly rejected the same shape of argument ("quietly makes the *interface* a Tally interface with an adapter bolted on").

**C — Two-digit statutory numeric (`33`) canonical.** **Chosen.**

## Decision

### 1. The canonical internal representation is the two-digit statutory numeric state code

`33`, `27`, `07` — the code assigned by the GST registry. It is the only one of the three backed by a **fixed, government-assigned vocabulary** rather than free-form spelling or an informal convention. Two further properties follow from that and matter in practice:

- **It is already in the data.** `vendor_gstin[:2]` *is* the supplier's state code, on a field both `DraftEntry` and `VOUCHER` already carry. Choosing numeric makes an existing implicit fact explicit rather than introducing a fourth representation.
- **It is checkable.** A two-character numeric code either is or is not in the published list. `"Tamil Nadu"` vs `"TAMIL NADU"` vs `"Tamilnadu"` are three strings a validator cannot adjudicate without a normalisation policy nobody has written.

`DraftEntry` therefore carries the numeric code — **not** alpha, **not** the full name.

### 2. Translation to a backend's native format happens only at the adapter boundary

One static lookup table, sourced from the **CBIC-published state code list**, translated as late as possible:

- `ZohoAdapter`: numeric → alpha, immediately before the API call.
- `TallyAdapter`: numeric → full state name, immediately before XML generation.

This is ADR 0011's existing principle, applied to one more field: backend shapes belong at the edge. Nothing above the adapter boundary sees alpha or a state name.

### 3. The intra-state / inter-state determination is a single shared function, above both adapters

```python
def determine_tax_jurisdiction(
    supplier_state_code: str,
    place_of_supply_code: str,
) -> TaxJurisdiction:  # IntraState | InterState
    ...
```

Called **once**, above the `BooksConnector` boundary, before either adapter is invoked. The adapters receive the determination; they do not make it.

**This supersedes Amendment 1's "addition" clause.** Both adapters still derive their own backend's *representation* — `TallyAdapter` still computes the CGST/SGST/IGST amounts from `tax_rate` and selects ledger names, `ZohoAdapter` still resolves `tax_rate` to a `tax_id`. What neither does any more is decide **which** jurisdiction applies.

The reason is finding #9 specifically, and it is worth stating as a rule rather than a preference: **when two backends need the same decision and only one of them validates it, per-backend copies of that decision will diverge, and the divergence will surface first as corrupted books on the silent backend — not as a test failure.**

## Consequences

- **A new small shared module.** One pure function plus one static table. It sits above `app/books_connector/`, is backend-agnostic, and is trivially unit-testable — no mocking, no I/O. Per CG10 it should be tested directly, including the intra/inter boundary and rejection of codes not in the published list.
- **Both adapters get simpler, not more complex.** They lose a branch they should never have owned. This *reduces* the surface that issues #2 and #5 have to implement, and removes the duplicated-logic risk from both.
- **The CBIC state-code table becomes a maintained reference.** It changes rarely but it does change — states and union territories have been added and merged (the Dadra & Nagar Haveli / Daman & Diu merger is the recent precedent). It needs an owner and a documented provenance, not an inline dict copied from a blog post. Treat an unknown code as a Task Engine exception, never a guess — same pattern as BK-03's missing-ledger case.
- **`vendor_gstin[:2]` and `supplier_state` must be reconciled, not assumed equal.** They should agree, and when they do not, that is a real extraction problem worth a Task rather than a silent preference for one. This is new validation surface for BK-01.
- **Amendment 1's `DraftEntry` code block is now partly wrong** — its `place_of_supply: str  # state code, e.g. "TN"` comment shows the alpha form. Amendment 1 is not rewritten (it is an accepted record of a decision made on the evidence then available); this amendment is the correction, and the code comments are updated to match.
- **`VOUCHER`'s columns are unaffected**, exactly as under Amendment 1. Whether `VOUCHER` should also retain the determinants remains issue #10's question, and issue #10's provisional column type for these two fields is now settled: numeric.
- **Nothing to migrate.** Both `post_entry` methods still raise `NotImplementedError`, and no model field, test, or ER-diagram entity currently stores a state value in any representation. This is free now and expensive after either adapter is written — the same timing argument Amendment 1 made.

## What is decided vs. what is deferred

**Decided and closed by this amendment:** the canonical representation, where translation happens, and where the jurisdiction determination lives. Issue #50 closes on this.

**Deferred to Sprint 1–2, deliberately:** the *implementation* — `determine_tax_jurisdiction()`, the `TaxJurisdiction` type, and the CBIC lookup table. Phase 0 is a measurement and validation phase; writing the module now would be implementation ahead of the phase, and the decision is what was blocking. It lands with issues #2 and #5, which cannot be implemented without it.

## Open

- **The reconciliation rule between `vendor_gstin[:2]` and `supplier_state` is stated but not specified.** "Raise a Task on mismatch" is the right shape; which field wins for a *posting* that must go out anyway is not decided here.
- **Mixed-rate invoices remain unhandled**, unchanged from Amendment 1's Open section. This amendment does not touch it.
- **Place of supply is not always the recipient's state.** GST's place-of-supply rules have service-specific exceptions. `DraftEntry` carries the code; deciding *which* code is correct for a given supply is BK-01's extraction problem, and this amendment does not solve it.

## References

- ADR 0011 — Multi-Backend Bookkeeping Connector (`audit-platform-ADR-0011-addendum.md`)
- ADR 0011 Amendment 1 — Tax Modelling in `DraftEntry` (`audit-platform-ADR-0011-amendment-1-tax-modelling.md`)
- Issue #50 — three unreconciled state representations (promoted from `PENDING:018`)
- Issue #10 — tax-determinant persistence on `VOUCHER`
- P0-06 finding #8 — Zoho's tax decomposition, and the absence of `cgst_total`/`sgst_total`/`igst_total`
- P0-06 finding #9 — Zoho *validates* the tax choice rather than deriving it; code 3032, symmetric
- P0-02 findings #18/#20 — Tally's `STATENAME` is a name, with sentinel values
- P0-02 finding #2 — a Tally write can report success while storing nothing, which is why the silent path is the dangerous one
