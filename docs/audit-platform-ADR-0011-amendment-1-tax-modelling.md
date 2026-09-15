# ADR 0011 — Amendment 1: Tax Modelling in `DraftEntry`

**Status:** Accepted
**Amends:** ADR 0011 (Multi-Backend Bookkeeping Connector)
**Date:** 2026-09-15
**Raised by:** the P0-06 Zoho spike (`docs/spikes/P0-06-zoho-api-runbook.md`)
**Blocks:** issue #5 (`ZohoAdapter.post_entry`)

## Context

ADR 0011 established a `BooksConnector` interface with Tally and Zoho adapters, on the premise that both could be hidden behind one normalized schema. Drafting the actual Zoho requests during the P0-06 spike surfaced a case where that premise doesn't hold cleanly: **the two backends model GST incompatibly.**

| | Tally | Zoho Books |
|---|---|---|
| How tax is represented | Explicit CGST/SGST/IGST **ledger lines**, each with a computed amount | A `tax_id` reference **per line item** |
| Who computes the split | The caller | Zoho, server-side |
| How intra- vs inter-state is decided | The caller, by choosing which tax ledgers to use | Zoho, by comparing `source_of_supply` to `destination_of_supply` |

`BooksConnector.DraftEntry` was written before the Zoho adapter existed, and carries:

```python
amount: Decimal
cgst: Decimal
sgst: Decimal
igst: Decimal
```

That is a faithful model of a Tally voucher and a poor fit for Zoho. `ZohoAdapter.post_entry` cannot pass these fields through — it has to work backwards from computed amounts to a tax-rate reference, which is the wrong direction and lossy (two different rate configurations can produce the same rupee amount).

This is not an implementation detail. It's a question about what the shared interface means, so it belongs in an ADR rather than being settled quietly inside one adapter.

## Options considered

**Option A — Keep `DraftEntry` as-is; `ZohoAdapter` translates.**
The adapter maintains a tax-rate → `tax_id` lookup per Zoho organization, derives the applicable rate from the computed amounts, and sources the two state codes separately. Most work, concentrated in one place.

**Option B — Add Zoho-shaped optional fields to `DraftEntry`.**
Add `tax_id`, `source_of_supply`, `destination_of_supply` as optional fields alongside the existing ones. Rejected outright: it puts backend-specific concepts into the shared interface, which is exactly what ADR 0011's central rule forbids. The Bookkeeping Agent would end up populating fields whose meaning depends on which backend the client happens to use — the branch-on-backend that the whole design exists to prevent.

**Option C — Change `DraftEntry` to carry tax *rate* rather than computed amounts.**
Replace `cgst`/`sgst`/`igst` with a rate plus a place-of-supply pair, and let each adapter derive what its backend needs — Tally computing the split, Zoho passing the rate through as a `tax_id` lookup.

## Decision

**Option C**, with one addition.

`DraftEntry` changes from carrying computed tax amounts to carrying the tax *determinants*:

```python
@dataclass(frozen=True)
class DraftEntry:
    vendor_gstin: str | None
    invoice_number: str
    invoice_date: str
    taxable_amount: Decimal        # pre-tax line total
    tax_rate: Decimal              # e.g. Decimal("18") for 18%
    place_of_supply: str           # state code, e.g. "TN"
    supplier_state: str            # state code, for intra/inter determination
    ledger_name: str
```

Reasoning, having initially leaned toward Option A:

1. **It matches what the Bookkeeping Agent actually extracts.** BK-01 reads an invoice: a taxable value, a GST rate, and the parties' states. The rate is on the source document; the CGST/SGST split is a *derivation* from it. Option A would have the agent compute a split, then have `ZohoAdapter` immediately un-compute it — deriving, discarding, and re-deriving the same fact.

2. **It removes a lossy round-trip.** Going from computed amounts back to a rate is not reliably invertible (rounding, mixed-rate invoices). Going from rate to amounts is deterministic. Carrying the determinant and deriving at the edge is the direction that doesn't lose information.

3. **Both adapters do symmetrical work.** Under Option A, Tally is the privileged backend and Zoho carries all the translation cost — which quietly makes the "interface" a Tally interface with an adapter bolted on. Under Option C, each adapter translates from a neutral shape into its own. That's what ADR 0011 claimed the design was.

**The addition:** `TallyAdapter` becomes responsible for computing the CGST/SGST/IGST split from `tax_rate`, `place_of_supply` and `supplier_state`, and for selecting the correct tax ledger names. That logic is a genuine part of the Tally adapter, not agent logic — Tally is the backend that needs it.

## Consequences

- **`DraftEntry` changes shape**, so this must land before either `post_entry` is implemented (issues #2 and #5). Currently costless — both adapters raise `NotImplementedError`, so there is no implementation to migrate. **Doing this after either adapter is written would be considerably more expensive.**
- **`TallyAdapter` gains split-computation logic** that ADR 0001 didn't anticipate, including the intra- vs inter-state determination and tax-ledger name selection. Worth unit-testing directly — the rounding behaviour on odd rates is exactly where a silent Decimal bug would hide, and CG5 applies throughout.
- **The Bookkeeping Agent must extract two new fields** it wasn't previously asked for: `place_of_supply` and `supplier_state`. Both are normally present on a GST invoice, but this adds extraction scope to BK-01 and is a new failure mode when they're absent or unreadable — which should route through the Task Engine as an exception like any other low-confidence extraction, not be guessed at.
- **Mixed-rate invoices are not handled by this shape.** A single `tax_rate` on `DraftEntry` assumes one rate per entry. Real invoices can carry multiple rates across line items. This amendment does not solve that; it's deferred, and should be reconsidered when line-item-level extraction is built. Flagged explicitly so it isn't discovered mid-implementation.
- **The Zoho tax-rate → `tax_id` lookup is still required**, just simpler — a direct rate match rather than an inference from amounts. Still needs caching per organization, and still needs a real answer to what happens when no matching tax rate exists in the client's Zoho org (likely a Task Engine exception, same pattern as BK-03's missing-ledger case).
- **`VOUCHER`'s `cgst`/`sgst`/`igst` columns stay as they are, and stay correct.** `DraftEntry` is the pre-post interface shape; `VOUCHER` is the platform's own record of what was actually posted, *after* the adapter derived the split. Storing the computed amounts there remains the right model, and the ER diagrams need no change on account of this amendment. Note though that **nothing writes those columns until issue #2 or #5 lands** — until then they are unpopulated by design, not by oversight, which is worth knowing before anyone reads an empty column as a bug. Whether `VOUCHER` should also retain the determinants a split was derived from is tracked separately in #10.

## Open

- **Not validated against either API.** Both spikes remain unrun; this decision is reasoned from the two APIs' documented models. If Test 5 in the P0-06 runbook reveals Zoho behaves differently than documented, revisit.
- **Mixed-rate handling**, per the consequence above.
