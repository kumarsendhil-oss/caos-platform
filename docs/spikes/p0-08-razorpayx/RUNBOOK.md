# P0-08 Spike — RazorpayX Payroll Scoping Runbook

**Status:** **Not started — scoped only.** No account, no credential, no live call, and
no vendor documentation has been read. Every line below is a **question**, not a finding.
**Declared by:** ADR 0016 (Attendance, Payroll and Performance — Native Capture with
RazorpayX Payroll), which depends on this spike and marks every vendor capability
unverified pending it
**Supersedes the assumptions of:** ADR 0013 (HRMS Integration — Frappe HR), **superseded
by ADR 0016**. Where this runbook needs a statement of what the platform delegates to a
payroll vendor, it cites 0016; 0013 is referenced only where the *history* of an
assumption matters
**Blocks:** leave placement (ADR 0016 Decision 5, open); the TDS agent's scope (ADR 0016's
conditional); the attendance export path
**Does not block:** the attendance schema (`PENDING:028`) — ADR 0016 Decision 4 establishes
that CAOS needs it under every possible outcome of this spike

## Read this before running anything

**This spike has produced nothing. Do not cite it as evidence of anything.**

That warning is heavier here than on most spikes, because two of this project's earlier
spikes found vendor claims that did not survive contact:

- **P0-06 finding #6** — Zoho's own published example contradicted its live API.
- **P0-04** — WhiteBooks' marketing claimed a gate-free self-serve sandbox their own
  onboarding document contradicts.

So: **nothing in the tests below is a statement about what RazorpayX Payroll does.** Each
is phrased as a question precisely so that a later reader skimming for answers finds none
and goes looking for the findings file instead.

## What this spike is for

ADR 0016 changes the payroll target from a self-hosted Frappe HR instance to **RazorpayX
Payroll**, on the customer's decision. The argument *against building payroll in-house*
carries over from ADR 0013 unchanged — India's statutory surface is federated across 28+
states and changes with each Union Budget — but that argument was only ever an argument for
*some* vendor. **Nothing establishes that this vendor covers what the previous one was
assumed to.**

ADR 0016 Decision 1 lists ten capabilities ADR 0013 delegated to Frappe HR / India Payroll
— PF, ESI, PT, LWF, salary TDS, Form 24Q, Form 16, shift rules, auto-attendance and payroll
linkage — and marks **every one of them unverified**. This spike is what would change that.

Three things in ADR 0016 are explicitly gated on it:

| Gated on | Test | ADR 0016 reference |
|---|---|---|
| Where leave lives | **T2** | Decision 5, open half |
| Whether the TDS agent's 26Q/27EQ narrowing reverses | **T4** | "Conditional, not decided" |
| Whether a shared vendor account breaks the per-deployment model | **T7** | Consequences |

## Setup

1. **Obtain a RazorpayX Payroll account** for the practice, or sandbox/demo access if one is
   offered. **Whether this is self-serve is itself unknown** — see §5's stop rule, and note
   that P0-04's equivalent step turned out to require two support calls despite marketing
   claiming otherwise.
2. **Read the vendor's own API documentation before making any call.** Several of the
   questions below (T4's Form 24Q question in particular) may be answerable from
   first-party documentation without an account at all — which is exactly how P0-04 closed
   its central question, and it is the cheapest possible outcome here.
3. **Credentials go in a secrets manager, never in a file in this repo** — Security Standard
   §3, and CG4 for anything that reaches application config. This runbook's companion
   scripts, if any are written, must read from the environment and log nothing.
4. **Record every response in full.** Follow the evidence discipline the P0-02, P0-06 and
   P0-07 spikes established: raw responses saved under a timestamped run directory, with a
   `FINDINGS.md` numbering findings sequentially.

## Tests

### T1 — Does the API accept attendance / check-in data as input?

CAOS is the sole check-in surface (ADR 0016, carried forward from 0013 unchanged) and
performs geofencing validation itself. What it does with the result depends entirely on what
the vendor will accept.

**Record:**
- The **endpoint** and **payload shape** for attendance or check-in data, if one exists at all.
- Whether **GPS coordinates are accepted or discarded.** If discarded, CAOS's geofencing
  validation is purely internal and the location data never leaves the platform — which is
  materially better for `PENDING:031`'s DPDP question, and worth recording as such.
- Whether **backdated timestamps** are accepted. A correction to a missed check-in is normal
  practice-floor reality; a vendor that rejects backdated events forces CAOS to hold the
  correction and reconcile at period close.
- Whether the API accepts **raw events** (check-in/check-out pairs) or only **resolved days**
  (present/absent/half-day). This determines whether shift-rule resolution is the vendor's
  job or CAOS's, and it interacts with T4.

**Feeds:** ADR 0016 Decision 4's `source` field, which is the one attendance-schema field
the ADR declined to specify pending this answer.

### T2 — Leave: does it manage types, balances and approvals, and are they READABLE?

> **This is the decision-critical check. It is the one that closes ADR 0016 Decision 5's
> open half.** Run it first if anything forces a partial spike.

ADR 0016 **decides that the holiday calendar lives in CAOS** and **deliberately leaves leave
placement open**, gated on this test.

**Record:**
- Whether RazorpayX manages **leave types**, **balances** and **approval workflows** at all.
- **Critically: whether those are readable by CAOS, or write-only.** A vendor that accepts
  leave and never gives it back is, for CAOS's purposes, a system that does not have it.

**Why it decides something.** Utilisation is In Progress minutes over **attended** minutes
(ADR 0016 Decision 3), and available-hours cannot be computed without knowing who was on
leave. The two shapes ADR 0016 states:

- **Leave in CAOS** — CAOS holds types, balances and approvals, and exports resolved leave
  alongside attendance. Cost: a leave workflow is real scope.
- **Leave in RazorpayX, read by CAOS** — cost: a read dependency on an external service for
  a core internal metric.

**If leave is not readably exposed, the second shape does not exist and leave must live in
CAOS.** That is the same failure mode that sank the Frappe arrangement — 0013 pushed
attendance out and specified no read path back, leaving CAOS able to compute a numerator and
not its own denominator. Establishing this *before* committing is the entire point of asking.

### T3 — Does it impose its own holiday calendar in a way that conflicts?

**Narrowed deliberately. This is no longer "does CAOS need its own calendar" — ADR 0016
Decision 5 decides that CAOS holds it**, and that decision does not depend on this test.

The reasoning is already settled and is not reopened here: PM-04 requires a working-day
calendar regardless of anything to do with payroll, and the practice is in **Tamil Nadu**, so
a national-holiday list is insufficient — state holidays are what determine whether the
office is open.

**Record only:**
- Whether RazorpayX **imposes its own holiday calendar** on payroll processing.
- If it does, **whether it conflicts** with CAOS holding the authoritative one — specifically
  whether the vendor's calendar affects LOP or salary computation in a way that a divergent
  CAOS calendar would silently contradict.
- **If there is a conflict: how to reconcile it.** Is the vendor calendar configurable
  (CAOS pushes its Tamil Nadu calendar in), overridable per run, or fixed? A fixed vendor
  calendar that cannot be aligned is a real finding and should be written up as one.

### T4 — LOP computation, and Form 24Q

**Two questions, deliberately together, because both turn on how much of the payroll run the
vendor actually owns.**

**Record, on LOP:**
- Does RazorpayX **compute loss-of-pay from attendance data**, or does it **expect LOP days
  as input**?
- If it computes LOP, from what — raw check-in events, resolved days, or its own shift rules?
  This closes the loop with T1 and T3: LOP computed from the vendor's own holiday calendar,
  against attendance CAOS resolved, is exactly the conflict T3 is looking for.

**Record, on Form 24Q:**
- **Does RazorpayX file Form 24Q** (salary TDS return)?

**Why the 24Q question matters beyond payroll.** ADR 0013 narrowed CAOS's TDS/TCS Return
Automation Agent to **26Q/27EQ (non-salary TDS)**, with 24Q "owned end-to-end by Frappe HR /
India Payroll" and CAOS reflecting only its filing status for dashboard visibility. **That
narrowing was a consequence of the vendor choice, not an independent decision about the
agent** — and ADR 0016 carries it as an explicit conditional, tracked as `PENDING:030`.

**If RazorpayX does not file 24Q, the narrowing reverses and the TDS agent's scope grows to
include salary TDS** — a materially larger agent than the one specified today, landing on
whichever sprint owns the TDS module. **Nothing should be built against either scope until
this test reports.**

### T5 — Auth model, against Security Standard §3

**Record:**
- The **auth model** — API key, OAuth2, signed requests, something else.
- Token and credential **lifetimes**, and what revocation looks like.
- **Which of §3's existing shapes this fits**, because §3 currently describes two and they are
  genuinely different:
  - **Fixed-schedule rotation**, like Tally and GSP — rotated every ~90 days and immediately
    on suspected compromise, needing a runbook step (RB-01).
  - **Revocation-triggered**, like Zoho Books — short-lived access tokens against a
    longer-lived refresh token, where the trigger is a consent revocation surfacing as a
    status change rather than a calendar date.
  - **Or a third shape**, which is a real possible answer and should be written up as one
    rather than forced into the nearer of the two.

Whatever the answer, §3's absolute rule holds and needs no test: **no credential ever appears
in a log line** (Logging Standard §6) **or in an error returned to the frontend.**

### T6 — Rate limits and billing, against Security Standard §8

**Record:**
- Published **rate limits**, and whether responses carry rate-limit headers.
- **Whether calls are billed** — per call, per employee, per payroll run, or bundled into the
  subscription.

§8's framing applies directly: a runaway retry loop against a per-call-billed API "isn't just
a performance problem, it's a real cost/availability problem." Internal rate limiting is
required regardless of what the vendor enforces, as a defence against the platform's own bugs.

Scale note for sizing: ADR 0013 scoped this at **~10 internal staff** (4 article clerks, 6
paid assistants), which is small — but see T7, because the relevant number may not be 10.

### T7 — Per-firm deployment under ADR 0009

**Record:**
- Does each practice need **its own RazorpayX account**, or would CAOS operate **one shared
  account** across practices?
- If shared: what isolates one practice's employee data from another's, and who is the
  account holder of record?

**Why this is more than a billing question.** ADR 0009 commits the project to **one deployment
per customer**, and ADR 0010 builds a base product with per-practice customization on top of
that. **A shared vendor account would be the first thing in this architecture that is not
per-deployment** — a single external dependency spanning tenants, in a design whose entire
isolation story is that tenants do not share anything.

ADR 0016 records this in its Consequences and **explicitly assumes no answer**. If the answer
is "shared, and there is no per-practice option", that is an architectural finding that
deserves its own ADR discussion rather than a line in a spike report.

### T9 — Employee identity mapping, and what PII the vendor holds

**Record:**
- How employees are **identified** in RazorpayX, and what CAOS must store to map its own
  `USER` rows onto them.
- **What PII the vendor holds** — enumerate it: identity, salary, bank details, statutory
  identifiers (PAN, UAN, ESI number), and whether any location data reaches it (this depends
  on T1's GPS answer).

**Two separate things hang off this.**

The mapping half is a carried-forward operational risk: ADR 0013 flagged that "employee ID
mapping between CAOS and Frappe HR must stay in sync; drift breaks attendance posting."
**The vendor changed; the failure mode did not.**

The PII half **establishes facts for `PENDING:031` but does not answer it.** ADR 0016's "New
surface" section records that employee data — including, under Decision 4, location traces
about identifiable employees — now sits with an external processor where self-hosted Frappe
kept it inside the practice's infrastructure, and that this cuts against ADR 0004's
DPDP-surface-narrowing argument in two ways. **That question is routed to the practice's legal
contact and is not this spike's to resolve.** What the spike owes it is an accurate inventory.

### There is no T8 — and it was not overlooked

**T8 was scoped as the Goal/KRA equivalence check:** whether RazorpayX offers an entity CAOS
could push a utilisation figure at, the way ADR 0013 specified pushing progress against a
Frappe HR `Goal` that auto-feeds a linked KRA score.

**It is removed, because the thing it was checking for no longer exists.** The customer has
settled that **performance measurement is quantitative only** and that **qualitative appraisal
is out of scope** — so ADR 0016 Decision 2 removes the Goal/KRA push entirely, with **no
replacement target**. Utilisation, bandwidth, cycle time and actual-vs-standard are computed
in CAOS and displayed in CAOS, and that is their terminus. A push to a system that is not the
appraisal system of record is a write with no reader.

**Nothing else is renumbered.** T9 keeps its number rather than sliding up into the gap,
specifically so that this note is what a later reader finds when they notice T8 missing —
rather than concluding it was dropped by accident.

If qualitative appraisal is ever added, ADR 0016 Decision 2 records that it is added
**natively to CAOS**, not delegated to a vendor. So T8 does not come back if that happens.

## 5. Stop rule — what to do if an account cannot be obtained

**If a RazorpayX Payroll account or sandbox cannot be obtained within the Phase 0 window,
P0-08 records that as its finding and closes** — with the engineering-side deliverables done
— **rather than sitting open indefinitely.**

This is deliberate, and it is a lesson taken from P0-04, which has sat open pending a vendor
sandbox account that needs a support call, while the question it was opened to answer was
eventually closed from first-party documentation instead.

**"Closes with the engineering-side deliverables done" means:**

- Everything answerable from **first-party vendor documentation** is answered and written up,
  with the source cited. P0-04's precedent is that this can be most of the value.
- Every test above that could not be run is recorded as **explicitly unrun**, with what
  blocked it.
- **ADR 0016's Decision 1 table stays marked unverified**, and the three gated items
  (T2/leave, T4/TDS scope, T7/deployment) stay open with that recorded as their status.
- The blocker is named as **what it is** — a commercial or access obstacle, not an
  engineering one — so that whoever picks it up knows it needs a phone call and not a
  developer.

**What closing does not mean.** It does not mean assuming a capability, and it does not mean
ADR 0016's conditionals resolve by default. An unrun T4 leaves the TDS agent's scope
**conditional**, not narrowed — `PENDING:030` stays open, and nothing gets built against
either scope on the strength of a spike that did not run.

## After the spike

- Write `FINDINGS.md` in this directory, numbering findings sequentially, following the
  P0-02 / P0-06 / P0-07 pattern. Save raw responses under timestamped run directories.
- **Update ADR 0016's Decision 1 table** — replace `Unverified` per row with what was
  established, citing the finding number.
- **Close or restate ADR 0016 Decision 5's open half** from T2. If leave lands in CAOS, that
  is new scope and needs to be said out loud, not absorbed.
- **Resolve or re-flag `PENDING:030`** from T4's Form 24Q answer.
- **Update `PENDING:031`** with T9's PII inventory — facts for the legal contact, not an
  answer to their question.
- If T7 returns "shared account", **raise it as an architecture question against ADR 0009**
  rather than recording it as a spike note.
- Feed T6's billing answer into the Section 9 recurring cost model, which ADR 0016 notes lost
  0013's Frappe hosting line and has not gained a replacement.
