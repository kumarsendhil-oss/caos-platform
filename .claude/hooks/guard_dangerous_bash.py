#!/usr/bin/env python3
"""
PreToolUse hook on Bash/PowerShell — blocks a short, deliberately
conservative list of commands that would be a real problem in this
specific repo: deleting git history, force-pushing, or hand-editing an
already-applied Alembic migration (which should be a new migration, not
a rewrite of history).

Invoked via bash (see .claude/settings.json — was PowerShell until
2026-09-15; see KNOWN ISSUE below). Patterns cover both PowerShell's own
cmdlets (Remove-Item, git push -Force) and the Bash equivalents
(rm -rf, git push --force), since the matcher fires for either tool
regardless of which shell runs this script.

This is NOT a general security sandbox — Claude Code's own permission
system handles that. This exists for repo-specific footguns worth an
extra deterministic check on top of the model's own judgment.

KNOWN ISSUE — fails OPEN under `"shell": "powershell"`. FIXED on
2026-09-15 by switching this hook to `"shell": "bash"` in
`.claude/settings.json` (which also required `$env:CLAUDE_PROJECT_DIR`
to become `$CLAUDE_PROJECT_DIR`). Blocking now works; verified with a
matching payload that no `permissions.deny` rule covers. Do not switch
this hook back to `"shell": "powershell"` without re-testing.

The history below describes the broken configuration.
Observed on Windows/PowerShell (Claude Code 2.1.226; session transcripts
record version 2.1.266). When a PreToolUse run matches, this script
writes its block message to stderr and returns 2 — but the harness
records exitCode 1. Exit code 2 is the only "block" signal; a 1 becomes
`hook_non_blocking_error` and the command is allowed through.

This is NOT intermittent. Across the 2026-09-15 session, 15 of 15 hook
runs that matched were recorded with exitCode 1 and zero with exitCode
2 — no `hook_blocking_error` event was ever emitted. It affects both
tool surfaces: 13 on PreToolUse:Bash, 2 on PreToolUse:PowerShell.
Invoked directly (`python guard_dangerous_bash.py < payload.json`), the
same payloads return a correct exit code 2 every time, so the
discrepancy is in the harness invocation path, not in this script.

Full write-up, with transcript evidence and environment details:
`.claude/hooks/ISSUE-DRAFT-hook-exit-code.md`.

Occurrences where the command actually executed as a result:
  1. 2026-09-15 — {"tool_name": "Bash",
     "tool_input": {"command": "git push --force"}}
     Reached git; failed only because no remote is configured.
  2. 2026-09-15 — {"tool_name": "Bash",
     "tool_input": {"command": "echo git push --force"}}
     Executed and printed. Caught later only once a matching
     `permissions.deny` rule existed.

The reliable backstop is the `permissions.deny` block in
`.claude/settings.json`, which is enforced by the core permission
engine and does not depend on this script's exit code. This hook is a
second layer, not the guarantee.

Related upstream issues (all three confirmed to exist, 2026-09-15):
  #90077 — hooks with shell:"powershell" spawn pwsh with no fallback.
           RULED OUT here: pwsh 7.6.6 is installed and this hook
           demonstrably ran (its own stderr, realistic durationMs).
  #60664 — PowerShell tool returns exit 1 silently (closed as dup of
           #55727). Same spurious-exit-1 signature, tool path not hook
           path. Not confirmed to be the same defect.
  #94196 — Bash/PowerShell tool fails instantly, exit 1, no output.
           Same caveat as #60664.
"""

from __future__ import annotations

import json
import re
import sys

BLOCKED_PATTERNS = [
    # Deleting .git — bash and PowerShell forms
    (r"\brm\s+-rf\s+.*\.git\b", "Refusing to delete .git — history is not recoverable from here."),
    (
        r"Remove-Item\s+.*-Recurse.*\.git\b",
        "Refusing to delete .git — history is not recoverable from here.",
    ),
    (
        r"\brd\s+/s\s+.*\.git\b",
        "Refusing to delete .git — history is not recoverable from here.",
    ),
    # Force-push — same git syntax regardless of shell.
    # Known false positives: `-f\b` also fires on branch names containing
    # -f (e.g. `git push origin feature/-f-thing`), and any command that
    # merely contains the string (e.g. `echo git push --force`) matches too.
    (
        r"\bgit\s+(-\S+\s+|--\S+\s+|-c\s+\S+\s+)*push\s+.*(--force\b|-f\b|--force-with-lease\b)",
        "Refusing a force-push (including --force-with-lease). Confirm with the user first.",
    ),
    # Migration rollback that drops every table
    (
        r"\balembic\s+downgrade\s+base\b",
        "Refusing 'alembic downgrade base' — this drops every table. "
        "Confirm with the user and downgrade one revision at a time instead.",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    for pattern, message in BLOCKED_PATTERNS:
        # PowerShell cmdlets/flags are case-insensitive (Remove-Item vs
        # remove-item, -Force vs -force) — bash equivalents are already
        # lowercase in practice, so this is safe for both.
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(f"[blocked] {message}\nCommand was: {command}\n")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
