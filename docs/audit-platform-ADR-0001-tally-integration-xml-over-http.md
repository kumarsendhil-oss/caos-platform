# ADR 0001 — Tally Integration via XML-over-HTTP

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

The platform needs both read access (purchase register, ledgers, bank book) and write access (posting draft vouchers) to the practice’s Tally Cloud environment. Initial assumption was that this required procured licensing; verified against Tally Solutions’ own documentation that this is a native, built-in capability.

## Decision

Use TallyPrime’s XML-over-HTTP interface (default port 9000) as the primary integration method, for both reads and writes. ODBC is available but read-only (no INSERT/UPDATE) — not usable for voucher posting, though it remains an option for simple reporting-style extraction if useful later. Development and testing happens against the official TallyPrime API Explorer sandbox before any real client data is touched.

## Consequences

- The Tally Connector (a co-located service or reachable endpoint) must be able to reach port 9000 on the practice’s Tally Cloud host — this is a hosting/network question to confirm with the provider, not a licensing cost.

- Tally’s XML import does not prevent duplicate vouchers on its own; the platform must implement its own duplicate check (vendor GSTIN + invoice number + date) before posting.
- A TDS/TCS-style deep customization (via TDL) may be needed to shape reports/collections exactly as the platform needs them — this is development effort, not just configuration.

## Alternatives considered

- Browser automation against a hosted remote-UI — rejected as the fallback only if XML/HTTP access turns out to be unreachable; less reliable, higher maintenance, avoided as the primary path.

- ODBC as primary — rejected since it cannot write vouchers, which the Bookkeeping Agent requires.
