# CAOS — Project Context (living status doc)

Updated by `/wrapup` at the end of each build session. Read this first in any new session — Claude Code or otherwise — before re-deriving status from scratch or asking the human to re-explain it.

## Current focus

Phase 0 Tally integration spike (`spikes/p0-02-tally/`), verifying the multi-backend bookkeeping connector design (ADR 0001, ADR 0011) against a real TallyPrime instance before Sprint 1 starts.

## Active work

**PR #23 — fix voucher read query (finding #11) — MERGED** (`a648dfd`)
- Live-verified 2026-09-16 against `Coastal Services Ltd` via `no_inventory_test.py --send`; runs committed (`runs/2026-09-16T04-34-13-noinv-*`). The split was always landing; the read was broken.
- CG7 confirmed: a byte-identical repost was accepted (`CREATED: 1`), readback went 3 → 4 vouchers. Tally does **not** prevent duplicates, so ADR 0001 stands and CG7's platform-side check is justified.
- Finding #13 (malformed `TYPE:COLLECTION`+`Day Book` crashes Tally's HTTP listener) confirmed non-recurring after the fix.

**PR — `--company` flag for `post_voucher.py` (issue #28, first half) — open, awaiting review**
- Branch: `fix/post-voucher-company-flag`
- `company_from_argv()` resolves `--company`, threaded through all eight `__main__` call sites (`build_reset_duty_heads`, `build_voucher`, `build_read_daybook`, across the dry run and the five `--send` steps). The unthreaded call sites were the actual gap — the flag alone would not have fixed it.
- Adds the validation `no_inventory_test.py`'s copy lacks: a missing value and a flag-as-value both fail with a clear message and exit 1, instead of `IndexError` / silently targeting a company named `--send`.
- **Verified by dry run only** — `ruff` clean, payload inspection for both the default and `--company "Coastal Services Ltd"`, `build_read_daybook(company)` via direct import, and both error paths. No live `--send` run: this is an argv-parsing change and dry-run coverage was judged sufficient.
- **Issue #28 is not closed by this PR** — only the `--company` half is done.

## Next action

Review and merge the `--company` PR above.

Then: the remaining half of **issue #28** — the inventory-bearing voucher shape and BK-01 stock-item mapping for inventory-enabled clients. Finding #7's conclusion (inventory handling is conditional on client config, not universal) is confirmed; what a correct inventory-bearing voucher actually looks like is still untested.

## Known blockers (tracked separately)

- ~~`post_voucher.py` is hardcoded to `Coastal Test Traders` with no `--company` flag~~ — **resolved** by the `fix/post-voucher-company-flag` PR above (issue #28, first half). Previously the argument was silently unread, so a run *looks* like it succeeded against a company it never touched; PR #23 worked around it by verifying via `no_inventory_test.py` instead.
- `no_inventory_test.py`'s own `--company` parsing is still unvalidated (`IndexError` on a missing value, accepts the next flag as a company name) — `STUB_ISSUES` `PENDING:008`, a copy-across of `post_voucher.py`'s `company_from_argv()`.
- Inventory/stock-item mapping for inventory-enabled clients is still unscoped — also #28. Finding #7's conclusion (inventory handling is conditional on client config, not universal) is confirmed; what a correct inventory-bearing voucher looks like is still untested.

## Open anomaly — leading hypothesis, unconfirmed

**Two separate things, related but distinct — don't conflate them.**

**Coastal Services Ltd — benign accumulation (not an anomaly).** Now holds 4 identical `SVC-INV-0001` vouchers. `no_inventory_test.py --send` posts two per run (steps 2 and 4), and the company was not empty when the 2026-09-16 run started — two pre-existed, so two posts produced four. Provenance looks ordinary: all four are `OBJVIEW="Accounting Voucher View"` with sequential REMOTEIDs and voucher numbers 1–4, i.e. leftovers from previous runs of the same script, **not** manual entry. Tracked as `PENDING:009` (no reset mechanism). Expect two more per verification run until that exists.

**Coastal Test Traders — leading hypothesis, unconfirmed.**

A Day Book read against `Coastal Test Traders` on 2026-09-16 returned **6 vouchers**, not the 2 expected per FINDINGS.md #11 (captured ~11 minutes earlier in the same day). One (`REMOTEID ...-00000006`) has `OBJVIEW="Invoice Voucher View"`, unlike the other five (`"Accounting Voucher View"`).

**Leading hypothesis (new 2026-09-16, not confirmed):** voucher #6 is a leftover from a past `post_voucher.py` run against `Coastal Test Traders`, *not* manual UI entry as originally guessed. `post_voucher.py`'s voucher payload emits `OBJVIEW="Invoice Voucher View"` and `PERSISTEDVIEW="Invoice Voucher View"` — confirmed directly in this session's dry-run output — matching #6's outlier value exactly, while the other five match `no_inventory_test.py`'s `"Accounting Voucher View"` shape. That makes the outlier a script signature rather than evidence of a human.

Two reasons this is **not** confirmed, and why the anomaly is downgraded rather than closed:
- voucher #6's `VOUCHERNUMBER` was never captured, so it has not been compared against `post_voucher.py`'s `TEST-INV-0001` constant — the single check that would settle it;
- the timing of #6 relative to any `post_voucher.py` run is unknown.

Re-reading the Day Book against `Coastal Test Traders` and comparing #6's voucher number to `TEST-INV-0001` would confirm or kill this cheaply. Consider resetting `Coastal Test Traders` to a clean state before further duplicate-prevention testing there, since untracked leftover vouchers make it hard to trust what a "new duplicate" test is actually testing against.

## Reference

- All 13 findings: `spikes/p0-02-tally/FINDINGS.md`
- Coding/testing/security/logging/performance standards: `docs/`
- Build/wrap-up workflow: `.claude/commands/build.md`, `.claude/commands/wrapup.md`, `docs/CAOS-prompt-conventions.md`

---
*Last updated: 2026-09-16 by `/wrapup` (`--company` flag, issue #28 first half). Originally seeded manually via claude.ai chat. From this point, `/wrapup` should keep this current — if it isn't, that's a sign `/wrapup` isn't being run, not that the file is wrong.*
