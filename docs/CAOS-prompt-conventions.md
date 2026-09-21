# CAOS — Claude Code Prompt Conventions (draft)

Purpose: keep requests to Claude Code and its output consistent, traceable, and safe to merge without re-litigating context every session. This is a draft — refine once a few sprints have exercised it.

---

## 1. How to phrase requests to Claude Code

**Anchor to a decision, not just an outcome.**
Reference the governing ADR or finding when one exists, rather than re-describing the constraint from scratch.
- Good: "Fix the voucher export per finding #11 — use `EXPORT/TYPE:DATA/ID:Day Book`, not `TYPE:COLLECTION`."
- Avoid: "Make the voucher export work" (forces Claude Code to rediscover context that's already written down).

**Reference guideline rules by number.** `CAOS-coding-guidelines-v0.2.md` numbers its rules CG1–CG11; use that ID in prompts and PRs instead of re-describing the rule ("per CG7" rather than re-explaining duplicate-prevention each time). The logging, security, testing-strategy, and performance docs aren't numbered the same way, and that's staying as-is: coding-guidelines is authored as a flat list of atomic, one-per-item rules, which numbering fits — the other four are organized as topical sections (§1, §2...) each covering substantial ground, not atomic one-liners. Forcing CG-style numbering onto section-structured prose would be artificial. Reference them by section (e.g. "Security Standard §2"); only number an individual rule within one of them if it starts getting referenced piecemeal often enough that pointing to a whole section becomes imprecise.

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

Report these five, every time. **Claude produces this block itself, unprompted, as part of reporting done** — it is not something the user has to ask for.

`/verify-done` is the **user's** independent re-run of the same five items, and it is the same rule, not a second one. The skill carries `disable-model-invocation: true` by design: the model cannot invoke it, and therefore cannot sign off on its own work. So there are two steps — Claude reports the evidence, the user checks it — and an instruction telling Claude to "run `/verify-done`" is asking for something the harness will refuse. Ask for the §2 block instead.

1. **`git status`, pasted verbatim.** Not summarised. The untracked-files section is the part that catches a stray scratch file.
2. **Per-file line counts, before and after.** Requires capturing the baseline *before* editing, so decide at the start of a change that you will be reporting it. A count that only exists after the fact is a guess.
3. **`python scripts/check_md_tables.py docs/` and `python scripts/check_doc_versions.py docs/`, with their exit codes.** Both, whenever anything under `docs/` changed. `check_md_tables.py` also runs automatically on each docs edit via a PostToolUse hook; `check_doc_versions.py` deliberately does not, because header-and-changelog consistency only holds once a multi-step edit is finished — this block is where it gets checked.
4. **An explicit list of files NOT touched**, naming any the brief put off-limits. "I didn't change anything else" is not that list. Naming them is what lets a reviewer confirm scope without reading the whole diff.
5. **Confirmation that any required status-check context string is unchanged**, quoted exactly, when the change goes anywhere near CI config. Branch protection matches these by literal string: a rename reports a context nobody requires, the required one never arrives, and every open PR blocks — with `enforce_admins: true`, nobody can click through it.

Where a step genuinely doesn't apply — no docs changed, so no check scripts — say so rather than omitting it silently. An absent line reads the same as a skipped one.

**Uncertainty.** Where Claude Code is inferring intent rather than following an explicit instruction or ADR, say so in the output rather than presenting an assumption as settled.

**Precision over analogy.** When a PR or report describes something as "reusing" a pattern from a prior fix or ADR, verify that against the actual code/diff rather than assuming it matches because the situation looks similar. Say precisely what's shared (the underlying concept or decision) versus what differs (the actual implementation) — don't let a plausible-sounding analogy stand in for reading the diff.

---

## 3. Branch naming

Codifying the pattern already consistent across the repo's branches (confirmed via `git branch -a`, 2026-09-16, across 16+ branches) — not introducing something new:

`<type>/<short-kebab-case-slug>`

- `<type>` matches the commit-type vocabulary from §2 (`feat`, `fix`, `docs`, `chore`, `test`, etc.) — one taxonomy for both.
- `<slug>` is short and descriptive. Where the work maps to a specific ADR/finding/issue shorthand, use that shorthand in the slug (`adr-0011-a1-followups`, `te-02-routing-rules`) rather than restating the full description — but the issue number itself isn't embedded in the branch name (no observed branch does `fix/123-something`); the PR closes the issue instead, per §2's "PR descriptions."

Examples already in the repo: `fix/voucher-read-daybook`, `docs/seed-context`, `feat/te-02-routing-rules`, `chore/file-stub-issues`.

## 4. STUB_ISSUES vs. a real GitHub issue

A `STUB_ISSUES` entry gets promoted to a tracked GitHub issue when either becomes true:
- Someone (human or Claude Code, via `/build`'s "Anchor" step) is about to actually start work on it, or
- It's blocking something already in flight — e.g. finding #7 blocking full live verification of PR #23 is exactly this case.

Until either is true, it stays a lightweight `STUB_ISSUES` line — not every discovered gap needs full issue ceremony immediately.

## 5. Why this stays a flat doc, not `.claude/rules/`

`.claude/rules/*.md` path-scoped files auto-load based on which files Claude Code is touching — a good fit for file-type-specific guidance. This document is phase-based, not path-based: it governs how a request gets phrased and how output gets prepared, regardless of which files are touched. `/build` and `/wrapup` already reference the relevant part of it at exactly the right moment (mode selection, PR prep and merge), which does the job path-scoping would do, without forcing phase-based content into a shape built for file-glob-based content. Revisit only if a specific piece of this genuinely is file-type-scoped and would benefit from auto-loading — that's a candidate for extraction into `.claude/rules/`, not a reason to move the whole document.

## 6. Prompt convention - fenced code block

When producing a prompt for me to paste into Claude Code, always emit it
in a fenced code block, one block per request, following
docs/CAOS-prompt-conventions.md §1: anchor to the governing ADR/finding,
name the files in scope, state the mode (investigate / plan-first /
direct edit), and state the phase constraint. Never use blockquotes or
prose for these — they can't be copied with one click.

## 7. Changelog order: ascending, newest last

Every changelog table in `docs/` runs **oldest row first, newest row appended
last**. This documents the convention eight of the ten changelogs in `docs/`
already followed rather than imposing a new one — only the Sprint Plan and
Performance & Scaling deviated, and both were corrected on 2026-09-19.

**The primary reason is that ascending fails safe.** A new entry lands where an
append puts it, at the end. Descending needs a top-insert every single time,
and a top-insert is a positioning decision that can be got wrong — which is
exactly how the Sprint Plan's changelog became mixed rather than merely
reversed: `v0.1` first, then `v0.2.3, v0.2.2, v0.2.1, v0.2`. Neither "read the
first row" nor "read the last row" gave the newest version.

Two secondary reasons: a changelog is a chronological record, so ascending is
the order the events actually happened; and eight of ten files already did it,
so this is two files changing rather than eight.

**Why this is worth having as a rule rather than left to taste.** It is the
defect that opened the 2026-09-19 documentation-currency audit. `context.md`
cited the Sprint Plan at v0.2.2 and a reader citing the same file reported
v0.2, and **both were correct** — one had read the changelog, the other the
title header, and the header was stale. Chasing that down then surfaced a
second, subtler case: Performance & Scaling's rows were not merely reversed but
genuinely unsorted (`v0.1` 2026-08-16, `v0.1 (rev)` 2026-09-17, `v0.1
(extracted)` 2026-08-22), so a naive "read the last row" returned
2026-08-22 and missed the 2026-09-17 revision entirely. A misread that a
convention would have prevented is the argument for the convention.

When rows share a date, order them by version — `v0.2.1` before `v0.2.2`, not
whichever sorted first.

A new document inherits this rule. Do not copy the ordering of whichever
neighbouring document it was modelled on; check here.

## 8. Errata vs. versioned changes

**An encoding or rendering fix that changes no content takes no version bump
and no changelog row, but must be disclosed in the commit body. Anything that
changes what a reader understands takes both.**

The worked example is PR #72's fix to `CAOS-api-spec-v0.2.md`: a pipe inside an
inline code span, `` `{status: "cleared"|"blocked"}` ``, was splitting a
markdown table cell and had rendered that row as a broken 7-column row since
2026-08-22. The fix escaped one character to `\|`. No content changed — the
literal was always intended to read `"cleared"|"blocked"` — so it took no bump
and no row, and was disclosed in the commit body instead. A bump would have
restaled the PRD's §3 roadmap row the day after PR #71 rebuilt it, cascading
across three files for no gain to any reader.

**A title header that misstates the version its own changelog already records
is an erratum, not a new version.** Correcting a wrong statement of an existing
fact does not create a new one. The document was already at that version; the
header was simply wrong about it.

This last point had diverged in practice before it was written down, and a
reader finding both precedents should know this section governs: **PR #70**
synced the PRD's header to the version its changelog already showed and added
no row, which is what §8 now requires; **PR #71** synced the Sprint Plan's
header and additionally invented `v0.2.3` for the sync itself. PR #71's extra
version is left in place — rewriting history to match a rule written afterwards
is worse than the inconsistency — but it is not the pattern to copy. The ER
diagram header, corrected on 2026-09-19 from `Draft v0.1 (reconstructed)` to
the `v0.2.1` its changelog already recorded, follows §8.

Reordering existing changelog rows is likewise an erratum: it changes no
content. The 2026-09-19 reordering of the Sprint Plan and Performance & Scaling
changelogs added no rows to either, per this rule applied to itself.

## 9. One place states a version; everything else points

**Exactly one place per document states its version. Every other reference
points at that place rather than copying it.**

For a document with a `## Changelog`, that place is its changelog (§7), and its
title header restates it — enforced mechanically by
`scripts/check_doc_versions.py`, so the header cannot drift from the changelog
without CI failing. For an artifact with no in-repo changelog — the Feature
Backlog and Dev Readiness Checklist spreadsheets, the customer-facing `.docx`,
the wireframes — the PRD's §3 table *is* that one place, and correctly carries
a version there.

Applications on record:

- **`docs/README.md` carries no version numbers at all.** It says what each
  file is; versions live in each file's changelog.
- **`docs/README.md` points at `ADR-INDEX.md` rather than listing ADRs**, so
  ADR status has one home rather than two.
- **§7 and §8 of this document are the single home for changelog convention**,
  rather than each document describing its own.
- **PRD §3 points for the ten documents that have changelogs**, keeping a
  version only for the five artifacts that have no other record.

**Why there is no version manifest.** One was queued from PR #70 onward and is
deliberately not being built. A manifest stores a copy of what these documents
already state, and a stored copy goes stale with nothing to catch it — PRD §3
*is* that table, and it went stale the same day PR #71 rebuilt it, the Coding
Guidelines row still reading v0.2 after PR #73 took the file to v0.2.1. Neither
of the two people looking at it noticed across two subsequent PRs. A manifest
verified by a check is redundant with the check; a manifest not verified by one
is worse than nothing, because it reads as authoritative. The check is the
whole fix.
