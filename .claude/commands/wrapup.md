---
description: Close out a build-phase session — verify, update context.md and tracked issues, prepare a PR
---

# Wrap-up phase

This is wrap-up, not build — no new feature code. If closing this out turns out to need new implementation work (not just a fix to what's already there), stop and tell the user the build was incomplete, rather than quietly finishing it here.

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
2. **Update `docs/context.md`.** Record:
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
8. **Prepare the PR**, per `docs/CAOS-prompt-conventions.md`:
   - Title: conventional-commit style (`fix(tally): use TYPE:DATA export for vouchers (finding #11)`)
   - Description: what changed, which ADR/finding it implements, what's verified vs. pending, links to any new issues, and any closing keywords from step 5
   - If the description says this reuses a pattern from a prior fix or ADR, confirm that against the actual diff first — state what's genuinely shared (the concept/decision) versus what differs in this implementation, rather than assuming it matches because the situation looks similar.
9. **Confirm before pushing.** Show the PR description and the list of issues it will close, and ask before actually opening/pushing it or closing anything directly.
