# CAOS — Project Context (living status doc)

Updated by `/wrapup` at the end of each build session. Read this first in any new session — Claude Code or otherwise — before re-deriving status from scratch or asking the human to re-explain it.

## Current focus

Phase 0 Tally integration spike (`spikes/p0-02-tally/`), verifying the multi-backend bookkeeping connector design (ADR 0001, ADR 0011) against a real TallyPrime instance before Sprint 1 starts.

## Active work

**PR #23 — fix voucher read query (finding #11)**
- Branch: `fix/voucher-read-daybook`
- Fix: voucher reads must use `EXPORT/TYPE:DATA/ID:Day Book`, not `TYPE:COLLECTION` (which returns zero results with no error — FINDINGS.md #11)
- Status: fix implemented, live-verification runs captured against `Coastal Test Traders`, but those runs are inconclusive — see "Next action"
- Related: finding #13 (a malformed `TYPE:COLLECTION`+`Day Book` request crashes Tally's HTTP listener, requiring a manual restart) was discovered while investigating #11 — not yet separately re-verified as non-recurring after the fix

## Next action

Run against `Coastal Services Ltd` (no inventory), **not** `Coastal Test Traders` (inventory-enabled — see "Known blockers"):

```powershell
cd spikes\p0-02-tally
python post_voucher.py --send --company "Coastal Services Ltd"
```

Check: Step 2 should now correctly show CGST 1,656 / SGST 1,656 (previously misreported as missing, per finding #11 — the read was broken, not the tax split). Steps 3–5 deliberately post two more duplicates, cumulative to 4 vouchers in that company by design — expected, not a bug.

If this comes back clean: merge PR #23.

## Known blockers (tracked separately — not blocking PR #23)

- `post_voucher.py` is hardcoded to `Coastal Test Traders`, which is inventory-enabled and rejects plain Purchase vouchers (finding #7). Needs a `--company` flag — confirm current status before assuming it's done.
- Inventory/stock-item mapping for inventory-enabled clients is unscoped (finding #7) — separate piece of work from PR #23.

## Open anomaly — not yet explained

A Day Book read against `Coastal Test Traders` on 2026-09-16 returned **6 vouchers**, not the 2 expected per FINDINGS.md #11 (captured ~11 minutes earlier in the same day). One (`REMOTEID ...-00000006`) has `OBJVIEW="Invoice Voucher View"`, unlike the other five (`"Accounting Voucher View"`) — suggests a different entry path, possibly manual UI entry between sessions. Unresolved. Consider resetting `Coastal Test Traders` to a clean state before further duplicate-prevention testing there, since untracked leftover vouchers make it hard to trust what a "new duplicate" test is actually testing against.

## Reference

- All 13 findings: `spikes/p0-02-tally/FINDINGS.md`
- Coding/testing/security/logging/performance standards: `docs/`
- Build/wrap-up workflow: `.claude/commands/build.md`, `.claude/commands/wrapup.md`, `docs/CAOS-prompt-conventions.md`

---
*Last updated: 2026-09-16, manually seeded via claude.ai chat. From this point, `/wrapup` should keep this current — if it isn't, that's a sign `/wrapup` isn't being run, not that the file is wrong.*
