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

Finding #15 leaves two risks open that this script is the tool for —
run it, change the condition, run it again, and diff:

  - restart-stability: run, restart TallyPrime, run again. A live
    concern for VCHKEY specifically, whose middle segment (0000b49a)
    is an unexplained constant shared across two different companies
    and may be a build or session handle.
  - edit-stability: run, alter a voucher in the Tally UI, run again.
    Untested so far only because no voucher has ever been altered —
    ALTERID equals MASTERID on every voucher checked, which is an
    absence of a negative result, not a positive one.
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


def company_from_argv(argv: list[str]) -> str:
    """--company VALUE, defaulting to COMPANY.

    Validates the value: exits with a message rather than raising
    IndexError when the flag is last, and rejects a following flag as a
    company name. Copied from post_voucher.py (STUB_ISSUES PENDING:008).
    """
    if "--company" not in argv:
        return COMPANY
    i = argv.index("--company") + 1
    if i >= len(argv):
        sys.exit("error: --company requires a company name")
    value = argv[i]
    if value.startswith("--"):
        sys.exit(f"error: --company requires a company name, got the flag {value!r}")
    return value


def identifiers(body: str) -> list[tuple[str | None, ...]]:
    """Every voucher's identifier fields, in Day Book order."""
    root = ET.fromstring(sanitise(body))
    return [
        tuple(v.get(f) if f in ("REMOTEID", "VCHKEY") else v.findtext(f) for f in FIELDS)
        for v in root.iter("VOUCHER")
    ]


def report(first: list[tuple[str | None, ...]], second: list[tuple[str | None, ...]]) -> int:
    """Print a field-by-field diff. Returns the number of fields that moved."""
    print(f"\nread 1: {len(first)} vouchers | read 2: {len(second)} vouchers")
    if len(first) != len(second):
        print("  WARNING: voucher counts differ — something wrote between the reads")

    moved = 0
    for i, (a, b) in enumerate(zip(first, second), 1):
        print(f"--- voucher {i} ---")
        for name, va, vb in zip(FIELDS, a, b):
            same = va == vb
            moved += not same
            print(f"  {name:<14} r1={va}")
            print(f"  {'':<14} r2={vb}   [{'SAME' if same else '*** DIFFERS ***'}]")
    return moved


def main() -> None:
    company = company_from_argv(sys.argv)
    payload = build_daybook_read(company, DATE)
    print(f"Target company: {company!r} (read-only — nothing is posted or altered)\n")

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
    if moved:
        print(f"{moved} field(s) changed between two identical reads. An identifier")
        print("that moves on read cannot correlate a posted voucher with its")
        print("source document — PENDING:010 needs rethinking, not patching.")
    else:
        print("No field changed. Stable across reads WITHIN ONE SESSION — which")
        print("is not the same as stable across a restart or an edit. See the")
        print("module docstring for how to test those two.")
    print("=" * 64)


if __name__ == "__main__":
    main()
