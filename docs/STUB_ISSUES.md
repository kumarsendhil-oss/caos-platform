# Stub / Incomplete Code Tracker

Per the CLAUDE.md convention: every stub, hardcoded placeholder, or
intentionally incomplete implementation in this codebase must carry a
`STUB(...)` marker in a comment, and that marker must resolve to something
tracked — either a real GitHub issue (`#123`) once this repo has a GitHub
remote and `gh` is authenticated, or an entry in this file
(`PENDING:NNN`) until then.

**All seven original stubs were filed as real GitHub issues on 2026-09-15**
against `kumarsendhil-oss/caos-platform` (issues #1–#7, label `stub`), and
every `STUB(PENDING:NNN)` marker in `services/api` was replaced with the
corresponding `STUB(#N)`. The ID column below keeps the historical
`PENDING:NNN` id so markers in older commits stay traceable.

For a **new** stub from here on, file the issue first and use `STUB(#N)`
directly:

```bash
gh issue create --title "<title>" --body "<body>" --label stub
```

Fall back to a `PENDING:NNN` marker (next unused number, plus a row here)
only if `gh` is unavailable or unauthenticated at the time.

## Open stubs

| ID | Location | Title | Blocked on | Status |
|---|---|---|---|---|
| PENDING:001 | `app/books_connector/tally_adapter.py` — `extract_purchase_register`, `extract_sales_register`, `extract_bank_book` | Implement Tally register extraction via XML-over-HTTP (TC-02) | Dev Readiness Checklist `P0-02` (port 9000 reachability), `ENV-05` (TallyPrime API Explorer sandbox access) | Filed — #1 |
| PENDING:002 | `app/books_connector/tally_adapter.py` — `post_entry` | Implement Tally voucher posting via XML import (TC-04) | `P0-02`, `ENV-05` | Filed — #2 |
| PENDING:003 | `app/books_connector/tally_adapter.py` — `connection_health` | Implement real Tally Cloud host ping for connection health (TC-05) | `P0-02` | Filed — #3 |
| PENDING:004 | `app/books_connector/zoho_adapter.py` — `extract_purchase_register`, `extract_sales_register`, `extract_bank_book` | Implement Zoho Books register extraction via REST API v3 (ZB-02) | `P0-06` (Zoho sandbox spike), `ENV-07` (Zoho developer account + sandbox org) | Filed — #4 |
| PENDING:005 | `app/books_connector/zoho_adapter.py` — `post_entry` | Implement Zoho Bill/Journal Entry posting (ZB-03) | `P0-06`, `ENV-07` | Filed — #5 |
| PENDING:006 | `app/books_connector/zoho_adapter.py` — `connection_health` | Implement Zoho OAuth refresh-token validation for connection health (ZB-05) | `P0-06` | Filed — #6 |
| PENDING:008 | `spikes/p0-02-tally/no_inventory_test.py` — `__main__` argv parsing | `--company` took its value with no validation: `IndexError` when the flag was last with no value, and the next flag silently accepted as the company name. `--company --send` targeted a company called `--send` **and still posted live** — consuming `--send` as a value did not remove it from `sys.argv`, so the `"--send" not in sys.argv` dry-run guard did not catch it | Nothing — resolved by `fix/no-inventory-test-company-validation`, a copy-across of `post_voucher.py`'s `company_from_argv()` (PR #29). Never promoted to a GitHub issue, so no closing keyword | **Resolved** |
| PENDING:009 | `spikes/p0-02-tally/` — both sandbox companies | No reset or cleanup mechanism between verification runs. `Coastal Services Ltd` has accumulated 4 `SVC-INV-0001` duplicates (two per run of `no_inventory_test.py --send`), the same problem `docs/context.md` already flags for `Coastal Test Traders`. Untracked leftovers make it hard to trust what a duplicate-prevention test is measuring against | Nothing — but worsens with every verification run | PENDING |
| PENDING:010 | `app/books_connector/tally_adapter.py` — post-verification correlation (BK-07) | Carry-forward of finding #10's open item and #11's `REMOTEID`/`VCHKEY` note. #14 rules out `VOUCHERNUMBER` (Tally auto-assigns it). **#15 narrows this to `REMOTEID`, not `VCHKEY`**: `REMOTEID` is byte-identical to the voucher's own `GUID` and stable across repeated reads, while `VCHKEY`'s middle segment (`0000b49a`) is an unexplained constant shared across two companies and may be a build/session handle. `TallyAdapter` should capture `REMOTEID` at post time | **Still open** — per-response stability is confirmed, but two risks are not: stability across a TallyPrime restart (the live concern for `VCHKEY`) and across a voucher edit (untested — `ALTERID` still equals `MASTERID` everywhere, an absence of a negative result, not a positive one). `post_entry` (#1) may be built on `REMOTEID` before these settle; the platform should not *depend* on the correlation in production until at least the restart case is checked. Re-run `spikes/p0-02-tally/remoteid_stability_probe.py` under each condition | PENDING |
| PENDING:011 | `spikes/p0-02-tally/` — `company_from_argv()` duplicated three times | `post_voucher.py`, `no_inventory_test.py` and `remoteid_stability_probe.py` each carry a byte-identical copy. Copying was deliberate for the first two (spike scripts are standalone by design, and PR #30 explicitly chose copy-across over a shared helper); the third copy is where that trade-off flips. A shared `spikes/_args.py`, alongside the existing `_runner.py`, would be the consistent home — `_runner.py` already establishes that spikes share infrastructure | Nothing — deliberately deferred, not blocked. Low value on its own; worth doing the next time one of these scripts is edited for another reason, or if a fourth copy appears. Note the copies are currently identical, so this is duplication, not drift — if they diverge, fix that first | PENDING |

## Resolved

| ID | Location | Title | Issue | Outcome |
|---|---|---|---|---|
| PENDING:007 | `app/task_engine/service.py` — `escalate_overdue` | Route escalation to a specific role/person via TE-02's routing rule table, instead of only flipping task status | #7 | Resolved — TE-02 routing rules implemented; `RoutingRule` model, migration, and `GET`/`PUT /admin/routing-rules` landed. Escalation now targets the role above the routine owner. |

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

**PENDING:007 — TE-02 routing** *(resolved — kept for the record)*
> `escalate_overdue()` currently just sets `status="escalated"` without
> picking a specific assignee. Needs the routing rule table (task_type →
> default role/person) from TE-02, plus the `PUT /admin/routing-rules/{task_type}`
> endpoint already specified in the API Spec §4.
