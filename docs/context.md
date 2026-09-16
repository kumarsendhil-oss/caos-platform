# CAOS — Project Context (living status doc)

Updated by `/wrapup` at the end of each build session. Read this first in any new session — Claude Code or otherwise — before re-deriving status from scratch or asking the human to re-explain it.

## Current focus

Phase 0 Tally integration spike (`spikes/p0-02-tally/`), verifying the multi-backend bookkeeping connector design (ADR 0001, ADR 0011) against a real TallyPrime instance before Sprint 1 starts.

## Active work

**PR #23 — fix voucher read query (finding #11) — VERIFIED, ready to merge**
- Branch: `fix/voucher-read-daybook`
- Fix: voucher reads must use `EXPORT/TYPE:DATA/ID:Day Book`, not `TYPE:COLLECTION` (which returns zero results with no error — FINDINGS.md #11)
- Status: **live-verified 2026-09-16 against `Coastal Services Ltd`** via `no_inventory_test.py --send`. Runs committed to the branch (`runs/2026-09-16T04-34-13-noinv-*`). This supersedes the earlier `Coastal Test Traders` runs, which were inconclusive because that company is inventory-enabled and rejects plain Purchase vouchers (finding #7) — they could not distinguish a read bug from a post failure.
  - Post real: `CREATED: 1`, `ERRORS: 0`, `EXCEPTIONS: 0` — unlike finding #7's content-free `EXCEPTIONS: 1`
  - Split confirmed **on readback**, not merely accepted: CGST and SGST both 1656.00, no `MISSING`/`WRONG` on any voucher. The split was always landing; the read was broken.
  - CG7 confirmed: a byte-identical repost was accepted (`CREATED: 1`), readback went 3 → 4 vouchers. Tally does **not** prevent duplicates, so ADR 0001 stands and CG7's platform-side check is justified.
- Related: finding #13 (a malformed `TYPE:COLLECTION`+`Day Book` request crashes Tally's HTTP listener) — **confirmed non-recurring** after the fix: all five steps HTTP 200, under 750ms total, no hang and no modal-dialog timeout across both Day Book reads.
- Remaining: merge. Nothing else pending on this PR.

## Next action

Merge PR #23 — verification is complete (see above), CI is green, and nothing on it is outstanding.

Then: **issue #28** (finding #7 follow-up) is the next piece of work — add the `--company` flag to `post_voucher.py`, modelled on `no_inventory_test.py`'s working implementation. Note the flag alone is not enough: `post_voucher.py`'s three builder call sites in `__main__` pass no arguments, so the resolved company has to be threaded through each.

## Known blockers (tracked separately — not blocking PR #23)

- **Now tracked as issue #28.** `post_voucher.py` is hardcoded to `Coastal Test Traders` and has no `--company` flag at all — confirmed 2026-09-16, on every branch. Passing `--company` does not error; the argument is simply unread, so a run *looks* like it succeeded against a company it never touched. Worked around for PR #23 by verifying via `no_inventory_test.py`, which has the flag implemented properly.
- Inventory/stock-item mapping for inventory-enabled clients is still unscoped — also #28. Finding #7's conclusion (inventory handling is conditional on client config, not universal) is confirmed; what a correct inventory-bearing voucher looks like is still untested.

## Open anomaly — not yet explained

**Two separate things, related but distinct — don't conflate them.**

**Coastal Services Ltd — benign accumulation (not an anomaly).** Now holds 4 identical `SVC-INV-0001` vouchers. `no_inventory_test.py --send` posts two per run (steps 2 and 4), and the company was not empty when the 2026-09-16 run started — two pre-existed, so two posts produced four. Provenance looks ordinary: all four are `OBJVIEW="Accounting Voucher View"` with sequential REMOTEIDs and voucher numbers 1–4, i.e. leftovers from previous runs of the same script, **not** manual entry. Tracked as `PENDING:009` (no reset mechanism). Expect two more per verification run until that exists.

**Coastal Test Traders — genuinely unexplained.**

A Day Book read against `Coastal Test Traders` on 2026-09-16 returned **6 vouchers**, not the 2 expected per FINDINGS.md #11 (captured ~11 minutes earlier in the same day). One (`REMOTEID ...-00000006`) has `OBJVIEW="Invoice Voucher View"`, unlike the other five (`"Accounting Voucher View"`) — suggests a different entry path, possibly manual UI entry between sessions. Unresolved. Consider resetting `Coastal Test Traders` to a clean state before further duplicate-prevention testing there, since untracked leftover vouchers make it hard to trust what a "new duplicate" test is actually testing against.

## Reference

- All 13 findings: `spikes/p0-02-tally/FINDINGS.md`
- Coding/testing/security/logging/performance standards: `docs/`
- Build/wrap-up workflow: `.claude/commands/build.md`, `.claude/commands/wrapup.md`, `docs/CAOS-prompt-conventions.md`

---
*Last updated: 2026-09-16, manually seeded via claude.ai chat. From this point, `/wrapup` should keep this current — if it isn't, that's a sign `/wrapup` isn't being run, not that the file is wrong.*
