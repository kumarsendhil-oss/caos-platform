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

- GSP API access has its own subscription cost — a new line item for the investment conversation.
- WhiteBooks’ free sandbox (apisandbox.whitebooks.in) is confirmed safe to prototype against; their published pricing is not reliable (internally inconsistent on their own site) and needs a direct sales quote before being used in cost planning.
- Full Winman replacement (ITR, TDS) is explicitly out of scope for this phase — noted as a candidate for a future initiative.

## Alternatives considered

- File-based export from Winman — rejected as the primary path since it still requires a human to operate Winman’s UI per client, which doesn’t solve the bottleneck.

- Building an independent, non-GSP GSTN integration — rejected; becoming a GSP directly is a heavy compliance undertaking disproportionate to this project’s scope. Using an existing licensed GSP is the right level of effort.
