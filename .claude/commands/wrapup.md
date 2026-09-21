---
description: Close out a session — verify, update context.md, commit, push, open the PR and merge it. The single end-of-session path to main.
---

# Wrap-up phase

This is wrap-up, not build — no new feature code. If closing this out turns out to need new implementation work (not just a fix to what's already there), stop and tell the user the build was incomplete, rather than quietly finishing it here.

**This is the single end-of-session path to main.** It updates `docs/context.md`, commits it onto the working branch so it merges alongside the work it describes, opens the PR, and merges it. Running only part of this is how `context.md` fell three days behind merged work — it was optional, so it was skipped along with everything else whenever a session didn't feel like a "build".

**Step 2 is unconditional.** Every other step is conditional on there being something to ship; step 2 runs in every session, including one that only investigated and produced no branch. See "Sessions with nothing to merge" at the end.

Before ending the session:

1. **Verify the branch and CI gates.** These are the actual required gates (Testing Strategy §6) — run all of them, don't stop at a subset:
   - `git fetch && git checkout <branch> && git pull`
   - `git status` — must be clean
   - `git log --oneline main..HEAD` — confirm the expected commit(s), nothing stray
   - `ruff check . --no-fix` (CG1) — zero warnings
   - Type check (mypy or ruff's type-aware rules)
   - `pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=85` (CG10) — coverage must actually clear 85%, "tests pass" alone isn't the bar
   - Confirm no new dependency was added without a pinned exact version (CG1 / Security Standard §7)
   - If this change touches books-system write logic: confirm the test suite exercises both `TallyAdapter` and `ZohoAdapter` where the change is adapter-generic (per ADR 0011 / CG7)
   - **Stop if any check fails** — don't proceed to PR prep on a broken check.

   Not required per-PR — only on merge to main (Testing Strategy §6, items 5–6): the integration suite against Tally API Explorer / Zoho Books developer sandbox / WhiteBooks GSP sandbox, and the 4 critical end-to-end flows (including both adapter variants of flow #1). Don't run these speculatively on every wrap-up, but don't skip them if this PR is the one landing on main.
2. **Update `docs/context.md`.** **This step is unconditional — it runs in every session, whether or not there is code to ship.**

   **Write it so it is still true after the merge.** `context.md` is committed in step 7a, *before* the PR merges, so it cannot describe its own merge. Write "pending merge", "landing in this PR", or "landing in the PR from branch `<branch-name>`" — never "merged on `<date>`", which is false at the moment it is written and which nobody comes back to fix. **Do not write a PR number here:** step 7a commits this file before step 8 creates the PR, so any number would be a guess. If you want the number in the text, leave an explicit placeholder and have step 8 back-fill it in a follow-up commit on the same branch — never by amending, since force-push is denied and should stay denied. And because `main` is protected with `enforce_admins: true`, there is no way to push a post-merge correction directly; that would need a second PR, which defeats the point. Get the tense right the first time.

   Record:
   - What was completed this session, with ADR/finding/issue references
   - What's still open or pending live verification
   - Any new gaps discovered, with a link to the tracked item (see next step) rather than left in prose
   - **If this session changed a document under `docs/` that carries a `## Changelog`, decide whether the change earns a changelog row.** This is a judgement the CI check cannot make: `scripts/check_doc_versions.py` enforces that a header matches its newest changelog row, but not whether a row should exist. Per `docs/CAOS-prompt-conventions.md` §8, a change to what a reader understands takes a version bump **and** a row; an encoding or rendering fix that changes no content takes **neither**, and is disclosed in the commit body instead. A reordering, or a header corrected to match the version its changelog already records, is the second kind. **The check is required; a row often is not** — deciding a change is an erratum is a valid outcome, and saying so in the PR description is the point. New rows go **last** (§7, ascending).
   - **If this session added or corrected a `FINDINGS.md` entry, check whether `docs/CAOS-tally-integration-schema-reference.md` needs a matching update.** That document is a view over FINDINGS.md organised by area, so it drifts silently — nothing fails when it goes stale. Three cases to look for: a **new finding** (does it belong in an existing section, or is there now an area the document doesn't cover?), a **corrected finding** (#7 is the precedent — the reference restated a conclusion that turned out to be wrong, so a correction has to propagate or the reference actively misleads), and a **status or severity change** (a gap closing, an unknown moving between §6's cheap/expensive/untested buckets). **The check is required; an edit often isn't** — plenty of findings are already covered by what the reference says, and saying so explicitly is a valid outcome. Note in the PR description which it was.
3. **Track new gaps.** If step 1 or the build session surfaced something new, make sure it's in `STUB_ISSUES` or a GitHub issue — not only mentioned in the PR description. When it crosses the promotion threshold (`docs/CAOS-prompt-conventions.md` §4), create the issue directly with `gh issue create`, using this session's actual findings — don't draft it elsewhere and paste it in.
4. **ADR changes.** If a decision needs revisiting, don't edit the ADR in place — add an amendment or addendum file, matching the existing `ADR-0011-amendment-1-...` / `ADR-0001-...-open-items` pattern.
5. **Close resolved issues.** Identify any GitHub issue this session actually resolved (not just touched). Reference it in the PR description with a closing keyword (`Closes #N` / `Fixes #N`) so it closes automatically on merge. If there's no PR to carry the auto-close — or the issue was resolved outside the diff itself (e.g. a decision resolved by the ADR amendment in step 4) — close it directly and say so, rather than leaving it open with the fix already shipped. Don't close an issue that's only partially addressed; note what remains instead.
6. **Secrets & PII check.** Confirm no credential appears in the diff, in any new log line, or in an error message returned to the frontend (CG4, Security Standard §3/§9). If a new setting was added, confirm `.env.example` got a matching placeholder in this PR. Confirm any new or changed log line follows the masking rules (GSTIN last-4-only, no bank numbers, no raw document content, no contact details — Logging Standard §6), and that anything touching an approval, override, reassignment, or client-record change routes through `AuditTrailService` rather than the logger (Logging Standard §5).
7. **Test data check.** If this session added or changed test fixtures, confirm they're synthetic only — no real client GSTIN, financial document, or extracted data (Testing Strategy §4).
7a. **Commit `docs/context.md` onto the working branch.** Its own commit, `docs(context): <what this session did>`, before any PR exists — so the status update merges in the same PR as the work it describes rather than trailing behind it in a follow-up nobody opens.

8. **Prepare the PR**, per `docs/CAOS-prompt-conventions.md`:
   - Title: conventional-commit style (`fix(tally): use TYPE:DATA export for vouchers (finding #11)`)
   - **Write the body to a file outside the repo** (the session scratchpad) and pass it with `gh pr create --body-file <path>`. **Never `--body` inline, and never a heredoc.** Two quoting failures in one week are the reason this is a rule and not a preference: a PowerShell here-string, and a Bash heredoc that died on ``unexpected EOF while looking for matching `'`` despite being quote-delimited. Both produced no PR. Writing the file with the Write tool sidesteps shell quoting entirely.
   - Description: what changed, which ADR/finding it implements, what's verified vs. pending, links to any new issues, and any closing keywords from step 5
   - If the description says this reuses a pattern from a prior fix or ADR, confirm that against the actual diff first — state what's genuinely shared (the concept/decision) versus what differs in this implementation, rather than assuming it matches because the situation looks similar.
9. **Confirm before pushing.** Show the PR description and the list of issues it will close, and ask before actually opening/pushing it or closing anything directly.

10. **Merge.** Three commands, and the middle one needs its own confirmation.

    ```bash
    # a. Wait for every required check to conclude. Exits non-zero if any fails.
    gh pr checks <n> --watch
    ```

    **Run this as a standalone command — never chained with `&&` after another command.** In PR #82 a case-sensitive `grep` was chained ahead of it, failed to match, and short-circuited the chain; its exit code was then read as the checks' result. The checks never ran, and the failure looked exactly like a check result. An exit code that looks like a result but isn't one is worse than no check at all.

    **A non-zero exit here is a hard stop.** Never merge a PR whose checks are pending or red — fix the failure in this session, where the context still exists, and re-run. Do not retry the merge hoping the check settles.

    ```bash
    # b. Ask the user. Show this exact command. Wait for an explicit yes.
    gh pr merge <n> --merge --delete-branch
    ```

    `--merge` matches this repo's history without exception: 61 merge commits, every PR landing as `Merge pull request #NN from …`, and `required_linear_history` is false. Don't substitute `--squash` or `--rebase`.

    `--delete-branch` is doing real work — `delete_branch_on_merge` is false at repo level, so nothing cleans up the branch otherwise.

    ```bash
    # c. Return to main
    git checkout main && git pull
    ```

    **The `git pull` is required, not a courtesy.** `gh pr merge --delete-branch` switches to the default branch and deletes the local one, but does **not** pull — so the working tree holds the pre-merge state while the merge exists only on the remote. Observed on PR #81: the skill listing showed this file's old description until the pull ran. A second `/wrapup` in the same session would otherwise run the superseded version of this file.

    **On `--auto`:** auto-merge is **disabled** on this repo (`allow_auto_merge: false`), so `gh pr merge --auto` fails outright. If that setting is ever turned on, `gh pr merge <n> --auto --merge --delete-branch` replaces (a) and (b). Note what `--auto` does and does not buy: **branch protection is what holds a merge until checks pass, not `--auto`.** `--auto` only queues the merge so you don't have to wait. The `--watch` form above is arguably better regardless, because it surfaces a red check in the session where it can still be fixed rather than handing the outcome to GitHub after everyone has moved on.

**The two confirmation gates are the control on this command. They do not become skippable for small changes.**

`/wrapup` can now put commits on `main`, which is a meaningful amount of authority for one command. What keeps that safe is narrow: a human says yes before the push, and a human says yes again before the merge, with green required checks in between. Both gates guard separately irreversible actions, which is why there are two rather than one.

The failure mode this command was changed to fix was stale documentation. The failure mode it could introduce is a merge nobody quite decided to make. A future edit that makes either gate conditional — on the change being small, on the checks having passed already, on the session running unattended — trades the second failure for the first and should be refused.

## Sessions with nothing to merge

`/wrapup` degrades; it does not fail. **Step 2 always runs.** The rest is conditional.

| Situation | What happens |
|---|---|
| **Investigate-only session** — no branch, no commits | Steps 1 and 7a–11 are skipped as written, but `context.md` still ships: create a branch, commit the step-2 update as `docs(context): <what was investigated>`, and take it through steps 8–11 as its own small PR. An investigation that produced findings is exactly what `context.md` exists to record. **Do not defer it to the next session** — that is the drift this command was changed to remove. |
| **Working branch with no commits yet** | Not a special case. Step 2 produces the `context.md` commit, and the normal flow continues from 7a. |
| **Work already merged** (`git log --oneline main..HEAD` empty, or `gh pr view --json state` reports `MERGED`) | Skip 7a–10. Still run step 2, and still finish with `git checkout main && git pull`. If step 2 produced changes, they ship as their own PR per the investigate-only row. |
