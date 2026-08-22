# Stub / Incomplete Code Tracker

Per the CLAUDE.md convention: every stub, hardcoded placeholder, or
intentionally incomplete implementation in this codebase must carry a
`STUB(...)` marker in a comment, and that marker must resolve to something
tracked — either a real GitHub issue (`#123`) once this repo has a GitHub
remote and `gh` is authenticated, or an entry in this file
(`PENDING:NNN`) until then.

**This repo has no GitHub remote configured yet**, so every stub below is
`PENDING`, not a real issue. Once the repo is pushed to GitHub:

```bash
gh issue create --title "<title from the table>" --body "<body>" --label stub
# then find-and-replace STUB(PENDING:NNN) -> STUB(#<real number>) at the
# locations listed below, and mark this file's Status column Filed.
```

## Open stubs

| ID | Location | Title | Blocked on | Status |
|---|---|---|---|---|
| PENDING:001 | `app/books_connector/tally_adapter.py` — `extract_purchase_register`, `extract_sales_register`, `extract_bank_book` | Implement Tally register extraction via XML-over-HTTP (TC-02) | Dev Readiness Checklist `P0-02` (port 9000 reachability), `ENV-05` (TallyPrime API Explorer sandbox access) | PENDING |
| PENDING:002 | `app/books_connector/tally_adapter.py` — `post_entry` | Implement Tally voucher posting via XML import (TC-04) | `P0-02`, `ENV-05` | PENDING |
| PENDING:003 | `app/books_connector/tally_adapter.py` — `connection_health` | Implement real Tally Cloud host ping for connection health (TC-05) | `P0-02` | PENDING |
| PENDING:004 | `app/books_connector/zoho_adapter.py` — `extract_purchase_register`, `extract_sales_register`, `extract_bank_book` | Implement Zoho Books register extraction via REST API v3 (ZB-02) | `P0-06` (Zoho sandbox spike), `ENV-07` (Zoho developer account + sandbox org) | PENDING |
| PENDING:005 | `app/books_connector/zoho_adapter.py` — `post_entry` | Implement Zoho Bill/Journal Entry posting (ZB-03) | `P0-06`, `ENV-07` | PENDING |
| PENDING:006 | `app/books_connector/zoho_adapter.py` — `connection_health` | Implement Zoho OAuth refresh-token validation for connection health (ZB-05) | `P0-06` | PENDING |
| PENDING:007 | `app/task_engine/service.py` — `escalate_overdue` | Route escalation to a specific role/person via TE-02's routing rule table, instead of only flipping task status | TE-02's routing rule table isn't built yet (Sprint 1-2 deliverable, per Sprint Plan) | PENDING |

## Suggested issue bodies (for when these get filed for real)

**PENDING:001 / PENDING:004 — register extraction**
> `TallyAdapter`/`ZohoAdapter.extract_*` currently raise `NotImplementedError`.
> Implement against the real sandbox once credentials exist (see "Blocked
> on" column). Normalize output to the `LedgerLine` shape in
> `app/books_connector/base.py` — both adapters must produce the same
> schema (TC-03 / ZB-02). Add integration tests per Testing Strategy §2
> (sandbox-only, not in the unit CI gate).

**PENDING:002 / PENDING:005 — posting**
> Implement the write path. CG7's duplicate-check happens in the caller,
> not here — don't re-implement it in the adapter. Money fields must be
> `Decimal` end-to-end (CG5). Add the dual-adapter variant of critical
> flow #1 per Testing Strategy §3 once both PENDING:002 and PENDING:005
> are done.

**PENDING:003 / PENDING:006 — connection health**
> Real health check replacing the current `"unknown"` stub return value.
> Surfaces on the Admin — Connections screen (TC-05 / ZB-05).

**PENDING:007 — TE-02 routing**
> `escalate_overdue()` currently just sets `status="escalated"` without
> picking a specific assignee. Needs the routing rule table (task_type →
> default role/person) from TE-02, plus the `PUT /admin/routing-rules/{task_type}`
> endpoint already specified in the API Spec §4.
