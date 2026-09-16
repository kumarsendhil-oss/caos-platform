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
artifacts between two runs; it has no way to observe what happened
between them, only that they differ in time. **The human asserts the
condition, the script checks what moved.** It will never print "stable
across a restart" — it prints which fields moved and whether the
vouchers' amounts moved with them, and you supply what you changed.

Not all movement is failure, which is the distinction PENDING:013 added
(see FIELDS below): an identity field moving defeats correlation, while
ALTERID moving is the *correct* result of a genuine edit. The banner
reports those differently. It also reports amounts, because a run where
nothing moved at all is indistinguishable from a run where the asserted
condition never happened — that is how an unsaved Tally edit read clean
on 2026-09-16 (runs 07-18-22 vs 07-20-42).

Finding #15's two risks:

  - restart-stability: RESOLVED 2026-09-16. REMOTEID byte-identical
    across a full TallyPrime close/reopen (runs 06-49 vs 06-55). This
    also disproved the guess that VCHKEY's 0000b49a segment was a
    build or session handle — it survived the restart. Still
    unexplained, and VCHKEY stays demoted on structural grounds.
  - edit-stability: RESOLVED 2026-09-16. An amount change to one
    voucher (runs 07-18-22 vs 07-23-13) moved ALTERID on that voucher
    alone, 1 → 5; REMOTEID, VCHKEY, GUID, VOUCHERNUMBER and MASTERID
    all held, and the three untouched vouchers were unaffected.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _args import company_from_argv, flag_value  # noqa: E402
from _runner import run  # noqa: E402
from tally_voucher_read import build_daybook_read  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Services Ltd"
DATE = "20260801"

# Three categories, because "did the field move" is not the same
# question as "is that a problem" (PENDING:013).
#
# IDENTITY        the correlation candidates. Movement defeats
#                 PENDING:010 outright — a voucher that cannot be found
#                 again cannot be reconciled against its source
#                 document.
# CHANGE_TRACKING fields Tally moves *on purpose* when a voucher is
#                 altered. ALTERID is a company-wide alteration
#                 sequence, not a per-voucher revision count
#                 (docs/context.md): ALTERID > MASTERID means altered.
#                 Movement here alongside stable identity fields is the
#                 expected, correct outcome of an edit-stability test.
# CONTEXT         neither. MASTERID held through the 2026-09-16 edit so
#                 it is not change-tracking, but finding #14 demotes
#                 Tally-assigned sequence numbers as correlation keys
#                 and neither field has been tested under a rewrite or
#                 reimport — so movement is worth printing without being
#                 a verdict either way.
IDENTITY = ("REMOTEID", "VCHKEY", "GUID")
CHANGE_TRACKING = ("ALTERID",)
CONTEXT = ("VOUCHERNUMBER", "MASTERID")
FIELDS = IDENTITY + CHANGE_TRACKING + CONTEXT

CATEGORIES = (
    ("identity", IDENTITY),
    ("change-tracking", CHANGE_TRACKING),
    ("context", CONTEXT),
)
CATEGORY_OF = {field: name for name, fields in CATEGORIES for field in fields}

# REMOTEID and VCHKEY are XML attributes; the rest are child elements.
ATTRIBUTES = ("REMOTEID", "VCHKEY")


class Voucher(NamedTuple):
    """One voucher's identifier fields plus its amounts.

    Amounts are not a fourth category and carry no verdict of their own.
    They are evidence that the condition the human asserted actually
    landed, which the identifier fields alone cannot show.
    """

    fields: dict[str, str | None]
    amounts: tuple[str, ...]


class VoucherMovement(NamedTuple):
    number: str | None
    moved_fields: list[str]
    amounts_moved: bool


class Movement(NamedTuple):
    by_category: dict[str, int]
    vouchers: list[VoucherMovement]
    count_mismatch: bool

    @property
    def total(self) -> int:
        return sum(self.by_category.values())

    @property
    def amounts_moved(self) -> bool:
        return any(v.amounts_moved for v in self.vouchers)


def clean(value: str | None) -> str | None:
    """Tally pads element text (' 5'); whitespace is not movement."""
    return value.strip() if value is not None else None


def load_baseline(path_str: str) -> list[Voucher]:
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


def voucher_fields(element: ET.Element) -> dict[str, str | None]:
    """REMOTEID/VCHKEY come off the attributes, the rest off child elements."""
    return {
        f: clean(element.get(f) if f in ATTRIBUTES else element.findtext(f)) for f in FIELDS
    }


def identifiers(body: str) -> list[Voucher]:
    """Every voucher's identifier fields and amounts, in Day Book order."""
    root = ET.fromstring(sanitise(body))
    return [
        Voucher(
            fields=voucher_fields(v),
            amounts=tuple(clean(e.text) or "" for e in v.iter("AMOUNT")),
        )
        for v in root.iter("VOUCHER")
    ]


def diff_voucher(a: Voucher, b: Voucher) -> VoucherMovement:
    """Which fields moved on one voucher, and whether its amounts did."""
    return VoucherMovement(
        number=b.fields["VOUCHERNUMBER"] or a.fields["VOUCHERNUMBER"],
        moved_fields=[f for f in FIELDS if a.fields[f] != b.fields[f]],
        amounts_moved=a.amounts != b.amounts,
    )


def print_voucher(index: int, a: Voucher, b: Voucher, la: str, lb: str, width: int) -> None:
    """Field-by-field diff for one voucher, grouped by category."""
    print(f"--- voucher {index} ---")
    for name, fields in CATEGORIES:
        print(f"  [{name}]")
        for f in fields:
            va, vb = a.fields[f], b.fields[f]
            verdict = "SAME" if va == vb else "*** DIFFERS ***"
            print(f"    {f:<14} {la:>{width}}={va}")
            print(f"    {'':<14} {lb:>{width}}={vb}   [{verdict}]")
    if a.amounts == b.amounts:
        print(f"  [amounts]      {len(a.amounts)} line(s), unchanged")
    else:
        print(f"  [amounts]      {la:>{width}}={list(a.amounts)}")
        print(f"                 {lb:>{width}}={list(b.amounts)}   [*** DIFFERS ***]")


def report(
    first: list[Voucher],
    second: list[Voucher],
    label_a: str = "r1",
    label_b: str = "r2",
) -> Movement:
    """Print a field-by-field diff and return what moved, by category."""
    width = max(len(label_a), len(label_b))
    print(f"\n{label_a}: {len(first)} vouchers | {label_b}: {len(second)} vouchers")
    mismatch = len(first) != len(second)
    if mismatch:
        print("  WARNING: voucher counts differ — something wrote between the two")

    by_category = {name: 0 for name, _ in CATEGORIES}
    movements: list[VoucherMovement] = []
    for i, (a, b) in enumerate(zip(first, second), 1):
        print_voucher(i, a, b, label_a, label_b, width)
        movement = diff_voucher(a, b)
        for field in movement.moved_fields:
            by_category[CATEGORY_OF[field]] += 1
        if movement.moved_fields or movement.amounts_moved:
            movements.append(movement)
    return Movement(by_category, movements, mismatch)


def summarise(mv: Movement) -> None:
    """Which vouchers moved and how — the 'was it the one I edited?' line."""
    if not mv.vouchers:
        print("  No voucher moved on any field, and no amounts moved.")
        return
    for v in mv.vouchers:
        parts = [f"{f} ({CATEGORY_OF[f]})" for f in v.moved_fields]
        if v.amounts_moved:
            parts.append("amounts")
        print(f"  VOUCHERNUMBER {v.number}: {', '.join(parts)}")


def banner_within_run(mv: Movement) -> None:
    """What two reads inside one invocation establish, and nothing more.

    Categories deliberately do not apply here. Nothing should move
    between two identical back-to-back reads — not even ALTERID, which
    moves only when a voucher is altered, and nothing altered one.
    """
    if mv.total or mv.amounts_moved:
        print(f"{mv.total} field(s) changed between two identical reads.")
        summarise(mv)
        print("Nothing altered a voucher between these two reads, so NO field")
        print("should have moved — not even a change-tracking one. An identifier")
        print("that moves on read cannot correlate a posted voucher with its")
        print("source document — PENDING:010 needs rethinking, not patching.")
        return
    print("No field or amount changed between the two reads in THIS run. That")
    print("is per-response stability only — this run did not test any condition,")
    print("because nothing changed between the two reads but time.")
    print("\nTo test whether an identifier survives a restart or an edit, make")
    print("the change and re-run against this run's artifacts:")
    print("  python remoteid_stability_probe.py --baseline runs/<this run's read-1 dir>")


def banner_identity_moved(mv: Movement) -> None:
    """The one outcome that defeats PENDING:010."""
    print(f"FAILURE — {mv.by_category['identity']} identity field(s) MOVED since that baseline.")
    print("Whatever you changed between the two runs, these identifiers did not")
    print("survive it — see the per-field diff above for which ones, on which")
    print("vouchers. An identifier that moves cannot correlate a posted voucher")
    print("with its source document (PENDING:010).")


def banner_expected(mv: Movement) -> None:
    """Identity held while change-tracking and/or amounts moved."""
    print("EXPECTED — identity fields (REMOTEID, VCHKEY, GUID) all held, while")
    print("change-tracking and/or amounts moved. That is what a genuine edit is")
    print("supposed to look like: the voucher changed and stayed findable.")
    if mv.by_category["context"]:
        print(f"Note: {mv.by_category['context']} context field(s) also moved — see the diff.")
    if not mv.amounts_moved:
        print("Note: change-tracking moved but no amount did — the edit did not")
        print("touch amounts (a narration or ledger change would look like this).")
    print("\nWhat the condition WAS is still your assertion, not this script's.")
    print("Record it yourself when citing this run.")


def banner_context_moved(mv: Movement) -> None:
    """Sequence numbers moved; correlation candidates did not."""
    print(f"NOTEWORTHY — identity fields held, but {mv.by_category['context']} context field(s)")
    print("moved (VOUCHERNUMBER/MASTERID). Neither is a correlation")
    print("candidate — finding #14 already rules out Tally-assigned sequence")
    print("numbers — so this is not a PENDING:010 verdict either way. Worth")
    print("understanding before relying on those fields for anything else.")


def banner_nothing_moved() -> None:
    """Nothing moved at all — stable, but also what a void run looks like."""
    print("Nothing moved since that baseline — no field, no amount.")
    print("\nFor a RESTART test that is the result you want: the identifiers")
    print("survived. For an EDIT test it is ambiguous, and this is the one case")
    print("where the script cannot decide for you. A voucher edit that was")
    print("never saved looks exactly like this — a real one would have moved")
    print("ALTERID, and the amounts with it if it touched any. If you asserted")
    print("an edit, it did not land: re-check that Tally accepted and saved it.")
    print("\nWhat the condition WAS is your assertion, not this script's — it")
    print("compared two sets of artifacts and can only see that time passed")
    print("between them. Record the condition yourself when citing this.")


def banner_vs_baseline(mv: Movement, source: str) -> None:
    """What a cross-run comparison establishes — deliberately not the condition.

    The script can see which fields moved between two sets of artifacts.
    It cannot see what happened in between, only that time passed. What
    it can now do is tell apart the kinds of movement: identity fields
    moving defeats PENDING:010, while ALTERID moving is what a genuine
    edit is supposed to look like.
    """
    print(f"Compared against baseline: {source}\n")
    summarise(mv)
    print()
    if mv.by_category["identity"]:
        banner_identity_moved(mv)
    elif mv.by_category["change-tracking"] or mv.amounts_moved:
        banner_expected(mv)
    elif mv.by_category["context"]:
        banner_context_moved(mv)
    else:
        banner_nothing_moved()


def main() -> None:
    company = company_from_argv(sys.argv, COMPANY)
    baseline_path = flag_value(sys.argv, "--baseline", "a run dir or response.xml")
    baseline = load_baseline(baseline_path) if baseline_path else None

    payload = build_daybook_read(company, DATE)
    print(f"Target company: {company!r} (read-only — nothing is posted or altered)")
    if baseline_path:
        print(f"Baseline: {baseline_path} ({len(baseline or [])} vouchers)")
    print()

    reads: list[list[Voucher]] = []
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
