---
description: File a row in docs/STUB_ISSUES.md for a new untracked stub, placeholder or incomplete implementation. Use when a STUB(PENDING:NNN) marker is needed, or when work surfaces a gap that does not yet meet the promotion threshold for a real GitHub issue.
allowed-tools: Read, Edit, Grep, Glob, Bash(python scripts/*), Bash(gh issue create*)
---

# File a stub / tracked gap

Governed by `CLAUDE.md` ("Stub tracking") and
`docs/CAOS-prompt-conventions.md` §4. Those state the rules; this runs them.

## 1. Decide: PENDING row, or real GitHub issue?

**Make this decision explicitly — `PENDING` is not the default.** Per §4, it
gets promoted to a tracked GitHub issue when **either** is true:

- someone (human, or Claude Code via `/build`'s Anchor step) is about to
  actually start work on it, or
- it is blocking something already in flight.

Until one of those holds, it stays a lightweight row. Not every discovered
gap needs issue ceremony immediately.

**If it does meet the threshold: stop and ask before filing.** Creating a
GitHub issue is outward-facing and visible to everyone on the repo. Show the
exact `gh issue create --title "..." --body "..." --label stub` command and
wait for an explicit go-ahead. Do not file it as part of a batch of edits.

Once a real issue exists, use `STUB(#N)` in code, and if the gap was
previously a `PENDING` row, find-and-replace `STUB(PENDING:NNN)` →
`STUB(#N)` at **every** occurrence and set that row's Status to `Filed`.

## 2. Pick the id

**Derive the next id; never read it from a stored number.** This skill
deliberately does not record what the next free id is — a file that allocates
ids must not also keep a copy of the current one, which goes stale the moment
it is used. Per §9, the grep is the single source:

```bash
grep -o 'PENDING:[0-9]\+' docs/STUB_ISSUES.md | sort -u
```

Take the highest and add one.

**`PENDING:018` is a permanent gap in the sequence and must never be reused.**
That is a standing fact, not a current-state number, which is why it is
recorded here and the next-free id is not.

## 3. Insert into the active table — and only that one

`docs/STUB_ISSUES.md` has **two** tables. Getting this wrong files the row
where nobody looks.

- **Active table** (header `| ID | Location | Title | Blocked on | Status |`)
  — this is the one.
- **Historical table** (header `| ID | Location | Title | Issue | Outcome |`)
  — closed/resolved entries. Never write here.

**Insert after the last row of the active table — do not append to the file.**
The historical table comes *after* the active one, so a literal append lands
in the wrong table: exactly the failure this step warns about. Find the last
`| PENDING:` row that precedes the historical table's header and insert below
it.

Five columns, in that order:

| Column | Contents |
|---|---|
| ID | `PENDING:NNN` |
| Location | File path and the specific function/section, in backticks |
| Title | What is incomplete, stated so a reader who wasn't there understands it |
| Blocked on | The checklist item, spike or credential it waits on — or `Not blocked — <why it is still a row>` |
| Status | `Open`, plus the reasoning and any decision already taken |

## 4. Escape every pipe inside a cell

**Write `\|`, not `|`, for any literal pipe — including inside backticks.**
Backticks do not protect a pipe in a GFM table cell; only a backslash does.
This has caused two real defects here: an unescaped regex in the PRD
changelog (PR #70) and an unescaped union type in the API spec, which
rendered as a broken row for a month (PR #72). Reading the diff caught
neither.

## 5. Close with the marker justification

When the row tracks something that is **not** a Python stub under
`services/api`, end the Status cell with a sentence in this form:

> No `STUB(...)` marker: `<file>` is not Python, the hook only guards `.py`
> files under `services/api`, and there is no incomplete implementation to
> mark — <what is actually true of this item instead>.

15 existing rows carry this. It exists because
`.claude/hooks/post_edit_python.py` only enforces markers on `.py` files
under `services/api`; an untracked stub in a `.yml`, `.toml` or `.md` passes
silently, so the row itself has to carry the justification for having no
in-code marker.

## 6. Verify

```bash
python scripts/check_md_tables.py docs/; echo "exit=$?"
```

Must exit 0. If it reports a column-count mismatch on your new row, the cause
is almost always an unescaped pipe from step 4.
