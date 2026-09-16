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

## 16. Voucher delete — two addressing schemes refused — CONCLUSION OVERTURNED 2026-09-16

> ### ⚠️ Correction (2026-09-16) — the conclusion in this finding's title was wrong
>
> **The observation below stands:** the two addressing schemes tried
> here (`REMOTEID`+`VCHKEY`, and `MASTERID` as a child element) were
> both refused, exactly as recorded.
>
> **The conclusion drawn from it — that vouchers cannot be deleted
> through the XML import API — is WRONG.** They can. A delete using
> `TAGNAME="VoucherNumber"` with a `dd-Mmm-yyyy` attribute date and a
> non-empty body succeeded cleanly on 2026-09-16: `DELETED: 1`, voucher
> count 5 → 4, no renumbering, and the financial effect reconciled
> exactly. See **#28**.
>
> **Why this finding got it wrong, stated plainly so it is not
> repeated.** It *did* identify `TAGNAME`/`TAGVALUE` — see "A third
> scheme was identified and deliberately not tested" below — and
> declined to test it on the grounds that it addresses by
> `VOUCHERNUMBER`, which #14 proved is Tally-assigned and not ours to
> rely on.
>
> **That reasoning was sound about the wrong question.** It is a good
> argument against *building a durable mechanism* on `VOUCHERNUMBER`.
> It is not evidence about *whether the API accepts that addressing at
> all* — and the finding treated the first as settling the second.
>
> **The distinction to keep:** "this identifier is unsuitable for our
> architecture" and "this request shape is rejected by Tally" are
> independent claims. Conflating them turned a design preference into a
> false capability limit that stood in this file, in the schema
> reference and in `PENDING:009` for a day.


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

# Round 7 — Financial reports and voucher lifecycle (2026-09-16)

Investigate session, read-only. Standard financial reports had never
been attempted — the reference covered Day Book reads, ledger and
stock-item masters, and voucher posting, and nothing else.

About fifteen read-only requests, no writes, no hangs. Artifacts:
`runs/2026-09-16T09-30-00-report-reads`.

**Documentation was useful here, which is worth noting against #4.**
That finding established the TDL Reference Manual as a dead end *for GST
field questions* because it predates GST. Report names and voucher
lifecycle are older than GST, and the same documentation answers both
cleanly. #4's conclusion should be read as scoped to GST-era fields, not
as "the documentation is useless."

## 23. Standard financial reports read cleanly via `TYPE: DATA`

Same envelope as the verified Day Book read (#11); only `<ID>` changes.

| `ID` | Result | Size |
|---|---|---|
| `Day Book` *(control)* | ✅ | 486 KB |
| `Trial Balance` | ✅ | 523 B |
| `Balance Sheet` | ✅ | 923 B |
| `Profit and Loss` | ✅ | 654 B |
| `Stock Summary` | ✅ | 238 B |
| `Profit & Loss` | ❌ `Could not find Report` | 214 B |

**The report is named `Profit and Loss`, spelled out.** `Profit & Loss`
fails even when correctly escaped as `Profit &amp; Loss`. Sent with a
raw `&` it fails differently — see #25.

`SVCURRENTCOMPANY` is required and validated. `SVFROMDATE`/`SVTODATE`
are honoured (see the methodology note below). `SVEXPORTFORMAT` is
accepted.

### Structure: a display layer, not a data API

Responses are `DSP*`-prefixed **display** structures:

```xml
<DSPACCNAME><DSPDISPNAME>Purchase Accounts</DSPDISPNAME></DSPACCNAME>
<DSPACCINFO>
  <DSPCLDRAMT><DSPCLDRAMTA>-147200.00</DSPCLDRAMTA></DSPCLDRAMT>
  <DSPCLCRAMT><DSPCLCRAMTA></DSPCLCRAMTA></DSPCLCRAMT>
</DSPACCINFO>
```

Three limitations, all structural:

1. **Group-level rollups only — no ledger drill-down.** Trial Balance
   returned `Current Liabilities` and `Purchase Accounts`, not the
   individual ledgers beneath them. Whether any parameter exposes
   ledger-level detail is untested.
2. **Name and value are positionally coupled, not nested.**
   `DSPACCNAME` and `DSPACCINFO` are *siblings* that must be zipped by
   document order. A parser that loses ordering silently mismatches
   names to amounts.
3. **Each report has its own vocabulary.** `BSNAME`/`BSAMT` for Balance
   Sheet, `PLAMT`/`BSMAINAMT` for P&L, `DSPSTKINFO`/`DSPCLQTY` for Stock
   Summary. There is no shared schema; each needs its own parser.

### Verified by reconciliation, not by a single read-back

Because this sandbox's entire contents are known, five independent
report figures could be checked against the posted vouchers
arithmetically:

| Report figure | Reconciles to | ✓ |
|---|---|---|
| Purchase Accounts `-147,200` | 8 vouchers × 18,400 | ✅ |
| Current Liabilities `163,760` Cr | 18,400 + (4 × 21,712) + 18,400 + 18,400 + 21,712 | ✅ |
| Duties & Taxes `-16,560` Dr | 5 taxed vouchers × 3,312 | ✅ |
| Stock Summary `Test` `-55,200` | 3 inventory vouchers × 18,400 | ✅ |
| P&L Cost of Sales `-92,000` | 147,200 − 55,200 | ✅ |

**This is a stronger verification than Rule 1's read-back, and the
difference is worth stating as method.** A read-back confirms that what
was written can be read again — it shares the write path's assumptions,
so a systematic error in those assumptions survives it. Reconciliation
checks *derived aggregates computed by Tally itself* against
independently-known inputs. Five figures from four separate reports all
tying out cannot easily be a coincidence of a shared bug.

**It also independently corroborates two earlier findings.** The
`147,200` total requires all eight vouchers to have posted, including
the five that #7's original text recorded as having failed — so the #7
correction is confirmed from a second direction. The `55,200` stock
figure requires exactly the three inventory-bearing vouchers to carry
stock value, confirming #21's structure landed as intended.

**Where reconciliation is available, prefer it.** For a real client it
usually will not be, and Rule 1 remains the fallback.

### Methodology note — a test that could not distinguish its hypotheses

The date-range question was initially answered wrongly. Full-year,
single-day and no-dates requests all returned **identical** output,
which reads as "`SVFROMDATE`/`SVTODATE` are ignored."

They are not. Every voucher in this company is dated `20260801`, so all
three ranges close *after* every transaction — identical closing
balances are the correct result in all three cases, and the test could
not have distinguished "dates ignored" from "dates honoured." Requesting
**`20260401`–`20260701`**, ending before any transaction, returns
`<ENVELOPE></ENVELOPE>`. Dates are honoured.

Same class of error as #15's voucher-1-vs-2 mix-up, and the same lesson:
**an asserted condition is a hypothesis about the evidence, not a fact
about it.** Here the flaw was subtler — the test ran correctly and the
data was real; the *discriminating power* was absent. Check that a test
can distinguish its hypotheses before trusting a negative result.

## 24. Report sign convention inverts the voucher convention — DATA CORRUPTION RISK

**In report output, a debit is a negative number.**

```
Purchase Accounts   <DSPCLDRAMTA>-147200.00</DSPCLDRAMTA>   (a DEBIT balance)
Current Liabilities <DSPCLCRAMTA>163760.00</DSPCLCRAMTA>    (a CREDIT balance)
```

At voucher level the convention is the opposite composite:
`ISDEEMEDPOSITIVE=Yes` **with a negative `AMOUNT`** is a debit; `No`
with a positive amount is a credit (§4.3). There, sign is one half of a
two-field encoding. In reports, **sign alone carries direction**, and it
carries it the other way round.

**Stated plainly: a parser that assumes one convention holds everywhere
will invert the books.** It will not error, and per #23 the figures look
entirely plausible. Debit/credit direction must be decoded per response
type — voucher entries by `ISDEEMEDPOSITIVE` + sign, report figures by
the containing element (`DSPCLDRAMT` vs `DSPCLCRAMT`) with sign treated
as magnitude-plus-convention, never as direction on its own.

Note the element names already state direction — `...DRAMT` vs
`...CRAMT`. **Trust the element, not the sign.**

## 25. Read failures are clean and self-describing — the read side can be trusted

Three distinct failure shapes, each naming itself:

```xml
<!-- unknown report name -->
<STATUS>0</STATUS> <LINEERROR>Could not find Report 'Profit &amp; Loss'!</LINEERROR>

<!-- company that does not exist -->
<STATUS>0</STATUS> <LINEERROR>Could not set 'SVCurrentCompany' to 'No Such Company Xyz'</LINEERROR>

<!-- malformed XML (raw & in the ID) -->
<RESPONSE>Unknown Request, cannot be processed</RESPONSE>
```

Successful reads carry `STATUS 1`, or for report responses no `HEADER`
at all. **Across roughly fifteen probes, `STATUS` and `LINEERROR` agreed
with reality every time.**

### This is NOT Rule 2 — it is close to its opposite

Rules 1–3 are all **write-side**: import responses misreport what
happened, and per #17 `ERRORS: 0` can accompany total failure. **That
does not generalise to reads.**

| | Write path (`Import Data`) | Read path (`EXPORT`) |
|---|---|---|
| Success signal | counters — **unreliable** (#2, #17) | `STATUS` — reliable in testing |
| Failure signal | `LINEERROR`, counters may all be `0` | `STATUS 0` + named `LINEERROR` |
| Silent wrong result | **yes** — #2, #3 discard values silently | not observed for `TYPE: DATA` |

**Do not over-generalise "nothing in Tally's responses can be trusted."**
The write path cannot be trusted; the read path's own status reporting
can, so far. Read-back verification works *because* reads are more
trustworthy than writes — if reads were equally unreliable, Rule 1 would
be worthless.

**One important exception remains: `TYPE: COLLECTION` pointed at
vouchers returns zero rows with no error** (#11). That is a read-side
silent failure. So the claim is scoped: **`TYPE: DATA` reads report
their own failures reliably; `COLLECTION` reads do not.**

### Consequence: report-name discovery is safe to do empirically

An unknown report name produces a named error, not a hang and not a
silent zero. The caution #13 imposed on constructing requests
dynamically **applies to `COLLECTION`/TDL, not to `TYPE: DATA` report
names.** Exploring the rest of Tally's report surface is low-risk.

## 26. `ACTION="Cancel"` works — and the `CANCELLED` counter does not track it

Originally written as a documentation-only lead. Tested live on
2026-09-16 under explicit authorisation. Artifacts:
`runs/2026-09-16T09-55-00-cancel-attempt-1-empty`,
`runs/2026-09-16T10-05-00-cancel-attempt-2-success`.

### Documentation, which was right

Tally's help documentation states that deleting removes a voucher
entirely with no trace, while **cancelling keeps it visible and marks it
Cancelled**, and that the Marked Voucher Register includes cancelled but
not deleted vouchers. Addressing for alter/cancel/delete is by
`TAGNAME`/`TAGVALUE` **attributes** on `<VOUCHER>` with a mandatory date.

### Attempt 1 — rejected for being empty

```xml
<VOUCHER DATE="20260801" TAGNAME="MASTER ID" TAGVALUE="4"
         ACTION="Cancel" VCHTYPE="Purchase" />
```
```
<LINEERROR>Cannot process 'empty' object: VOUCHER!</LINEERROR>
<ERRORS>0</ERRORS> <CANCELLED>0</CANCELLED>
```

Nothing changed; the read-back was identical. Note `ERRORS: 0` on a
total failure — **#17's pattern, fourth occurrence.**

**Method note — the minimal-payload trap, second instance.** The element
was deliberately empty so that nothing could partially land (Rule 1's
concern). That instinct is correct about partial landing and wrong about
*reaching the test*: a minimal payload has more ways to be rejected
outright, and a rejection before the interesting code path teaches
nothing about it. **#22's stock-item create failed the same way** — on
`PARENT: Primary`, before `ACTION="Delete"` was ever exercised. Twice in
one day a probe was defeated by payload shape rather than by the
question it was asking. **Mirror a documented working example and change
one variable, rather than stripping to a minimum.**

### Attempt 2 — succeeded

Mirroring Tally's own documented cancel example, changing only company,
date, voucher number and type:

```xml
<VOUCHER DATE="01-Aug-2026" TAGNAME="VoucherNumber" TAGVALUE="4"
         ACTION="Cancel" VCHTYPE="Purchase">
  <NARRATION>GAP2-CANCEL-PROBE-DO-NOT-USE-AS-EVIDENCE</NARRATION>
</VOUCHER>
```

Three things attempt 1 got wrong: the empty body, `TAGNAME="MASTER ID"`
(unproven spelling), and a `YYYYMMDD` date where the **attribute**
position takes `dd-Mmm-yyyy`. Every other date in this repo is
`YYYYMMDD` as a *child element*, and that remains correct there.

**Read-back — voucher 4 after cancel:**

| Field | Before | After |
|---|---|---|
| `ISCANCELLED` | `No` | **`Yes`** |
| `ALTERID` | 4 | **7** (company-wide, per #15) |
| Ledger entries | 4 | **0** — all stripped |
| Present in Day Book | yes | **yes** — still 5 vouchers |

Exactly what the documentation described: visible, marked, valueless.

### The `CANCELLED` counter read `0` on a successful cancel

```
<ALTERED>1</ALTERED>  <CANCELLED>0</CANCELLED>  <ERRORS>0</ERRORS>
```

**The counter named after the operation did not move. `ALTERED` did.**

**This is a new failure direction and deserves its own weight.** Findings
#2, #3 and #17 all describe responses that **hide failure** — a discard
reported as success, an enum silently dropped, `ERRORS: 0` on a total
failure. This one **hides success**. A caller checking `CANCELLED` — the
obvious field — concludes the cancel failed, sees no error anywhere, and
is wrong.

Rule 1's read-back catches it. Nothing else does. And note `DELETED: 1`
*was* accurate on the delete an hour later (#28) — same session, same
envelope, one counter truthful and one not. **No rule can be extracted
about which counters to trust; the answer is none of them, individually.**

The `CANCELLED` counter now has no known trigger. This finding
originally assumed it corresponded to this operation. It does not.

### Reconciliation confirmed the financial effect

Per #23's method, against `Coastal Services Ltd`'s Trial Balance:

| Figure | After cancel | Expected |
|---|---|---|
| Purchase Accounts | `-73,600` | 4 × 18,400 ✅ |
| Current Liabilities Cr | `86,850` | 21,714 + (3 × 21,712) ✅ |
| Duties & Taxes Dr | `-13,250` | (4 × 3,312) + 2 ✅ |

**The stray `+2` is a useful control.** It is voucher 1's `21,714` — the
amount #15's edit test produced. Its presence confirms the reconciliation
is measuring the right company *and* that #15's evidence voucher was
undisturbed by this probe, which is the one voucher in that company that
must not be touched.

### For `TallyAdapter`

Cancel is the right primitive for a void/correction path: it preserves
the audit trail that deletion destroys, which is what a CA practice
needs for BK-07 corrections.

Two caveats before it is adapter-ready:

- **Addressing used `TAGNAME="VoucherNumber"`**, which #14 rules out as
  a durable identifier. It was safe here because the read was seconds
  old and nothing wrote in between. **`TAGNAME="MASTER ID"` is what an
  adapter should use, and it is untested** — attempt 1 used it but died
  on the empty-body error before addressing was exercised.
- **Success must be confirmed by read-back**, given the counter above.

## 27. Master type catalogue — 34 types, two documented

Every response's `CMPINFO` block enumerates Tally's master types. This
is an **inventory of what types exist, not confirmation any are
populated** — per #5 the `CMPINFO` numbers are not counts.

**Likely relevant to CAOS:** `GROUP`, `LEDGER`, `COSTCATEGORY`,
`COSTCENTRE`, `GODOWN`, `STOCKGROUP`, `STOCKCATEGORY`, `STOCKITEM`,
`VOUCHERTYPE`, `CURRENCY`, `UNIT`, `BUDGET`, `TAXUNIT`,
`GSTCLASSIFICATION`, `VOUCHERNUMBERSERIES`, `TDSRATE`, `DEDUCTEETYPE`,
`COMPANY`

**Legacy, probably dead:** `FBTCATEGORY`, `FBTASSESSEETYPE`,
`EXCISEDUTYCLASSIFICATION`, `TARIFFCLASSIFICATION`, `LBTCLASSIFICATION`,
`STCATEGORY`, `ADJUSTMENTCLASSIFICATION`

**Documented, never touched:** `CLIENTRULE`, `SERVERRULE`, `STATE`,
`SERIALNUMBER`, `ATTENDANCETYPE`, `INCOMETAXSLAB`,
`INCOMETAXCLASSIFICATION`, `RETURNMASTER`, `TAXCLASSIFICATION`

**Only `LEDGER` and `STOCKITEM` are documented in the schema
reference.** `UNIT` and `STOCKGROUP` were read and confirmed empty
(#22's setup) but never created. Everything else is unexplored.

Nearest-term relevance: **`GODOWN`** and **`STOCKGROUP`** both appear in
voucher #6's inventory structure, and `STOCKGROUP` is the specific
blocker on a corrected stock-item create (#22).

### There is no fixed-asset register report

Stated plainly so it does not read as unexplored: **Tally has no
dedicated asset-register report.** Fixed assets are a *group* within the
Balance Sheet, not a separate report, so there is no report name to
call. `Coastal Test Traders` has no such group, so its Balance Sheet
shows none. Asset data would come from a Balance Sheet read or a
group-scoped ledger collection — neither attempted.

## Sources

Documentation consulted for #26 and the report names in #23. Cited
because these findings rest partly on documentation rather than purely
on observation, which is unusual for this file:

- [Understanding Integration — Reports](https://help.tallysolutions.com/developer-reference/introduction/understanding-integration-reports/) — `TYPE: DATA` + `ID` as TDL report name
- [Cancel/Delete Voucher in TallyPrime](https://help.tallysolutions.com/cancel-einv-ewb-voucher-delete/) — Cancel vs Delete semantics
- [Objects and Collections in TDL](https://help.tallysolutions.com/developer-reference/tally-definition-language/objects-and-collections/) — master object types

Everything in #23–#25 and #27's catalogue was observed live; only #26 is
documentation-only, and it says so.

# Round 8 — Voucher lifecycle, live (2026-09-16)

Three authorised mutations against `Coastal Services Ltd`, each with a
documentation pre-flight, an existence-check read, a payload checkpoint
and an immediate read-back. Two cancel attempts (#26) and one delete
(#28). Nothing sent to `Coastal Test Traders`.

## 28. Vouchers CAN be deleted — #16's conclusion overturned

Artifact: `runs/2026-09-16T10-15-00-delete-attempt-success`.

**The payload was #26's proven cancel shape with two changes** —
`ACTION` `Cancel` → `Delete`, and a different target. One variable of
interest, per #13's minimum-deviation discipline:

```xml
<VOUCHER DATE="01-Aug-2026" TAGNAME="VoucherNumber" TAGVALUE="3"
         ACTION="Delete" VCHTYPE="Purchase">
  <NARRATION>GAP2-DELETE-PROBE-DO-NOT-USE-AS-EVIDENCE</NARRATION>
</VOUCHER>
```

**Response, 112ms, no `LINEERROR`:** `DELETED: 1`, every other counter
`0`.

### Read-back — voucher 3 is gone, and nothing else moved

**Voucher count 5 → 4.**

| Vch | `MASTERID` | `ALTERID` | `REMOTEID` | |
|---|---|---|---|---|
| 1 | 1 | 5 | `...00000001` | unchanged — #15's evidence |
| 2 | 2 | 2 | `...00000002` | unchanged |
| ~~3~~ | — | — | — | **deleted** |
| 4 | 4 | 7 | `...00000004` | cancelled earlier (#26) |
| 5 | 5 | 6 | `...00000005` | unchanged |

**No renumbering.** Survivors kept their voucher numbers *and* their
`REMOTEID`s — the sequence has a hole at 3 rather than closing up. This
matters: a delete does not invalidate identifiers held for other
vouchers, so a reset loop can delete by number without re-reading
between iterations.

### Reconciliation — exact

| Trial Balance | After | Expected (vouchers 1, 2, 5 live) |
|---|---|---|
| Purchase Accounts | `-55,200` | 3 × 18,400 ✅ |
| Current Liabilities Cr | `65,138` | 21,714 + 21,712 + 21,712 ✅ |
| Duties & Taxes Dr | `-9,938` | (3 × 3,312) + 2 ✅ |

Voucher 3 is fully and correctly out of the books.

### `DELETED: 1` was accurate — which proves nothing general

An hour earlier `CANCELLED: 0` accompanied a successful cancel (#26).
Here `DELETED: 1` accompanied a successful delete. **Same session, same
envelope, same response shape — one counter truthful, one not.** There
is no rule here about which counters to trust. The rule remains Rule 1:
read back.

### Consequences

**`PENDING:009` is no longer blocked on capability.** A scripted sandbox
reset is now possible — enumerate the Day Book, delete each voucher by
`TAGNAME="VoucherNumber"`. The capability is proven; **the script does
not exist**, and that is the remaining work.

**The "every test voucher is permanent, mark them all" discipline was
stricter than necessary** — though it cost little and the markers remain
useful. Probe vouchers can now be cleaned up.

**Cancel and delete are different operations with different uses.**
Delete removes; cancel neutralises while preserving an audit trail
(#26). For `TallyAdapter`'s BK-07 correction path, **cancel is the
appropriate primitive** — a CA practice should not be silently removing
posted vouchers. Delete belongs to test-fixture management, not to
production book-keeping.

**CG7 is unaffected.** #9 showed Tally does not prevent duplicate
posting; that is unchanged, and the platform-side duplicate check
remains necessary.

## Hypothesis, NOT tested — #22's crash may also be an addressing artifact

**This is a hypothesis recorded for a future session. It was not tested
today, was not authorised today, and is not scheduled.**

#22 crashed TallyPrime with `c0000005` deleting a **stock item that did
not exist**, addressed as `<STOCKITEM NAME="..." ACTION="Delete" />`.
Today established that for **vouchers**, `NAME=`-style and child-element
addressing are both refused while `TAGNAME`/`TAGVALUE` works. #16 and
#22 therefore share a property: both used addressing now known to be
wrong for vouchers.

So it is *possible* that master deletion also wants `TAGNAME`/`TAGVALUE`
against a verifiably-existing target, and that #22's crash was the
combination of wrong addressing and an absent target rather than a
fundamental limit.

**Today's good results do not change #22's risk profile, and are not a
reason to test this now.** Specifically:

- #22's crash is **real and reproduced nothing** — it cost a full
  application restart, not a clean error.
- **Masters and vouchers demonstrably behave differently on delete.**
  A nonexistent *voucher* delete returns `Voucher does not exist!` in
  0.1s (#16); a nonexistent *master* delete crashes the process (#22).
  Evidence from the voucher path does not transfer to the master path —
  that non-transfer is exactly what #22 established.
- The one condition #22's attempt could not satisfy — a target that
  actually exists — still cannot be satisfied, because creating a stock
  item is itself blocked on the stock-group question (#22).

**If revisited, it needs a fresh session, its own authorisation, and its
own pre-flight** — resolve the parent/stock-group problem, create a
master, confirm it exists by read, and only then attempt a
`TAGNAME`-addressed delete. Not formalised as a `STUB_ISSUES` row yet;
noted there as a candidate.

# Round 9 — Reset-script validation (2026-09-16)

Build session closing out `PENDING:009`. The keep-list audit earlier in
this session established that **every voucher in both sandbox companies
is cited by at least one finding** — `Coastal Services Ltd` 1, 2, 4, 5
and `Coastal Test Traders` 1–8 — so `reset_sandbox.py`'s `--confirm`
path had no target it could be validated against without destroying
evidence. A voucher was posted for the sole purpose of being deleted.

Artifacts: `runs/2026-09-16T10-26-48-pending009-1` … `-5`,
`10-27-08-reset-delete-6`, `10-27-08-reset-readback-6`,
`10-27-19-pending009-6-final-daybook`, `-7-final-tb`.
Scripts: `pending009_validate.py` (post + reads only, never deletes) and
`reset_sandbox.py` (the delete).

## 29. `reset_sandbox.py`'s delete path works end to end — PENDING:009 closed

**The sequence, in order, with the gate between steps 2 and 3 honoured.**

| # | Step | Result |
|---|---|---|
| 1 | Post, marked `PENDING009-VALIDATION-DELETE-ME` | `CREATED: 1`, `LASTVCHID: 7`, 168ms |
| 2 | Read back (Rule 1) | stored as **voucher 6**, marker verbatim in `NARRATION` |
| 3 | `reset_sandbox.py` dry run | **1 DELETE (voucher 6), 4 KEEP, 0 SKIP** — zero `Import Data` sent |
| 4 | `reset_sandbox.py --confirm` | `DELETED: 1`, no `LINEERROR`, 140ms; script's own read-back confirmed absence; exit 0 |
| 5 | Independent Day Book + Trial Balance | count 4, validation voucher gone, survivors untouched |

The payload was #21a's accounting-view shape with **only values
changed** — the marker, and distinct amounts (1000 / 90 / 90 / 1180
rather than the usual 18400 / 1656 / 1656 / 21712) chosen so the report
delta could not be confused with vouchers 2 or 5, whose figures are
identical to each other.

### Reconciliation — the Trial Balance returned exactly to baseline

Per #23's method, and it is the check that makes this conclusive rather
than merely consistent:

| Figure | Before post | After post | After delete |
|---|---|---|---|
| Purchase Accounts Dr | `-55,200` | `-56,200` | **`-55,200`** ✅ |
| Current Liabilities Dr | `-9,938` | `-10,118` | **`-9,938`** ✅ |
| Current Liabilities Cr | `65,138` | — | **`65,138`** ✅ |

The post moved Purchase by exactly `1,000` and Duties by exactly `180`
(90 + 90); the delete moved both back. **The delete removed exactly the
voucher that was added and nothing else** — established from derived
aggregates Tally computed itself, not from the read path that wrote it.

### Survivors — nothing moved

All four checked field-by-field against the pre-post baseline:

| Vch | `ALTERID` | `REMOTEID` | Amounts |
|---|---|---|---|
| 1 | 5 → 5 | unchanged | unchanged |
| 2 | 2 → 2 | unchanged | unchanged |
| 4 | 7 → 7 | unchanged | unchanged |
| 5 | 6 → 6 | unchanged | unchanged |

This extends #28, which showed a delete does not renumber survivors, to
a full **post-and-delete cycle**: the validation voucher carried
`ALTERID 10`, so the company-wide sequence (#15) advanced past 7, 8, 9
and 10 while all four survivors held their own values. A voucher's
`ALTERID` is untouched by other vouchers' lifecycles, not merely by
their edits.

### `DELETED: 1` was accurate again — and this still establishes no rule

Second accurate `DELETED` counter in two attempts. Set against #26's
`CANCELLED: 0` on a successful cancel, the position is unchanged: the
counters are not individually trustworthy, and Rule 1's read-back is
what decided this run. Had the counter lied in either direction here,
the script would have caught it — `LINEERROR` is checked independently
of every counter (#17), and absence is confirmed by a fresh read.

### New, and it contradicts a natural assumption: `REMOTEID`'s trailing counter is not the voucher number

The validation voucher stored as **voucher 6** but carries
`REMOTEID`/`GUID` suffix **`-00000007`**, matching the `LASTVCHID: 7` in
the import response rather than its own voucher number.

Every previously observed voucher in this company had suffix == number
(1→1, 2→2, 4→4, 5→5), which made the two look interchangeable. They are
not. The suffix follows an internal creation counter that #28's delete
of voucher 3 had already advanced past. **Consequence for
`TallyAdapter`:** never derive one identifier from the other in either
direction. #15 established `REMOTEID` as the correlation field and #14
ruled out `VOUCHERNUMBER`; this adds that they are independent values
which merely coincided in the sandbox's early, gap-free state.

### `PENDING:009` is closed

The capability was proven by #28; the script now exists, and its
destructive path is validated against a live delete. The remaining
limits are recorded rather than open: masters still cannot be reset
through the API (#22), and both companies' keep-lists
(`keep-coastal-services.txt`, `keep-coastal-test-traders.txt`) currently
protect every voucher they contain, so the script has no routine work to
do until new debris accumulates.
