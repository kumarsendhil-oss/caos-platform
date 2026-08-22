#!/usr/bin/env python3
"""
PreToolUse hook on Bash/PowerShell — blocks a short, deliberately
conservative list of commands that would be a real problem in this
specific repo: deleting git history, force-pushing, or hand-editing an
already-applied Alembic migration (which should be a new migration, not
a rewrite of history).

Invoked via PowerShell (see .claude/settings.json) — patterns below cover
both PowerShell's own cmdlets (Remove-Item, git push -Force) and the Bash
equivalents (rm -rf, git push --force), since the matcher fires for
either tool depending on which one Claude actually used.

This is NOT a general security sandbox — Claude Code's own permission
system handles that. This exists for repo-specific footguns worth an
extra deterministic check on top of the model's own judgment.
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
    # Force-push — same git syntax regardless of shell
    (
        r"\bgit\s+push\s+.*(--force\b|-f\b|--force-with-lease\b)",
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
