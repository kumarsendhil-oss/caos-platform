"""
P0-02 — Is REMOTEID stable per-voucher, or regenerated per-response?

PENDING:010 proposes REMOTEID/VCHKEY as the field correlating a posted
voucher with its source document, since finding #14 rules out
VOUCHERNUMBER. That direction is only viable if the identifier is
assigned once at creation and constant thereafter. Finding #11 named
both fields together; this probe separates them.

Read-only: EXPORT / TYPE: DATA / ID: Day Book, the verified read from
finding #11. It posts nothing and alters nothing, so it is safe to run
against a live instance at any time.

    python remoteid_stability_probe.py
    python remoteid_stability_probe.py --company "Coastal Test Traders"

Two reads inside one invocation can only show per-response stability.
To test whether an identifier survives a *condition* — a restart, an
edit — run once, make the change, then run again pointing at the first
run's artifacts:

    python remoteid_stability_probe.py --baseline runs/2026-09-16T06-49-24-remoteid-stability-read-1

Note what that does and does not establish. The script compares
identifiers between two sets of artifacts; it has no way to observe
what happened between them, only that they differ in time. **The human
asserts the condition, the script checks the identifiers.** It will
never print "stable across a restart" — it prints that the identifiers
did or did not move between the baseline and now, and you supply what
you changed.

Finding #15's two risks:

  - restart-stability: RESOLVED 2026-09-16. REMOTEID byte-identical
    across a full TallyPrime close/reopen (runs 06-49 vs 06-55). This
    also disproved the guess that VCHKEY's 0000b49a segment was a
    build or session handle — it survived the restart. Still
    unexplained, and VCHKEY stays demoted on structural grounds.
  - edit-stability: still open. Run, alter a voucher in the Tally UI,
    run again with --baseline. Untested so far only because no voucher
    has ever been altered — ALTERID equals MASTERID on every voucher
    checked, which is an absence of a negative result, not a positive
    one.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_voucher_read import build_daybook_read  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Services Ltd"
DATE = "20260801"

# REMOTEID and VCHKEY are the candidates; the rest are read alongside
# them because a field that moves while those hold still is a clue.
FIELDS = ("REMOTEID", "VCHKEY", "VOUCHERNUMBER", "MASTERID", "ALTERID", "GUID")


def flag_value(argv: list[str], flag: str, what: str) -> str | None:
    """VALUE for `flag`, or None if the flag is absent.

    Exits with a message rather than raising IndexError when the flag is
    last with no value, and rejects a following flag as the value.
    Extracted so --company and --baseline share one set of guards rather
    than carrying a copy each; this file's own duplication only. The
    cross-file triplication of company_from_argv() across post_voucher.py
    and no_inventory_test.py is STUB_ISSUES PENDING:011 and is untouched.
    """
    if flag not in argv:
        return None
    i = argv.index(flag) + 1
    if i >= len(argv):
        sys.exit(f"error: {flag} requires {what}")
    value = argv[i]
    if value.startswith("--"):
        sys.exit(f"error: {flag} requires {what}, got the flag {value!r}")
    return value


def company_from_argv(argv: list[str]) -> str:
    """--company VALUE, defaulting to COMPANY."""
    return flag_value(argv, "--company", "a company name") or COMPANY


def load_baseline(path_str: str) -> list[tuple[str | None, ...]]:
    """Identifiers from a previous run's artifacts.

    Accepts either a run directory or a response.xml directly — the
    directory form is what _runner.run() prints, so it is what gets
    pasted back in.
    """
    path = Path(path_str)
    if path.is_dir():
        path = path / "response.xml"
    if not path.is_file():
        sys.exit(f"error: no baseline response at {path} — expected a run dir or a response.xml")
    try:
        return identifiers(path.read_text(encoding="utf-8", errors="replace"))
    except ET.ParseError as exc:
        sys.exit(f"error: baseline at {path} is not parseable XML: {exc}")


def identifiers(body: str) -> list[tuple[str | None, ...]]:
    """Every voucher's identifier fields, in Day Book order."""
    root = ET.fromstring(sanitise(body))
    return [
        tuple(v.get(f) if f in ("REMOTEID", "VCHKEY") else v.findtext(f) for f in FIELDS)
        for v in root.iter("VOUCHER")
    ]


def report(
    first: list[tuple[str | None, ...]],
    second: list[tuple[str | None, ...]],
    label_a: str = "r1",
    label_b: str = "r2",
) -> int:
    """Print a field-by-field diff. Returns the number of fields that moved."""
    width = max(len(label_a), len(label_b))
    print(f"\n{label_a}: {len(first)} vouchers | {label_b}: {len(second)} vouchers")
    if len(first) != len(second):
        print("  WARNING: voucher counts differ — something wrote between the two")

    moved = 0
    for i, (a, b) in enumerate(zip(first, second), 1):
        print(f"--- voucher {i} ---")
        for name, va, vb in zip(FIELDS, a, b):
            same = va == vb
            moved += not same
            print(f"  {name:<14} {label_a:>{width}}={va}")
            print(f"  {'':<14} {label_b:>{width}}={vb}   [{'SAME' if same else '*** DIFFERS ***'}]")
    return moved


def banner_within_run(moved: int) -> None:
    """What two reads inside one invocation establish, and nothing more."""
    if moved:
        print(f"{moved} field(s) changed between two identical reads. An identifier")
        print("that moves on read cannot correlate a posted voucher with its")
        print("source document — PENDING:010 needs rethinking, not patching.")
        return
    print("No field changed between the two reads in THIS run. That is")
    print("per-response stability only — this run did not test any condition,")
    print("because nothing changed between the two reads but time.")
    print("\nTo test whether an identifier survives a restart or an edit, make")
    print("the change and re-run against this run's artifacts:")
    print("  python remoteid_stability_probe.py --baseline runs/<this run's read-1 dir>")


def banner_vs_baseline(moved: int, source: str) -> None:
    """What a cross-run comparison establishes — deliberately not the condition.

    The script can see that the identifiers did or did not move between
    two sets of artifacts. It cannot see what happened in between, only
    that time passed. Naming the condition here would be a verdict about
    something unobserved, which is the defect this banner replaced.
    """
    print(f"Compared against baseline: {source}")
    if moved:
        print(f"\n{moved} field(s) MOVED since that baseline. Whatever you changed")
        print("between the two runs, these identifiers did not survive it — see")
        print("the per-field diff above for which ones, on which vouchers.")
        print("An identifier that moves cannot correlate a posted voucher with")
        print("its source document across that condition (PENDING:010).")
        return
    print("\nNo field moved since that baseline. The identifiers survived")
    print("whatever changed between the two runs.")
    print("\nWhat that condition WAS is your assertion, not this script's — it")
    print("compared two sets of artifacts and can only see that time passed")
    print("between them. Record the condition yourself when citing this.")


def main() -> None:
    company = company_from_argv(sys.argv)
    baseline_path = flag_value(sys.argv, "--baseline", "a run dir or response.xml")
    baseline = load_baseline(baseline_path) if baseline_path else None

    payload = build_daybook_read(company, DATE)
    print(f"Target company: {company!r} (read-only — nothing is posted or altered)")
    if baseline_path:
        print(f"Baseline: {baseline_path} ({len(baseline or [])} vouchers)")
    print()

    reads: list[list[tuple[str | None, ...]]] = []
    for n in (1, 2):
        body = run(f"remoteid-stability-read-{n}", payload)
        if not body:
            sys.exit(f"error: read {n} returned no response — is Tally listening on :9000?")
        reads.append(identifiers(body))
        if n == 1:
            time.sleep(2)

    moved = report(*reads)
    print(f"\n{'=' * 64}")
    banner_within_run(moved)
    print("=" * 64)

    if baseline is not None:
        moved_vs_baseline = report(baseline, reads[0], "baseline", "current")
        print(f"\n{'=' * 64}")
        banner_vs_baseline(moved_vs_baseline, baseline_path or "")
        print("=" * 64)


if __name__ == "__main__":
    main()
