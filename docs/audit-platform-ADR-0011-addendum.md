# Architecture Decision Records — Addendum
### Practice Automation Platform — Venture Assist / Srivatsan & Associates

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 (addendum) | 2026-08-22 | ADR 0011 added: multi-backend bookkeeping connector (Tally + Zoho Books), following discovery that ~20-40% of clients maintain books in Zoho Books rather than Tally, with full read/write parity required. ADR 0001 amended accordingly. |

---

## ADR 0011 — Multi-Backend Bookkeeping Connector (Tally + Zoho Books)

**Status:** Accepted (pending Zoho sandbox spike — see Consequences)

### Context

ADR 0001 and the original PRD (§5.3) assumed Tally is the practice's sole bookkeeping system, with a small-percentage secondary path (TC-06/07) for clients who maintain their own Tally and hand over a backup file. Follow-up discovery found this assumption is wrong in a material way: roughly 20-40% of the client base maintains books in **Zoho Books**, not Tally, and the practice needs the platform to read from *and* write to Zoho Books with the same level of automation as Tally — not a reduced, read-only, or manual-fallback experience.

This is a different situation from the existing TC-06/07 secondary path. That path exists for a small minority of clients and only needs periodic backup-file ingestion. A 20-40% Zoho population needing full Bookkeeping Agent parity (extraction, fuzzy vendor matching, draft posting, duplicate prevention) is a second first-class backend, not an edge case.

### Decision

Introduce a **BooksConnector interface** with two adapters, both living in the core codebase (not `practices/{practice_slug}/`, per ADR 0010 — this is a generic platform capability, not an idiosyncrasy of this one practice):

```
BooksConnector (interface)
    ├── TallyAdapter   — XML-over-HTTP, port 9000 (per ADR 0001)
    └── ZohoAdapter    — Zoho Books REST API v3, OAuth2
```

Every downstream agent (Bookkeeping, Reconciliation, Working Paper) is built against the interface's normalized schema — the same normalization principle TC-03 already established for cross-version Tally data now generalizes to cross-backend data. No agent module contains conditional logic branching on which backend a client uses; that decision lives entirely inside the adapter layer.

Which adapter a given client uses is **per-client configuration** (a `books_system` field on the client record — `tally` | `zoho_books`), not a code fork or a customization under `practices/`.

**Key differences the two adapters must each absorb:**

| | TallyAdapter | ZohoAdapter |
|---|---|---|
| Auth | Username/password on the practice's Tally Cloud host (practice-wide credential) | OAuth2 authorization-code flow, per-client-organization consent, refresh-token storage in Secrets Manager (CG4, Security Standard §3) |
| Write model | Draft voucher, CGST/SGST/IGST ledger split | Bill / Journal Entry via Zoho's own tax-component fields |
| Consent model | Practice-wide — the practice controls Tally provisioning | Per-client-organization — closer to the GSP's per-GSTIN OTP/consent model (ADR 0002) than to Tally's single practice-wide connection |
| Read output | Normalized via TC-03 | Normalized to the same schema |
| Duplicate check (CG7) | Runs against the platform's own VOUCHER table before posting | Same check, same table — CG7 itself does not change; it runs once, before either adapter is called |

### Consequences

- **Sequencing changes.** Because ~20-40% of clients need Zoho from day one, both adapters must be built in Phase 1 (Foundation), before the Bookkeeping Agent build in Phase 2 — not sequenced as a later add-on. This grows Phase 1's scope (see Feature Backlog v0.2).
- **A Zoho sandbox spike belongs in Phase 0**, mirroring the existing WhiteBooks GSP spike (P0-04) and PaddleOCR validation (P0-05): validate the OAuth flow, the Bill/Journal-posting shape, and Zoho's published API rate limits before Sprint 1 begins. This ADR is marked Accepted rather than fully Proposed-and-closed because that spike hasn't run yet — the *approach* is decided, the exact rate-limit and pricing-tier numbers are not yet verified against Zoho's own current documentation.
- **New cost line item.** Zoho Books API access requires a paid subscription tier with API enabled per client organization — a new line item for the investment conversation, the same pattern as the GSP cost note (ADR 0002/RC-01b).
- **Per-client OAuth consent UI needed.** The Admin — Connections screen (already wireframed for Tally/GSP health, per TC-05/TC-08) needs a Zoho equivalent: per-client OAuth connection status, token health, and re-consent flow when a refresh token lapses.
- **Client Profiling module gains a field.** `CB-01` (client master profile) needs a `books_system` attribute recorded per client, driving which adapter the platform uses for that client's Bookkeeping/Reconciliation/Working Paper flows.
- **Testing Strategy extends.** Per CG10 and the Testing Strategy's critical-flow list, "Document intake → bookkeeping → voucher posted" (flow #1) needs a Zoho variant alongside the Tally variant; Zoho calls are mocked at the client boundary the same way Tally and the GSP already are.
- **ER model changes.** `TALLY_COMPANY` generalizes to `BOOKS_CONNECTION` (system-agnostic), and `VOUCHER` now references it regardless of backend. See the updated ER diagram.

### Alternatives considered

- **Zoho via file export/import (CSV), mirroring the Tally-backup secondary path (TC-06/07)** — rejected. Full read/write parity was confirmed as the actual requirement, and Zoho's REST/OAuth2 API is materially better suited to real-time automation than a manual file-export workaround. Using the weaker path when a proper API exists would be solving the wrong problem.
- **Build Zoho support as a practice-specific customization under `practices/{practice_slug}/`, per ADR 0010's extension-point pattern** — rejected. At 20-40% of this practice's own client base, and given that a Tally/Zoho split is a common pattern across CA practices generally, this is a generic platform capability likely to matter for future deployments too — it belongs in core, not behind an extension point meant for genuine one-off idiosyncrasies.
- **Defer Zoho support to a later phase, routing Zoho clients through the existing Tally-backup secondary path temporarily** — rejected. This was the original (incorrect) assumption before discovery surfaced the real proportion and the full-parity requirement; explicitly superseded now.

---

## Amendment to ADR 0001 — Tally Integration via XML-over-HTTP

**Status:** Accepted, amended by ADR 0011.

ADR 0001's decision, consequences, and alternatives remain accurate and unchanged **as a description of the TallyAdapter specifically**. What changes is scope: ADR 0001 is no longer "the" bookkeeping integration approach — it is now one of two adapters implementing the `BooksConnector` interface established in ADR 0011. Nothing in ADR 0001's technical content (port 9000, XML-over-HTTP, ODBC being read-only, the TallyPrime API Explorer sandbox, the CG7 duplicate-check requirement) needs to change; only its framing does.
