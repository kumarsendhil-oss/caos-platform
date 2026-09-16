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

## 7. `Invoice Voucher View` requires inventory entries on inventory-enabled companies — RESOLVED, evidence corrected 2026-09-16

> **Correction (2026-09-16).** This finding originally stated that all
> seven payload variants failed and concluded that Tally "requires a
> stock item on a Purchase voucher" for an inventory-enabled company.
> Both claims are wrong against the committed artifacts — **five of the
> seven were created**, with no inventory entries, on that very company.
> The discriminator is `OBJVIEW`, not inventory. The original text is
> replaced below; the *consequence* for `TallyAdapter` was right for the
> wrong reason and is restated. Caught while designing the gap 2 probe,
> whose whole design depended on which rule is true.

**Observed.** Seven variants against `Coastal Test Traders`
(`Maintain Inventory: Yes` + `Integrate Accounts with Inventory: Yes`),
artifacts `runs/2026-09-15T15-38-17-variant-*`:

| Variant | `OBJVIEW` | Tax ledgers | Result |
|---|---|---|---|
| A minimal-no-tax | *(none)* | no | **CREATED 1** |
| B minimal-with-tax | *(none)* | yes | **CREATED 1** |
| C accounting-objview | `Accounting Voucher View` | yes | **CREATED 1** |
| D invoice-objview | `Invoice Voucher View` | yes | `EXCEPTIONS 1` |
| E invoice-plus-persisted | `Invoice Voucher View` + `PERSISTEDVIEW` | yes | `EXCEPTIONS 1` |
| F no-voucher-number | *(none)* | yes | **CREATED 1** |
| G no-partyledgername | *(none)* | yes | **CREATED 1** |

`runs/2026-09-15T15-38-18-variants-readback` confirms the five landed:
exactly 5 vouchers, numbered 1–5, every one stored as
`OBJVIEW="Accounting Voucher View"`. **Those five are vouchers 1–5 in
that company's day book** — not background clutter of unknown origin.

**B vs. D isolates the cause.** Both carry the same four ledger entries
including CGST and SGST; they differ only in `OBJVIEW` (and a
`VOUCHERNUMBER` Tally discards anyway, finding #14). So the trigger is
`OBJVIEW="Invoice Voucher View"` alone. Inventory-enabled companies
accept accounting-view purchase vouchers with no inventory entries.

**The rule, corrected:** on an inventory-enabled company,
`Invoice Voucher View` requires inventory entries; `Accounting Voucher
View` does not, and posts fine without them. The manual-UI observation
that a hand-entered voucher could not be completed without creating a
stock item is consistent with this — Tally's manual entry was in item
invoice mode, which is the mode that needs items — but it was
generalised past what the payloads showed.

Voucher #6 in the same company is the positive case: `Invoice Voucher
View` **with** an `ALLINVENTORYENTRIES.LIST`, stored successfully. See
findings #18–#20.

The identical payload posted first try against `Coastal Services Ltd`
(`Maintain Inventory: No`) — `CREATED: 1`.

**Consequence for `TallyAdapter` (issue #2):** inventory handling is
**conditional on client configuration**, not universal — the original
conclusion stands, and the corrected evidence sharpens it into a choice
the adapter actually controls. The adapter picks the voucher *view*: it
can post `Accounting Voucher View` and need no stock item at all, even
against an inventory-enabled client, or post `Invoice Voucher View` and
must then supply a matching `ALLINVENTORYENTRIES.LIST`. For
service-business clients — common in a CA practice — accounting-only
purchase vouchers post cleanly either way.

**Open question the correction raises:** posting accounting-view
vouchers to an inventory-enabled client is *accepted*, but that does not
make it *correct* for the client's books — it bypasses stock movement on
a company configured to track it. Whether that is an acceptable adapter
default or a silent data-quality problem is a judgement for the
practice, not something these artifacts settle.

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

## 15. `REMOTEID` is stable across reads, restarts and edits; `VCHKEY` is demoted

Finding #14 rules out `VOUCHERNUMBER` as an identity field, leaving
`PENDING:010`'s proposal — `REMOTEID`/`VCHKEY`, inherited from #11 —
resting on an assumption nobody had tested: that the identifier is
assigned once at creation rather than regenerated per response. An
identifier that moves on read cannot correlate anything.

**Method.** The same Day Book read (`EXPORT` / `TYPE: DATA` / `ID: Day
Book`, the #11 shape) sent twice as two separate requests, ~2s apart,
against `Coastal Services Ltd`. Read-only — nothing posted, nothing
altered. Both HTTP 200 (177ms, 100ms).

`runs/2026-09-16T06-32-15-remoteid-stability-read-1/`
`runs/2026-09-16T06-32-17-remoteid-stability-read-2/`
`remoteid_stability_probe.py` is the script; re-run it to test the two
open risks below.

**Result: every identifier field identical across both reads**, on all
four vouchers — `REMOTEID`, `VCHKEY`, `GUID`, `MASTERID`, `ALTERID`,
`VOUCHERNUMBER`. Voucher 1:

```
REMOTEID  5f8d5006-709d-427b-bc95-57a3212e7b23-00000001   both reads
VCHKEY    5f8d5006-709d-427b-bc95-57a3212e7b23-0000b49a:00000008
```

**`REMOTEID` is byte-identical to the voucher's own `GUID`** — checked
on all 4 vouchers here and all 6 in the `Coastal Test Traders` readback
(`runs/2026-09-16T02-15-54-voucher-2-readback/`). That makes it object
identity, not a transport artifact of the response. Use it.

**`VCHKEY` is demoted — structure, not this test, is the reason.** It
decomposes as `<company-GUID>-0000b49a:<8-hex>`:

- the trailing segment is a **storage offset**, stepping by 8 in hex
  (`08, 10, 18, 20, 28, 30` across six vouchers) — not a read counter,
  but stable only while that layout is;
- the middle `0000b49a` is **identical across two different companies**
  (`5f8d5006-...` and `e0b7ed19-...`), on different days. It is not
  company-derived. Unexplained — see the restart result below, which
  rules out the build/session-handle guess this finding originally
  made without replacing it.

#11 named `REMOTEID` and `VCHKEY` together as "the only stable handles".
That was right about `REMOTEID` and optimistic about `VCHKEY`.

### Restart-stability — RESOLVED 2026-09-16, `REMOTEID` holds

Risk 1 below is now closed. TallyPrime was fully closed and reopened
and the same company reloaded, with a baseline read taken before and a
comparison read after — two separate invocations of the probe, compared
field by field (timestamps and request ids differ by construction and
are not the signal).

`runs/2026-09-16T06-49-24-remoteid-stability-read-1/` — pre-restart baseline
`runs/2026-09-16T06-49-26-remoteid-stability-read-2/`
`runs/2026-09-16T06-55-26-remoteid-stability-read-1/` — post-restart
`runs/2026-09-16T06-55-28-remoteid-stability-read-2/`

**`REMOTEID` is byte-identical across the restart on all four vouchers.**
`VCHKEY` likewise, including both of its variable parts:

| # | `REMOTEID` (pre = post) | `VCHKEY` (pre = post) |
|---|---|---|
| 1 | `5f8d5006-...-7b23-00000001` | `5f8d5006-...-7b23-0000b49a:00000008` |
| 2 | `5f8d5006-...-7b23-00000002` | `5f8d5006-...-7b23-0000b49a:00000010` |
| 3 | `5f8d5006-...-7b23-00000003` | `5f8d5006-...-7b23-0000b49a:00000018` |
| 4 | `5f8d5006-...-7b23-00000004` | `5f8d5006-...-7b23-0000b49a:00000020` |

Full company prefix on every value, both runs:
`5f8d5006-709d-427b-bc95-57a3212e7b23`. `VOUCHERNUMBER`, `MASTERID`,
`ALTERID` and `GUID` also held.

**Correction — the `0000b49a` build/session-handle guess is wrong.**
This finding predicted the segment was "precisely the kind of value
that changes when TallyPrime restarts." It did not change. A session
handle would not survive the process closing and reopening, so that
reading is ruled out. The segment is **durable but still unexplained**,
and what is unaccounted for is now sharper than before: it is neither
session-scoped (survives a restart) nor company-derived (shared by
`5f8d5006-...` and `e0b7ed19-...` on different days). Nothing yet
explains what it actually encodes. The stride-of-8 pattern in the
trailing segment (`08, 10, 18, 20`) held across the restart too, which
rules out the load-time-offset reading of that half as well.

**`VCHKEY` stays demoted, and this result does not promote it.** The
demotion above rests on structure — an opaque constant plus a storage
offset, neither documented nor tied to voucher identity — not on the
session-handle guess. One wrong sub-hypothesis does not restore a field
whose stability is a property of a storage layout rather than of the
voucher. `REMOTEID` remains the field to use, now on strictly better
evidence: object identity (`== GUID`), stable per response, stable
across a restart.

### Edit-stability — RESOLVED 2026-09-16. Both risks now closed.

Risk 2 is the last one, and it is now settled. A voucher already stored
in `Coastal Services Ltd` was altered in the TallyPrime UI — its amount
changed and saved — with a read taken before and after.

`runs/2026-09-16T07-18-22-remoteid-stability-read-1/` — pre-edit baseline
`runs/2026-09-16T07-18-24-remoteid-stability-read-2/`
`runs/2026-09-16T07-20-42-remoteid-stability-read-1/` — void attempt, see below
`runs/2026-09-16T07-20-44-remoteid-stability-read-2/`
`runs/2026-09-16T07-23-13-remoteid-stability-read-1/` — post-edit
`runs/2026-09-16T07-23-15-remoteid-stability-read-2/`

**The edit reached stored data**, not a cosmetic field — voucher 1's
party amount went `21712.00` to `21714.00` and Tally recomputed the tax
split to `1657.00` CGST and `1657.00` SGST (`Purchase @18%` unchanged at
`18400.00`).

**`REMOTEID` survived it.** On the edited voucher, `REMOTEID`, `VCHKEY`,
`GUID`, `VOUCHERNUMBER` and `MASTERID` are all byte-identical to the
pre-edit baseline. One field moved, and only one:

| # | edited | `REMOTEID` | `MASTERID` | `ALTERID` pre → post |
|---|---|---|---|---|
| 1 | yes | unchanged | 1 | **1 → 5** |
| 2 | no | unchanged | 2 | 2 → 2 |
| 3 | no | unchanged | 3 | 3 → 3 |
| 4 | no | unchanged | 4 | 4 → 4 |

Editing one voucher had **zero effect on the other three's identifiers**
— every field held, `ALTERID` included.

**`ALTERID` is a company-wide alteration sequence, not a per-voucher
revision counter. This is easy to misread and worth reading twice.** The
edited voucher's `ALTERID` went `1 → 5`, not `1 → 2`. With `MASTERID`
1–4 across the four vouchers, 5 is simply the next number in a sequence
the whole company shares. So `ALTERID > MASTERID` means "this voucher
has been altered"; the *value* orders alterations across the company,
not within one voucher's own history. Reading it as "revision 5 of this
voucher" would be wrong — voucher 1 has been altered exactly once.

**Both risks are now resolved.** `REMOTEID` is confirmed stable across
repeated reads, across a TallyPrime restart, and across an edit to an
existing voucher.

### Method note — an asserted condition needs checking against evidence

`--baseline` is built so the script never claims what condition held
between two runs; the human asserts it. That division only works if the
assertion is then **verified against the evidence rather than taken on
trust**, and this run demonstrates why, twice:

1. **A void run that read clean.** The first post-edit attempt
   (`07-20-42`) reported every field `SAME`, which looks like a result.
   The two responses were byte-identical, so nothing in that company had
   changed at all — the edit had not been saved. Reported as
   "`REMOTEID` survived an edit", it would have been a false positive on
   the one question `PENDING:010` was still open on. The same shape as
   #14's void `TEST-INV-0001` check: a test that reads clean while
   exercising nothing.
2. **The wrong voucher.** The condition was asserted as voucher 2. The
   amounts show voucher 1, and `ALTERID` moved on exactly the voucher
   whose amounts moved. The conclusion is unaffected — an edited voucher
   kept its `REMOTEID` either way — but the finding would have recorded
   the wrong voucher permanently.

Both were caught by comparing amounts in the readback, which the probe
does not read (`PENDING:013`). The generalisable rule: **an asserted
condition is a hypothesis about the evidence, not a fact about it.**
Check it against what the artifacts actually show, every time, not only
when something looks off — in both cases here, nothing looked off.

`TallyAdapter.post_entry` should capture `REMOTEID` at post time and use
it for read-back verification, including for vouchers amended after
posting — the ordinary BK-07 correction case, now tested rather than
assumed. `PENDING:010` is resolved.


# Round 4 — Voucher deletion and sandbox reset (2026-09-16)

Investigate session against `PENDING:009` (no reset mechanism for either
sandbox company). Two live `ACTION="Delete"` attempts against
`Coastal Services Ltd`, read-only on code. Both failed; neither crashed
anything. Artifacts: `runs/2026-09-16T08-21-*`, `08-22-*`, `08-27-*`.

## 16. Vouchers cannot be deleted through the XML import API — two addressing schemes refused

**Setup.** `Coastal Services Ltd` held 4 vouchers. Voucher 1 is the
*edited* one from #15 (`ALTERID 5`, amounts `21714`) and was excluded as
live evidence; vouchers 2–4 are the identical `21712` duplicates.
Voucher 4 was targeted — a true duplicate, and the highest number, so
any renumbering would disturb the others least.

**Attempt 1 — addressed by `REMOTEID` + `VCHKEY`**
(`runs/2026-09-16T08-21-43-pending009-delete-attempt/`):

```xml
<VOUCHER REMOTEID="5f8d5006-...-00000004"
         VCHKEY="5f8d5006-...-0000b49a:00000020"
         VCHTYPE="Purchase" ACTION="Delete">
```
```
<LINEERROR>Voucher does not exist!</LINEERROR>
<DELETED>0</DELETED> <ERRORS>1</ERRORS>
```

Tally could not resolve the target. This is consistent with `REMOTEID`
being *Tally-generated* here: we have never supplied one at create time,
so on import there is no external id to match against. The same
`REMOTEID` reads back fine — see #15.

**Attempt 2 — addressed by `MASTERID`**
(`runs/2026-09-16T08-27-27-pending009-delete-masterid/`):

```xml
<VOUCHER VCHTYPE="Purchase" ACTION="Delete">
  <MASTERID>4</MASTERID>
  <DATE>20260801</DATE>
  <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
  <VOUCHERNUMBER>4</VOUCHERNUMBER>
</VOUCHER>
```
```
<LINEERROR>Cannot delete unnamed object: VOUCHER!</LINEERROR>
<DELETED>0</DELETED> <ERRORS>0</ERRORS>
```

**The second error is the informative one.** It is not a failure to find
the voucher — addressing resolved. Tally objected to the *kind of
object*. The only voucher-delete syntax confirmed verbatim from
documentation is for masters and deletes by name
(`<LEDGER NAME="ICICI" ACTION="Delete">`); a voucher has no name, so
"unnamed object" is a structural refusal, not a wrong-field error.

**Neither attempt showed #13's crash pattern.** Both returned in 0.1s,
well-formed, and readbacks afterward
(`08-22-09-*`, `08-27-37-*`) confirm all 4 vouchers still present and
unchanged. The difference from #13 is likely that these used the proven
`Import Data` envelope rather than a malformed read query.

**This nuances `PENDING:010`; it does not invalidate it.** Two distinct
claims that must not be conflated:

- **`REMOTEID` is stable and correct for read-back correlation.**
  Confirmed across reads, a restart and an edit (#15). This is what
  BK-07 actually needs, and it stands unchanged.
- **`REMOTEID` is NOT confirmed addressable for writes** — delete,
  amend-by-id, or any operation that identifies an existing voucher in
  an import request. Attempt 1 is direct evidence against it.

If `TallyAdapter` ever needs to delete or amend a voucher it posted, it
cannot assume the identifier it reads back is the one it can write
against. It may need to **supply `REMOTEID` itself at create time** —
untested in either direction.

**A third scheme was identified and deliberately not tested.**
`TAGNAME`/`TAGVALUE` (e.g. `TAGNAME="Voucher Number" TAGVALUE="4"`)
appeared in search results as a way to address an otherwise-unnamed
object, which is exactly what attempt 2's error points at. It was not
attempted, and the reason is not caution about the API: **even if it
works, it addresses by a Tally-auto-assigned voucher number, which #14
proved is assigned by Tally and not ours to rely on.** A reset keyed on
that number is one renumbering away from deleting the wrong voucher — in
the company that holds #15's evidence. Not worth building on whether or
not it functions. Note also that the source asserting this syntax could
not be confirmed verbatim when fetched.

## 17. `ERRORS: 0` does not mean no error — check `LINEERROR` independently

**Observed.** Attempt 2 above returned:

```
<LINEERROR>Cannot delete unnamed object: VOUCHER!</LINEERROR>
<CREATED>0</CREATED> <ALTERED>0</ALTERED> <DELETED>0</DELETED>
<ERRORS>0</ERRORS> <CANCELLED>0</CANCELLED> <EXCEPTIONS>0</EXCEPTIONS>
```

Every numeric counter is zero, including `ERRORS`. The operation
completely failed, and the only evidence of that in the response is the
`LINEERROR` element. Attempt 1, which also failed, reported
`ERRORS: 1` — so the counter is not reliably set even between two
failures of the same operation minutes apart.

**Consequence.** A caller that checks `ERRORS` (or any counter) to
decide success would read this response as a clean no-op success.
`TallyAdapter` must treat **the presence of `LINEERROR` as failure
regardless of what the counters say**, rather than checking counters
first and `LINEERROR` only when a counter is non-zero.

**This is #2's pattern via a second, independent mechanism.** #2 showed
a *success* response (`CREATED: 4, ERRORS: 0`) where the data silently
did not land, discovered by read-back. This shows a *failure* response
wearing the same zeros. The shared rule is the one #2 already stated —
the import response is not a trustworthy account of what happened — but
the two are different failure modes and a guard against one does not
catch the other. #2 argues for reading back after a write; #17 argues
for parsing the response more carefully than its counters. Both are
needed.

Tracked for `TallyAdapter`'s response handling as `PENDING:014`.

# Round 5 — Stock item masters and inventory scope (2026-09-16)

Investigate session against issue #28's remaining half: the
inventory-bearing voucher shape and BK-01's stock-item mapping gap.
Starting point was voucher #6 in `Coastal Test Traders` — a stored,
already-posted `Item Invoice` purchase voucher carrying an
`ALLINVENTORYENTRIES.LIST`
(`runs/2026-09-16T02-15-54-voucher-4-readback-after-duplicate`,
lines 8752–10346). One live call, read-only: a `TYPE>StockItem`
collection dump, artifact `runs/2026-09-16T08-45-10-stockitem-master-dump`.
No writes.

## 18. The stock item `Test` is a real master — and near-empty, which is why voucher #6 has no quantity

**Observed.** `Coastal Test Traders` contains exactly **one** stock item:

```xml
<STOCKITEM NAME="Test" RESERVEDNAME="">
  <GUID>e0b7ed19-50af-411d-8919-c29f16ad87ae-000000d2</GUID>
  <PARENT>&#4; Primary</PARENT>
  <ALTERID> 223</ALTERID>
```

So voucher #6's `STOCKITEMNAME: Test` resolves to a backing master.
Tally did **not** create it implicitly on import — the master exists
independently, with its own GUID under the company's GUID prefix. This
closes the question left open in `docs/context.md`: the "implicitly
created on import" possibility is ruled out. `ALTERID 223` against the
voucher's `ALTERID 6` puts the item far later in the company's
alteration sequence than the vouchers, consistent with the
manual-UI-entry reading — but it still does not *prove* provenance, and
nothing in the artifact records who created it.

**The definition is almost entirely unset:**

| Field | Value |
|---|---|
| `BASEUNITS` / `ADDITIONALUNITS` | `<EOT> Not Applicable` — **no unit of measure** |
| `HSNCODE`, `HSN`, `HSNMASTERNAME`, `HSNCLASSIFICATIONNAME` | empty |
| `OPENINGBALANCE`, `OPENINGRATE` | empty; `OPENINGVALUE` `0.00` |
| `DESCRIPTION` | empty |
| `GSTTYPEOFSUPPLY` | `Goods` |
| `COSTINGMETHOD` / `VALUATIONMETHOD` | `Default` |
| `ISBATCHWISEON`, `ISPERISHABLEON`, `IGNOREGODOWNS`, `ISCOSTCENTRESON` | all `No` |

**This explains voucher #6's amount-only line.** That voucher's
`ACTUALQTY`, `BILLEDQTY`, `RATE` and `GSTITEMUQCUOM` are all
present-but-empty, with only `AMOUNT: -18400.00` and a
`BATCHALLOCATIONS.LIST` naming `Main Location` / `Primary Batch`. An
item with no `BASEUNITS` cannot carry a quantity, so Tally stored the
line as a value with no quantity or rate.

**Consequence — voucher #6 is the minimum case, not the representative
one.** It is a valid worked example of the *structural* shape: the
purchase ledger nested inside
`ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST`, the party ledger
at voucher level in `LEDGERENTRIES.LIST` (not `ALLLEDGERENTRIES.LIST`),
`VCHENTRYMODE: Item Invoice`, `ISINVOICE: Yes`. It is **not** evidence
about quantity, rate or UoM handling, because this item cannot exercise
any of it. A real client's stock item will have a unit, and the quantity
and rate fields will be populated and are likely mandatory. Do not
generalise from the empty fields here to "quantity is optional".

### Stock-item master schema, for BK-01

- **Identity:** the `NAME` attribute, plus `LANGUAGENAME.LIST` →
  `NAME.LIST` → `NAME` (an alias list; here it just repeats `Test`, but
  a real client's item can carry several). Invoice-line-text → item
  matching should read the alias list, not only the `NAME` attribute —
  this is BK-02's vendor-to-ledger matching problem again, against stock
  items. `GUID` is the stable key; `ALTERID` is change-tracking — the
  identity-vs-change-tracking distinction finding #15 already drew for
  vouchers holds here too.
- **Hierarchy:** `PARENT` (stock group), `CATEGORY`.
- **Units:** `BASEUNITS`, `ADDITIONALUNITS`, `DENOMINATOR`,
  `CONVERSION`, and `REPORTINGUOMDETAILS.LIST`.
- **GST:** `GSTDETAILS.LIST` → `STATEWISEDETAILS.LIST` →
  `RATEDETAILS.LIST`, keyed by `GSTRATEDUTYHEAD`, each generation dated
  by `APPLICABLEFROM` (`20260401` here) and scoped by `STATENAME`
  (`<EOT> Any` here). Rates are **state-wise and time-sliced** — a real
  client can have per-state rows and several `APPLICABLEFROM`
  generations. Any mapping that treats "the item's GST rate" as a single
  scalar is wrong by construction.
- **HSN:** `HSNDETAILS.LIST`, same `APPLICABLEFROM` + `SRCOF...` shape.
- **Pricing / stock:** `PRICELEVELLIST.LIST`, `FULLPRICELIST.LIST`,
  `BATCHALLOCATIONS.LIST`, `STANDARDCOSTLIST.LIST`,
  `COMPONENTLIST.LIST` (BOM).

## 19. `GSTRATEDUTYHEAD` spells a duty head differently from `GSTDUTYHEAD` — #3's pattern, now cross-master

**Observed.** The stock item's `RATEDETAILS.LIST` entries enumerate:

```
CGST | SGST/UTGST | IGST | Cess | State Cess
```

Finding #3 established that a ledger master's `GSTDUTYHEAD` is validated
against an unknown list, silently dropping unrecognised values — and
that on ledgers the accepted spellings are `CGST` and `State Tax`, with
`Central Tax` discarded. **The same duty head is `SGST/UTGST` on a stock
item and `State Tax` on a ledger.**

**What this changes about #3.** #3 read as a per-field quirk: one field
with a vocabulary we had to discover by probing. It is now confirmed to
be **per-master-type** — the vocabulary differs between master types for
the same underlying concept. A single shared `DUTY_HEADS` constant in
`TallyAdapter`, applied to both ledger and stock-item payloads, would be
silently wrong on one of them, and per #3 and #2 the response would not
say so. Each master type's vocabulary has to be established
independently against a live instance before anything writes to it.

Note that the `RATEDETAILS.LIST` inside voucher #6's inventory entry
uses the stock-item spelling (`SGST/UTGST`), not the ledger one — so the
split is by master type, not by read-vs-write path.

**Also note** the `&#4;` (EOT) sentinels are pervasive in this master —
`<EOT> Not Applicable`, `<EOT> Primary`, `<EOT> Any`,
`<EOT> Applicable`. Same control character finding #1 made a parser
blocker, here carrying *meaningful enum values* rather than incidental
noise, so `sanitise()` must preserve them distinguishably rather than
strip them.

## 20. `SRCOFGSTDETAILS` / `SRCOFHSNDETAILS` — an item's own rate and HSN can be empty by inheritance

**Observed.** Both nested blocks carry a source field, and both read the
same way:

```xml
<GSTDETAILS.LIST>
  <APPLICABLEFROM>20260401</APPLICABLEFROM>
  <SRCOFGSTDETAILS>As per Company/Stock Group</SRCOFGSTDETAILS>
  ... all five RATEDETAILS GSTRATE values are 0 ...

<HSNDETAILS.LIST>
  <APPLICABLEFROM>20260401</APPLICABLEFROM>
  <SRCOFHSNDETAILS>As per Company/Stock Group</SRCOFHSNDETAILS>
  ... no HSNCODE ...
```

The zeros and the absent HSN code are **not** the item's effective
values. They are placeholders for values the item defers upward to its
stock group or the company.

**Consequence — BK-01 cannot resolve a stock item's effective GST rate
or HSN code from the item master alone.** It must read
`SRCOFGSTDETAILS` / `SRCOFHSNDETAILS` first and, when either says
`As per Company/Stock Group`, walk the chain: item → `PARENT` stock
group → company. Combined with #18's state-wise and `APPLICABLEFROM`
dimensions, "the HSN code for this line" is the output of a resolution
over (item, parent chain, state, date), not a field read.

**This is new, previously-unaccounted-for scope.** Finding #7 flagged
stock-item *mapping* as unscoped work comparable to BK-02's
vendor-to-ledger matching. The inheritance chain sits on top of that:
matching an invoice line to an item is one problem, resolving that
item's effective tax attributes is a second, and neither is in BK-01
today. Tracked as `PENDING:015`.

**Not yet established:** what a stock group or company-level GST master
looks like on the wire, or whether the chain can terminate anywhere
other than those two levels. Only the item level has been read.

## 21. Gap 2 RESOLVED — tax ledgers attach at voucher level, as `LEDGERENTRIES.LIST` siblings of the party

Four live calls in the approved order, each read back before the next.
Artifacts `runs/2026-09-16T08-51-12-gap2-step2-*`,
`08-51-46-gap2-step3-*`, `08-52-15-gap2-step4-*`.

### 21a. Marker fields survive a post — `NARRATION` and `REFERENCE` both round-trip

Sent against `Coastal Services Ltd` (disposable per `PENDING:009`) on the
proven accounting-view shape, so the only variable was the markers:

```xml
<NARRATION>GAP2-PROBE-DO-NOT-USE-AS-EVIDENCE</NARRATION>
<REFERENCE>GAP2-PROBE-DO-NOT-USE-AS-EVIDENCE</REFERENCE>
```

`CREATED: 1`, and the read-back returns **both verbatim**. This was worth
testing rather than assuming: `NARRATION` had never been observed
surviving anything in this repo, because the only script that sent one
(`post_voucher.py`) only ever sent it on requests that failed. Under
finding #2's silent-discard pattern, an unverified marker that gets
dropped leaves an *unlabelled* permanent voucher — the exact outcome
marking is supposed to prevent.

**Consequence:** a `NARRATION`/`REFERENCE` marker is a usable
self-identification mechanism for probe vouchers, and — unlike
`VOUCHERNUMBER`, which finding #14 rules out — it is scriptable as a
filter. All three vouchers this probe created carry one.

### 21b. Control — voucher #6's shape reproduces exactly

Posted against `Coastal Test Traders`: `OBJVIEW="Invoice Voucher View"`,
`VCHENTRYMODE: Item Invoice`, `ISINVOICE: Yes`, one
`ALLINVENTORYENTRIES.LIST` (`STOCKITEMNAME: Test`, `AMOUNT -18400.00`,
`BATCHALLOCATIONS.LIST` → `Main Location` / `Primary Batch`,
`ACCOUNTINGALLOCATIONS.LIST` → `Purchase @18%`), party in
`LEDGERENTRIES.LIST` at `+18400.00`. No tax, no quantity, no rate.

`CREATED: 1`, no `LINEERROR`. Read back as voucher 7. A structural diff
against voucher #6 — comparing list nesting, ledger names and amounts —
differs in **exactly one** respect:

```diff
  <AMOUNT>18400.00</AMOUNT>
- <BILLALLOCATIONS.LIST>
- <AMOUNT>18400.00</AMOUNT>
- </BILLALLOCATIONS.LIST>
  </LEDGERENTRIES.LIST>
```

Voucher #6 carries a bill reference (`NAME: 6`, `BILLTYPE: New Ref`) on
the party line; the control does not, because none was sent. Everything
else — including the `LEDGERENTRIES.LIST` spelling — matches.

**This resolves the `LEDGERENTRIES.LIST` vs `ALLLEDGERENTRIES.LIST`
confound.** The spelling voucher #6 stores is the spelling import
accepts, on an invoice-view voucher. Note the existing accounting-view
scripts send `ALLLEDGERENTRIES.LIST` and those vouchers store it too, so
this is view-dependent, not one spelling being globally correct.

### 21c. Candidate 1 is correct — and it was the first one tried

Same payload plus two `LEDGERENTRIES.LIST` siblings of the party for
CGST and SGST, with the party line raised to the gross `21712.00`:

```xml
<LEDGERENTRIES.LIST>
  <LEDGERNAME>CGST</LEDGERNAME>
  <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
  <AMOUNT>-1656.00</AMOUNT>
</LEDGERENTRIES.LIST>
```

`CREATED: 1`, no `LINEERROR`. Read back as voucher 8:

| Container | Ledger / item | Amount |
|---|---|---|
| `ALLINVENTORYENTRIES.LIST` | `Test` | `-18400.00` |
| ` → ACCOUNTINGALLOCATIONS.LIST` | `Purchase @18%` | `-18400.00` |
| `LEDGERENTRIES.LIST` | `Coastal Components Pvt Ltd` | `21712.00` |
| `LEDGERENTRIES.LIST` | `CGST` | `-1656.00` |
| `LEDGERENTRIES.LIST` | `SGST` | `-1656.00` |

The amounts landed exactly as sent and the voucher balances
(`-18400 - 1656 - 1656 + 21712 = 0`).

**Candidates 2 and 3 were not tried and are not needed.** Candidate 1
worked on the first attempt, so nothing further was posted — deliberately,
since every attempt is permanent (finding #16). Candidate 2 (tax inside
`ACCOUNTINGALLOCATIONS.LIST`) and candidate 3 (no explicit tax ledgers,
letting Tally infer from the item's `GSTDETAILS`) remain untested; #3 in
particular was expected to produce zero tax here, because per finding #20
the `Test` item defers its rates upward and they resolve to `0`.

**The pre-flight risk analysis held.** Structural guesses were predicted
to fail cleanly rather than land wrong data, on the strength of variants
D/E returning `EXCEPTIONS: 1` with nothing created. No wrong-shape post
was actually needed to test that prediction, so it remains a prediction —
three for three succeeded.

### What this does and does not establish

**Established:** the structural placement of tax ledgers on an
inventory-bearing purchase voucher, verified by read-back rather than by
the response counters (findings #2 and #17).

**Not established — the amounts here were supplied, not computed.** CGST
and SGST were sent as explicit `1656.00` values and stored verbatim. This
probe says nothing about whether Tally would *derive* the correct tax
from the stock item's own GST configuration, which is what candidate 3
would have tested and what a real client's voucher may depend on. Per
finding #20 that derivation requires the item → stock group → company
inheritance chain, none of which is exercised here.

**Also not established:** anything about quantity, rate or unit of
measure. The `Test` item has no `BASEUNITS` (finding #18), so both
vouchers this probe created carry empty `ACTUALQTY`/`BILLEDQTY`/`RATE`,
exactly as voucher #6 does. A voucher for an item that *has* a unit is
still untested, and remains the most likely place for a further
surprise.

### Sandbox state after this probe

`Coastal Test Traders` now holds **8** vouchers: 1–5 from
`voucher_variants.py` (finding #7 as corrected), 6 unattributed, and
**7 and 8 from this probe**, both marked
`GAP2-PROBE-CONTROL-DO-NOT-USE-AS-EVIDENCE` and
`GAP2-PROBE-TAX-DO-NOT-USE-AS-EVIDENCE` respectively in both `NARRATION`
and `REFERENCE`. `Coastal Services Ltd` gained one, marked
`GAP2-PROBE-DO-NOT-USE-AS-EVIDENCE`. None can be deleted (finding #16);
all three are unambiguously identifiable as test artifacts by any future
reader or script.

# Round 6 — Master creation and deletion (2026-09-16)

Investigate session against issue #28's two remaining cases (tax
derivation via #20's inheritance chain, and an item with a unit of
measure). Both need a stock item that does not exist in either sandbox,
so the session opened with a deletability probe — establishing whether
master experimentation is one-shot or iterative before spending any
budget on the harder GST-vocabulary question.

The probe never reached the question it was designed to answer. It
crashed TallyPrime instead. Artifacts:
`runs/2026-09-16T09-01-57-delprobe-*`, `09-02-27-*`.

Two read-only collection dumps earlier in the same session established
the setup facts: `Coastal Test Traders` has **zero `Unit` masters and
zero `StockGroup` masters**. That is why `Test` carries
`BASEUNITS: <EOT> Not Applicable` — there was never a unit to pick — and
it is directly why step 1 below failed.

## 22. `ACTION="Delete"` for a nonexistent master crashes TallyPrime — CRITICAL, escalates #13

**Severity note.** This is not a restatement of #13. #13 was a malformed
*read* raising a modal dialog that blocked the HTTP listener, recoverable
by dismissing it at the console. This is a **well-formed write** causing
a memory access violation that terminates the process. Different trigger,
different failure mode, worse outcome.

### The exact sequence

**Step 1 — `ACTION="Create"` with an invalid `PARENT`: failed clean.**

```xml
<STOCKITEM NAME="CAOS-PROBE-DELETE-ME-NOT-EVIDENCE" ACTION="Create">
  <NAME>CAOS-PROBE-DELETE-ME-NOT-EVIDENCE</NAME>
  <PARENT>Primary</PARENT>
</STOCKITEM>
```

```
<LINEERROR>Stock Group 'Primary' does not exist!</LINEERROR>
<CREATED>0</CREATED> <ERRORS>0</ERRORS> <EXCEPTIONS>1</EXCEPTIONS>
```

The bare word `Primary` was wrong. The `Test` item reads back
`PARENT: <EOT> Primary`, where the `&#4;` prefix marks a **sentinel, not
a name** — and the `TYPE>StockGroup` dump from earlier in the same
session had already shown the company has no stock groups at all. The
evidence to predict this failure was in hand and was not applied to the
payload.

Note `ERRORS: 0` on a total failure — **finding #17 again**, third
independent occurrence. `LINEERROR` was the only signal.

**Step 2 — dump: confirms nothing was created.** Exactly one stock item,
`Test`. This matters for what follows: step 3 therefore targeted a name
that **did not exist**.

**Step 3 — `ACTION="Delete"` on that nonexistent stock item: hung.**

```xml
<STOCKITEM NAME="CAOS-PROBE-DELETE-ME-NOT-EVIDENCE" ACTION="Delete" />
```

No response. Timed out at 30s. **Step 4** (an ordinary read) also timed
out at 30s. Neither run folder has a `response.xml` — the timeout is the
evidence.

**Step 5 — diagnosis at the console.** `tally.exe` was still running and
port 9000 still `LISTENING`, with a `CLOSE_WAIT` socket — which initially
looked like #13's blocking-dialog pattern. It was not. The TallyPrime
window showed:

```
Internal Error. Contact Tally Solutions.
Software Exception c0000005 (Memory Access Violation)
```

A genuine application crash. **A full restart was required**; dismissing
a dialog was not sufficient.

**Recovery was clean.** After restart, a single read-only stock-item dump
returned `200` in 43ms and was **byte-identical** to the same call made
earlier that day — same GUID, same `ALTERID 223`, same fields. No data
loss, no corruption, and the failed create left no residue.

### The contrast with #16 is the point

| | Nonexistent VOUCHER | Nonexistent STOCKITEM |
|---|---|---|
| Request | `ACTION="Delete"` | `ACTION="Delete"` |
| Envelope | `Import Data` | `Import Data` |
| Result | `Voucher does not exist!` | **process crash, c0000005** |
| Time | 0.1s | 30s timeout, then dead |
| Recovery | none needed | full restart |

Same API, same envelope shape, a delete against a target that isn't
there — and one returns a clean diagnostic while the other kills the
process. The object type is the only variable. There is no way to
predict which behaviour a given master type has except by finding out,
and finding out is what crashes it.

### Consequence for `TallyAdapter` — mandatory, not defensive hygiene

**Never send `ACTION="Delete"` for a master without first confirming the
target exists via a read.** Not a nice-to-have guard: on the practice's
deployment every client company runs in one Tally Cloud instance (ADR
0001, TC-01), so a single delete against a stale or mistyped master name
takes the integration down **for every client on that instance**, and
recovery needs a human with console access to restart the application.

This composes badly with two things already known:

- **#2 and #3.** A master's state cannot be trusted from a write
  response, so "I created it, therefore it exists" is not a safe premise
  for a later delete. The existence check has to be a real read, not an
  inference from an earlier `CREATED: 1`.
- **#13's consequence 3.** A health check must distinguish *unreachable*
  from *unresponsive*. This adds a third state: **dead but still
  listening.** The port stayed `LISTENING` on a crashed process, so a
  TCP-connect health check would have reported Tally healthy. TC-05 needs
  a real request-response round trip with a timeout, not a socket probe.

### Worth reporting upstream

A `c0000005` from a delete-on-nonexistent-master is plausibly
reproducible on any TallyPrime instance and is not specific to this
sandbox or to Educational Mode. Nothing in the payload was malformed —
it mirrors the documented master-delete pattern from #16
(`<LEDGER NAME="ICICI" ACTION="Delete">`) exactly, with the object type
changed. This looks like an application bug worth reporting to Tally
Solutions directly, separate from anything `TallyAdapter` can work
around. Tracked as `PENDING:016`.

### What remains unanswered

**Stock-item deletability is still unknown.** The probe was designed to
answer it and did not: the delete targeted a name that did not exist, so
it tested the nonexistent-target path, not the delete path. Whether a
**real** stock item can be deleted by name — the question that decides
whether master experimentation is iterative or one-shot — is exactly as
open as it was before, and is now more expensive to ask.

A corrected attempt needs, in order: resolve the parent problem (create a
stock group first, or establish how the `<EOT>` sentinel must be sent),
create the item, **read it back to confirm it exists**, and only then
attempt the delete. The existence check is no longer a matter of rigour;
#22 is the reason it is mandatory.
