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

---

# Round 2 — Voucher posting (2026-09-15, runs 15:23–15:50 UTC)

## 7. Purchase vouchers require inventory entries on inventory-enabled companies — RESOLVED

**Observed:** seven payload variants (varying OBJVIEW, PERSISTEDVIEW,
tax ledgers, voucher number, party ledger) all failed identically
against `Coastal Test Traders` with `EXCEPTIONS: 1` and no detail.
Creating the same voucher by hand in Tally revealed why: that company
has `Maintain Inventory: Yes` + `Integrate Accounts with Inventory: Yes`,
so Tally requires a stock item on a Purchase voucher. Manual entry could
not be completed without creating one.

The identical payload posted first try against `Coastal Services Ltd`
(`Maintain Inventory: No`) — `CREATED: 1`.

**Consequence for `TallyAdapter` (issue #2):** inventory handling is
**conditional on client configuration**, not universal. The adapter must
know each client's inventory setting and supply `ALLINVENTORYENTRIES.LIST`
only where required. For service-business clients — common in a CA
practice — accounting-only purchase vouchers post cleanly.

**Still unknown:** what a correct inventory-bearing voucher looks like.
Not yet tested. BK-01 currently extracts invoice line items with no
notion of mapping them to a client's stock item master; for
inventory-enabled clients that mapping is new scope, comparable to
BK-02's vendor-to-ledger matching but against stock items.

## 8. The tax split computes correctly — `GSTDUTYHEAD: CGST` works

Verified in the Tally UI, not just by read-back:

```
To  Coastal Components Pvt Ltd              21,712.00 Cr
By  Purchase @18%            18,400.00 Dr
By  CGST                      1,656.00 Dr
By  SGST                      1,656.00 Dr
```

This closes the open question from §3. `CGST` as a `GSTDUTYHEAD` value is
not merely accepted — it produces the correct intra-state split. (Whether
some other value is more canonical is still unknown; this one works.)

## 9. CG7 CONFIRMED — Tally does not prevent duplicate vouchers

Two identical imports produced two vouchers: `LASTVCHID` 1 then 2, both
`CREATED: 1, ERRORS: 0`. The Day Book shows both, and party `Cur Bal`
of 43,424.00 Cr (= 2 × 21,712) confirms both posted in full.

**ADR 0001's claim stands.** Tally's own TPA documentation states
*"invalid or duplicate requests will reflect in the error count"* —
that is **wrong** for voucher imports. CG7's platform-side duplicate
check is genuinely necessary, not defensive over-engineering.

## 10. Tally assigns its own voucher numbers, discarding ours

We sent `VOUCHERNUMBER: SVC-INV-0001`; Tally stored `1` and `2`.

Same silent-discard class as §2. It matters specifically for CG7: the
platform cannot use the voucher number as a duplicate key on Tally's
side, because it does not control that value. The check must live
entirely in the platform's own `Voucher` table — which is what CG7
specifies, so the design is right, for a reason now better understood.

**Open:** whether a supplier invoice number can be carried in a
different field (the UI shows an empty "Supplier Invoice No." on the
posted voucher). Worth testing — without it, a posted voucher has no
link back to the source document.

## 11. Our voucher read-back query is broken — spike bug, not Tally

`EXPORT / COLLECTION / TYPE: Voucher / FETCH *` returned zero vouchers
while the Day Book showed two. The vouchers exist; the query is wrong.
Note `CMPINFO.COMPANY` read `1` on these responses and `0` on earlier
ones, which may indicate a company-context problem in the request.

Unresolved. `TallyAdapter` needs a working voucher read for TC-02 and
for the read-back verification §2 makes mandatory, so this must be
fixed before issue #1 is implemented.

## 12. Tally reports import exceptions with no diagnostic detail anywhere

Checked and ruled out, all of them:

| Channel | Result |
|---|---|
| XML response | counts only |
| `tally.imp` | summaries only (whole file checked, not just tail) |
| `logs/` folder | `tallyscheduler.log` only — unrelated component |
| Data directory | binary `.TSF`, locked while Tally runs |
| `tally.ini` | no verbosity or debug setting exists |
| Calculator Pane (`Ctrl+N`) | stayed empty during a reproduced failure |

A third-party source claimed `tally.imp` *"dumps the validation errors
and unimported structures"*. It does not, at least not by default and
not with any setting exposed.

**Consequence:** when a post fails, `TallyAdapter` can report *that* it
failed but never *why*. Combined with §2 (success responses that are not
true), read-back verification is the only mechanism available for
knowing what actually happened. That belongs in ADR 0001 as a stated
constraint, not tribal knowledge.

---

# Round 3 — Voucher reads (2026-09-16)

## 11. RESOLVED — vouchers need `TYPE: DATA` + `ID: Day Book`

Finding #11 said our voucher read returned zero while the Day Book
showed two. The query was wrong, and this is the fix:

| Object | Working shape |
|---|---|
| Ledgers, masters | `EXPORT` / `TYPE: COLLECTION` + custom TDL collection |
| **Vouchers** | `EXPORT` / **`TYPE: DATA`** + **`ID: Day Book`** |

Verified: `runs/2026-09-16T02-04-*-vchread-A-data-daybook` returned both
posted vouchers with full ledger entries. `ID: Voucher Register` also
works and returns the same two.

The failure mode matters: pointing a `COLLECTION` at vouchers returns
**zero results with no error**. It looks like an empty period rather
than a wrong query, which is how it went unnoticed for a whole session.

Useful extra: Day Book responses carry `REMOTEID` and `VCHKEY`
attributes on each `<VOUCHER>`. Given finding #10 (Tally discards our
`VOUCHERNUMBER` and assigns its own), these are the only stable handles
the platform has on a posted voucher. `TallyAdapter` should capture them
at post time.

`spikes/tally_voucher_read.py` implements the verified read.
`post_voucher.py` and `no_inventory_test.py` now delegate to it.

## 13. A malformed TDL request can crash TallyPrime — AVAILABILITY RISK

`TYPE: COLLECTION` with `ID: Day Book` — a plausible-looking mix of the
two shapes above — makes TallyPrime raise a **modal GUI dialog**:

```
Error in TDL.
'Collection:Day Book'
Could not find description!
```

While that dialog is open the HTTP listener serves nothing. Three
further requests each raised it again, and TallyPrime then **closed
itself entirely**. Observed, not inferred: three consecutive requests
timed out at 8s, and the process was gone afterwards.

**Why this is more than a spike detail.** The practice runs every client
company in one Tally Cloud instance (ADR 0001, TC-01). So:

- One malformed request blocks the integration for **every** client on
  that instance, not just the one whose request failed.
- Recovery needs a human at the console to dismiss a dialog, or to
  restart Tally. On a hosted or headless server there may be nobody to
  click OK.
- The platform sees a **timeout, not an error** — it cannot distinguish
  "Tally is down" from "Tally is waiting on a dialog nobody can see".

**Consequences:**

1. CG6's explicit-timeout rule stops being hygiene and becomes load-
   bearing. Without it a hung Tally call hangs a Celery worker
   indefinitely. The failure mode is a hang, not a rejection.
2. `TallyAdapter` must send only request shapes that have been verified
   against a real instance. Constructing TDL dynamically from
   user-supplied values is a crash risk, not just a correctness risk.
3. A Tally health check (TC-05) should distinguish *unreachable* from
   *unresponsive*, because the second may mean a blocking dialog and
   needs a different escalation — a person at the server, not a retry.
4. Worth raising with the Tally Cloud provider alongside the port 9000
   question: what happens to a hosted instance that raises a modal
   dialog, and who can dismiss it?

**Not retested deliberately.** Reproducing a crash to confirm it a
second time costs a restart and teaches nothing new. Variants D, E and F
remain untested for this reason; A and B work, which is what the adapter
needs.

**Note the irony against finding #12.** Yesterday established that Tally
reports import exceptions with no diagnostic detail anywhere. Here it
produced a genuinely useful message — "Could not find description" —
and sent it to a GUI dialog box, the one place an integration cannot
read it.

## 14. `VOUCHERNUMBER` is unusable as an identity field — extends #10

Finding #10 established that Tally discards the `VOUCHERNUMBER` we send
and assigns its own, observed once, on `Coastal Services Ltd`. This
extends it in three ways. Nothing here contradicts #10 — #10 remains
the canonical statement of the discard itself.

**1. Confirmed on a second company.** Not specific to one company's
configuration:

| Company | Sent | Stored | Artifact |
|---|---|---|---|
| Coastal Test Traders | `TEST-INV-0001` | `1`–`6` | `runs/2026-09-16T02-15-54-voucher-2-readback/` |
| Coastal Services Ltd | `SVC-INV-0001` | `1`–`4` | `runs/2026-09-16T04-34-13-noinv-5-readback-after-duplicate/` |

Observed, not inferred: the `TEST-INV-0001` value is present in that
run's own `voucher-1-post/request.xml` and `voucher-3-duplicate/request.xml`,
and absent from every voucher in the readback taken minutes later.

**2. The mechanism has a name.** The stored vouchers carry
`NUMBERINGSTYLE: Auto Retain`. So this is Tally's configured numbering
behaviour for the voucher type, not a parse failure or a silent drop of
an unrecognised value — which distinguishes it from the §2 class of
silent discard that #10 grouped it with.

**3. The consequence is wider than CG7.** #10 drew the duplicate-key
conclusion, which stands. But the same fact also breaks *read-back
correlation*: after posting, the platform cannot find "the voucher we
just posted" by the number it sent, because no voucher in Tally will
ever carry that value. This matters for the read-back-and-verify step
§2 makes mandatory — verification has to locate the voucher before it
can verify it.

**Demonstrated concretely, and it already cost us something.**
`docs/context.md` carried an open action to identify an unexplained
voucher by comparing its `VOUCHERNUMBER` against `post_voucher.py`'s
`TEST-INV-0001` constant, described there as "the single check that
would settle it". That check cannot ever succeed, for any voucher, from
any source. It was struck rather than performed.

**Direction, not a new open question.** #11 (round 3) already notes
that Day Book responses carry `REMOTEID` and `VCHKEY` per `<VOUCHER>`
and that `TallyAdapter` should capture them at post time. That note is
the answer to this, and #10's open item about linking a posted voucher
back to its source document. Tracked as `PENDING:010`.
