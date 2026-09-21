"""Tests for scripts/check_readme_refs.py.

Stdlib `unittest`, not pytest, so the CI job that runs this keeps its
"stdlib only, no install step" property -- it installs nothing but the
pinned ruff.

Each test builds a throwaway repo in a temp directory, writes a README,
and `git add`s selectively. Nothing is ever committed: `git ls-files`
reads the index, so staging is enough and no user.name/user.email has to
exist in the CI environment.

Run: python -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_readme_refs.py"


class RepoCase(unittest.TestCase):
    """A temp git repo with helpers to write, stage and run the check."""

    def setUp(self) -> None:
        # ignore_cleanup_errors: on Windows git leaves handles open in .git
        # briefly after a subprocess exits, and the teardown races them.
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.git("init", "-q")

    def git(self, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), *args], check=True, capture_output=True
        )

    def write(self, rel: str, text: str = "x\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" plus explicit \n: never depend on core.autocrlf or on
        # the platform's default line ending.
        path.write_text(text, encoding="utf-8", newline="")
        return path

    def stage(self, rel: str) -> None:
        self.git("add", "--", rel)

    def run_check(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=str(cwd or self.root),
            capture_output=True,
            text=True,
        )


class TestReferences(RepoCase):
    def test_resolving_reference_passes(self) -> None:
        self.write("docs/CAOS-PRD-v0.2.md")
        self.write("docs/README.md", "| `CAOS-PRD-v0.2.md` | the PRD |\n")
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("all resolve", result.stdout)

    def test_stale_reference_fails(self) -> None:
        self.write("docs/CAOS_Feature_Documentation_v0_6.docx")
        self.write(
            "docs/README.md", "| `CAOS_Feature_Documentation_v0_5.docx` | flows |\n"
        )
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("CAOS_Feature_Documentation_v0_5.docx", result.stdout)
        self.assertIn("does not resolve", result.stdout)

    def test_non_path_tokens_ignored(self) -> None:
        self.write(
            "docs/README.md",
            "IDs `BK-01`, `ENV-05`, a glob `spikes/*.py`, a command `/wrapup`,\n"
            "an identifier `PENDING:NNN`, a bare extension `.xlsx`, a field\n"
            "`created_at` and a URL `https://example.invalid/a.md`.\n",
        )
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 references checked", result.stdout)

    def test_untracked_but_present_file_fails(self) -> None:
        # The case a filesystem check gets wrong: the file is on disk, so
        # globbing would find it, but nobody has staged it.
        self.write("docs/orphan.md")
        self.write("docs/README.md", "| `orphan.md` | never added |\n")
        self.stage("docs/README.md")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("orphan.md", result.stdout)

    def test_basename_fallback_resolves_nested_file(self) -> None:
        self.write("spikes/p0-06-zoho/FINDINGS.md")
        self.write("docs/README.md", "the results (`FINDINGS.md`, scripts)\n")
        self.stage("spikes")
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runs_from_a_subdirectory(self) -> None:
        # Paths must be repo-root-relative whatever the cwd, so a run from
        # inside docs/ must agree with a run from the root.
        self.write("docs/CAOS-PRD-v0.2.md")
        self.write("docs/README.md", "| `CAOS-PRD-v0.2.md` | the PRD |\n")
        self.stage("docs")
        result = self.run_check("README.md", cwd=self.root / "docs")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("all resolve", result.stdout)

    def test_missing_path_argument_is_usage_error(self) -> None:
        self.write("docs/README.md")
        self.stage("docs")
        result = self.run_check("nope/")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("no such file or directory", result.stderr)


class TestKnownAbsent(RepoCase):
    """KNOWN_ABSENT is checked in both directions."""

    NAME = "CAOS-dev-readiness-checklist-v0.1.xlsx"

    def test_declared_absent_reference_is_exempt(self) -> None:
        self.write("docs/README.md", f"- **Dev Readiness Checklist** (`{self.NAME}`)\n")
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_declared_absent_but_tracked_fails(self) -> None:
        self.write(f"docs/{self.NAME}")
        self.write("docs/README.md", f"- **Dev Readiness Checklist** (`{self.NAME}`)\n")
        self.stage("docs")
        result = self.run_check("docs/")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("now git-tracked", result.stdout)
        self.assertIn(self.NAME, result.stdout)


if __name__ == "__main__":
    unittest.main()
