# CAOS — TallyPrime XML Integration Schema Reference

**Status:** point-in-time, 2026-09-16. Compiled from Phase 0 spike P0-02.
**Source of truth:** `spikes/p0-02-tally/FINDINGS.md` (findings #1–#32).
**Evidence:** every claim traces to a run artifact under `spikes/p0-02-tally/runs/`.

This document is a **navigable view over FINDINGS.md**, organised by area
rather than by the order things were discovered. It does not replace it.
Where the two disagree, FINDINGS.md wins — it carries the evidence and
the reasoning; this carries the conclusions.

Everything here was **observed against a live instance**, not taken from
documentation. That distinction matters here more than usual: per **#4**
the canonical TDL Reference
Manual predates GST entirely and cannot answer a GST field question, and per
**#12** Tally reports import failures with no diagnostic detail
anywhere. Reading the wire is the only method available.

## How to read this document

Every claim carries a provenance tag. **This is not decoration** — the
distinction between "Tally behaves this way" and "this company happens
to be configured this way" is exactly the confusion that crashed the
sandbox during finding #22.

| Tag | Means |
|---|---|
| **[Tally]** | Believed universal to the TallyPrime XML API |
| **[Edu]** | A TallyPrime **Educational Mode** constraint; may not apply to a licensed instance |
| **[Sandbox]** | True of `Coastal Test Traders` / `Coastal Services Ltd` **as configured today** — a fixture fact, not an API property |

A **[Sandbox]** tag is a warning: do not build against it, and do not
infer an API rule from it.

### Scope

**In scope:** TallyPrime's XML-over-HTTP interface — the transport ADR
0001 selected, and the Tally half of the `BooksConnector` interface
(ADR 0011 addendum).

**Out of scope:**
- **GST return data.** That comes from a GSP, not from Tally — ADR 0002,
  which contains no Tally content at all.
- **Tally's UI, TDL language, and data file formats**, except where a
  failure mode forced us into them.

### Environment these observations came from

TallyPrime **Educational Mode**, local, port 9000. Two companies:

| Company | `Maintain Inventory` | Role |
|---|---|---|
| `Coastal Test Traders` | **Yes** (+ `Integrate Accounts with Inventory`) | Inventory-enabled cases |
| `Coastal Services Ltd` | **No** | Accounting-only cases; disposable |

Both carry GSTIN `33AAAAA0000A1Z5` (Tamil Nadu). All test data is
synthetic.

---

# 1. Environment and version specifics

Facts that are properties of *this deployment*, not of the API. Check
each against a licensed instance before relying on it.

### 1.1 Educational Mode restricts posting dates **[Edu]**

Vouchers can only be posted on the **1st, 2nd and 31st** of a month.
Every spike payload uses `20260801` for this reason. A licensed instance
has no such restriction, so **test dates in this repo are not
representative** and any date-handling logic must not be validated
against them.

### 1.2 Transport: POST only, no GET **[Tally]** — #6

Everything is `POST` to `http://localhost:9000/`, body `text/xml`.
**There are no GET endpoints.** Reads and writes use the same verb and
the same envelope; only `TALLYREQUEST` differs.

### 1.3 Voucher numbering is Tally's, not ours **[Tally]** — #10, #14

Stored vouchers carry `NUMBERINGSTYLE: Auto Retain`. Tally **discards
the `VOUCHERNUMBER` we send** and assigns its own sequence. Confirmed on
both companies:

| Company | Sent | Stored |
|---|---|---|
| `Coastal Test Traders` | `TEST-INV-0001` | `1`–`6` |
| `Coastal Services Ltd` | `SVC-INV-0001` | `1`–`4` |

This is configured numbering behaviour for the voucher type — **not** a
silent discard of an unrecognised value (§2.3's class). The distinction
matters: it means the behaviour is predictable and probably
configurable, rather than a validation mystery. See §4.5 for why it
still breaks identity.

### 1.4 GST/HSN details are time-sliced by `APPLICABLEFROM` **[Tally]** — #18

Stock item GST and HSN blocks are dated generations, not single values:

```xml
<GSTDETAILS.LIST>
  <APPLICABLEFROM>20260401</APPLICABLEFROM>
```

`20260401` is the current financial year's start **[Sandbox]**, but the
*pattern* is general: a real client can carry several generations, and
rates are additionally scoped by `STATENAME`. Any code treating "the
item's GST rate" as a scalar is wrong by construction.

### 1.5 Unverified environment questions

- **UTF-16 encoding** is required for the ₹ symbol per Tally's own docs.
  **Untested.** Relevant to any amount field carrying a currency symbol.
- **Tally Cloud hosting.** All observations are against a local
  instance. Behaviour of a hosted instance under §5's failure modes —
  particularly who can dismiss a modal dialog or restart a crashed
  process — is unknown and is an open question for the provider.

---

# 2. Envelope basics and the three trust rules

## 2.1 Responses must be sanitised before parsing **[Tally]** — #1, BLOCKER

Tally emits `&#4;` (EOT) in responses. XML 1.0 forbids character
references to control characters, so **`ElementTree` fails outright**:

```
reference to invalid character number: line 80, column 27
```

Not defensive hardening — **without a sanitiser, no parse succeeds at
all.** `spikes/tally_xml.py` implements one handling all four forms
(decimal, zero-padded, hex, literal byte).

**`&#4;` is a separator, not noise.** It prefixes enum sentinel values —
`<EOT> Not Applicable`, `<EOT> Primary`, `<EOT> Any`, `<EOT> Applicable`.
The sanitiser replaces it with a newline rather than deleting it, so the
boundary survives; deletion would silently concatenate. Since these are
*meaningful values* (§3.4), a sanitiser must keep them distinguishable.

> **Untested:** whether the `\x04` prefix is required when *sending* these
> values on import. Every spike payload has sent plain names only.

## 2.2 Working request shapes **[Tally]** — #6, #11

| Purpose | Shape | Status |
|---|---|---|
| Create/alter/delete masters | `Import Data` + `REPORTNAME: All Masters` | ✅ |
| Post vouchers | `Import Data` + `REPORTNAME: Vouchers` | ✅ |
| Full field dump of a master type | `EXPORT` / `TYPE: COLLECTION` + `FETCH *` | ✅ |
| Named field export | `EXPORT` / `TYPE: COLLECTION` + `NATIVEMETHOD` list | ✅ |
| **Read vouchers** | `EXPORT` / **`TYPE: DATA`** + **`ID: Day Book`** | ✅ |
| Read vouchers via COLLECTION | `EXPORT` / `TYPE: COLLECTION` / `TYPE: Voucher` | ❌ **silent zero** |
| Single object | `EXPORT` / `TYPE: OBJECT` | ❌ `Could not find (null):Ledger!` |
| `TYPE: COLLECTION` + `ID: Day Book` | — | ☠️ **crashes Tally**, see §5.2 |

**Masters and vouchers use different import reports and different read
shapes.** Mixing them is the single most common error in this spike's
history, and one mixture is actively dangerous.

**The COLLECTION-on-vouchers failure is the nastiest of the safe ones:**
it returns **zero results with no error**, indistinguishable from an
empty period. It went unnoticed for an entire session (#11).

## 2.3 The three trust rules

Findings #2, #3 and #17 reached the same conclusion by three independent
routes: **the import response is not a trustworthy account of what
happened.** The rest of this document refers to these by number.

### Rule 1 — Read back after every write **[Tally]** — #2

`create_ledgers.py` returned `CREATED: 4, ERRORS: 0, EXCEPTIONS: 0`.
A full-field read-back showed the `CGST` ledger's `GSTDUTYHEAD` **was
never set**. Tally accepted the import, discarded a value it didn't
recognise, and reported complete success.

This is a **third state** beyond success and failure: *partially applied,
reported as success.* BK-07 and CG7 both assume writes are binary.

> Verification must locate the object before it can verify it — which is
> why §4.5's identity problem is load-bearing, not academic.

### Rule 2 — `LINEERROR` overrides every counter **[Tally]** — #17

A failed delete returned:

```xml
<LINEERROR>Cannot delete unnamed object: VOUCHER!</LINEERROR>
<CREATED>0</CREATED> <ALTERED>0</ALTERED> <DELETED>0</DELETED>
<ERRORS>0</ERRORS> <CANCELLED>0</CANCELLED> <EXCEPTIONS>0</EXCEPTIONS>
```

**Every counter is zero, including `ERRORS`**, on a total failure. A
different failure of the same operation minutes earlier reported
`ERRORS: 1` — the counter is not reliably set even between two failures
of the same call.

`TallyAdapter` must treat **the presence of `LINEERROR` as failure
regardless of the counters**, not check counters first.

Observed three times: #17, #22 step 1, and the stock-group rejection.

**Rules 1 and 2 are not redundant.** Rule 1 catches a *success* response
where data didn't land; Rule 2 catches a *failure* response wearing
success's clothes. A guard against one does not catch the other.

### Rule 3 — Enum vocabularies are validated against undocumented lists **[Tally]** — #3, #19

Probing `GSTDUTYHEAD` on a ledger by altering and reading back:

| Sent | Read back |
|---|---|
| `State Tax` | `State Tax` ✅ |
| `CGST` | `CGST` ✅ |
| `Central Tax` | *(empty)* ❌ |
| `CENTRAL TAX` | *(empty)* ❌ |
| `Central` | *(empty)* ❌ |
| `Integrated Tax` | *(empty)* ❌ |

**Every one returned `ALTERED: 1, ERRORS: 0`.** The pattern is not
understood — `State Tax` accepted but `Central Tax` not, with no obvious
logic. **No theory here fits the evidence, so none is offered.**

Any enum-valued field is suspect until probed. §3.4 shows the vocabulary
also **differs between master types** for the same concept.

### These are write-side rules — the read side is different **[Tally]** — #25

Rules 1–3 describe the **`Import Data` path**. They do **not** generalise
to reads, and over-generalising them into "nothing in Tally's responses
can be trusted" would be wrong in a costly direction.

| | Write path (`Import Data`) | Read path (`EXPORT` / `TYPE: DATA`) |
|---|---|---|
| Success signal | counters — **unreliable** (#2, #17) | `HEADER/STATUS` — reliable in testing |
| Failure signal | `LINEERROR`; counters may all read `0` | `STATUS 0` **plus** a named `LINEERROR` |
| Silent wrong result | **yes** (#2, #3) | not observed for `TYPE: DATA` |

Successful `TYPE: DATA` reads carry `STATUS 1` — or, for report
responses, no `HEADER` at all. Across roughly fifteen probes `STATUS`
and `LINEERROR` agreed with reality every time (#25).

> **Counters hide success as well as failure.** #26 recorded
> `CANCELLED: 0` on a *successful* cancel, while `DELETED: 1` was
> accurate on a successful delete in the same session. Rules 1–3 all
> concern responses that understate or hide **failure**; that one hides
> **success**. Taken together: **no individual counter can be trusted in
> isolation, in either direction** — read-back is the only mechanism
> that establishes what happened. See §4.8.

**Rule 1 works *because* reads are more trustworthy than writes.** If
reads were equally unreliable, read-back verification would be
worthless.

> **One scoped exception.** `TYPE: COLLECTION` pointed at vouchers
> returns zero rows with no error (§2.2, #11) — a genuine read-side
> silent failure. The claim is therefore: **`TYPE: DATA` reads report
> their own failures reliably; `COLLECTION` reads do not.**

## 2.4 Response counters

`CREATED`, `ALTERED`, `DELETED`, `IGNORED`, `ERRORS`, `EXCEPTIONS`,
`CANCELLED`, `COMBINED`, `LASTVCHID`, `LASTMID`.

Useful for *what* happened when a call succeeds. **Not usable to decide
whether it succeeded** — see Rules 1 and 2. `EXCEPTIONS: 1` with no
detail is the standard structural-rejection signal, and per #12 the
reason is available nowhere: not in `tally.imp`, not in `tally.ini`, not
in the Calculator Pane.

**Adapter consequences (§2)**
- Sanitise before parsing, always (#1).
- Check `LINEERROR` before counters, always (Rule 2).
- Read back after writes that matter (Rule 1).
- When a post fails, report *that* it failed — you will never know *why*
  (#12).

---

# 3. Master data shapes

## 3.1 Envelope **[Tally]** — #6

```xml
<ENVELOPE>
  <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
  <BODY><IMPORTDATA>
    <REQUESTDESC>
      <REPORTNAME>All Masters</REPORTNAME>
      <STATICVARIABLES><SVCURRENTCOMPANY>...</SVCURRENTCOMPANY></STATICVARIABLES>
    </REQUESTDESC>
    <REQUESTDATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <!-- LEDGER / STOCKITEM / ... -->
```

## 3.2 Ledger create and alter **[Tally]** — verified

```xml
<LEDGER NAME="CGST" ACTION="Create">
  <NAME>CGST</NAME>
  <PARENT>Duties &amp; Taxes</PARENT>
  <OPENINGBALANCE>0</OPENINGBALANCE>
  <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
  <TAXTYPE>GST</TAXTYPE>
  <GSTDUTYHEAD>CGST</GSTDUTYHEAD>
  <RATEOFTAXCALCULATION>0</RATEOFTAXCALCULATION>
</LEDGER>
```

`ACTION="Alter"` uses the identical body. Both verified working.

> **`GSTDUTYHEAD` is Rule 3 territory.** The example above uses `CGST`,
> which is confirmed both accepted *and* computationally correct — #8
> verified the resulting intra-state split in the Tally UI, not merely
> by read-back. `Central Tax` is silently discarded and leaves a ledger
> that looks fine and won't participate in GST computation.

## 3.3 Stock item masters **[Tally]** — #18

Read via `TYPE: COLLECTION` / `TYPE: StockItem` / `FETCH *`. Fields that
matter for BK-01's mapping:

| Area | Fields |
|---|---|
| **Identity** | `NAME` attribute; `LANGUAGENAME.LIST` → `NAME.LIST` → `NAME` (**alias list**); `GUID` (stable key); `ALTERID` (change-tracking) |
| **Hierarchy** | `PARENT` (stock group), `CATEGORY` |
| **Units** | `BASEUNITS`, `ADDITIONALUNITS`, `DENOMINATOR`, `CONVERSION`, `REPORTINGUOMDETAILS.LIST` |
| **GST** | `GSTDETAILS.LIST` → `STATEWISEDETAILS.LIST` → `RATEDETAILS.LIST`, keyed by `GSTRATEDUTYHEAD`, dated by `APPLICABLEFROM`, scoped by `STATENAME` |
| **HSN** | `HSNDETAILS.LIST`, same dating + `SRCOF...` shape |
| **Pricing/stock** | `PRICELEVELLIST.LIST`, `FULLPRICELIST.LIST`, `BATCHALLOCATIONS.LIST`, `STANDARDCOSTLIST.LIST`, `COMPONENTLIST.LIST` (BOM) |

**Match on the alias list, not just `NAME`.** Invoice-line-text → item
matching is BK-02's vendor-to-ledger problem again, against stock items.

### The inheritance chain — #20

```xml
<SRCOFGSTDETAILS>As per Company/Stock Group</SRCOFGSTDETAILS>
<SRCOFHSNDETAILS>As per Company/Stock Group</SRCOFHSNDETAILS>
```

When either field reads this, **the item's own rate and HSN fields are
deferral placeholders, not effective values** — all five `GSTRATE` rows
read `0` and `HSNCODE` is absent, and none of that is the truth about
the item.

**BK-01 cannot resolve a stock item's effective GST rate or HSN code
from the item master alone.** It must read the `SRCOF...` fields first
and walk item → `PARENT` stock group → company. Combined with the
state-wise and `APPLICABLEFROM` dimensions, *"the HSN code for this
line"* is a resolution over **(item, parent chain, state, date)**, not a
field read.

> **Untested:** the literal value that means "specify rates here" rather
> than deferring. Every artifact in the repo contains exactly one value
> for these fields — the deferring one. This is Rule 3 on a GST field,
> so a wrong guess will be silently discarded. Tracked as `PENDING:015`.

### Sandbox fixture state **[Sandbox]**

`Coastal Test Traders` currently contains **one stock item, zero unit
masters, zero stock groups**. Consequences, all fixture facts:

- The `Test` item has `BASEUNITS: <EOT> Not Applicable` because **there
  was never a unit to pick** — not because units are optional.
- `PARENT: <EOT> Primary` is the built-in root sentinel; **there is no
  stock group named `Primary`**, and sending that literal is rejected
  (#22 step 1).
- The `As per Company/Stock Group` deferral resolves straight to
  **company** level. The chain here is two links, not three.

## 3.4 Duty-head spelling differs by master type **[Tally]** — #19

| Master type | Field | Spelling for the same duty head |
|---|---|---|
| Ledger | `GSTDUTYHEAD` | `State Tax` |
| Stock item | `GSTRATEDUTYHEAD` | `SGST/UTGST` |

Stock items enumerate `CGST | SGST/UTGST | IGST | Cess | State Cess`.

**This escalates Rule 3 from per-field to per-master-type.** A single
shared `DUTY_HEADS` constant applied to both payload kinds **would be
silently wrong on one of them**, and per Rule 3 the response would not
say so. Each master type's vocabulary must be established independently
against a live instance.

The `RATEDETAILS.LIST` embedded in a *voucher's* inventory entry uses the
**stock-item** spelling, so the split is by master type, not by
read-versus-write path.

## 3.5 Master deletion

Documented shape, by name: `<LEDGER NAME="ICICI" ACTION="Delete">`.

> ⚠️ **Read §5.3 before sending any master delete.** Deleting a master
> that does not exist **crashes TallyPrime**. Whether deleting one that
> *does* exist works has never been established for any master type.

## 3.6 Master type catalogue **[Tally]** — #27

Every response's `CMPINFO` block enumerates Tally's master types. **This
is an inventory of what types exist — not confirmation that any are
populated.** Per #5 the `CMPINFO` numbers are *not* counts.

**Likely relevant to CAOS**
`GROUP` · `LEDGER` · `COSTCATEGORY` · `COSTCENTRE` · `GODOWN` ·
`STOCKGROUP` · `STOCKCATEGORY` · `STOCKITEM` · `VOUCHERTYPE` ·
`CURRENCY` · `UNIT` · `BUDGET` · `TAXUNIT` · `GSTCLASSIFICATION` ·
`VOUCHERNUMBERSERIES` · `TDSRATE` · `DEDUCTEETYPE` · `COMPANY`

**Legacy, probably dead**
`FBTCATEGORY` · `FBTASSESSEETYPE` · `EXCISEDUTYCLASSIFICATION` ·
`TARIFFCLASSIFICATION` · `LBTCLASSIFICATION` · `STCATEGORY` ·
`ADJUSTMENTCLASSIFICATION`

**Documented, never touched**
`CLIENTRULE` · `SERVERRULE` · `STATE` · `SERIALNUMBER` ·
`ATTENDANCETYPE` · `INCOMETAXSLAB` · `INCOMETAXCLASSIFICATION` ·
`RETURNMASTER` · `TAXCLASSIFICATION`

**Only `LEDGER` (§3.2) and `STOCKITEM` (§3.3) are documented here.**
`UNIT` and `STOCKGROUP` have been read and confirmed empty **[Sandbox]**
but never created. Everything else is unexplored.

Nearest-term: **`GODOWN`** and **`STOCKGROUP`** both appear in the
inventory voucher structure (§4.4), and `STOCKGROUP` is the specific
blocker on a corrected stock-item create (§5.1).

**Adapter consequences (§3)**
- Never share an enum constant across master types (§3.4).
- Resolve GST/HSN through the inheritance chain, never from the item
  alone (§3.3).
- Match items on the alias list (§3.3).
- Existence-check before every delete (§5.3).

---

# 4. Vouchers and financial reports

## 4.1 Reading vouchers **[Tally]** — #11

```xml
<HEADER>
  <TALLYREQUEST>EXPORT</TALLYREQUEST>
  <TYPE>DATA</TYPE>
  <ID>Day Book</ID>
</HEADER>
```

with `SVFROMDATE` / `SVTODATE` in `STATICVARIABLES`. `ID: Voucher
Register` also works. **`TYPE: COLLECTION` does not** — it returns zero
with no error (§2.2). Implemented in `spikes/tally_voucher_read.py`.

Day Book responses carry `REMOTEID` and `VCHKEY` attributes per
`<VOUCHER>` — see §4.5.

## 4.2 Accounting view vs. invoice view **[Tally]** — #7 *(corrected)*

The discriminator for whether a purchase voucher needs inventory
entries is **`OBJVIEW`, not the company's inventory setting**:

| `OBJVIEW` | On an inventory-enabled company |
|---|---|
| *(omitted)* or `Accounting Voucher View` | ✅ Posts fine **with no inventory entries** |
| `Invoice Voucher View` | ❌ `EXCEPTIONS: 1` unless `ALLINVENTORYENTRIES.LIST` is supplied |

Established by seven variants where five created and two failed; B vs. D
isolates `OBJVIEW` cleanly (identical ledger entries, differing only in
that attribute).

> **This finding's original text was wrong** and was corrected
> 2026-09-16. It recorded all seven variants as failing and concluded
> Tally requires a stock item on any purchase voucher for an
> inventory-enabled company. Both claims are contradicted by the
> artifacts. If you have read an older copy, re-read #7.

**Open practice question, not an API question:** posting accounting-view
vouchers to an inventory-enabled client is *accepted*, but it bypasses
stock movement on books configured to track it. Whether that is an
acceptable adapter default is a judgement for the practice.

## 4.3 Accounting-view voucher **[Tally]** — verified

```xml
<VOUCHER VCHTYPE="Purchase" ACTION="Create">
  <DATE>20260801</DATE>
  <EFFECTIVEDATE>20260801</EFFECTIVEDATE>
  <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
  <PARTYLEDGERNAME>Coastal Components Pvt Ltd</PARTYLEDGERNAME>
  <NARRATION>...</NARRATION>
  <ALLLEDGERENTRIES.LIST>
    <LEDGERNAME>Coastal Components Pvt Ltd</LEDGERNAME>
    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
    <AMOUNT>21712.00</AMOUNT>
  </ALLLEDGERENTRIES.LIST>
  <!-- Purchase @18% -18400.00, CGST -1656.00, SGST -1656.00, all Yes -->
</VOUCHER>
```

**Sign convention:** `ISDEEMEDPOSITIVE=Yes` + negative `AMOUNT` = debit;
`No` + positive = credit.

**The tax split computes correctly** — #8 verified in the Tally UI:
`Purchase @18% 18,400.00 Dr`, `CGST 1,656.00 Dr`, `SGST 1,656.00 Dr`,
party `21,712.00 Cr`.

### Sales is the same shape with the roles swapped **[Tally]** — #30, verified live

`VCHTYPE="Sales"` takes the identical envelope and `ALLLEDGERENTRIES.LIST`
structure. Only the accounting roles move:

| | Purchase | Sales |
|---|---|---|
| Party group | Sundry Creditors | Sundry Debtors |
| Party side | Credit (`No` + positive) | **Debit** (`Yes` + negative) |
| Income/expense side | Debit | **Credit** |
| Tax ledgers | Debit (input) | **Credit (output)** |

**The same `CGST`/`SGST` ledger masters serve both** — the Dr/Cr side
distinguishes input from output tax, so `TallyAdapter` does not need a
second set of tax masters for sales.

**Three scope limits, all of which matter before generalising this:**
`OBJVIEW="Accounting Voucher View"` was sent **explicitly**, so §4.2's
omitted-`OBJVIEW` result — established on *Purchase* variants only —
remains untested for Sales; tax was supplied, not derived (as in #8);
and the test party carried no `PARTYGSTIN` or `STATENAME`, so this says
**nothing** about outward-supply place-of-supply determination
(`PENDING:018` is untouched by it).

## 4.4 Inventory-bearing voucher **[Tally]** — #21, verified live

The full confirmed-working structure:

```xml
<VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">
  <DATE>20260801</DATE>
  <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
  <PARTYLEDGERNAME>...</PARTYLEDGERNAME>
  <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
  <VCHENTRYMODE>Item Invoice</VCHENTRYMODE>
  <ISINVOICE>Yes</ISINVOICE>

  <ALLINVENTORYENTRIES.LIST>
    <STOCKITEMNAME>Test</STOCKITEMNAME>
    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
    <AMOUNT>-18400.00</AMOUNT>
    <BATCHALLOCATIONS.LIST>
      <GODOWNNAME>Main Location</GODOWNNAME>
      <BATCHNAME>Primary Batch</BATCHNAME>
      <AMOUNT>-18400.00</AMOUNT>
    </BATCHALLOCATIONS.LIST>
    <ACCOUNTINGALLOCATIONS.LIST>          <!-- purchase ledger lives HERE -->
      <LEDGERNAME>Purchase @18%</LEDGERNAME>
      <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
      <AMOUNT>-18400.00</AMOUNT>
    </ACCOUNTINGALLOCATIONS.LIST>
  </ALLINVENTORYENTRIES.LIST>

  <LEDGERENTRIES.LIST>                     <!-- note: NOT ALLLEDGERENTRIES -->
    <LEDGERNAME>Coastal Components Pvt Ltd</LEDGERNAME>
    <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
    <AMOUNT>21712.00</AMOUNT>              <!-- gross -->
  </LEDGERENTRIES.LIST>
  <LEDGERENTRIES.LIST>                     <!-- tax: voucher-level siblings -->
    <LEDGERNAME>CGST</LEDGERNAME>
    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
    <AMOUNT>-1656.00</AMOUNT>
  </LEDGERENTRIES.LIST>
  <!-- SGST likewise -->
</VOUCHER>
```

Three structural points that differ from the accounting-view shape and
are easy to get wrong:

1. **The purchase ledger is nested inside the inventory entry**, under
   `ACCOUNTINGALLOCATIONS.LIST` — not a voucher-level sibling.
2. **Tax ledgers *are* voucher-level siblings**, in `LEDGERENTRIES.LIST`,
   alongside the party. Confirmed by read-back on the first attempt.
3. **The container is `LEDGERENTRIES.LIST`, not `ALLLEDGERENTRIES.LIST`.**
   Invoice-view import accepts the spelling the voucher stores;
   accounting-view vouchers use the `ALL...` spelling. **This is
   view-dependent** — neither spelling is globally correct.

> **What #21 does NOT establish** — stated plainly because the shape
> above looks more complete than it is:
> - **Tax amounts were supplied, not computed.** `1656.00` was sent and
>   stored verbatim. Whether Tally *derives* correct tax from the stock
>   item's own GST config is untested, and per §3.3 would require the
>   inheritance chain.
> - **No quantity, rate or UoM was exercised.** The `Test` item has no
>   `BASEUNITS` **[Sandbox]**, so `ACTUALQTY`, `BILLEDQTY` and `RATE`
>   are present-but-empty on every voucher in this sandbox. **Do not
>   read that as "quantity is optional."**

## 4.5 Identity and correlation **[Tally]** — #10, #14, #15

This determines whether Rule 1's read-back can find what it needs to
verify.

| Field | Verdict | Evidence |
|---|---|---|
| `REMOTEID` | ✅ **Stable for read correlation** — survives reads, restarts and edits | #15 |
| `REMOTEID` | ❌ **NOT confirmed addressable for writes** — a delete addressed by it returned `Voucher does not exist!` | #16 |
| `VCHKEY` | ⚠️ Demoted — stable in testing but superseded by `REMOTEID` | #15 |
| `GUID` | ✅ Stable | #15 |
| `VOUCHERNUMBER` | ❌ **Unusable as identity** — Tally assigns its own, **and it is not even unique within a company** | #10, #14, #31 |
| `MASTERID` | ⚠️ Stable per object, but see #14's caution | #15 |
| `ALTERID` | ℹ️ **Company-wide alteration sequence, not a per-object counter** | #15 |

**`VOUCHERNUMBER` is scoped per voucher type — a correction, not an
addition — #31.** #10 and #14 established that Tally assigns the number
itself, so the platform cannot choose it. It was reasonable to read that
as "the number is Tally's, but at least it identifies a voucher within
the company." **It does not.** Numbering is a series *per voucher type*:
`Coastal Services Ltd` holds Purchase 1, 2, 5 and Sales 1, 2 at the same
time. A Sales voucher posted into a company already holding Purchase 1
was itself numbered 1.

> **Consequence, and it is the normal case rather than an edge case.**
> Any addressing, keep-list, reconciliation or read-back verification
> that treats `VOUCHERNUMBER` as company-unique is unsound on a company
> holding more than one voucher type — which in production is every
> client company. `reset_sandbox.py` is affected today (issue #48,
> `PENDING:019`): its keep-list over-protects and so fails *safe*, but
> `verify_gone()` dedupes same-numbered vouchers into one set member and
> so can **mask a collateral loss**. Whether `VCHTYPE` in the delete
> payload disambiguates Tally-side is a separate, untested question.

**`ALTERID` is widely misread.** An edited voucher's `ALTERID` went
`1 → 5`, not `1 → 2`, because the counter is shared across the whole
company. So `ALTERID > MASTERID` means *"this object has been altered
since creation"* — it is **not** a per-object version number and must
not be used as one. The stock item's `ALTERID 223` against a voucher's
`ALTERID 6` reflects position in the company's alteration history, not
223 edits to that item.

**`REMOTEID`'s trailing counter is NOT the voucher number — #29.** A
voucher stored as **6** carried `REMOTEID`/`GUID` suffix `-00000007`,
matching the import response's `LASTVCHID: 7` rather than its own number.
Every earlier voucher in that company had suffix == number (1→1, 2→2,
4→4, 5→5), which made the two look interchangeable; they diverged once a
delete (#28) advanced the internal creation counter past the numbering.
**Never derive either identifier from the other, in either direction.**
The coincidence held only while the sandbox was gap-free.

**Two claims about `REMOTEID` that must not be conflated:** stable for
*read-back correlation* (confirmed, and what BK-07 needs), versus
addressable for *writes* (disconfirmed). If the adapter ever needs to
delete or amend a voucher it posted, it cannot assume the identifier it
reads back is one it can write against; it may need to supply `REMOTEID`
itself at create time — **untested in either direction**.

## 4.6 Duplicates are not prevented **[Tally]** — #9, CG7 CONFIRMED

Two identical imports produced two vouchers, both `CREATED: 1,
ERRORS: 0`, party balance `43,424.00 Cr` (= 2 × 21,712).

**Tally's own TPA documentation is wrong here** — it states *"invalid or
duplicate requests will reflect in the error count."* For voucher
imports, they do not. **CG7's platform-side duplicate check against the
platform's own `Voucher` table is genuinely necessary**, and since Tally
also controls voucher numbering (§1.3), the check *cannot* live on
Tally's side even in principle.

## 4.7 Financial report reads **[Tally]** — #23, #24

Same envelope as §4.1's Day Book read; only `<ID>` changes.

| `ID` | Status |
|---|---|
| `Day Book` | ✅ §4.1 |
| `Trial Balance` | ✅ |
| `Balance Sheet` | ✅ |
| `Profit and Loss` | ✅ — **spelled out** |
| `Stock Summary` | ✅ |
| `Profit & Loss` | ❌ `Could not find Report` even when escaped |

`SVCURRENTCOMPANY` is required and validated; `SVFROMDATE`/`SVTODATE`
are honoured; `SVEXPORTFORMAT` is accepted.

> ## ⚠️ SIGN CONVENTION INVERTS — read this before parsing any report
>
> **In report output, a debit is a NEGATIVE number.**
>
> ```
> Purchase Accounts    <DSPCLDRAMTA>-147200.00</DSPCLDRAMTA>   DEBIT
> Current Liabilities  <DSPCLCRAMTA>163760.00</DSPCLCRAMTA>    CREDIT
> ```
>
> At **voucher** level (§4.3) the convention is the opposite composite:
> `ISDEEMEDPOSITIVE=Yes` with a **negative** `AMOUNT` is a debit. There,
> sign is half of a two-field encoding. In **reports**, sign alone
> carries direction — and carries it the other way round.
>
> **A parser that assumes one convention holds everywhere will invert
> the books.** It will not error, and the figures will look entirely
> plausible.
>
> **Trust the element name, not the sign.** `DSPCLDRAMT` vs
> `DSPCLCRAMT` already state direction. Decode direction from the
> containing element; treat the number as magnitude.

### Structure — a display layer, not a data API

```xml
<DSPACCNAME><DSPDISPNAME>Purchase Accounts</DSPDISPNAME></DSPACCNAME>
<DSPACCINFO>
  <DSPCLDRAMT><DSPCLDRAMTA>-147200.00</DSPCLDRAMTA></DSPCLDRAMT>
  <DSPCLCRAMT><DSPCLCRAMTA></DSPCLCRAMTA></DSPCLCRAMT>
</DSPACCINFO>
```

1. **Group-level rollups only — no ledger drill-down.** Trial Balance
   returns `Current Liabilities` and `Purchase Accounts`, not the
   ledgers beneath them. Whether any parameter exposes ledger detail is
   **untested**.
2. **Name and value are positionally coupled, not nested.**
   `DSPACCNAME` and `DSPACCINFO` are *siblings* zipped by document
   order. A parser that loses ordering silently mismatches names to
   amounts.
3. **Each report has its own vocabulary** — `BSNAME`/`BSAMT`,
   `PLAMT`/`BSMAINAMT`, `DSPSTKINFO`/`DSPCLQTY`. No shared schema; each
   needs its own parser.

### Reports do not echo company or period

Nothing in the response identifies which company or date range produced
it. An empty period returns `<ENVELOPE></ENVELOPE>` — **indistinguishable
from a correctly-empty company**. The adapter must track request context
itself; the response cannot tell you.

### Report-name discovery is safe **[Tally]** — #25

An unknown report name returns `STATUS 0` and a named `LINEERROR`, not a
hang and not a silent zero. §5.2's caution about dynamically-constructed
requests applies to `COLLECTION`/TDL, **not** to `TYPE: DATA` report
names.

## 4.8 Deleting and cancelling a voucher **[Tally]** — #26, #28, verified live

Both operations address the voucher by **attributes on `<VOUCHER>`**,
not child elements, and both require a **non-empty body**.

```xml
<!-- inside the standard Import Data / REPORTNAME: Vouchers envelope -->
<VOUCHER DATE="01-Aug-2026" TAGNAME="VoucherNumber" TAGVALUE="3"
         ACTION="Delete" VCHTYPE="Purchase">
  <NARRATION>...</NARRATION>
</VOUCHER>
```

`ACTION="Cancel"` is the identical shape with the action changed.

> **`DATE` here is `dd-Mmm-yyyy`, not `YYYYMMDD`.** Every other date in
> this document is `YYYYMMDD` as a **child element**, which remains
> correct there. The **attribute** position takes the spelled-out form.
> A mandatory field, per documentation.

### Delete — #28

`DELETED: 1`. Voucher count 5 → 4. **No renumbering:** survivors keep
their voucher numbers *and* `REMOTEID`s, leaving a hole in the sequence.
So a cleanup loop can iterate one Day Book enumeration without
re-reading between deletes. Trial Balance reconciled exactly.

### Cancel — #26

`ALTERED: 1` (**not** `CANCELLED` — see below). The voucher **remains in
the Day Book** with `ISCANCELLED: Yes` and **all ledger entries
stripped**, so it is visible but carries no value. `ALTERID` advances on
the company-wide sequence (§4.5).

**Cancel is the right primitive for a correction/void path.** It
preserves an audit trail; delete destroys it. For BK-07 corrections a CA
practice should cancel, not delete. Delete belongs to test-fixture
management.

### Caveats before either is adapter-ready

- **Addressing was `TAGNAME="VoucherNumber"`**, which §4.5 rules out as
  a *durable* identifier. It is safe immediately after a read, as used
  here. **`TAGNAME="MASTER ID"` is what an adapter should use and is
  untested** — the one attempt that tried it died on the empty-body
  error before addressing was exercised.
- **Confirm by read-back, never by counter** — see below.

> ### ⚠️ `CANCELLED: 0` accompanied a *successful* cancel — #26
>
> The counter named after the operation did not move; `ALTERED` did. An
> hour later `DELETED: 1` *was* accurate on a successful delete. **Same
> session, same envelope, one counter truthful and one not.**
>
> This is a different failure direction from Rules 1–3, which all
> describe responses that **hide failure**. This one **hides success** —
> a caller checking the obvious field concludes it failed, with no error
> anywhere to suggest otherwise.
>
> **No individual counter can be trusted in isolation.** Only read-back
> establishes what happened. The `CANCELLED` counter currently has no
> known trigger.

**Adapter consequences (§4)**
- Use `TYPE: DATA` + `ID: Day Book` for reads; never `COLLECTION` (§4.1).
- Choose `OBJVIEW` deliberately — it decides whether inventory is
  required (§4.2).
- Capture `REMOTEID` at post time for read-back; never use
  `VOUCHERNUMBER` (§4.5).
- Never treat `ALTERID` as a per-object version (§4.5).
- Keep CG7's duplicate check platform-side (§4.6).
- Decode report debit/credit from the **element name**, never the sign
  (§4.7) — and never reuse the voucher-level convention there.
- Track company and period yourself; reports don't echo them (§4.7).
- **Cancel, don't delete**, for BK-07 corrections — cancel preserves the
  audit trail (§4.8).
- Confirm a cancel or delete by **read-back, never by counter** (§4.8).

---

# 5. Failure modes, by severity

**These are three different severities, not a list.** The differences
decide how much a mistake costs, and on the practice's single-tenant
deployment (ADR 0009) every client company shares one Tally instance
(ADR 0001, TC-01) — so the blast radius of the top two is *every client
on the box*, not just the one whose request failed.

## 5.1 ☠️ CRITICAL — master delete on a nonexistent target crashes Tally — #22

**Trigger:** `ACTION="Delete"` for a master whose name does not exist.

```xml
<STOCKITEM NAME="CAOS-PROBE-DELETE-ME-NOT-EVIDENCE" ACTION="Delete" />
```

**Result:** request hangs, no response, 30s timeout. At the console:

```
Internal Error. Contact Tally Solutions.
Software Exception c0000005 (Memory Access Violation)
```

**Recovery: full application restart.** Dismissing a dialog is not
sufficient — the process is dead.

**The payload was not malformed.** It mirrors the documented master
delete pattern with the object type changed. This is plausibly
reproducible on any TallyPrime instance and looks like an **application
bug worth reporting to Tally Solutions** (`PENDING:016`).

> **A crashed Tally still LISTENs on port 9000.** A TCP-connect health
> check reports healthy against a dead process. TC-05 needs a real
> request/response round trip with an explicit timeout.

**Rule: never send a master delete without first confirming the target
exists via a read.** Per Rule 1, a prior `CREATED: 1` is **not**
sufficient evidence that it exists.

## 5.2 ⚠️ HIGH — malformed read raises a modal dialog and blocks the listener — #13

**Trigger:** `TYPE: COLLECTION` with `ID: Day Book` — a plausible-looking
mix of two valid shapes.

**Result:** a modal GUI dialog — *"Error in TDL. 'Collection:Day Book'
Could not find description!"* While it is open the HTTP listener serves
nothing. Three further requests each raised it again and TallyPrime then
**closed itself entirely**.

**Recovery:** a human dismisses the dialog at the console. On a headless
or hosted instance there may be nobody to click OK.

**The platform sees a timeout, not an error** — it cannot distinguish
"Tally is down" from "Tally is waiting on a dialog nobody can see".

> **The irony worth remembering:** #12 established that Tally reports
> import failures with no diagnostic detail anywhere. Here it produced a
> genuinely useful message — and sent it to a GUI dialog box, the one
> place an integration cannot read it.

**Rule: send only request shapes verified against a real instance.**
Constructing TDL dynamically from user-supplied values is a crash risk,
not merely a correctness risk.

## 5.3 ✅ BENIGN — voucher delete/cancel refuse cleanly when the shape is wrong — #16, #26

> **#16's conclusion was overturned on 2026-09-16.** It concluded
> vouchers cannot be deleted through this API. **They can** — see §4.8.
> Its *observations* (two addressing schemes refused) stand; the
> capability claim drawn from them was wrong.

Failures on this path are well-behaved — fast, well-formed, no side
effects — whatever the cause:

| Attempt | Response | Time |
|---|---|---|
| Delete by `REMOTEID`+`VCHKEY` (#16) | `Voucher does not exist!`, `ERRORS: 1` | 0.1s |
| Delete by `MASTERID` child (#16) | `Cannot delete unnamed object: VOUCHER!`, `ERRORS: 0` | 0.1s |
| Cancel with an **empty** `<VOUCHER/>` (#26) | `Cannot process 'empty' object: VOUCHER!`, `ERRORS: 0` | 0.07s |

All three left every voucher intact, verified by read-back.

**Read these errors precisely.** `Cannot delete unnamed object` is about
*addressing* — a voucher has no name, so name-based addressing cannot
resolve it. `Cannot process 'empty' object` is about *payload shape* —
the element needs a body. Neither says the operation is unavailable, and
#16 read the first as though it did.

> **Method note — the minimal-payload trap.** Two probes in one session
> were defeated by payload shape before reaching the question they were
> asking: #26's empty `<VOUCHER/>`, and #22's stock-item create dying on
> `PARENT: Primary`. Stripping a payload to its minimum reduces what can
> *partially land* but increases what can be *rejected outright*, and a
> rejection before the interesting code path teaches nothing. **Mirror a
> documented working example and change one variable.**

### The contrast with §5.1 still holds

| | Nonexistent **voucher** | Nonexistent **master** |
|---|---|---|
| Result | `Voucher does not exist!` | **crash, `c0000005`** |
| Recovery | none needed | full restart |

Object type is the only variable. **This remains accurate and
unchanged** — nothing learned about vouchers transfers to masters, which
is precisely what §5.1 established.

> **Hypothesis for a future session — not tested, not scheduled.**
> §5.1's crashing attempt used `<STOCKITEM NAME="..." ACTION="Delete"/>`,
> and §4.8 shows that for vouchers the `NAME=`/child-element schemes are
> refused while `TAGNAME`/`TAGVALUE` works. It is *possible* §5.1's crash
> was wrong addressing plus an absent target rather than a fundamental
> limit. **This does not lower §5.1's risk** — that crash was real, the
> two object types demonstrably differ, and the condition it could not
> satisfy (a target that exists) still cannot be satisfied, since
> creating a stock item is itself blocked on the stock-group problem.
> Revisiting needs a fresh session and its own authorisation.

# 6. Confirmed working vs. explicitly untested

## 6.1 Verified live

| Capability | Finding |
|---|---|
| Response sanitisation handles all four `&#4;` forms | #1 |
| Ledger create and alter | #2, #3 |
| `GSTDUTYHEAD: CGST` produces a **correct** intra-state split (UI-verified) | #8 |
| Full-field master dump via `COLLECTION` + `FETCH *` | #6 |
| Stock-item master read and schema | #18 |
| Voucher read via `TYPE: DATA` + `ID: Day Book` | #11 |
| Accounting-view purchase voucher with tax split | #8 |
| **Accounting-view Sales voucher** — same shape, roles swapped | #30 |
| **Inventory-bearing voucher incl. tax placement** | #21 |
| `OBJVIEW` decides whether inventory entries are required | #7 *(corrected)* |
| Tally does **not** prevent duplicate vouchers (Purchase **and** Sales) | #9, #32 |
| `REMOTEID` stable across reads, restarts and edits | #15 |
| **`VOUCHERNUMBER` is per-voucher-type, not company-unique** | #31 |
| `NARRATION` / `REFERENCE` survive a post verbatim | #21a |
| **Vouchers CAN be deleted** (`TAGNAME`/`TAGVALUE`, `dd-Mmm-yyyy`, non-empty body) — *overturns #16* | #28 |
| `ACTION="Cancel"` works; voucher stays visible, entries stripped | #26 |
| `CANCELLED: 0` can accompany a **successful** cancel | #26 |
| Master delete on a nonexistent target **crashes** Tally | #22 |
| Trial Balance / Balance Sheet / Profit and Loss / Stock Summary reads | #23 |
| Report figures reconcile exactly against known posted data | #23 |
| Report sign convention inverts the voucher convention | #24 |
| `TYPE: DATA` read failures are clean and self-describing | #25 |

## 6.2 Genuinely unknown — *cheap to resolve*

| Question | Why it's cheap |
|---|---|
| Quantity / rate / UoM handling on a voucher | Needs a stock item with `BASEUNITS`; read-verifiable |
| Whether `BASEUNITS` implicitly creates a `Unit` master | The attempt **is** the test — create, then re-dump units |
| Whether `<EOT>` sentinels must carry `\x04` on import | One create attempt, read back |
| The `SRCOFGSTDETAILS` "specify here" literal | Rule 3 probe, like #3's — **but** needs §6.3's answer first |
| Supplier invoice number in a non-`VOUCHERNUMBER` field | #10's open item; one post + read-back |
| Whether an **omitted `OBJVIEW`** behaves as accounting view on **Sales** | #30 sent it explicitly, so the default is untested for this type; one post + read-back |
| Whether any report exposes **ledger-level** detail | Report-name and parameter discovery is safe (#25) |
| The other 32 master types (§3.6) | Reads are safe; only creation carries risk |

## 6.3 Genuinely unknown — *expensive, cost now known*

| Question | Why it's expensive |
|---|---|
| **Can a stock item that exists be deleted?** | #22 established what asking carelessly costs: a crash and a restart. The question that decides whether all of §6.2's master probes are iterative or one-shot — and it is **still open**, because #22's probe tested the nonexistent-target path, not the delete path |
| Can `REMOTEID` be supplied at create time and used to address writes? | #15/#16 leave this open in both directions; tests the write path with no undo |
| Does Tally **derive** tax from a stock item's GST config? | Needs §3.3's inheritance chain resolved first, and every attempt is a permanent voucher (#16) |
| Does **`TAGNAME="MASTER ID"`** addressing work for cancel/delete? | The identifier an adapter should use (§4.5); the one attempt died on an unrelated payload error first (#26) |
| Does master deletion want `TAGNAME`/`TAGVALUE` too? | **Hypothesis only** (§5.3). Blocked on creating a stock item at all, and §5.1's crash risk is unchanged |

---

# Appendix — finding index

| # | Subject | § |
|---|---|---|
| 1 | `&#4;` breaks standard XML parsers | 2.1 |
| 2 | Success response ≠ data landed (**Rule 1**) | 2.3 |
| 3 | `GSTDUTYHEAD` validated against unknown list (**Rule 3**) | 2.3, 3.2 |
| 4 | TDL Reference Manual predates GST — dead end | preamble |
| 5 | `CMPINFO.LEDGER` is not a ledger count | — |
| 6 | Request shapes that work | 1.2, 2.2 |
| 7 | `OBJVIEW` decides inventory requirement *(corrected)* | 4.2 |
| 8 | Tax split computes correctly | 3.2, 4.3 |
| 9 | Duplicates not prevented — CG7 confirmed | 4.6 |
| 10 | Tally assigns its own voucher numbers | 1.3 |
| 11 | Voucher reads need `TYPE: DATA` + `ID: Day Book` | 2.2, 4.1 |
| 12 | Import exceptions have no diagnostic detail | 2.4 |
| 13 | Malformed read → modal dialog → hang | 5.2 |
| 14 | `VOUCHERNUMBER` unusable as identity | 1.3, 4.5 |
| 15 | `REMOTEID` stable; `ALTERID` is company-wide | 4.5 |
| 16 | Voucher delete refused — *conclusion overturned by #28* | 5.3 |
| 17 | `ERRORS: 0` ≠ no error (**Rule 2**) | 2.3 |
| 18 | Stock item `Test` is real; master schema | 3.3 |
| 19 | Duty-head spelling differs by master type | 3.4 |
| 20 | `SRCOF...` inheritance chain | 3.3 |
| 21 | Inventory voucher tax placement | 4.4 |
| 22 | Master delete on nonexistent target crashes Tally | 5.1 |
| 23 | Financial reports read via `TYPE: DATA`; reconciliation method | 4.7 |
| 24 | Report sign convention inverts | 4.7 |
| 25 | Read-side failures are clean; reads vs writes | 2.3, 4.7 |
| 26 | `ACTION="Cancel"` works; `CANCELLED` counter lies | 4.8 |
| 27 | Master type catalogue (34 types) | 3.6 |
| 28 | Vouchers CAN be deleted — overturns #16 | 4.8, 5.3 |
| 29 | `REMOTEID` suffix is not the voucher number | 4.5 |
| 30 | Sales voucher = Purchase shape, roles swapped | 4.3 |
| 31 | `VOUCHERNUMBER` is per-type, not company-unique | 4.5 |
| 32 | Duplicates not prevented for Sales either | 4.6 |

## Related documents

| Document | Bearing |
|---|---|
| `spikes/p0-02-tally/FINDINGS.md` | **Source of truth** — evidence and reasoning |
| ADR 0001 | Tally integration via XML-over-HTTP; TC-01 single instance |
| ADR 0011 addendum | `BooksConnector` interface, dual backend |
| ADR 0011 amendment 1 | Tax modelling in `DraftEntry` |
| ADR 0009 | Single-tenant deployment — why §5's blast radius is all clients |
| ADR 0002 | GST via GSP — **out of scope**, contains no Tally content |
| `docs/STUB_ISSUES.md` | `PENDING:009`, `PENDING:014`, `PENDING:015`, `PENDING:016`, `PENDING:019` |
