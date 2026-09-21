---
description: Run the standard pre-report verification sweep and produce the evidence block. Use before reporting any change complete. Invoke once at the start of a change to record baselines, and again at the end to report.
disable-model-invocation: true
allowed-tools: Read, Bash(git status*), Bash(git diff*), Bash(git log*), Bash(wc *), Bash(python scripts/*)
---

# Verify before reporting done

This is the mechanical form of `docs/CAOS-prompt-conventions.md` §2, "Before
saying done". **§2 states the rule; this skill runs it.** If the two ever
disagree, §2 wins and this file is the thing to fix — per §9, one place states
a rule and everything else points at it.

## This skill is invoked twice, not once

Step 2 below reports line counts *before and after*. A count captured only at
the end is a guess dressed as evidence.

- **At the start of a change** — run `## Baseline` and keep the output in the
  session. Nothing is reported to the user yet.
- **At the end** — run `## Report`.

If you reach the end without a baseline, say so plainly in the report
("baseline not captured; before-counts reconstructed from `git diff --stat`")
rather than printing numbers that look measured. `git diff --stat` recovers
the delta for tracked files, but not for files created during the change, and
not at all if the work is uncommitted and the file is new.

## Baseline

Record, for every file the brief puts in scope — including ones that may not
end up being touched:

```bash
wc -l <each in-scope file>
git status --short
git rev-parse --abbrev-ref HEAD
```

Note which files the brief explicitly put **off-limits**. Step 4 of the report
names them.

## Report

Produce all five. Where one genuinely does not apply, say so — an omitted line
reads the same as a skipped check.

1. **`git status`, verbatim.** Paste the whole thing, untracked section
   included. Do not summarise it.

2. **Per-file line counts, before → after**, as a table, with the delta. Cover
   every file touched. A file that was in scope and ended up unchanged belongs
   in step 4, not here.

   **A file created during the change has no baseline.** Report its line count
   and put `new` in the delta column — do not write `+92`, which implies a
   measured before-count of zero rather than a file that did not exist. The
   before/after delta applies to **edited files only**; for created files the
   count is the whole file.

3. **Both doc checks, with exit codes**, whenever anything under `docs/`
   changed:

   ```bash
   python scripts/check_md_tables.py docs/; echo "exit=$?"
   python scripts/check_doc_versions.py docs/; echo "exit=$?"
   ```

   `check_md_tables.py` also runs automatically on every docs edit via the
   PostToolUse hook (`.claude/hooks/post_edit_docs.py`), so a failure should
   already have surfaced. `check_doc_versions.py` is **not** in that hook —
   header-and-changelog consistency only holds once a multi-step edit is
   finished, and enforcing it per-edit would fire on every legitimate
   changelog-row-then-header sequence. This is where it gets checked. Run it.

4. **An explicit list of files NOT touched**, naming every file the brief put
   off-limits, plus any in-scope file that ended up unchanged. "Nothing else
   changed" is not this list. Naming them is what lets a reviewer confirm
   scope without reading the diff.

5. **Required status-check context strings, confirmed unchanged**, quoted
   exactly, whenever the change goes near CI config or workflow job names.
   Today those are `Backend (ruff + pytest)` and `Frontend (typecheck +
   build)`. Branch protection matches by literal string: rename one and it
   reports a context nobody requires, the required context never arrives, and
   every open PR blocks — with `enforce_admins: true` nobody can click
   through it. Verify with `grep -c`, not by eye.

   Note this list is a floor, not a verified complete set: it was read from
   classic branch protection, not from repository rulesets. See `PENDING:022`.

## What this skill does not do

It does not run `ruff` or `pytest` — those are `/wrapup`'s job (its step 1 is
the full CI-gate list) and belong to a build session, not a docs or config
change. Don't duplicate them here.

It does not commit, push, or open a PR.
