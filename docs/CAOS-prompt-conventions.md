# CAOS — Claude Code Prompt Conventions (draft)

Purpose: keep requests to Claude Code and its output consistent, traceable, and safe to merge without re-litigating context every session. This is a draft — refine once a few sprints have exercised it.

---

## 1. How to phrase requests to Claude Code

**Anchor to a decision, not just an outcome.**
Reference the governing ADR or finding when one exists, rather than re-describing the constraint from scratch.
- Good: "Fix the voucher export per finding #11 — use `EXPORT/TYPE:DATA/ID:Day Book`, not `TYPE:COLLECTION`."
- Avoid: "Make the voucher export work" (forces Claude Code to rediscover context that's already written down).

**Reference guideline rules by number.** `CAOS-coding-guidelines-v0.2.md` numbers its rules CG1–CG11; use that ID in prompts and PRs instead of re-describing the rule ("per CG7" rather than re-explaining duplicate-prevention each time). The logging, security, and testing-strategy docs aren't numbered the same way — reference them by section (e.g. "Security Standard §2") until/unless they get the same treatment.

**Flag adapter-parity explicitly.** Since ADR 0011 (the Tally/Zoho dual-backend), a change to books-system write logic that's meant to be adapter-generic isn't done until it's been exercised against both `TallyAdapter` and `ZohoAdapter`. State which adapter(s) a request or a report covers — "Tally only for now" or "both adapters" — since this is the single easiest thing to silently under-scope after ADR 0011.

**Name the scope explicitly.**
State which service/module/file the change belongs to. In a multi-service repo, "fix the export" is ambiguous; "fix it in `services/tally/vouchers.py`" is not.

**Say which mode you want.**
- *Investigate* — read-only. No branch, no code changes, no commits. Used to reproduce a bug, confirm a hypothesis, or assess impact before committing to a fix approach. Ends in a report, not a diff. Use this whenever the fix approach isn't decided yet — don't let Claude Code default to fixing what it was asked to investigate.
- *Plan first* — for anything touching more than one file, a schema, an ADR-governed decision, or something you haven't reviewed yet. Ask for a plan or diff summary before it edits.
- *Direct edit* — for small, well-scoped, reversible changes (typo fixes, adding a flag, one-file bug fixes) where a plan step just adds friction.
State which one you want; don't leave Claude Code to guess.

**State the phase constraint when relevant.**
CAOS is still pre-sprint / design-doc phase. If a request could imply starting implementation work ahead of that, say so explicitly ("this is exploratory, not for merge" or "we're past design review on this ADR, go ahead").

**Flag when something needs verification against a live system.**
Anything touching Tally, GSP, or other external integrations should be called out as needing manual/live verification before merge — Claude Code should not treat a passing unit test as sufficient for those paths.

---

## 2. Conventions for Claude Code's own output

**Commits.** Conventional-commit style: `<type>(<scope>): <summary>`, e.g. `fix(tally): use TYPE:DATA export for vouchers (finding #11)`. Reference the finding/ADR/issue number in the body when one exists.

**PR descriptions.** Include: what changed, which ADR/finding it implements or amends, what's been verified vs. still needs live verification, and any new open items it surfaces (link or create the issue rather than leaving it in prose).

**Touching an ADR.** Don't edit an existing ADR's decision in place. Add an amendment or addendum (matches the existing `ADR-0011-amendment-1-...` / `ADR-0001-...-open-items` pattern) so the decision history stays intact.

**New open items.** When work surfaces a gap (e.g. the inventory/stock-item mapping gap against BK-01), raise it as a tracked item (`STUB_ISSUES` or a GitHub issue) rather than leaving it as a code comment or chat note.

**Before saying "done."** Run the closest relevant tests and lint; report what ran and what didn't, rather than asserting completion. Don't claim a fix is verified against Tally unless it was actually run against a live instance.

**Uncertainty.** Where Claude Code is inferring intent rather than following an explicit instruction or ADR, say so in the output rather than presenting an assumption as settled.

**Precision over analogy.** When a PR or report describes something as "reusing" a pattern from a prior fix or ADR, verify that against the actual code/diff rather than assuming it matches because the situation looks similar. Say precisely what's shared (the underlying concept or decision) versus what differs (the actual implementation) — don't let a plausible-sounding analogy stand in for reading the diff.

---

## Open questions (fill in as conventions solidify)
- [ ] Branch naming convention
- [ ] Who/what triggers moving an item from `STUB_ISSUES` to a real GitHub issue
- [ ] Whether `.claude/rules/` path-scoped files should carry any of this instead of a flat conventions doc
- [ ] Whether the logging, security, and performance docs should get CG-style rule numbers too, now that coding guidelines has one
