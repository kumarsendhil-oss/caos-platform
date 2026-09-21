"""Check that every file reference in a README resolves to a git-tracked file.

`docs/README.md` is an index: almost every row names a file. A row can go
stale in a way no other check in this repo can see. `check_doc_versions.py`
structurally cannot catch it -- it compares a document's header against that
document's own changelog, and a binary deliverable (.docx, .pptx, .xlsx,
.pdf) has no changelog to compare against. That is not hypothetical: the
`CAOS_Feature_Documentation_v0_5.docx` row went stale when PR #78 replaced
the file with v0_6, and it was found by eye, not by a check, and fixed in
PR #83. A convention nobody runs is worth less than a check that runs
itself.

References are resolved against the git index (`git ls-files`), not the
filesystem. The untracked-docs triage showed filesystem globbing silently
counts files nobody has committed -- such a reference passes on the author's
machine and 404s for everyone else. Reading the index gives CI (a fresh
checkout, nothing untracked) and a local run the same answer.

Only inline code spans are treated as references. `docs/README.md` contains
no markdown links today, so link-target parsing would be code with no input
exercising it; add it to `code_spans()` when a link first appears.

KNOWN LIMITATION -- the basename fallback. A token with no slash that
matches no path may still resolve on basename alone, anywhere in the tree.
So a stale bare basename that collides with a different tracked file of the
same name passes: `FINDINGS.md` exists under several spike directories, and
a reference to a deleted further one would be resolved by any of the others.
The anchor case is unaffected (a versioned deliverable filename is unique),
and without the fallback the check reports false positives on a correct
document -- see below.

The fallback and KNOWN_ABSENT both exist because an earlier rule without
them reported six failures against a correct `docs/README.md`, all false:
`FINDINGS.md`, `gsp_requests.py`, `tally_payloads.py`, `zoho_requests.py`
and `.env.example` (real tracked files the index names by bare basename, or
as parenthetical examples expanding a `spikes/*.py` glob row), plus
`CAOS-dev-readiness-checklist-v0.1.xlsx` (declared absent on purpose).

Exit codes: 0 clean, 1 problems found, 2 usage error.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from pathlib import Path

CODE_SPAN = re.compile(r"`([^`]+)`")
EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")
BARE_EXTENSION = re.compile(r"\.[A-Za-z0-9]+")
FENCES = ("```", "~~~")

# Files a README states are deliberately not in this repo, keyed by the
# README that says so. `docs/README.md` section "Delivered separately,
# genuinely not in this repo" declares this one; without the exemption the
# check fails on a correct document. Checked in both directions: if an entry
# here becomes git-tracked, the README's claim is now wrong and that is
# reported too.
KNOWN_ABSENT: dict[str, frozenset[str]] = {
    "docs/README.md": frozenset({"CAOS-dev-readiness-checklist-v0.1.xlsx"}),
}


class Index:
    """The git index, in the three shapes resolution needs."""

    def __init__(self, paths: set[str]) -> None:
        self.paths = paths
        self.dirs = {
            "/".join(p.split("/")[:i]) for p in paths for i in range(1, len(p.split("/")))
        }
        self.basenames: dict[str, str] = {}
        for path in sorted(paths):
            self.basenames.setdefault(path.split("/")[-1], path)


def git(*args: str) -> str:
    """Run a git command, raising CalledProcessError on a non-zero exit."""
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def load_index() -> tuple[Path, Index]:
    """Resolve the repo root and read its index.

    `-z` so non-ASCII names come back raw rather than quoted, and `-C root`
    so paths are repo-root-relative whatever the cwd.
    """
    root = Path(git("rev-parse", "--show-toplevel").strip())
    raw = git("-C", str(root), "ls-files", "-z")
    return root, Index({p for p in raw.split("\0") if p})


def skip_reason(token: str) -> str | None:
    """Why this code span is not a file reference, or None if it is one."""
    if "://" in token:
        return "url"
    if any(char in token for char in " \t*()"):
        return "glob or prose"
    if token.startswith("/"):
        return "slash command"
    if ":" in token:
        return "identifier"
    if BARE_EXTENSION.fullmatch(token):
        return "bare extension"
    if not token.endswith("/") and not EXTENSION.search(token):
        return "no extension"
    return None


def code_spans(lines: list[str]) -> list[tuple[int, str]]:
    """Inline code spans as (line number, token), skipping fenced blocks."""
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, raw in enumerate(lines, 1):
        if raw.strip().startswith(FENCES):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.extend((number, token) for token in CODE_SPAN.findall(raw))
    return found


def candidates(token: str, doc_dir: str) -> list[str]:
    """Repo-root-relative paths to try, in order: doc-relative, then root."""
    tried: list[str] = []
    for base in (doc_dir, ""):
        candidate = posixpath.normpath(posixpath.join(base, token)).lstrip("./")
        if candidate and candidate not in tried:
            tried.append(candidate)
    return tried


def resolve(token: str, doc_dir: str, index: Index) -> str | None:
    """Resolve a reference against the index, or None if nothing matches."""
    for candidate in candidates(token, doc_dir):
        if candidate in index.paths or candidate in index.dirs:
            return candidate
    if "/" not in token:
        return index.basenames.get(token)
    return None


def check_absent(rel: str, lines: list[str], index: Index) -> list[str]:
    """Report KNOWN_ABSENT entries that have since become git-tracked."""
    problems: list[str] = []
    for name in sorted(KNOWN_ABSENT.get(rel, frozenset())):
        tracked = index.basenames.get(name)
        if tracked is None:
            continue
        number = next((n for n, line in enumerate(lines, 1) if name in line), 0)
        problems.append(
            f"{rel}:{number}: `{name}` is declared not in this repo, but it is "
            f"now git-tracked at {tracked}\n"
            f"    the README's claim is out of date -- move the row, or drop the "
            f"KNOWN_ABSENT entry"
        )
    return problems


def check_file(path: Path, root: Path, index: Index) -> tuple[list[str], int]:
    """Check one README. Returns (problems, number of references checked)."""
    rel = path.resolve().relative_to(root).as_posix()
    doc_dir = posixpath.dirname(rel)
    lines = path.read_text(encoding="utf-8").split("\n")
    exempt = KNOWN_ABSENT.get(rel, frozenset())
    problems = check_absent(rel, lines, index)
    checked = 0
    for number, token in code_spans(lines):
        if token in exempt or skip_reason(token) is not None:
            continue
        checked += 1
        if resolve(token, doc_dir, index) is None:
            fallback = ", basename" if "/" not in token else ""
            problems.append(
                f"{rel}:{number}: `{token}` does not resolve to a git-tracked file\n"
                f"    tried: {', '.join(candidates(token, doc_dir))}{fallback}"
            )
    return problems, checked


def collect(targets: list[Path]) -> tuple[list[Path], int]:
    """Expand path arguments to README.md files."""
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.rglob("README.md")))
        elif target.is_file():
            files.append(target)
        else:
            print(f"error: no such file or directory: {target}", file=sys.stderr)
            return [], 2
    return files, 0


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [Path("docs")]
    files, error = collect(targets)
    if error:
        return error
    try:
        root, index = load_index()
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"error: could not read the git index: {exc}", file=sys.stderr)
        return 2

    problems: list[str] = []
    checked = 0
    for path in files:
        found, count = check_file(path, root, index)
        problems.extend(found)
        checked += count

    for problem in problems:
        print(problem)
    if problems:
        count = len(problems)
        print(f"\n{count} unresolved reference{'s' if count != 1 else ''} "
              f"in {len(files)} file{'s' if len(files) != 1 else ''}.")
        print("A README may only name files that are committed to this repo.")
        return 1
    print(f"OK: {checked} references checked in {len(files)} "
          f"file{'s' if len(files) != 1 else ''}, all resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
