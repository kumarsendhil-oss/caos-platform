# ADR 0002 — GST Data Access via Direct GSP Integration (Bypassing Winman)

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

GSTR-2A/2B reconciliation data was assumed to be accessible “through the Winman API.” Independent verification found Winman has no open third-party API — it’s a desktop application that connects to the GST portal internally via its own GSP (GST Suvidha Provider) relationship. Having Winman export data still requires manual UI operation per client per period, which is the actual bottleneck the platform is meant to remove.

## Decision

Register the practice directly with a GSTN-licensed GSP offering a developer REST API (shortlist: WhiteBooks, GSTHero, Adaequare, GSPIndia, MasterGST, Cygnet, IRIS GST), and integrate against it directly for both GSTR-2A/2B fetch and GSTR-1/3B filing. This removes Winman from the GST reconciliation/filing critical path entirely. Scope is limited to GST — Income Tax (ITR) and TDS filing remain on Winman for now, since they run through separate government systems (Income Tax e-filing infrastructure, TRACES) with their own integration requirements, and are not part of the current 500-returns-per-month goal.

## Consequences

- GSTN’s OTP/consent step per client GSTIN still applies regardless of GSP chosen — this becomes a scriptable, automated step rather than a manual one, but it doesn’t disappear entirely.

  > **⚠ OPEN QUESTION — this consequence is challenged and unverified. See [issue #51](https://github.com/kumarsendhil-oss/caos-platform/issues/51).**
  >
  > "A scriptable, automated step rather than a manual one" is the part at
  > risk. The P0-04 GSP spike runbook documents two constraints that, if
  > they hold, mean this step is **not** automated:
  >
  > 1. GSTN requires each taxpayer to enable API access from the GST
  >    portal, and that consent has a duration — commonly **30 days**.
  > 2. The OTP for that consent goes to the mobile/email registered
  >    against that GSTIN — **the client, not the practice.** The request
  >    and the submission are scriptable; the *receipt* is not.
  >
  > At 500 clients that is a recurring, per-client, ~monthly human
  > interaction whose timing the practice does not control.
  >
  > **Nothing here is verified** — no live request has been made against
  > any GSP, the session TTL is unknown, and whether a session can be
  > refreshed without a fresh OTP is untested (if it can, much of this
  > deflates). A sandbox alone cannot close it either: the portal consent
  > duration is a GST-portal property, not a GSP API one.
  >
  > **This does not reopen the decision.** A GSP remains far better than
  > driving Winman's UI per client per period, and the rejected
  > alternatives stay rejected. What is at stake is the strength of the
  > claim — the bottleneck is likely **relocated and shrunk**, not
  > "removed at its root". If confirmed, the fix is an amendment in the
  > shape of ADR 0011 Amendment 1, not a new decision.
  >
  > Blocks confidence in **RC-01** (Reconciliation Agent, Sprint 7) and
  > **CC-05**, not just P0-04.

- GSP API access has its own subscription cost — a new line item for the investment conversation.
- WhiteBooks’ free sandbox (apisandbox.whitebooks.in) is confirmed safe to prototype against; their published pricing is not reliable (internally inconsistent on their own site) and needs a direct sales quote before being used in cost planning.
- Full Winman replacement (ITR, TDS) is explicitly out of scope for this phase — noted as a candidate for a future initiative.

## Alternatives considered

- File-based export from Winman — rejected as the primary path since it still requires a human to operate Winman’s UI per client, which doesn’t solve the bottleneck.

- Building an independent, non-GSP GSTN integration — rejected; becoming a GSP directly is a heavy compliance undertaking disproportionate to this project’s scope. Using an existing licensed GSP is the right level of effort.
