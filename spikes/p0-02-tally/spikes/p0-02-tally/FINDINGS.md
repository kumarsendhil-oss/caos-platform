# P0-02 Findings — TallyPrime XML Integration

Empirical results from a local TallyPrime Educational Mode instance,
company `Coastal Test Traders` (Tamil Nadu, GSTIN `33AAAAA0000A1Z5`),
port 9000. All runs captured under `spikes/p0-02-tally/runs/`.

Everything here was observed, not inferred from documentation. Where a
cause is unknown, it says so.

## 1. Tally emits XML that standard parsers reject — BLOCKER

**Observed:** responses contain `&#4;` (EOT). XML 1.0 forbids character
references to control characters, so `ElementTree` fails outright:

```
reference to invalid character number: line 80, column 27
```

**Consequence for `TallyAdapter` (issue #1):** every response must pass
through a sanitiser before parsing. This is not defensive hardening —
without it, no parse succeeds at all. `spikes/tally_xml.py` implements
it and handles all four forms (decimal, zero-padded, hex, literal byte).

**Open:** `&#4;` appears to be an internal field separator rather than
noise. The sanitiser replaces it with a newline rather than deleting it,
so the boundary survives if a multi-value field turns out to matter.
Deletion would silently concatenate. Revisit if a field comes back
looking run-together.

## 2. A successful response does not mean the data landed — IMPORTANT

**Observed:** `create_ledgers.py` returned `CREATED: 4, ERRORS: 0`. A
full-field read-back showed CGST's `GSTDUTYHEAD` was never set. Tally
accepted the import, discarded a value it didn't recognise, and reported
complete success.

**Consequence:** writes cannot be verified from the import response.
`BK-07` (posting approved vouchers) and `CG7` (duplicate prevention)
both assume a post either succeeds or fails; this shows a third state —
partially applied, reported as success.

`TallyAdapter.post_entry` should read back and verify after writing, at
least for fields that affect tax computation. That is new scope not in
ADR 0001 or the Sprint Plan.

## 3. `GSTDUTYHEAD` is validated against an unknown list — UNRESOLVED

Probed by altering CGST and reading back after each (single-write
single-read confirmed separately, so not a sequencing artefact):

| Value sent | Read back |
|---|---|
| `State Tax` | `State Tax` ✅ |
| `CGST` | `CGST` ✅ |
| `Central Tax` | *(empty)* ❌ |
| `CENTRAL TAX` | *(empty)* ❌ |
| `Central` | *(empty)* ❌ |
| `Integrated Tax` | *(empty)* ❌ |

Every one returned `ALTERED: 1, ERRORS: 0`.

**The pattern is not understood.** `State Tax` is accepted but
`Central Tax` is not, which has no obvious logic. `CGST` is accepted.
No theory here fits the evidence, so none is offered.

**Practical position:** `CGST` is an accepted value. Whether it produces
a *correct* tax split is a separate question, answered only by the
voucher test — an accepted string that computes wrongly is no better
than a rejected one. Do not treat this as settled until a voucher
posts with the right split.

## 4. The TDL Reference Manual predates GST — dead end

85 VAT references, no `GSTDUTYHEAD`, explicitly Tally.ERP 9 era. It is
the canonical TDL reference and it cannot answer any GST field question.
Use a `FETCH *` dump against a live instance instead (see
`dump_ledger.py`), which returns the real field names.

## 5. `CMPINFO.LEDGER` is not a ledger count — read with care

**Observed:** the field reported 4, then 5, 6, 7, 8, 9, 10, 11 across
successive requests, incrementing on every write. The Chart of Accounts
showed six ledgers throughout (`Cash`, `Profit & Loss A/c`, and the four
created).

It appears to be a session or alter-sequence counter. Reading it as
"ledgers in this company" — the obvious interpretation — is wrong.
`TallyAdapter` should count actual `<LEDGER>` elements instead.

## 6. Request shapes that work

| Purpose | Shape | Works |
|---|---|---|
| Create/alter masters | `Import Data` + `REPORTNAME: All Masters` | ✅ |
| Full field dump | `EXPORT` / `COLLECTION` + `FETCH *` + name filter | ✅ |
| Named field export | `EXPORT` / `COLLECTION` + `NATIVEMETHOD` list | ✅ |
| Single object | `EXPORT` / `TYPE: OBJECT` | ❌ `Could not find (null):Ledger!` |
| Built-in report | `EXPORT` / `ID: List of Ledgers` | ⚠️ returns ledgers but no GST fields |

Everything is `POST` to `http://localhost:9000/`. There are no GET
endpoints.

## Still to test

- **Voucher import** — the test this spike was set up for. Needs
  Educational Mode dates (1st, 2nd, 31st only).
- **Duplicate voucher (CG7)** — ADR 0001 claims Tally does not prevent
  duplicates, which is CG7's entire justification. Tally's own TPA
  documentation says *"invalid or duplicate requests will reflect in the
  error count"*, which points the other way. Unresolved, and it matters:
  if Tally does reject duplicates, CG7's rationale needs revisiting.
- **UTF-16 encoding** — required for the ₹ symbol per Tally's docs.
  Untested; relevant to any amount field carrying a currency symbol.
- **Whether `GSTDUTYHEAD: CGST` computes the correct split** — see §3.
