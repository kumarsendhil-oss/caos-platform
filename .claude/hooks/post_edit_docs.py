#!/usr/bin/env python3
"""
PostToolUse hook — after Claude edits or writes a markdown file under
docs/, run scripts/check_md_tables.py. Catches a broken GFM table row at
the moment it is introduced rather than at review time.

The defect this exists for: a pipe inside an inline code span still splits
a table cell — backticks do not protect it, only a backslash escape does.
That has produced two real defects in this repo (an unescaped regex in the
PRD changelog, PR #70; an unescaped union type in the API spec, PR #72,
which rendered broken for a month). Reading the diff caught neither; a
structural check did.

Invoked as `python "$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_docs.py"`
via bash (`"shell": "bash"` in .claude/settings.json) — the shebang above
is a no-op on Windows and harmless elsewhere; this script is always
launched explicitly with `python`, never executed directly. The shell is
bash, not PowerShell: under PowerShell these hooks fail open (exit 2 is
recorded as exit 1 and nothing blocks). See the KNOWN ISSUE docstring in
guard_dangerous_bash.py before changing it.

Filtering is done here, not by the settings.json matcher. Hook matchers
are evaluated against the TOOL NAME and cannot match file paths, so the
matcher is the broad `Edit|Write` and this script returns 0 early for
anything that is not a .md file under docs/. (Claude Code also offers an
`if` field taking permission-rule syntax for this; it is deliberately not
used, being unverified on this platform — and this repo has prior history
of documented hook behaviour not holding on Windows.)

DELIBERATELY DOES NOT RUN scripts/check_doc_versions.py. That check
enforces that a document's title header matches the newest row of its own
changelog, which is only true once a multi-step edit is finished — running
it per-edit would fire on every legitimate "add the changelog row, then
update the header" sequence and block the second half of a correct change.
It runs in `/verify-done` instead (its Report step 3), and in CI via
.github/workflows/md-tables.yml.

Reads the standard PostToolUse hook payload from stdin (JSON with
tool_name / tool_input). Exit 0 = fine, nothing blocking. Exit 2 = the
table check failed; stderr is fed back to Claude so it can fix it in the
same turn, per Claude Code's documented hook exit-code contract.

TESTING THIS HOOK — read before concluding it works.

This script returns 0 on a malformed payload, on an unparseable
file_path, and on any path it cannot resolve under docs/. That is the
correct behaviour: a hook must not block an edit because it failed to
understand its own input. But it means the hook can look perfectly
healthy while never actually firing, and a green run proves nothing.

So test it against a file you KNOW is bad -- create a scratch .md under
docs/ with a row whose column count does not match its header, confirm
exit 2 AND the message, then delete the scratch file. A run that exits 0
is only meaningful once you have seen the same setup exit 2.

Generate the payload with Python, not by hand in the shell:

    python -c "import json,pathlib; p=pathlib.Path('docs/x.md').resolve(); \\
      pathlib.Path('payload.json').write_text(json.dumps( \\
      {'tool_name':'Edit','tool_input':{'file_path':str(p)}}))"
    python .claude/hooks/post_edit_docs.py < payload.json; echo "exit=$?"

Both false starts when this hook was written were bad payloads, not hook
bugs, and both presented as a silent exit 0: first a Git Bash path
(`/d/Users/...`), which Python cannot resolve against `D:\\Users\\...` so
the docs/ filter correctly rejected it; then a hand-written JSON string
whose backslash escapes the shell mangled, making the payload invalid
JSON. Python's json.dumps plus Path.resolve() avoids both.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
CHECKER = PROJECT_ROOT / "scripts" / "check_md_tables.py"


def is_docs_markdown(file_path: str) -> bool:
    """True only for a .md file resolving under docs/."""
    path = Path(file_path)
    if path.suffix.lower() != ".md":
        return False
    try:
        path.resolve().relative_to(DOCS_DIR.resolve())
    except ValueError:
        return False
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # nothing to act on

    file_path = payload.get("tool_input", {}).get("file_path")
    if not file_path or not is_docs_markdown(file_path):
        return 0

    if not CHECKER.exists():
        # Don't block on a missing checker — that's a repo problem, not a
        # defect in the edit Claude just made.
        sys.stderr.write(f"[md-tables] checker not found at {CHECKER}; skipped.\n")
        return 0

    result = subprocess.run(
        [sys.executable, str(CHECKER), str(DOCS_DIR)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        rel = Path(file_path).resolve().relative_to(DOCS_DIR.resolve())
        sys.stderr.write(
            f"[md-tables] markdown table check failed after editing docs/{rel}:\n"
            f"{result.stdout}{result.stderr}\n"
            f"A row's column count does not match its header. The usual cause is a "
            f"literal pipe inside a cell -- including inside backticks, which do NOT "
            f"protect it. Escape it as \\| and re-check with "
            f"`python scripts/check_md_tables.py docs/`.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
