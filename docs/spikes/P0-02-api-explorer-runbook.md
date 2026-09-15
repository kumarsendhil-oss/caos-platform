# P0-02 Spike — TallyPrime API Explorer Runbook

**Status:** payloads drafted, **nothing validated yet**
**Blocks:** Sprint 1-2's `TallyAdapter` build (STUB PENDING:001, PENDING:002, PENDING:003)
**Companion file:** `tally_payloads.py` — run it to print each payload

## What this spike settles, and what it doesn't

| Question | Settled here? |
|---|---|
| What XML does TallyPrime accept for register/ledger reads? | Yes, once run through the Explorer |
| Does our voucher-import payload produce a correct, balanced voucher? | Yes, once run |
| Which collection name returns a usable purchase register? | Yes — this is the main unknown to resolve |
| **Is port 9000 reachable on the practice's hosted instance?** | **No — separate question, still open with the provider** |

That last row matters. The Explorer runs against a sandbox, not the practice's Tally Cloud. A fully successful spike still leaves reachability unanswered — it just means that once reachability is resolved, the adapter's payload work is already done and validated.

## Setup

1. Open the TallyPrime API Explorer (Tally Solutions' own sandbox — no live client data needed, per ADR 0001 / TC-01b).
2. Run `python tally_payloads.py` and copy each payload in turn.
3. For each test below: paste, send, and **save the full response XML** — the response shapes are what `TallyAdapter`'s parsing code gets written against, and they're as important as confirming the request worked.

## Test 1 — Purchase register export (TC-02)

Payload 1 from the script. The `<ID>` value is the real unknown: `Purchase Register` is the documented-looking guess, but Tally's collection naming is inconsistent (the Rust SDK found vouchers live under `DayBook`, no space, rather than an obvious name).

Try in order, and record which returns a usable line-item list:
- `Purchase Register`
- `Purchase Vouchers`
- `DayBook` (then filter client-side by voucher type)
- `All Vouchers`

**Record:** which ID worked; the response's line-item structure; whether GSTIN, invoice number, and amount are all present per line (these three are what RC-02 matches on).

## Test 2 — Ledger master export (BK-02)

Payload 2. Uses an inline TDL collection to request exactly four fields rather than Tally's full ledger dump.

**Record:** whether `PartyGSTIN` comes back populated. If it doesn't, BK-02's vendor matching loses its most reliable key and falls back to name-only fuzzy matching — worth knowing early, since it changes the matching engine's design.

## Test 3 — Purchase voucher import (TC-04)

Payload 3. Creates one synthetic voucher.

**Prerequisite:** the ledgers named in the payload must already exist in the sandbox company — `Coastal Components Pvt Ltd`, `Purchase @18%`, `CGST`, `SGST`. Create them first, or the import fails with Tally's characteristically terse error. (This is exactly the failure BK-03 is designed to prevent in production, by raising a new-ledger task rather than attempting a doomed post.)

**Record:** the response's created/altered/ignored counts and any error text. Then open the voucher in the sandbox UI and confirm the tax split landed on the right ledgers.

## Test 4 — Duplicate-prevention check (CG7)

Send payload 3 **again, unchanged**.

Per ADR 0001, Tally's XML import does not prevent duplicate vouchers on its own — which is why CG7 requires the platform to check before posting. This test confirms that claim on the actual version we're targeting rather than taking the docs' word for it.

**Expected:** a second identical voucher is created.
**If Tally actually rejects it:** that's a meaningful finding — CG7's rationale would need revisiting, though the check is still worth keeping as defence in depth.

## Test 5 — Inter-state (IGST) variant

Modify payload 3: set `cgst`/`sgst` to `0.00` and `igst` to the full tax amount. The builder omits zero-value tax ledgers automatically, so this should produce a three-entry voucher.

**Record:** whether Tally accepts an IGST-only purchase voucher with no CGST/SGST lines present at all.

## After the spike

- Paste real request/response pairs into this file as an appendix — future-you writing the adapter parser will want the actual response shapes, not a description of them.
- If all five pass, `TallyAdapter`'s payload design is settled and PENDING:001/002 become straightforward implementation rather than research.
- Update `docs/STUB_ISSUES.md` with anything learned that changes those stubs' scope.
- **Do not** mark P0-02 complete on the Dev Readiness Checklist. This spike is its technical half; the reachability question with the hosting provider is the other half, and that one is still open.
