# ADR 0016 — Attendance, Payroll and Performance: Native Capture with RazorpayX Payroll

**Status:** Proposed
**Date:** 2026-09-20
**Supersedes:** ADR 0013 (HRMS Integration for Internal Staff Management — Frappe HR, *Proposed*)
**Relates to:** ADR 0004 (Platform as a Thin Layer), ADR 0007 (Technology Stack), ADR 0009 (Deployment Model — Single-Tenant), ADR 0014 (IaC Scope — Terraform Without Fargate), ADR 0015 (Engagement and Task Model Redesign, *Proposed*)
**Depends on:** `P0-08` — the RazorpayX Payroll scoping spike, **declared by this ADR** and not yet run
**Corrects:** ADR 0013's two references to a "Supabase/Postgres/Railway" stack — see "Correction carried through the supersession"
**Out of scope:** the attendance schema itself (Decision 4 states the obligation, not the shape); where leave lives (Decision 5, gated on `P0-08` T2); qualitative appraisal (Decision 2, out of scope by customer decision)

## Context

### Why 0013 is superseded rather than amended

ADR 0013 chose **Frappe HR** as the system of record for HR and payroll compliance, and split
ownership three ways: payroll and statutory compliance to Frappe, attendance capture to CAOS,
and performance management across both. **The customer has dropped Frappe HR.** Attendance is
captured natively in CAOS and exported to **RazorpayX Payroll**.

ADR 0015 Decision 7 already reached the conclusion this ADR acts on, and the reasoning is not
repeated at length here. In short: an amendment is the right instrument when a decision's
reasoning survives and its details move. Here the vendor is different, the direction of the
integration inverts — CAOS pushed attendance *into* a self-hosted system it also read from,
where it now exports to a SaaS payroll service — and one of 0013's three pillars is deleted
rather than changed. What would remain after amending is not 0013.

0013 is still **Proposed**, so nothing Accepted is disturbed by this.

### What is *not* changed by the vendor decision

Three of 0013's positions survive intact, because none of them depended on Frappe. They are
carried forward below with attribution rather than silently re-decided — a reader should be able
to see that these are 0013's calls, still standing, not new ones.

### The scoping spike does not exist yet

**This ADR declares `P0-08` and depends on it. The spike has not been run and has produced no
findings.** Every RazorpayX capability referenced below is written as a **question the spike must
answer**, never as a statement about what the vendor does. That discipline is deliberate and has
precedent on this project: P0-06 finding #6 found Zoho's own published example contradicting its
live API, and P0-04 found WhiteBooks' marketing claiming a gate-free self-serve sandbox their own
onboarding document contradicts. **Do not read any line below as a vendor capability claim.**

## Carried forward from ADR 0013, unchanged

- **Attendance capture is built natively in CAOS** — check-in/check-out plus GPS coordinates,
  from CAOS's own interface. *(ADR 0013, Decision 2 and Integration Architecture.)*
- **Geofencing validation is performed by CAOS itself.** This was 0013's stated reason for
  rejecting Frappe's own mobile PWA for attendance: it "forces staff into a second app for a
  daily action, and Frappe's native geolocation capture lacks geofencing (location enforcement)
  — a gap CAOS can close by building this piece itself." The second half of that argument is
  vendor-specific and now moot; the first half is not, and it is the half that mattered.
  *(ADR 0013, Alternatives Considered.)*
- **CAOS is enforced as the sole check-in surface.** 0013 recorded the risk plainly — "a dual
  path (CAOS + Frappe's own app) would produce duplicate or conflicting attendance logs" — and
  the risk is unchanged in shape by the change of vendor. Any surface RazorpayX offers for
  check-in must be disabled or unused. *(ADR 0013, Consequences → Negative / Risks.)*

These three are the reason this ADR is a supersession and not a restart. **The attendance
decision was always CAOS's own**; what changes is only what happens downstream of it.

## Decision

### 1. Payroll target changes from self-hosted Frappe HR to RazorpayX Payroll

Payroll and Indian statutory compliance are delegated to **RazorpayX Payroll** rather than to a
self-hosted Frappe HR instance.

**What 0013 delegated to Frappe, and what is now unverified.** 0013 assigned the following to
Frappe HR / India Payroll. Each is now an open question against a different vendor, and **not one
of them is confirmed**:

| Delegated to Frappe by ADR 0013 | Status under this ADR | Settled by |
|---|---|---|
| Provident Fund (PF) | Unverified | `P0-08` |
| ESI | Unverified | `P0-08` |
| Professional Tax (PT), state-wise | Unverified | `P0-08` |
| Labour Welfare Fund (LWF), state-wise | Unverified | `P0-08` |
| Salary TDS | Unverified | `P0-08` T4 |
| **Form 24Q** (salary TDS return) | Unverified — **and it has a second consequence**, see "Conditional" below | `P0-08` T4 |
| Form 16 | Unverified | `P0-08` |
| Shift rules | Unverified | `P0-08` T1 |
| Auto-attendance (deriving present/absent/LOP from check-ins) | Unverified | `P0-08` T1, T4 |
| Payroll linkage (attendance feeding the salary run) | Unverified | `P0-08` T1, T4 |

**Reasoning.** The argument that survives unchanged from 0013 is the one *against building
payroll in-house*: India's statutory surface is federated across 28+ states, changes with each
Union Budget, and "AI-accelerated development compresses implementation time, not the multi-year
burden of getting statutory logic right and keeping it current." That reasoning was never about
Frappe specifically — it was about not becoming the permanent owner of that maintenance surface,
and it argues for *some* vendor. The customer has chosen which one.

**Rejected: retain self-hosted Frappe HR.** Primarily a customer decision and not this ADR's to
re-litigate. Two supporting points worth recording: 0013's own **GPL-3.0/AGPL open item** ("needs
confirmation from counsel before production use, not assumption") was never closed, so the
retained option carries an unresolved legal question of its own; and self-hosting adds a second
database engine and a second backup surface to a deployment ADR 0009 wants reproducible.

**Rejected: build payroll in-house.** Rejected for exactly 0013's reasons, restated above. This
is the one part of 0013's analysis the vendor change does not touch.

**Rejected: defer the payroll target until `P0-08` reports.** Tempting, since nothing about
RazorpayX is verified. Rejected because the *attendance* work — Decisions 3 and 4, and everything
0015's utilisation metric depends on — does not wait on the payroll target, and leaving 0013
standing as the current decision would leave the documents asserting a Frappe integration the
customer has already dropped. Naming the target and marking every capability unverified is more
honest than either alternative.

### 2. Performance measurement is quantitative only

Utilisation, bandwidth, cycle time and actual-vs-`standard_minutes` are computed **in CAOS**,
from its own task data (ADR 0015 Decision 4's two clocks) and its own attendance data.

**ADR 0013's Goal/KRA push is removed, with no replacement target.** 0013 specified that CAOS
"pushes progress updates against a designated Goal (e.g., 'Billable Utilization') via Frappe HR's
`Goal` entity, which auto-feeds the linked KRA score." There is no equivalent push in this ADR
and none is sought: the metric is computed and displayed in CAOS, and that is its terminus.
0013's Phase 0 open item to "define the exact Goal/KRA name(s) CAOS will feed automatically" is
closed as **not applicable** rather than carried.

**Qualitative appraisal is explicitly out of scope** — peer feedback, self-assessment,
judgment-based KRAs and appraisal cycles. If it is added later, it is **added natively to CAOS,
not delegated to a vendor.**

**This narrows 0013's three-way split to two.** 0013 split ownership across payroll compliance,
attendance capture, and performance management. Performance management is no longer a shared
component: its quantitative half is wholly CAOS's, and its qualitative half is not being built by
anyone. Two components remain — payroll (vendor) and attendance (CAOS).

**Rejected: find a qualitative-appraisal module in RazorpayX or elsewhere.** Rejected as a
customer decision, and it would recreate precisely the coupling this supersession removes — a
vendor holding half of a measurement CAOS computes the other half of.

**Rejected: keep the Goal/KRA push and retarget it.** There is nothing to retarget it at. A push
to a system that is not the appraisal system of record is a write with no reader.

**Rejected: defer the qualitative decision.** Rejected because 0013's positive consequence —
"performance appraisal gets an objective, task-derived quantitative signal without losing the
qualitative judgment a metrics-only system would strip out" — is no longer true, and a reader is
entitled to know that this ADR accepts a metrics-only system knowingly rather than by oversight.
That is the cost of this decision and it is recorded as such in Consequences.

### 3. CAOS owns both sides of the utilisation fraction

Utilisation is **In Progress minutes over attended minutes** — ADR 0015 Decision 4's employee
clock as the numerator, and this ADR's natively captured attendance as the denominator. Both
sides are computed inside CAOS from data CAOS holds.

**This is what native capture buys, and it is what 0013's push-only model could not deliver.**
0013 committed CAOS to computing "utilization/billing metrics per employee from task-engine data
it already owns." Billable utilisation is billable time over *available* time. Under 0013's
architecture, CAOS pushed attendance *out* to Frappe and read nothing back: shift rules,
auto-attendance resolution, leave and holidays all lived on the Frappe side, and 0013 specified
no read path in the other direction. CAOS could therefore compute a numerator and had no access
to its own denominator. The commitment was half-satisfiable on its own terms, independently of
the fact — established by 0015's gap report — that the numerator's time data did not exist
either.

Native capture closes the half that the vendor change is responsible for. **ADR 0015 closes the
other half**; neither ADR delivers utilisation alone.

**Rejected: read the denominator back from the payroll vendor.** This is the 0013 architecture
with a different vendor's name in it, and it makes a core internal metric depend on a
round-trip to an external service — including on that service exposing resolved attendance
readably, which is exactly the class of assumption `P0-08` T2 exists to stop us making.

### 4. The attendance schema is net-new, and is required under any `P0-08` outcome

**0013 said attendance is "built natively in CAOS" and named no entity, no fields and no
storage.** That is not a criticism of 0013 so much as an observation about where the gap sits:
neither `docs/audit-platform-ER-core.mermaid` nor
`docs/audit-platform-ER-compliance-billing.mermaid` declares an attendance entity, and
`services/api/app/models/` contains no attendance model. The feature 0013 assigned to CAOS has
never had a schema anywhere.

**This schema is required regardless of how `P0-08` resolves.** No outcome of the spike removes
the need for it: CAOS is the capture surface (carried forward from 0013), it performs geofencing
validation itself, and it owns the utilisation denominator per Decision 3. Whether RazorpayX
accepts GPS, or discards it, or accepts only resolved present/absent days, changes what CAOS
*exports* — not what it must *record*.

**What it must hold, at minimum** — stated as obligations, not as a schema:

- the **user** the event belongs to
- the **event type** (check-in / check-out, at least)
- the **timestamp**
- the **geo coordinates** captured at the event
- the **accuracy** reported with those coordinates — 0013 flagged "mobile GPS accuracy variance"
  as a Phase 0 concern, and an accuracy figure that is recorded is auditable where one that is
  discarded is not
- the **device** the event came from
- the **source** of the event

**The schema is not written here**, and this ADR deliberately does not write it — tracked as
`PENDING:028`. Designing it belongs with whoever scopes the sprint that builds attendance, and at
least one of its fields (what `source` may contain) reads on `P0-08` T1.

**Rejected: define the schema in this ADR.** Rejected because part of it is genuinely
spike-dependent, and a schema written now would either guess at the export shape or pretend the
question is closed.

**Rejected: treat the attendance entity as `P0-08`'s output.** Rejected because it inverts the
dependency. CAOS's record of its own staff's attendance is not a projection of a vendor's data
model, and deriving it from one would make an internal entity change shape if the vendor ever
changed.

### 5. The holiday calendar lives in CAOS; leave placement is not decided here

**Decided: the holiday calendar is CAOS's.**

**Reasoning.** PM-04 specifies a "deadline calendar across all clients and all compliance types
(GST, IT, TDS, ROC)", which requires a working-day calendar regardless of anything in this ADR —
so CAOS needs a holiday calendar whether or not payroll also has one. And the practice is in
**Tamil Nadu**: a national-holiday list is insufficient, because state holidays are what actually
determine whether the office is open. Given CAOS needs a Tamil Nadu calendar anyway, holding a
second authoritative copy in the payroll vendor and reconciling the two is a synchronisation
problem adopted for no gain.

**Not decided: where leave lives.** This is genuinely open, and it is gated on **`P0-08` T2** —
whether RazorpayX manages leave types, balances and approvals, and critically whether those are
**readable by CAOS or write-only**. The two shapes:

- **Leave in CAOS.** CAOS holds leave types, balances and the approval workflow, and exports
  resolved leave to payroll alongside attendance. Available-hours is computed entirely from data
  CAOS holds. Cost: CAOS builds a leave workflow, which is real scope.
- **Leave in RazorpayX, read by CAOS.** The vendor holds leave, and CAOS reads balances and
  approved leave to compute available-hours. Cost: a read dependency on an external service for a
  core internal metric, and the same denominator fragility Decision 3 removed.

**What would settle it:** `P0-08` T2. If RazorpayX does not expose leave balances readably, the
second shape is not available at all and leave must live in CAOS for the denominator to be
computable — which is the same failure mode that sank the Frappe arrangement, and the reason this
question is worth asking before committing rather than after. If it does expose them readably,
the choice becomes a real trade-off between build cost and coupling, and should be decided then.

**Rejected: decide leave now, on the assumption that the vendor's leave data is readable.** That
assumption is precisely what `P0-08` T2 exists to test, and 0013's denominator gap is what
assuming it once already cost.

### 6. PM-03's capacity indicator becomes hours-based

PM-03 ("Capacity indicator — surfaces available bandwidth for new client work", PRD §5.14) is
specified in `docs/CAOS-api-spec-v0.2.md` §15 as:

| Method | Path | Response |
|---|---|---|
| GET | `/capacity` | `{available_staff: int, at_risk_clients: []}` |

**A headcount cannot answer the question PM-03 exists to answer.** "We have four available staff"
does not tell the proprietor whether the practice can take on another twenty GST returns a month;
the same four people are either near capacity or barely used, and `available_staff` reads
identically in both cases. The requirement says *bandwidth*; the response returns *headcount*.

**Decided: PM-03 becomes hours-based** — available hours against committed hours, computed from
attended minutes (this ADR) net of In Progress minutes and `standard_minutes` commitments
(ADR 0015). **The API response shape therefore changes**, and `{available_staff, at_risk_clients}`
does not survive in its current form. The replacement shape is not specified here; the API spec is
not edited in this pass. Tracked as `PENDING:029`.

**This is the user-visible payoff of ADR 0015 and ADR 0016 together.** Neither delivers it alone:
0015 supplies the numerator side (task time at engagement grain), this ADR supplies attended
hours, and PM-03 is the first screen where the practice sees the answer in the unit the question
was asked in. It is worth naming, because two schema-heavy ADRs otherwise read as infrastructure
with a deferred benefit.

**Rejected: keep the headcount response and add hours alongside it.** Rejected because
`available_staff` would remain the field consumers reach for first, and two capacity numbers that
disagree is worse than one that is right.

## Conditional, not decided — the TDS agent's scope

**ADR 0013 narrowed CAOS's TDS/TCS Return Automation Agent to 26Q/27EQ (non-salary TDS)** because
Frappe HR / India Payroll owned Form 24Q (salary TDS) "end-to-end", leaving CAOS to reflect 24Q
filing status "for dashboard visibility only — avoiding duplicate logic between the two systems."

That narrowing was a **consequence of the vendor choice, not an independent decision about the
TDS agent.** Its premise is now unverified.

**If `P0-08` T4 establishes that RazorpayX does not file Form 24Q, the narrowing reverses and the
TDS agent's scope grows to include it.** That is a materially larger agent than the one currently
specified, and it would land on whichever sprint owns the TDS module.

**This is flagged, not decided**, and it is not decidable today — it turns entirely on a vendor
fact nobody has checked. Tracked as `PENDING:030`. **Nothing should be built against either scope
until `P0-08` T4 reports.**

## Correction carried through the supersession

**ADR 0013 refers twice to a "Supabase/Postgres/Railway" stack.** Integration Architecture: Frappe
HR runs as a separate service "(Python/Frappe Framework, MariaDB — not CAOS's Supabase/Postgres
stack)". Consequences → Negative: a separate MariaDB service to host and back up, "outside the
existing Supabase/Postgres/Railway stack".

**Both are wrong, and they contradict three ADRs.** ADR 0007 revised hosting **away from Railway**
to **AWS ap-south-1 (Mumbai)**, on the reasoning that Railway has no India region and that
DPDP-driven self-hosted OCR "doesn't meaningfully improve on a cloud API with India-region
processing" if the hosting itself sits outside India. ADR 0009 assumes AWS Mumbai per deployment.
ADR 0014 settled the tooling as **Terraform** (Fargate still rejected).

**This ADR states the correct stack: AWS ap-south-1 (Mumbai), provisioned with Terraform per ADR
0014.** The correction is recorded here rather than carried silently, because the erroneous phrase
is load-bearing in 0013's argument — it is cited as the reason the Frappe service is *foreign* to
the platform's infrastructure. **ADR 0013 itself is not edited**; it is superseded by this ADR,
and a superseded document is left as written.

One consequence of the vendor change worth noting against this: **RazorpayX Payroll adds no
self-hosted infrastructure at all.** 0013's "new infrastructure dependency: a separate
MariaDB-backed service to host and back up" disappears entirely, along with its backup surface
and its absence from the Section 9 recurring cost model. What replaces it is not an
infrastructure cost but an external dependency and a data-residency question — the next section.

## New surface: employee PII held by an external processor

**This is the one genuinely new risk the vendor change introduces, and 0013 did not have it.**

A self-hosted Frappe HR instance, whatever else was wrong with it, kept employee personal data —
identity, salary, bank details, statutory identifiers, and under this ADR's Decision 4 also
**location traces** — inside infrastructure the practice controls. **RazorpayX Payroll is a SaaS
service, so that data is processed and held by an external party.**

**Assessed against ADR 0004.** 0004's central consequence is that the platform "narrows the DPDP
Act surface considerably — most obligations are already covered by the practice's existing use of
Tally and Dropbox; what's new is the platform's own metadata layer plus transient OCR/LLM
processing." It rejected a full data warehouse on the grounds that it "expands the DPDP surface
significantly." **This decision cuts against that argument in two ways.** First, it *widens* the
surface rather than narrowing it: a new external processor, holding data no existing system of
record holds. Second, and more sharply, 0004's whole narrowing argument rests on the data already
sitting in systems the practice already uses — Tally, Zoho, Dropbox. **Employee data has no such
pre-existing custodian.** There is no "the practice already accepted this posture" to fall back
on, because this is the practice's own staff data going somewhere it has not been before.

Geofenced check-in makes this sharper still: **continuous location data about identifiable
employees** is a more sensitive category than the financial metadata 0004 was reasoning about.

**This is flagged for the practice's legal contact and is not resolved here.** That routing is
consistent with how this project already handles DPDP questions — PRD §8 item 4 carries the DPDP
obligation question as "largely resolved — narrowed to: what DPDP obligations apply specifically
to the platform's own metadata layer", and §10 lists it among the open questions that block
architecture decisions. It is also the pattern 0013 itself used for its GPL-3.0 question: "needs
confirmation from counsel before production use, not assumption." Tracked as `PENDING:031`.

**What this ADR does not claim:** it does not claim the arrangement is compliant, nor that it is
not. It records that the surface changed, that nobody has assessed it, and who should.

## Consequences

**Positive**

- The utilisation metric becomes computable for the first time. CAOS holds both the numerator
  (ADR 0015) and the denominator (Decision 3); neither ADR achieves this alone.
- No self-hosted HRMS infrastructure. 0013's separate MariaDB service, its backup surface and its
  unbudgeted line in the Section 9 cost model all disappear.
- 0013's unresolved GPL-3.0/AGPL counsel question is moot — it attached to consuming Frappe, and
  nothing here consumes Frappe.
- The attendance feature CAOS builds is unchanged and still better than what 0013's rejected
  alternative offered: native capture with CAOS-side geofencing, on one app.
- PM-03 answers its own requirement's question in the unit the question is asked in.

**Negative / Risks**

- **Every statutory capability in Decision 1's table is unverified.** The spike that would verify
  them is declared by this ADR and has not been run. This is the largest open risk here, and it is
  not a small one: if RazorpayX covers materially less than Frappe's India Payroll did, the
  build-vs-integrate reasoning carried forward from 0013 is weakened against a vendor it was never
  tested on.
- **Performance measurement is now metrics-only, knowingly.** 0013's stated benefit — a
  quantitative signal "without losing the qualitative judgment a metrics-only system would strip
  out" — is given up. Decision 2 records this as a customer decision rather than an oversight; it
  remains a real loss and should be revisited if appraisal cycles start needing it.
- **Employee PII moves to an external processor**, unassessed. See the section above.
- **The attendance schema does not exist**, in either diagram or the model layer, and nothing is
  buildable until it does (`PENDING:028`).
- **PM-03's API response shape changes**, breaking its currently specified contract
  (`PENDING:029`).
- **The TDS agent's scope is conditional** on a vendor fact nobody has checked (`PENDING:030`).
- **Employee identity mapping remains a live concern.** 0013 flagged that "employee ID mapping
  between CAOS and Frappe HR must stay in sync; drift breaks attendance posting." The vendor
  changed; the failure mode did not. `P0-08` T9 covers it.
- A shared vendor account across practices would be the **first thing in this architecture that is
  not per-deployment**, which cuts against ADR 0009's single-tenant model. `P0-08` T7 asks the
  question; nothing here assumes the answer.

## `P0-08` — RazorpayX Payroll scoping spike (declared here, not yet run)

**These are questions, not findings. Nothing below has been checked.**

| ID | Question |
|---|---|
| **T1** | Does the API accept attendance / check-in data as input — what endpoint, what payload shape, is **GPS accepted or discarded**, and are **backdated timestamps** accepted? |
| **T2** | Does it manage leave types, balances and approvals — and are they **readable by CAOS or write-only**? *This is the check that closes Decision 5's open half.* |
| **T3** | Does it impose its own holiday calendar, in a way that conflicts with CAOS holding one (Decision 5)? |
| **T4** | Does it compute LOP from attendance, or expect LOP days as input? And **does it file Form 24Q**? *T4 also settles the TDS conditional above.* |
| **T5** | What is the auth model, and how do its credentials fit Security Standard §3 — fixed-schedule rotation like Tally/GSP, revocation-triggered like Zoho Books, or a third shape? |
| **T6** | What are the rate limits (Security Standard §8), and **are calls billed**? |
| **T7** | What does per-firm deployment imply under ADR 0009 — one vendor account per practice, or one shared account? *A shared account would be the first thing in this architecture that is not per-deployment.* |
| **T9** | Employee identity mapping between CAOS and the vendor, and **what PII the vendor holds**. |

**There is no T8, deliberately.** It was scoped as the Goal/KRA equivalence check — whether
RazorpayX offers something CAOS could push a utilisation figure at, as 0013 pushed at Frappe's
`Goal` entity. **Decision 2 removes the Goal/KRA push entirely**, so the check has no subject.
It is dropped rather than renumbered, and the remaining IDs keep their numbering, so that a later
reader finds this note rather than concluding T8 was overlooked.

## Follow-up work (not this pass)

**`docs/spikes/p0-08-razorpayx/RUNBOOK.md`** — **does not exist yet.** The scoping work behind the
test list above exists only as discussion and is **not repo state**. It is written to disk
immediately after this ADR, in the next step of this sequence. **This ADR therefore
forward-references a file that will exist shortly but does not at the time of writing** — noted
explicitly so that a reader who checks the path in between does not conclude the reference is
broken.

**`docs/CAOS-sprint-plan-v0.2.md`** — `P0-08` is **not** on the Phase 0 list, which currently ends
at P0-07. This ADR declares the spike; adding it to the plan (and to the Dev Readiness Checklist)
is a separate edit, not made here.

**`docs/audit-platform-ER-core.mermaid`** — the attendance entity, once `PENDING:028` is designed.
Whether it belongs in core or compliance-billing is itself undecided.

**`docs/CAOS-api-spec-v0.2.md`** — §15's `GET /capacity` response shape, per Decision 6 and
`PENDING:029`. Attendance check-in/out endpoints have no section at all.

**`docs/CAOS-PRD-v0.2.md`** — PM-03's wording, if the hours-based framing changes what the
requirement says; requirement IDs for attendance capture, which the PRD has never had.

**`docs/audit-platform-ADR-0013-hrms-integration.md`** — mark **Superseded by 0016** on its own
file. Not edited in this pass, and its content is deliberately left as written.

**`docs/CAOS-security-standard-v0.2.md`** — §3 gains RazorpayX credentials once `P0-08` T5
establishes their shape; §8 gains its rate-limit posture once T6 does.
