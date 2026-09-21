---
description: Start a build-phase session — implement a scoped change against an ADR, finding, or issue
---

# Build phase

Before writing any code:

1. **Anchor.** Confirm which ADR, spike finding, or issue governs this change. If none was given, ask rather than assuming.
2. **Scope.** Confirm which service/file(s) this touches. Don't edit outside that scope without flagging it first.
3. **Mode.** Confirm investigate, plan-first, or direct-edit (see `docs/CAOS-prompt-conventions.md` for the distinction). Default to plan-first unless told this is a small, reversible change.

   **If the mode is Investigate:** this is read-only. Do not create a branch, do not change code, do not commit. Reproduce the issue (state how many times and whether it's deterministic or a flake), trace the root cause, and report findings — do not propose or apply a fix unless explicitly asked to move to plan-first or direct-edit afterward.
4. **Standards — check what applies, don't just skim and move on.** Read `docs/CAOS-coding-guidelines-v0.2.md`, `docs/CAOS-security-standard-v0.2.md`, `docs/CAOS-logging-standard-v0.1.md`, and `docs/CAOS-testing-strategy-v0.2.md` for anything relevant. These are the specific traps worth checking explicitly, since they're the ones easy to miss and expensive to fix after merge:
   - **Books-system write (Tally or Zoho):** the duplicate-prevention check (CG7) ships in the *same PR* as the posting logic — never deferred. If the change is adapter-generic, it must be verified against both `TallyAdapter` and `ZohoAdapter`, not just whichever one happens to be the default test target — per ADR 0011, "works on Tally" no longer implies "works."
   - **Money handling:** every amount is `Decimal`, never `float` (CG5) — including values read straight from an external API response before anything else touches them.
   - **External API calls (Tally/Zoho/GSP/OCR):** explicit timeout, bounded retry, and a failure path into a Task rather than an unhandled exception (CG6).
   - **Human-judgment or review paths:** routed through the Task Engine (CG8) — no ad hoc email or flag that routes around it.
   - **Approvals, overrides, reassignments, client-record changes:** these are audit-trail events, not log lines — they go through `AuditTrailService`, never `logger.info` (Logging Standard §5). Easy to get backwards if pattern-matching off nearby logging code.
   - **New settings or credentials:** go through the centralized `Settings` object, never raw `os.environ` (CG4) — and every new setting needs a matching `.env.example` placeholder in the same PR.
   - **New or modified endpoints:** authorization is enforced server-side inside the handler, not just hidden in the UI (Security Standard §2).
   - **`practices/{practice_slug}/` changes:** confirm it's genuinely practice-specific and not actually configuration that belongs in that practice's settings/service-catalog data (CG11) — e.g. `books_system` choice is config, not a practice customization.
   - **New or changed log lines:** GSTIN masked to last 4 characters, no bank account numbers, no raw document content, no client contact details (Logging Standard §6).
   - **New or changed test fixtures:** synthetic only — no real client GSTIN, document, or extracted data (Testing Strategy §4).
5. **External integrations.** If this touches Tally, Zoho Books, GSP, or any other external system, flag explicitly that it needs live/sandbox verification — a passing unit test (which mocks these per CG10/Testing Strategy §2) is not sufficient on its own. If the change is meant to be adapter-generic, confirm it was actually exercised against both adapters, not just described as generic.
6. **New gaps.** If you discover something out of scope (a missing mapping, an undocumented constraint), say so explicitly rather than leaving it as an inline comment. It gets picked up in `/wrapup`.

Do not commit, open a PR, or merge from this command — all of that is handled by `/wrapup`, which is the single end-of-session path to main.
