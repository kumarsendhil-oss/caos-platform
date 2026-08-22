#!/usr/bin/env python3
"""
PostToolUse hook — after Claude edits or writes a Python file under
services/api, run ruff against it. Enforces CG1 ("zero warnings before
commit") continuously instead of hoping it gets checked before a commit.

Invoked as `python "$env:CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_python.py"`
via PowerShell (see .claude/settings.json) — the shebang above is a
no-op on Windows and harmless elsewhere; this script is always launched
explicitly with `python`, never executed directly.

Also enforces the stub-tracking convention (see CLAUDE.md): any TODO,
FIXME, HACK, XXX, or NotImplementedError must carry a STUB(#123) or
STUB(PENDING:NNN) marker so incomplete code can't silently ship untracked.

If the file is a model under app/models/, also run the model test suite
and print a reminder about generating an Alembic migration — models and
migrations drift apart easily if that step gets forgotten mid-session.

Reads the standard PostToolUse hook payload from stdin (JSON with
tool_name / tool_input). Exit 0 = fine, nothing blocking. Exit 2 = ruff,
an untracked stub, or the tests found something; stderr is fed back to
Claude so it can fix it in the same turn, per Claude Code's documented
hook exit-code contract.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_DIR = PROJECT_ROOT / "services" / "api"
IS_WINDOWS = os.name == "nt"

STUB_TRIGGER = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b|NotImplementedError\(", re.IGNORECASE)
STUB_MARKER = re.compile(r"STUB\((#\d+|PENDING:\d+)\)")


def venv_exe(name: str) -> Path:
    """
    Cross-platform venv executable lookup. Windows venvs put executables
    in .venv\\Scripts\\<name>.exe; everywhere else it's .venv/bin/<name>.
    """
    scripts_dir = API_DIR / ".venv" / ("Scripts" if IS_WINDOWS else "bin")
    exe_name = f"{name}.exe" if IS_WINDOWS else name
    return scripts_dir / exe_name


def find_untracked_stubs(source: str) -> list[tuple[int, str]]:
    """Lines with a stub/incomplete-code trigger but no tracked STUB(...) marker."""
    violations = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if STUB_TRIGGER.search(line) and not STUB_MARKER.search(line):
            violations.append((lineno, line.strip()))
    return violations


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # nothing to act on

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        return 0

    path = Path(file_path)
    if path.suffix != ".py":
        return 0
    try:
        rel_to_api = path.resolve().relative_to(API_DIR.resolve())
    except ValueError:
        return 0  # not under services/api — not our concern

    if path.exists():
        untracked = find_untracked_stubs(path.read_text())
        if untracked:
            lines_report = "\n".join(f"  line {n}: {text}" for n, text in untracked)
            sys.stderr.write(
                f"[stub-tracking] {rel_to_api} has stub/incomplete markers with no "
                f"tracked reference:\n{lines_report}\n\n"
                f"Every TODO/FIXME/HACK/XXX/NotImplementedError needs a STUB(#123) "
                f"(real GitHub issue) or STUB(PENDING:NNN) (see docs/STUB_ISSUES.md) "
                f"marker on the same line. Add the marker, and add a row to "
                f"docs/STUB_ISSUES.md if it's a new PENDING entry.\n"
            )
            return 2

    ruff_exe = venv_exe("ruff")
    ruff_cmd = [str(ruff_exe), "check", str(rel_to_api), "--no-fix"] if ruff_exe.exists() else [
        "ruff", "check", str(rel_to_api), "--no-fix"
    ]

    result = subprocess.run(ruff_cmd, cwd=API_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"[CG1] ruff found issues in {rel_to_api}:\n{result.stdout}\n")
        return 2

    # Models changed — remind about migrations, run the model tests as a fast sanity check.
    if str(rel_to_api).startswith("app/models/") and rel_to_api.name != "__init__.py":
        pytest_exe = venv_exe("pytest")
        pytest_cmd = (
            [str(pytest_exe), "tests/test_models.py", "-q"]
            if pytest_exe.exists()
            else ["pytest", "tests/test_models.py", "-q"]
        )
        test_result = subprocess.run(pytest_cmd, cwd=API_DIR, capture_output=True, text=True)
        if test_result.returncode != 0:
            sys.stderr.write(
                f"[CG10] tests/test_models.py failed after editing {rel_to_api}:\n"
                f"{test_result.stdout}\n"
            )
            return 2
        # Non-blocking reminder — printed to stdout so it doesn't misuse the
        # exit-2 "blocking error" channel for something that isn't an error.
        # Depending on the Claude Code version this may only reach the debug
        # log rather than the transcript; that's an acceptable degradation
        # for an FYI-level reminder.
        print(
            f"[reminder] {rel_to_api} changed — run "
            f'`alembic revision --autogenerate -m "..."` and read the generated '
            f"migration before applying it."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
