# CAOS — Project Context (living status doc)

Updated by `/wrapup` at the end of each build session. Read this first in any new session — Claude Code or otherwise — before re-deriving status from scratch or asking the human to re-explain it.

## Current focus

Phase 0 Tally integration spike (`spikes/p0-02-tally/`), verifying the multi-backend bookkeeping connector design (ADR 0001, ADR 0011) against a real TallyPrime instance before Sprint 1 starts.

## Active work

**PR #23 — fix voucher read query (finding #11) — MERGED** (`a648dfd`)
- Live-verified 2026-09-16 against `Coastal Services Ltd` via `no_inventory_test.py --send`; runs committed (`runs/2026-09-16T04-34-13-noinv-*`). The split was always landing; the read was broken.
- CG7 confirmed: a byte-identical repost was accepted (`CREATED: 1`), readback went 3 → 4 vouchers. Tally does **not** prevent duplicates, so ADR 0001 stands and CG7's platform-side check is justified.
- Finding #13 (malformed `TYPE:COLLECTION`+`Day Book` crashes Tally's HTTP listener) confirmed non-recurring after the fix.

**PR — `--company` flag for `post_voucher.py` (issue #28, first half) — merged as PR #29 (`9239744`)**
- Branch: `fix/post-voucher-company-flag`
- `company_from_argv()` resolves `--company`, threaded through all eight `__main__` call sites (`build_reset_duty_heads`, `build_voucher`, `build_read_daybook`, across the dry run and the five `--send` steps). The unthreaded call sites were the actual gap — the flag alone would not have fixed it.
- Adds the validation `no_inventory_test.py`'s copy lacks: a missing value and a flag-as-value both fail with a clear message and exit 1, instead of `IndexError` / silently targeting a company named `--send`.
- **Verified by dry run only** — `ruff` clean, payload inspection for both the default and `--company "Coastal Services Ltd"`, `build_read_daybook(company)` via direct import, and both error paths. No live `--send` run: this is an argv-parsing change and dry-run coverage was judged sufficient.
- **Issue #28 is not closed by this PR** — only the `--company` half is done.

**PR — `--company` validation for `no_inventory_test.py` (`PENDING:008`) — merged as PR #30**
- Branch: `fix/no-inventory-test-company-validation`
- Copies `post_voucher.py`'s `company_from_argv()` across verbatim (same signature, same two `sys.exit()` guards, same messages); only the docstring differs, since the original defined itself by contrast with this very file. No call sites changed — `no_inventory_test.py` already threaded `company` correctly.
- Also corrects `post_voucher.py`'s docstring, which cited this file as the cautionary counter-example — a claim this change falsifies directly, so it is fixed in the same diff rather than left stale on a merged file.
- **This closed a live-posting failure mode, not a cosmetic gap.** `--company --send` consumed `--send` as the company value but left it in `sys.argv`, so the `"--send" not in sys.argv` dry-run guard still saw it and the script posted live against a company named `--send`. Now exits 1 before reaching the `--send` branch.
- **Verified by dry run only** — `ruff` clean; backend suite 80 passed / 96.17% (unaffected, no `services/api` files in the diff, and nothing under `tests/` imports `spikes/`). Four cases: default, `--company "Coastal Test Traders"`, `--company` with no value, `--company --send`. No live `--send`; nothing reached Tally.
- `PENDING:008` marked **Resolved** in `docs/STUB_ISSUES.md`. Never promoted to a GitHub issue, so no closing keyword. Issue #28's remaining half is untouched.

**Investigate session — Coastal Test Traders anomaly (read-only, no code changes)**
- Resolved the voucher #6 question from the committed readback artifact alone; no live Tally call.
- Produced **FINDINGS.md #14** (extends #10, does not restate it): `VOUCHERNUMBER` discard confirmed on a second company, mechanism identified as `NUMBERINGSTYLE: Auto Retain`, and the consequence widened from CG7 duplicate-keying to read-back correlation.
- Anomaly narrowed — see the section below. The `TEST-INV-0001` comparison this file called decisive was void.
- New: `PENDING:010` (BK-07 post-verification needs a non-`VOUCHERNUMBER` correlation field; `REMOTEID`/`VCHKEY` is the likely answer per #11).
- **Incidental, relevant to issue #28:** voucher #6 is a real inventory-bearing purchase voucher sitting in the sandbox — `ALLINVENTORYENTRIES.LIST` with `STOCKITEMNAME: Test`, `LEDGERENTRIES.LIST`, `VCHENTRYMODE: Item Invoice`. #28's remaining half needs exactly this shape, and this is a worked example of it from Tally's own storage rather than a guess. Not yet turned into a payload or verified as postable.

**Investigate session — `REMOTEID` vs `VCHKEY` (live read-only, two Day Book reads)**
- Settled which field `PENDING:010`'s correlation direction should use: **`REMOTEID`**, not `VCHKEY`. It is byte-identical to the voucher's own `GUID` and unchanged across repeated reads; `VCHKEY` is demoted on structural grounds. Recorded as **FINDINGS.md #15** with both run artifacts committed.
- `spikes/p0-02-tally/remoteid_stability_probe.py` is committed alongside them — it is the re-run tool for the two risks below, not just the script that produced this result.
- **`PENDING:010` stays open.** Two risks are unverified (restart-stability, edit-stability); they are tracked there, deliberately not restated here.

**Investigate session — restart-stability (live read-only, pre/post TallyPrime restart)**
- Closed the first of `PENDING:010`'s two risks: **`REMOTEID` is byte-identical across a full TallyPrime restart**, all 4 vouchers on `Coastal Services Ltd`. Recorded as an extension to **FINDINGS.md #15** (not a new finding — it closes #15's own open risk), with the pre-restart baseline and post-restart artifact pairs committed.
- Corrected #15's `0000b49a` build/session-handle hypothesis, which the restart disproved. `VCHKEY` stays demoted — that rested on structure, not on the guess.
- **`PENDING:010` stays open on edit-stability alone**, which this test did nothing to reduce; tracked there, not restated here.
- New: `PENDING:012` (the probe's closing banner contradicts a restart result and the script cannot diff across runs).

## Next action

Issue #28's remaining half — the inventory-bearing voucher shape and BK-01 stock-item mapping. Start from voucher #6's structure in `runs/2026-09-16T02-15-54-voucher-2-readback/response.xml` (see above); it is a stored example of the target shape.

Finding #7's conclusion (inventory handling is conditional on client config, not universal) is confirmed; what a correct inventory-bearing voucher looks like when *posted* is still untested.

## Known blockers (tracked separately)

- ~~`post_voucher.py` is hardcoded to `Coastal Test Traders` with no `--company` flag~~ — **resolved** by the `fix/post-voucher-company-flag` PR above (issue #28, first half). Previously the argument was silently unread, so a run *looks* like it succeeded against a company it never touched; PR #23 worked around it by verifying via `no_inventory_test.py` instead.
- Inventory/stock-item mapping for inventory-enabled clients is still unscoped — also #28. Finding #7's conclusion (inventory handling is conditional on client config, not universal) is confirmed; what a correct inventory-bearing voucher looks like is still untested.

## Open anomaly — script origin ruled out, creator unidentified

**Two separate things, related but distinct — don't conflate them.**

**Coastal Services Ltd — benign accumulation (not an anomaly).** Now holds 4 identical `SVC-INV-0001` vouchers. `no_inventory_test.py --send` posts two per run (steps 2 and 4), and the company was not empty when the 2026-09-16 run started — two pre-existed, so two posts produced four. Provenance looks ordinary: all four are `OBJVIEW="Accounting Voucher View"` with sequential REMOTEIDs and voucher numbers 1–4, i.e. leftovers from previous runs of the same script, **not** manual entry. Tracked as `PENDING:009` (no reset mechanism). Expect two more per verification run until that exists.

**Coastal Test Traders — narrowed 2026-09-16 (investigate session, read-only).**

A Day Book read against `Coastal Test Traders` returned **6 vouchers**, not the 2 expected per FINDINGS.md #11. One (`REMOTEID ...-00000006`) has `OBJVIEW="Invoice Voucher View"`, unlike the other five (`"Accounting Voucher View"`).

**The previous leading hypothesis — that voucher #6 came from a past `post_voucher.py` run — is ruled out.** `post_voucher.py` contains zero `INVENTORY`-related code and cannot emit a stock item; voucher #6 carries an `ALLINVENTORYENTRIES.LIST` with `STOCKITEMNAME: Test`, and uses `LEDGERENTRIES.LIST` with `VCHENTRYMODE: Item Invoice`. The `OBJVIEW` match that motivated the hypothesis is a property of invoice entry mode generally, not a `post_voucher.py` signature — it never discriminated between the candidate sources.

**Manual UI entry is indicated but not proven.** The hand-named stock item `Test` and the company's `Maintain Inventory: Yes` both point that way, and it matches the original pre-hypothesis guess. But no artifact records who or what created voucher #6, and a third script or an import from outside this repo has not been excluded. Downgraded from anomaly to unexplained leftover; not worth further spend unless it recurs.

**The check this file previously called "the single check that would settle it" — comparing voucher #6's `VOUCHERNUMBER` against `post_voucher.py`'s `TEST-INV-0001` — is void and has been struck.** Tally auto-assigns voucher numbers (`NUMBERINGSTYLE: Auto Retain`), so **no** voucher in this sandbox can ever carry that value, whatever created it. Voucher #6's number is `6`; so is every other voucher's, sequentially. See FINDINGS.md #14.

Resetting `Coastal Test Traders` to a clean state before further duplicate-prevention testing still stands (`PENDING:009`) — leftover vouchers make it hard to trust what a duplicate test measures against.

## Reference

- All 13 findings: `spikes/p0-02-tally/FINDINGS.md`
- Coding/testing/security/logging/performance standards: `docs/`
- Build/wrap-up workflow: `.claude/commands/build.md`, `.claude/commands/wrapup.md`, `docs/CAOS-prompt-conventions.md`

---
*Last updated: 2026-09-16 by `/wrapup` (finding #15, `REMOTEID` confirmed as the correlation field). Originally seeded manually via claude.ai chat. From this point, `/wrapup` should keep this current — if it isn't, that's a sign `/wrapup` isn't being run, not that the file is wrong.*
