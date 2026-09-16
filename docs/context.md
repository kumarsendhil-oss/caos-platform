# CAOS — Project Context (living status doc)

Updated by `/wrapup` at the end of each build session. Read this first in any new session — Claude Code or otherwise — before re-deriving status from scratch or asking the human to re-explain it.

## Current focus

Phase 0 Tally integration spike (`spikes/p0-02-tally/`), verifying the multi-backend bookkeeping connector design (ADR 0001, ADR 0011) against a real TallyPrime instance before Sprint 1 starts.

## Active work

**TallyPrime crash during deletability probe — finding #22 (2026-09-16)**
- **CRITICAL, and it escalates #13.** `ACTION="Delete"` for a stock item that **did not exist** crashed TallyPrime: `Software Exception c0000005 (Memory Access Violation)`. Process dead, **full restart required** — dismissing a dialog was not enough, unlike #13.
- Sequence: the `ACTION="Create"` before it failed clean (`LINEERROR: Stock Group 'Primary' does not exist!`, `ERRORS: 0`, `EXCEPTIONS: 1` — #17's pattern for the third time) because the bare word `Primary` is a sentinel, not a name, and this company has **zero stock groups**. So the delete targeted a name that was never created. Artifacts `runs/2026-09-16T09-0*-delprobe-*`; steps 3 and 4 have no `response.xml` because the timeout *is* the evidence.
- **Contrast #16:** the same request shape against a nonexistent *voucher* returns `Voucher does not exist!` in 0.1s. Object type is the only variable.
- **Recovery confirmed clean.** Post-restart read returned `200` in 43ms, byte-identical to the morning's dump. **Nothing was created; sandbox state is unchanged from before this attempt** — 8 vouchers and 1 stock item (`Test`) in `Coastal Test Traders`, exactly as the previous session left it.
- `TallyAdapter` consequence and the upstream bug report are tracked as `PENDING:016`. Also sharpens TC-05: the port stayed `LISTENING` on a dead process, so a socket-level health check would have reported healthy.
- **Stock-item deletability is still unknown** — the probe tested the nonexistent-target path, not the delete path.

**Gap 2 resolved + finding #7 corrected — findings #21, #7 (2026-09-16, authorised live probe)**
- **Gap 2 CLOSED.** Tax ledgers on an inventory-bearing voucher attach at **voucher level, as `LEDGERENTRIES.LIST` siblings of the party**, party line carrying the gross. Candidate 1, correct first try; candidates 2 and 3 not tried. Verified by read-back, not response counters. Artifacts `runs/2026-09-16T08-5*-gap2-*`.
- Two side results: `NARRATION` and `REFERENCE` both survive a post verbatim (so probe vouchers can be self-identifying, which `VOUCHERNUMBER` cannot do per #14); and the control post settled `LEDGERENTRIES.LIST` vs `ALLLEDGERENTRIES.LIST` — invoice-view import accepts the spelling voucher #6 stores.
- **Finding #7's evidence was wrong and is corrected.** It recorded all seven `voucher_variants.py` payloads as failing and concluded Tally requires a stock item on any purchase voucher for an inventory-enabled company. Five of the seven were **created**, with no inventory entries. The real discriminator is `OBJVIEW="Invoice Voucher View"` (B vs D isolates it). The `TallyAdapter` consequence survives, restated as a choice the adapter controls via voucher view — plus an open practice question: accounting-view posting to an inventory-enabled client is *accepted*, but whether it is *correct* for books configured to track stock is a judgement these artifacts don't settle.
- Knock-on: five of the six `Coastal Test Traders` "anomaly" vouchers are now attributed to `voucher_variants.py`, which the mis-recorded #7 had obscured. Only voucher #6 remains unexplained.

**Stock-item master schema — findings #18–#20 (2026-09-16, investigate session)**
- Closes **gap 1** of issue #28's remaining half. One live read-only call (`TYPE>StockItem` collection, `FETCH *`); artifact `runs/2026-09-16T08-45-10-stockitem-master-dump`. No writes.
- `Test` **is** a real stock-item master (`GUID ...-000000d2`, `ALTERID 223`) and the company's only one — Tally did not create it implicitly on import. Its definition is near-empty: no `BASEUNITS`, no `HSNCODE`, no opening balance. The missing unit is why voucher #6's line carries `AMOUNT` with empty `ACTUALQTY`/`BILLEDQTY`/`RATE`.
- **Voucher #6 is therefore the minimum inventory case, not the representative one.** It is good evidence for the *structure* (purchase ledger nested in `ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST`, party ledger at voucher level in `LEDGERENTRIES.LIST`, `VCHENTRYMODE: Item Invoice`) and no evidence at all about quantity/rate/UoM. Don't generalise the empty fields into "quantity is optional".
- Two new findings for BK-01, both new scope: **#19** — `GSTRATEDUTYHEAD` spells the same duty head `SGST/UTGST` on a stock item where ledger `GSTDUTYHEAD` takes `State Tax`, so finding #3's unknown-vocabulary problem is **per-master-type**, not per-field, and a shared `DUTY_HEADS` constant would be silently wrong on one of them. **#20** — `SRCOFGSTDETAILS`/`SRCOFHSNDETAILS` read `As per Company/Stock Group`, so an item's zero rates and absent HSN are deferral placeholders; effective values need the item → stock group → company chain. Tracked as `PENDING:015`.

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
- New: `PENDING:012` (the probe's closing banner contradicts a restart result and the script cannot diff across runs) — **resolved same day** by `fix/probe-cross-run-baseline`.

**Build session — probe cross-run comparison (`PENDING:012`, resolved)**
- `remoteid_stability_probe.py` now does cross-run comparison itself: `--baseline <run dir>` diffs the current read against a prior run's artifacts, and the closing banner is three cases instead of one static claim that contradicted the restart result.
- **Relevant to the next test.** Edit-stability now runs as one command against a pre-edit baseline, rather than two invocations compared by eye — which is how the restart result was actually produced.
- The script still never names the condition. It reports whether identifiers moved since a baseline; asserting *what changed* between the two runs stays with the human, deliberately.
- `flag_value()` extracted so `--baseline` reuses `--company`'s argv guards. This is the file's internal duplication only — **`PENDING:011` (the same helper triplicated across three spike scripts) is untouched and stays open.**

**Investigate session — edit-stability: `PENDING:010` RESOLVED**
- The last open risk is closed. A stored voucher's amount was altered in the Tally UI; **`REMOTEID` survived it**. `REMOTEID` is now confirmed stable across all three conditions — repeated reads, a TallyPrime restart, and an edit — and is the correlation field for `TallyAdapter.post_entry`, including the BK-07 amended-voucher case. Recorded as the third extension to **FINDINGS.md #15**; artifacts committed.
- New fact worth not misreading: **`ALTERID` is a company-wide alteration sequence, not a per-voucher revision counter** (1 → 5 on the edited voucher, with `MASTERID` 1–4 across four vouchers). `ALTERID > MASTERID` means altered; the value orders alterations across the company.
- **Method note carried into #15.** The first post-edit run read every field `SAME` — because the edit had not saved, and the responses were byte-identical. The asserted voucher was also wrong (voucher 1, not 2). Both were caught only by checking amounts, which the probe does not read. An asserted condition is a hypothesis about the evidence, not a fact about it.
- New: `PENDING:013` (the probe treats all field movement as failure, and cannot distinguish a void run from a real result — one root cause, one row).

**Build session — shared argv helper extracted (`PENDING:011`, resolved)**
- `spikes/_args.py` now holds `flag_value(argv, flag, what)` and `company_from_argv(argv, default)`; `post_voucher.py`, `no_inventory_test.py` and `remoteid_stability_probe.py` import from it and retain no local copies. Placed at the `spikes/` root beside `_runner.py`, not inside `p0-02-tally/` — same precedent, and the `sys.path.insert` every script already carries makes it reachable with no new plumbing.
- **The copies were byte-identical; their context was not.** Each closed over a different module-level `COMPANY` (`Coastal Test Traders` vs `Coastal Services Ltd`), which the `PENDING:011` row did not record. So the shared helper takes `default` as a **required positional** — a script silently inheriting another's target company would post to the wrong books. This is the reason the row's own "just move it" framing would have been wrong.
- `flag_value()` is the shared primitive; `company_from_argv()` stays as a named wrapper rather than collapsing into a spelled-out `flag_value(...) or COMPANY` at each call site. That is what keeps the error text byte-identical across all three scripts — three independent spellings could diverge on a typo in a refactor meant to prove nothing changed.
- **Verified as a pure refactor, both directions.** Pre-extraction output was captured to files *first*, then diffed against post-extraction output — not compared by eye. Missing-value and flag-as-value cases on all three scripts, `--baseline` with no value on the probe, and the full default dry-run payloads for both posting scripts: all byte-identical. `--company "Override Co"` confirmed still reaching `<SVCURRENTCOMPANY>`.
- Gates: `ruff` clean on `spikes/` and `services/api`. Backend suite not run — nothing under `services/api/` references `spikes/`, so the diff cannot reach it.
- `PENDING:011` marked **Resolved** in `docs/STUB_ISSUES.md`. Never promoted to a GitHub issue, so no closing keyword. `PENDING:013` is untouched and now has `_args.py` in place to build on.

**PR — field categories in `remoteid_stability_probe.py` (`PENDING:013`)**
- Branch: `fix/probe-field-categories`
- `FIELDS` split into `IDENTITY` (REMOTEID, VCHKEY, GUID) / `CHANGE_TRACKING` (ALTERID) / `CONTEXT` (VOUCHERNUMBER, MASTERID). The `--baseline` banner now reports the actual `PENDING:010`-resolving run (`07-18-22` -> `07-23-13`) as a **success**, not a failure — same artifacts, corrected reading.
- MASTERID is CONTEXT deliberately: it held through the edit so it is not change-tracking, but finding #14 demotes Tally-assigned sequence numbers, so it is not identity either.
- Within-run and cross-run banners are asymmetric on purpose — nothing alters a voucher between two back-to-back reads, so *any* movement there, ALTERID included, is still a failure.
- Also carries per-voucher amounts, so the unsaved-edit run (`07-20-42`) that previously read clean is now caught. Voucher-body content diffing deliberately not built.
- Verified offline against committed artifacts; the FAILURE/NOTEWORTHY branches have no real artifacts and were exercised against synthetic mutations only.
- `PENDING:013` marked **Resolved** in `docs/STUB_ISSUES.md`. Never promoted to a GitHub issue, so no closing keyword.

**Investigate session — voucher deletion / sandbox reset (`PENDING:009`) — findings #16, #17**
- Two live `ACTION="Delete"` attempts against `Coastal Services Ltd`, both refused, neither crashed anything (artifacts `runs/2026-09-16T08-21-*`, `08-22-*`, `08-27-*`). `REMOTEID`+`VCHKEY` → `Voucher does not exist!`; `MASTERID` → `Cannot delete unnamed object: VOUCHER!`.
- **`REMOTEID` distinction worth carrying forward accurately, not flattening to "REMOTEID is stable, done":** it is confirmed stable and correct for **read-back correlation** (finding #15, which BK-07 actually needs — unchanged). It is **not confirmed addressable for writes** — delete, amend-by-id, or any import that identifies an existing voucher. Attempt 1 is direct evidence against the write case. `TallyAdapter` may need to supply `REMOTEID` itself at create time if it ever needs to amend or delete what it posted; untested either way.
- `TAGNAME`/`TAGVALUE` addressing identified as the remaining plausible scheme and **deliberately not tested** — even working, it addresses by a Tally-auto-assigned voucher number that finding #14 proved unreliable.
- `PENDING:009` **Resolved as a documented manual procedure**, not a script: delete/recreate the company in the Tally UI, then re-run `create_ledgers.py`. A reset script would have to key on a field that is either unverified or reassignable, in the company holding #15's evidence voucher.
- New `PENDING:014` — finding #17: `ERRORS: 0` with a `LINEERROR` present and everything zero. `TallyAdapter` must treat `LINEERROR` as failure regardless of counters. Same underlying distrust as finding #2, different mechanism; both guards needed.


## Next action

Issue #28's remaining half is now split in two, with the first half closed.

**Gap 1 — the stock-item master: CLOSED** (findings #18–#20, 2026-09-16). `Test` is a real master; the schema relevant to BK-01's mapping is documented, including the two complications that mapping design now has to account for (#19's per-master-type duty-head vocabulary, #20's inheritance chain).

**Gap 2 — where GST ledgers attach on an inventory-bearing voucher: CLOSED 2026-09-16** (finding #21, live probe run under explicit authorisation).

Tax ledgers attach at **voucher level, as `LEDGERENTRIES.LIST` siblings of the party**, with the party line carrying the gross. Candidate 1 was correct on the first attempt; candidates 2 (tax nested in `ACCOUNTINGALLOCATIONS.LIST`) and 3 (no explicit tax ledgers, inferred from the item) were deliberately not tried, since every attempt is permanent. Confirmed by read-back, not by the response counters — per findings #2 and #17 a `CREATED: 1` proves nothing on its own. A side effect of the control post also settled the `LEDGERENTRIES.LIST` vs `ALLLEDGERENTRIES.LIST` confound: on an invoice-view voucher, import accepts the spelling voucher #6 stores.

**Two things gap 2 did NOT establish, and they are the real remaining scope:**

1. **Tax amounts were supplied, not computed.** CGST/SGST were sent as explicit values and stored verbatim. Whether Tally *derives* correct tax from a stock item's own GST configuration is untested — that was candidate 3, and per finding #20 it requires the item → stock group → company inheritance chain (`PENDING:015`).
2. **Nothing exercised quantity, rate or unit of measure.** The `Test` item has no `BASEUNITS` (finding #18), so every voucher in this sandbox carries empty `ACTUALQTY`/`BILLEDQTY`/`RATE`. An item *with* a unit is untested and is the most likely place for a further surprise.

**If #28 continues, those two are the next scope** — and both need a stock item that does not exist yet in either sandbox, so the first step is creating one (a master write, not a voucher write), not another voucher post.

**The approach needs correcting first, per finding #22.** Two prerequisites before any further master experimentation:

1. **Resolve the parent question.** `PARENT: Primary` is rejected — this company has zero stock groups, and the `<EOT> Primary` seen on `Test` is a sentinel, not a name. Either create a stock group first, or establish how the sentinel must be sent (whether the `\x04` prefix is required on import is untested). This is answerable partly from a read; the `TYPE>StockGroup` dump is already known empty.
2. **Existence-check before every delete, without exception.** Finding #22 makes this mandatory rather than careful: a delete against a nonexistent master crashes the process, and per #2/#3 a prior `CREATED: 1` is not evidence the target exists. Any corrected probe runs create → **read back to confirm** → delete, never create → delete.

Stock-item deletability — the question that decides whether master work is iterative or one-shot — remains open and is now more expensive to ask.

## Known blockers (tracked separately)

- ~~`post_voucher.py` is hardcoded to `Coastal Test Traders` with no `--company` flag~~ — **resolved** by the `fix/post-voucher-company-flag` PR above (issue #28, first half). Previously the argument was silently unread, so a run *looks* like it succeeded against a company it never touched; PR #23 worked around it by verifying via `no_inventory_test.py` instead.
- Inventory/stock-item mapping for inventory-enabled clients — also #28, **substantially scoped as of 2026-09-16**. The stock-item master schema is documented (findings #18–#20) and the postable inventory-voucher shape including tax placement is verified live (finding #21). What remains is narrower than it was: tax *derivation* from the item's GST config via the inheritance chain (`PENDING:015`), and anything involving an item with a unit of measure. Neither is blocked; both need a new stock item in the sandbox first.

## Sandbox state (after the 2026-09-16 gap 2 probe)

Three vouchers were added by finding #21's probe. All three are marked in **both** `NARRATION` and `REFERENCE` — verified to survive a post (finding #21a), unlike `VOUCHERNUMBER`, which finding #14 rules out as an identifier. None can be deleted (finding #16), so they are permanent until a company reset.

| Company | Vouchers | Of which probe artifacts |
|---|---|---|
| `Coastal Test Traders` | 8 | #7 `GAP2-PROBE-CONTROL-DO-NOT-USE-AS-EVIDENCE`, #8 `GAP2-PROBE-TAX-DO-NOT-USE-AS-EVIDENCE` |
| `Coastal Services Ltd` | 5 | one marked `GAP2-PROBE-DO-NOT-USE-AS-EVIDENCE` |

`Coastal Test Traders` 1–5 are `voucher_variants.py`'s output (see below); #6 is the unattributed one. **Treat #7 and #8 as test fixtures, not evidence** — they were constructed to answer one structural question and their amounts were supplied rather than computed.

Resetting either company is the manual `PENDING:009` procedure. Note a reset of `Coastal Test Traders` destroys voucher #6 *and* the `Test` stock item, and `create_ledgers.py` recreates neither — but both are now captured as committed artifacts (`runs/2026-09-16T02-15-54-voucher-4-readback-after-duplicate`, `runs/2026-09-16T08-45-10-stockitem-master-dump`), so a reset costs rebuild time, not evidence.

## Open anomaly — script origin ruled out, creator unidentified

**Two separate things, related but distinct — don't conflate them.**

**Coastal Services Ltd — benign accumulation (not an anomaly).** Now holds 4 identical `SVC-INV-0001` vouchers. `no_inventory_test.py --send` posts two per run (steps 2 and 4), and the company was not empty when the 2026-09-16 run started — two pre-existed, so two posts produced four. Provenance looks ordinary: all four are `OBJVIEW="Accounting Voucher View"` with sequential REMOTEIDs and voucher numbers 1–4, i.e. leftovers from previous runs of the same script, **not** manual entry. Tracked as `PENDING:009`, **resolved 2026-09-16 as a manual procedure** (delete/recreate the company in the Tally UI, then re-run `create_ledgers.py`) — there is no scripted reset and findings #16/#17 explain why there should not be one. Expect two more per verification run unless the company is reset first. Note voucher 1 is no longer identical to the others: it carries the amount change from finding #15's edit test (`21714`, `ALTERID 5`), and is that finding's live evidence.

**Coastal Test Traders — largely resolved 2026-09-16 (investigate sessions; read-only for the attribution work itself, though the same day's gap 2 probe added vouchers 7–8 under separate authorisation).**

A Day Book read against `Coastal Test Traders` returned **6 vouchers**, not the 2 expected per FINDINGS.md #11. One (`REMOTEID ...-00000006`) has `OBJVIEW="Invoice Voucher View"`, unlike the other five (`"Accounting Voucher View"`).

**The five are now identified (2026-09-16) — they are `voucher_variants.py`'s successful posts.** Five of that script's seven variants (A, B, C, F, G) returned `CREATED: 1`, and `runs/2026-09-15T15-38-18-variants-readback` shows exactly 5 vouchers numbered 1–5, all accounting-view. This was obscured because FINDINGS.md #7 recorded all seven as having failed; that text is corrected as of this session. So five-sixths of the "anomaly" was a known script's known output, mis-recorded — not unexplained residue. Only voucher #6 remains unattributed.

**The previous leading hypothesis — that voucher #6 came from a past `post_voucher.py` run — is ruled out.** `post_voucher.py` contains zero `INVENTORY`-related code and cannot emit a stock item; voucher #6 carries an `ALLINVENTORYENTRIES.LIST` with `STOCKITEMNAME: Test`, and uses `LEDGERENTRIES.LIST` with `VCHENTRYMODE: Item Invoice`. The `OBJVIEW` match that motivated the hypothesis is a property of invoice entry mode generally, not a `post_voucher.py` signature — it never discriminated between the candidate sources.

**Manual UI entry is indicated but not proven.** The hand-named stock item `Test` and the company's `Maintain Inventory: Yes` both point that way, and it matches the original pre-hypothesis guess. The 2026-09-16 stock-item dump (finding #18) strengthens this without settling it: `Test` is a genuine master, so it was created deliberately by something, and its `ALTERID 223` against the voucher's `ALTERID 6` puts it far later in the company's alteration sequence than the vouchers. But no artifact records who or what created either the item or voucher #6, and a third script or an import from outside this repo has not been excluded. Downgraded from anomaly to unexplained leftover; not worth further spend unless it recurs.

**The check this file previously called "the single check that would settle it" — comparing voucher #6's `VOUCHERNUMBER` against `post_voucher.py`'s `TEST-INV-0001` — is void and has been struck.** Tally auto-assigns voucher numbers (`NUMBERINGSTYLE: Auto Retain`), so **no** voucher in this sandbox can ever carry that value, whatever created it. Voucher #6's number is `6`; so is every other voucher's, sequentially. See FINDINGS.md #14.

Resetting `Coastal Test Traders` to a clean state before further duplicate-prevention testing still stands — leftover vouchers make it hard to trust what a duplicate test measures against. `PENDING:009` is now resolved, so the *procedure* exists (manual, see above); what remains is remembering to run it before a test whose result depends on a known starting state.

## Reference

- All 13 findings: `spikes/p0-02-tally/FINDINGS.md`
- Coding/testing/security/logging/performance standards: `docs/`
- Build/wrap-up workflow: `.claude/commands/build.md`, `.claude/commands/wrapup.md`, `docs/CAOS-prompt-conventions.md`

---
*Last updated: 2026-09-16 by `/wrapup` (`PENDING:009` — sandbox reset resolved as a manual procedure; findings #16–#17). Originally seeded manually via claude.ai chat. From this point, `/wrapup` should keep this current — if it isn't, that's a sign `/wrapup` isn't being run, not that the file is wrong.*
