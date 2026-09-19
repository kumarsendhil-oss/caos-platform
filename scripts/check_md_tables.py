"""Check that every markdown table row has a consistent column count.

A pipe inside an inline code span still splits a GitHub-Flavored Markdown
table cell -- backticks do not protect it, only a backslash escape does.
That trap has produced two real defects in this repo: an unescaped regex
in the PRD's changelog (PR #70) and an unescaped union type in the API
spec, which rendered as a broken row for a month before anything caught
it. Reading the diff did not catch either; a structural check did.

Exit codes: 0 clean, 1 mismatches found, 2 usage error.
"""

from __future__ import annotations

import sys
from pathlib import Path

FENCES = ("```", "~~~")


def count_cells(line: str) -> int:
    """Count GFM table cells, splitting only on unescaped pipes.

    Deliberately does not exempt inline code spans: GFM splits on a pipe
    inside backticks exactly as it does outside them.
    """
    pipes = 0
    escaped = False
    for char in line.rstrip():
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            pipes += 1
    return pipes - 1


def find_tables(lines: list[str]) -> list[list[tuple[int, str]]]:
    """Group consecutive pipe-leading lines into tables, skipping fences."""
    tables: list[list[tuple[int, str]]] = []
    block: list[tuple[int, str]] = []
    in_fence = False
    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith(FENCES):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("|"):
            block.append((number, raw))
        elif block:
            tables.append(block)
            block = []
    if block:
        tables.append(block)
    return tables


def check_table(path: Path, block: list[tuple[int, str]]) -> list[str]:
    """Report rows whose cell count differs from the table's header row."""
    expected = count_cells(block[0][1])
    problems: list[str] = []
    for number, raw in block:
        actual = count_cells(raw)
        if actual != expected:
            problems.append(
                f"{path}:{number}: expected {expected} columns, got {actual}\n"
                f"    {raw.strip()[:100]}"
            )
    return problems


def check_path(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").split("\n")
    problems: list[str] = []
    for block in find_tables(lines):
        problems.extend(check_table(path, block))
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [Path("docs")]
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
        elif target.is_file():
            files.append(target)
        else:
            print(f"error: no such file or directory: {target}", file=sys.stderr)
            return 2

    problems: list[str] = []
    for path in files:
        problems.extend(check_path(path))

    for problem in problems:
        print(problem)
    if problems:
        count = len(problems)
        print(f"\n{count} malformed table row{'s' if count != 1 else ''} "
              f"in {len(files)} file{'s' if len(files) != 1 else ''}.")
        print(r"A pipe inside a table cell must be escaped as \|, even inside backticks.")
        return 1
    print(f"OK: {len(files)} files, all table rows consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
