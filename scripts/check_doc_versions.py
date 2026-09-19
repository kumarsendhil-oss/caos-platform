"""Check that each document's stated version matches its own changelog.

A document's changelog is the single source of truth for its version
(`docs/CAOS-prompt-conventions.md` section 9). This asserts the two
invariants that keep that true:

  1. The version in the title header equals the newest changelog row.
  2. Changelog rows run oldest first, newest last (section 7), with ties
     on date broken by version.

This exists instead of a version manifest. A manifest stores a copy of
what these files already say, and a stored copy goes stale: PRD section 3
is exactly that table, and it went stale the same day PR #71 rebuilt it.
A check derives its answer from the files every run and has nothing to
drift.

Exit codes: 0 clean, 1 problems found, 2 usage error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# "| v0.2.1 | 2026-09-19 | ..." -- the annotation in "v0.1 (rev)" labels the
# entry, it is not part of the version, so it is captured separately and
# ignored when comparing.
ROW = re.compile(r"^\|\s*(v[0-9][0-9.]*)(\s*\([a-z]+\))?\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|")
HEADER = re.compile(r"(?:Draft\s+)?(v[0-9][0-9.]*)(?:\s*\([a-z]+\))?\s*$")
# Must be a real heading, not a mention of one in prose.
HAS_CHANGELOG = re.compile(r"^## Changelog\s*$", re.MULTILINE)

# ADRs carry **Status:** / **Date:** by their own convention and do not put a
# version in a heading. Only the 0011 addendum has a changelog at all. The
# lint should not dictate document structure, so they are exempt.
EXEMPT = "audit-platform-ADR-"


def version_key(label: str) -> tuple[int, ...]:
    parts = [int(n) for n in re.findall(r"\d+", label)]
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def changelog_rows(lines: list[str]) -> list[tuple[int, str, str]]:
    """Return (line number, version, date) for each changelog row."""
    found = []
    for number, line in enumerate(lines, 1):
        match = ROW.match(line)
        if match:
            found.append((number, match.group(1), match.group(3)))
    return found


def header_version(lines: list[str]) -> str | None:
    for line in lines[:5]:
        if line.startswith("#"):
            match = HEADER.search(line.strip())
            if match:
                return match.group(1)
    return None


def check_order(path: Path, rows: list[tuple[int, str, str]]) -> list[str]:
    keyed = [(date, version_key(version)) for _, version, date in rows]
    if keyed == sorted(keyed):
        return []
    order = " -> ".join(f"{v} ({d})" for _, v, d in rows)
    return [
        f"{path}: changelog rows are not oldest-first (prompt-conventions section 7)\n"
        f"    found: {order}"
    ]


def check_header(path: Path, rows: list[tuple[int, str, str]], lines: list[str]) -> list[str]:
    newest = rows[-1][1]
    stated = header_version(lines)
    if stated is None:
        return [f"{path}: has a changelog but no version in its title header (newest: {newest})"]
    if stated != newest:
        return [
            f"{path}: title header says {stated}, newest changelog row is {newest}\n"
            f"    the changelog is authoritative -- fix the header"
        ]
    return []


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if not HAS_CHANGELOG.search(text):
        return []
    lines = text.split("\n")
    rows = changelog_rows(lines)
    if not rows:
        return []
    return check_order(path, rows) + check_header(path, rows, lines)


def collect(targets: list[Path]) -> tuple[list[Path], int]:
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
        elif target.is_file():
            files.append(target)
        else:
            print(f"error: no such file or directory: {target}", file=sys.stderr)
            return [], 2
    return [f for f in files if EXEMPT not in f.name], 0


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [Path("docs")]
    files, error = collect(targets)
    if error:
        return error

    problems: list[str] = []
    for path in files:
        problems.extend(check_file(path))

    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} version problem(s). A document's changelog is the "
              f"single source of truth for its version.")
        return 1
    checked = sum(1 for f in files if HAS_CHANGELOG.search(f.read_text(encoding="utf-8")))
    print(f"OK: {checked} documents with changelogs, versions consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
