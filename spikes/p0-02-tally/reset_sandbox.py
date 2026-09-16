"""
P0-02 — Delete test vouchers from a sandbox company (PENDING:009).

This is a destructive tool built for repeated use, not a probe. It
deletes vouchers from whichever company you name, so every default here
is the safe one:

  * **Dry run unless `--confirm`.** With no `--confirm` the script sends
    exactly one request — the read — and no `Import Data` at all.
  * **`--company` is required and has no default.** A reset script that
    inherits a company from a module constant resets the wrong books.
  * **Nothing is permanently protected in code.** Which vouchers matter
    changes as findings accumulate, so protection is a runtime
    keep-list: `--keep 1,3` and/or `--keep-file PATH`. An entry is
    either a bare number (protects that number in **every** voucher
    type — the safe, over-protecting default) or `Type:Number`, e.g.
    `Sales:1`, which protects exactly one. `Coastal Services Ltd`
    Purchase 1 is finding #15's evidence — protect it by passing
    `--keep Purchase:1`, or `--keep-file keep-coastal-services.txt`.

Usage (PowerShell):

    python reset_sandbox.py --company "Coastal Test Traders"
    python reset_sandbox.py --company "Coastal Services Ltd" `
        --keep-file keep-coastal-services.txt --confirm

Findings this implements:

  #11  Vouchers are read with EXPORT / TYPE: DATA / ID: Day Book.
       TYPE: COLLECTION on vouchers returns zero with no error, and with
       ID: Day Book can take TallyPrime down (#13). Never used here.
  #28  The one proven delete addressing: TAGNAME="VoucherNumber" +
       TAGVALUE, a dd-Mmm-yyyy DATE attribute, VCHTYPE, and a non-empty
       body. Also: a delete does not renumber survivors, so a single
       enumeration can be iterated over.
  Rule 1 / #26  Read back after every delete. CANCELLED read 0 on a
       successful cancel; DELETED read 1 on a successful delete. Same
       session, same envelope — counters decide nothing here.
  #17  A LINEERROR means failure regardless of what the counters say.
  #22  Masters are out of scope. ACTION="Delete" against a nonexistent
       master crashes TallyPrime. This script touches vouchers only.

MIXED-TYPE COMPANIES: the guard is fixed, the addressing question is not.

Voucher numbering is a series **per voucher type**, not per company
(#31), so a bare number identifies nothing on a company holding more
than one type. `Coastal Services Ltd` holds Purchase 1, 2, 4, 5 and
Sales 1, 2 simultaneously. Three layers were affected and they are in
different states now:

  * `classify()` matched the keep-list on a bare number, so a
    same-numbered voucher of another type was **KEPT**. That
    over-protects — it always failed in the safe direction. Still the
    default, and now joined by an exact `Type:Number` spelling for the
    cases a bare-number file cannot express.
  * `verify_gone()` was the unsound one: `still_there`, `expected` and
    `actual` were keyed on bare number, so two vouchers numbered "1"
    **deduped into one set member** — the guard meant to detect
    collateral loss was the one that could not. **FIXED (#33)**: every
    set is now keyed on `voucher_key()`, i.e. (type, number), and an
    unexplained *appearance* halts alongside an unexplained vanishing.
  * Whether Tally itself disambiguates is the third question and it is
    **still untested** — the delete payload carries VCHTYPE alongside
    TAGNAME/TAGVALUE, but nothing establishes that Tally reads it.

Because that third question is open, this script **refuses to delete
anything on a company holding more than one voucher type** unless
`--allow-mixed-types` is passed. A dry run still enumerates and prints
the plan; only the deletes are refused. Retire that refusal when the
addressing question is answered (issue #48 step 1) — **not** when the
guard was fixed. Those are different milestones.

Answering it means: establish whether VCHTYPE disambiguates, test
TAGNAME="MASTER ID" (schema reference 6.3, still untested), then rekey
on whatever survives. REMOTEID is stable for reads (#15) but NOT
confirmed addressable for writes (#16), so it is not automatically the
answer. Guessing is how #22 happened.

Scope limits worth knowing before you trust a summary:

  * A voucher with no VOUCHERNUMBER cannot be addressed by the only
    scheme that has been proven, so it is skipped and reported as a
    completeness failure. Guessing an untested addressing scheme is how
    #22 happened.
  * An already-cancelled voucher (`ISCANCELLED` = Yes, #26's voucher 4)
    is skipped: #28 deleted a *live* voucher, and what a delete does to a
    cancelled one is untested. Detection is the explicit field, not an
    entry-count heuristic — a cancelled voucher keeps one zero-amount
    entry, so counting entries does not find it.
  * A voucher with no ledger entries at all is skipped for manual
    inspection rather than deleted blind. This is also why enumeration
    here does not reuse `tally_voucher_read.parse_vouchers()`, which
    drops such vouchers entirely — correct for its callers, wrong for a
    tool that reports on its own completeness.
  * The Amount column is a recognition aid, not an accounting figure.
    Nothing branches on it, and it reads 0 for the inventory-view
    vouchers whose value sits in inventory entries (#18's voucher 6).
"""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _args import flag_value  # noqa: E402
from _runner import run  # noqa: E402
from tally_voucher_read import build_daybook_read  # noqa: E402
from tally_xml import sanitise  # noqa: E402

# Wide by default and deliberately not required. Enumeration is a read,
# so the failure mode of too wide a window is "you see more than you
# expected" — visible, in the plan, before anything is deleted. The
# failure mode of a required-but-mistyped window is a reset that silently
# misses vouchers and still reports clean.
DEFAULT_FROM = "20000401"
DEFAULT_TO = "20991231"

# A ceiling, not a target. Cheap insurance against a mistyped company or
# a window far wider than intended.
DEFAULT_MAX = 25

# Every call is given this timeout rather than _runner's 30s default, so
# a hang surfaces as a captured failure the script stops on. Every live
# probe today has stopped at the first sign of one rather than waiting it
# out; this script will eventually run unattended, so it must do the same.
HANG_SECONDS = 10

KNOWN_FLAGS = (
    "--company",
    "--from",
    "--to",
    "--keep",
    "--keep-file",
    "--confirm",
    "--url",
    "--max",
    "--allow-mixed-types",
)

# Both spellings are real. `ALLLEDGERENTRIES.LIST` is what the
# accounting-view vouchers of #21 carry; the inventory-view vouchers on
# `Coastal Test Traders` (#7, #18) carry `LEDGERENTRIES.LIST` instead.
# Counting only the first reads a perfectly ordinary voucher as empty —
# the same too-narrow-read failure as #11, and it would have labelled
# three live vouchers "unrecognised shape".
LEDGER_ENTRY_TAGS = ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST")

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


class Stop(Exception):
    """A condition that must halt the run. Never caught to retry."""


def tally_date(yyyymmdd: str) -> str:
    """`20260801` (what the Day Book returns) -> `01-Aug-2026` (what the
    delete attribute wants). Two formats in one API; the date is read
    from the response rather than assumed, so it has to be converted."""
    raw = yyyymmdd.strip()
    if len(raw) != 8 or not raw.isdigit():
        raise Stop(f"unparseable voucher date {yyyymmdd!r}")
    month = int(raw[4:6])
    if not 1 <= month <= 12:
        raise Stop(f"unparseable voucher date {yyyymmdd!r}")
    return f"{raw[6:8]}-{_MONTHS[month - 1]}-{raw[0:4]}"


def enumerate_vouchers(response: str) -> list[dict]:
    """Every <VOUCHER> in a Day Book response, including the ones that
    cannot be deleted.

    Unlike `parse_vouchers()`, nothing is filtered out. A voucher this
    script cannot address still has to appear in the summary, or the
    summary is a claim of completeness the script has not earned.
    """
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        raise Stop(f"Day Book response did not parse: {exc}") from exc

    out: list[dict] = []
    for vch in root.iter():
        if vch.tag.upper() != "VOUCHER":
            continue
        out.append(
            {
                "number": (vch.findtext("VOUCHERNUMBER") or "").strip(),
                "date": (vch.findtext("DATE") or "").strip(),
                "vchtype": (
                    vch.get("VCHTYPE") or vch.findtext("VOUCHERTYPENAME") or ""
                ).strip(),
                "party": (vch.findtext("PARTYLEDGERNAME") or "").strip(),
                "remote_id": vch.get("REMOTEID", ""),
                # Explicit field, not inferred. A cancelled voucher keeps
                # one zero-amount ledger entry (#26's voucher 4), so an
                # entry-count heuristic does not find it.
                "cancelled": (vch.findtext("ISCANCELLED") or "").strip().lower() == "yes",
                "amount": _voucher_amount(vch),
                "entries": _entry_count(vch),
            }
        )
    return out


def _entry_count(vch: ET.Element) -> int:
    return sum(1 for e in vch.iter() if e.tag.upper() in LEDGER_ENTRY_TAGS)


def _voucher_amount(vch: ET.Element) -> Decimal:
    """Sum of the debit side, as a display figure for the plan table.

    Nothing branches on this — it exists so a human reading the dry run
    can recognise the voucher. CG5 anyway: Decimal from strings.
    """
    total = Decimal("0")
    for e in vch.iter():
        if e.tag.upper() not in LEDGER_ENTRY_TAGS:
            continue
        raw = (e.findtext("AMOUNT") or "").strip()
        try:
            amount = Decimal(raw)
        except (InvalidOperation, ValueError):
            continue
        if amount < 0:
            total += -amount
    return total


def load_keep_list(argv: list[str]) -> set[str]:
    """Voucher numbers to protect, from `--keep` and/or `--keep-file`."""
    keep: set[str] = set()

    inline = flag_value(argv, "--keep", "one or more voucher numbers")
    if inline:
        keep |= {part.strip() for part in inline.split(",") if part.strip()}

    path = flag_value(argv, "--keep-file", "a path to a keep-list file")
    if path:
        keep |= _read_keep_file(Path(path))

    return keep


def _read_keep_file(path: Path) -> set[str]:
    if not path.is_file():
        sys.exit(f"error: --keep-file {path} does not exist")
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            out.add(entry)
    return out


def voucher_key(voucher: dict) -> tuple[str, str]:
    """The identity this script compares vouchers on: (type, number).

    Finding #31: TallyPrime numbers vouchers in a series **per voucher
    type**, so a bare number identifies nothing on a company holding more
    than one type. `Coastal Services Ltd` holds Purchase 1 and Sales 1
    simultaneously — different vouchers, same number.

    The type is case-folded because it arrives from two different places
    in `enumerate_vouchers` (the `VCHTYPE` attribute and the
    `VOUCHERTYPENAME` element) and nothing guarantees they agree on case.
    The number is not: it is a Tally-assigned string, compared verbatim.
    """
    return ((voucher.get("vchtype") or "").strip().casefold(),
            (voucher.get("number") or "").strip())


def keep_matches(voucher: dict, keep: set[str]) -> str | None:
    """The keep-list entry protecting this voucher, or None.

    Two spellings, and the looser one is the default deliberately:

      * `1` — a bare number protects voucher 1 **of every type**. This
        over-protects on a mixed-type company, which is the safe
        direction, and it is what every existing keep-file means.
      * `Sales:1` — a type-qualified entry protects exactly one voucher.
        Needed to express "delete Purchase 1, keep Sales 1" at all, which
        a bare-number file cannot say.
    """
    vtype, number = voucher_key(voucher)
    if not number:
        return None
    for entry in keep:
        if ":" in entry:
            want_type, _, want_number = entry.partition(":")
            if (want_type.strip().casefold(), want_number.strip()) == (vtype, number):
                return entry
        elif entry.strip() == number:
            return entry
    return None


def classify(vouchers: list[dict], keep: set[str]) -> list[dict]:
    """Attach a verdict to each voucher. Pure — sends nothing."""
    for v in vouchers:
        matched = keep_matches(v, keep)
        if not v["number"]:
            v["verdict"] = "SKIP"
            v["reason"] = "no VOUCHERNUMBER — not addressable, inspect manually"
        elif matched:
            v["verdict"] = "KEEP"
            v["reason"] = (
                f"matched keep-list entry {matched!r}"
                + ("" if ":" in matched else " (bare number — protects every type)")
            )
        elif v["cancelled"]:
            # Deleting an already-cancelled voucher has never been tested.
            # #28 deleted a live voucher; nothing establishes what this
            # does, and a reset script is not the place to find out.
            v["verdict"] = "SKIP"
            v["reason"] = "ISCANCELLED=Yes — deleting a cancelled voucher is untested"
        elif v["entries"] == 0:
            v["verdict"] = "SKIP"
            v["reason"] = "no ledger entries — unrecognised shape, inspect manually"
        else:
            v["verdict"] = "DELETE"
            v["reason"] = ""
    return vouchers


def voucher_types(vouchers: list[dict]) -> list[str]:
    """Distinct voucher types present, in display order."""
    seen: dict[str, str] = {}
    for v in vouchers:
        vtype = (v.get("vchtype") or "").strip()
        seen.setdefault(vtype.casefold(), vtype or "(no type)")
    return [seen[k] for k in sorted(seen)]


def check_mixed_types(vouchers: list[dict], allowed: bool) -> list[str]:
    """Refuse a mixed-type company unless `--allow-mixed-types` is passed.

    `verify_gone()` is type-aware as of #33, so this is no longer guarding
    a *detection* hole. It guards the one that is still open: whether the
    `VCHTYPE` the delete payload already carries actually disambiguates
    **Tally-side** has never been tested (issue #48, step 1). Until it
    has, a delete addressed at "Purchase 1" on a company that also holds
    "Sales 1" may remove either. The read-back would now catch that — but
    catching it means the voucher is already gone, and on these sandboxes
    several are irreplaceable.

    So the refusal stays until the addressing question is answered, not
    until the guard is fixed. Those are different milestones and it would
    be easy to retire this on the wrong one.
    """
    types = voucher_types(vouchers)
    if len(types) <= 1:
        return types
    numbers_by_type = {
        t: sorted(v["number"] for v in vouchers
                  if (v.get("vchtype") or "").strip().casefold() == t.casefold()
                  and v["number"])
        for t in types
    }
    collisions = sorted(
        {n for t in types for n in numbers_by_type[t]
         if sum(n in numbers_by_type[o] for o in types) > 1}
    )
    print(f"\n  MIXED VOUCHER TYPES: {', '.join(types)}")
    for t in types:
        print(f"    {t}: {numbers_by_type[t] or '(none numbered)'}")
    if collisions:
        print(f"    colliding numbers across types: {collisions}")
    if not allowed:
        raise Stop(
            "this company holds more than one voucher type, and whether VCHTYPE "
            "disambiguates a delete Tally-side is still untested (issue #48). "
            "Deletes refused. Pass --allow-mixed-types only once you have "
            "established that, or after a live test on a disposable voucher."
        )
    print(
        "    --allow-mixed-types was passed: proceeding on the caller's assertion "
        "that VCHTYPE addressing is safe here. The read-back guard is type-aware "
        "(#33) and will halt on collateral loss, but only after the fact."
    )
    return types


def print_plan(vouchers: list[dict], company: str, keep: set[str]) -> None:
    print(f"\n  Company: {company!r}")
    print(f"  Keep-list: {sorted(keep) if keep else '(empty — nothing protected)'}")
    print(f"\n  {'Vch':>6}  {'Date':<11} {'Type':<12} {'Party':<28} {'Amount':>12}  Verdict")
    print(f"  {'-' * 6}  {'-' * 11} {'-' * 12} {'-' * 28} {'-' * 12}  {'-' * 7}")
    for v in vouchers:
        label = v["number"] or "(none)"
        date = v["date"] or "(none)"
        verdict = v["verdict"] + (f" — {v['reason']}" if v["reason"] else "")
        print(
            f"  {label:>6}  {date:<11} {v['vchtype']:<12} {v['party'][:28]:<28} "
            f"{v['amount']:>12}  {verdict}"
        )

    for entry in sorted(keep):
        if not any(keep_matches(v, {entry}) for v in vouchers):
            print(f"\n  WARNING: keep-list entry {entry!r} matched no voucher.")
            print("           A typo in a keep-list protects nothing.")


def build_delete(company: str, voucher: dict) -> str:
    """The #28 payload, with the date converted from the read response.

    The NARRATION is not decoration: #28's successful delete carried a
    non-empty body, and the attempt before it was rejected for being
    empty (#26, attempt 1). Minimum deviation from the proven shape.
    """
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(env, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")
    desc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "Vouchers"
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

    data = ET.SubElement(importdata, "REQUESTDATA")
    msg = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    vch = ET.SubElement(
        msg,
        "VOUCHER",
        {
            "DATE": tally_date(voucher["date"]),
            "TAGNAME": "VoucherNumber",
            "TAGVALUE": voucher["number"],
            "ACTION": "Delete",
            "VCHTYPE": voucher["vchtype"],
        },
    )
    ET.SubElement(vch, "NARRATION").text = "CAOS-SANDBOX-RESET"

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def read_daybook(company: str, name: str, url: str, dates: tuple[str, str]) -> str:
    """One Day Book read, or Stop. Never TYPE: COLLECTION (#11, #13)."""
    payload = build_daybook_read(company, dates[0], dates[1])
    response = run(name, payload, url=url, timeout=HANG_SECONDS)
    if response is None:
        raise Stop("no response to the Day Book read — stopping before any delete")
    if "LINEERROR" in response.upper():
        raise Stop("LINEERROR in a Day Book read — stopping (#17)")
    return response


def _label(obj: dict | tuple[str, str]) -> str:
    """A voucher rendered the way the plan table reads: "Sales 1".

    Takes either a voucher dict or a bare `voucher_key()`. The dict form
    is preferred wherever one is in hand, because the key case-folds the
    type for comparison and a message reading "purchase 1" looks like a
    different object than the "Purchase" in the plan table above it.
    """
    if isinstance(obj, dict):
        vtype = (obj.get("vchtype") or "").strip()
        number = (obj.get("number") or "").strip()
    else:
        vtype, number = obj
    return f"{vtype or '(no type)'} {number or '(no number)'}"


def verify_gone(before: list[dict], after: list[dict], target: dict) -> None:
    """Rule 1. The response counters are recorded, never trusted.

    Two collateral checks beyond "is the target gone", because an
    unattended tool must stop on anything it cannot explain rather than
    continue through it.

    Every set here is keyed on `voucher_key()` — (type, number) — not on
    the bare number. Issue #48 / finding #33: keyed on number alone,
    Purchase 1 and Sales 1 **deduped into one set member**, so a delete
    that took both would leave `expected - actual` empty and this guard
    would report the run clean. The guard whose whole job is detecting
    collateral loss was the one place the collision was fatal.
    """
    target_key = voucher_key(target)
    # Display case is only recoverable from the dicts, not from the keys.
    shown = {voucher_key(v): v for v in [*before, *after]}

    still_there = [v for v in after if voucher_key(v) == target_key]
    if still_there:
        raise Stop(
            f"voucher {_label(target)} is still present after its delete — stopping"
        )

    expected = {voucher_key(v) for v in before if voucher_key(v) != target_key}
    actual = {voucher_key(v) for v in after}
    vanished = expected - actual
    if vanished:
        raise Stop(
            f"vouchers {sorted(_label(shown[k]) for k in vanished)} vanished "
            f"alongside {_label(target)} — unexplained collateral, stopping"
        )
    appeared = actual - expected
    if appeared:
        raise Stop(
            f"vouchers {sorted(_label(shown[k]) for k in appeared)} appeared during "
            f"a delete of {_label(target)} — unexplained, stopping"
        )
    if len(after) != len(before) - 1:
        raise Stop(
            f"voucher count went {len(before)} -> {len(after)} deleting one "
            "voucher — stopping"
        )


def delete_one(
    voucher: dict, company: str, url: str, dates: tuple[str, str], before: list[dict]
) -> list[dict]:
    """Send one delete, read back, verify. Returns the new enumeration."""
    number = voucher["number"]
    # The artifact name carries the type too: two vouchers numbered "1"
    # would otherwise write their request/response into run directories
    # that differ only by timestamp (#33).
    slug = f"{(voucher['vchtype'] or 'untyped').replace(' ', '-')}-{number}"
    response = run(
        f"reset-delete-{slug}",
        build_delete(company, voucher),
        url=url,
        timeout=HANG_SECONDS,
    )
    if response is None:
        raise Stop(f"no response deleting voucher {number} — stopping")
    if "LINEERROR" in response.upper():
        raise Stop(f"LINEERROR deleting voucher {number} — stopping (#17)")

    after = enumerate_vouchers(
        read_daybook(company, f"reset-readback-{slug}", url, dates)
    )
    verify_gone(before, after, voucher)
    print(f"  {_label(voucher)}: deleted and confirmed absent by read-back")
    return after


def run_deletes(
    vouchers: list[dict], company: str, url: str, dates: tuple[str, str]
) -> tuple[list[str], str | None]:
    """Delete the planned vouchers one at a time. Stops on the first
    anomaly and reports what was not attempted — no retry, anywhere."""
    planned = [v for v in vouchers if v["verdict"] == "DELETE"]
    current = vouchers
    done: list[str] = []
    for voucher in planned:
        try:
            current = delete_one(voucher, company, url, dates, current)
        except Stop as exc:
            return done, str(exc)
        done.append(_label(voucher))
    return done, None


def print_summary(
    vouchers: list[dict], deleted: list[str], halt: str | None, confirmed: bool
) -> None:
    print("\n  === Summary ===")
    if confirmed:
        print(f"  Deleted ({len(deleted)}): {deleted or '(none)'}")
    else:
        would = [_label(v) for v in vouchers if v["verdict"] == "DELETE"]
        print("  Deleted (0): dry run — nothing was sent")
        print(f"  Would delete ({len(would)}): {would or '(none)'}")

    for verdict in ("KEEP", "SKIP"):
        rows = [v for v in vouchers if v["verdict"] == verdict]
        print(f"  {verdict} ({len(rows)}):")
        for v in rows:
            print(f"    {_label(v)}: {v['reason']}")

    unaddressable = [v for v in vouchers if not v["number"]]
    if unaddressable:
        print(
            f"\n  COMPLETENESS FAILURE: {len(unaddressable)} voucher(s) have no "
            "VOUCHERNUMBER and cannot be addressed by the only proven delete "
            "scheme. This reset is not complete."
        )

    if halt:
        print(f"\n  HALTED: {halt}")
        print("  Nothing after this point was attempted. No retry was made.")


def parse_argv(argv: list[str]) -> dict:
    """Flags, with the guards a destructive tool needs up front."""
    for arg in argv[1:]:
        if arg.startswith("--") and arg not in KNOWN_FLAGS:
            sys.exit(f"error: unknown flag {arg!r}")

    company = flag_value(argv, "--company", "a company name")
    if not company:
        sys.exit(
            "error: --company is required and has no default.\n"
            '       e.g. --company "Coastal Test Traders"'
        )

    raw_max = flag_value(argv, "--max", "a number of vouchers")
    if raw_max is not None and not raw_max.isdigit():
        sys.exit(f"error: --max requires a number, got {raw_max!r}")

    return {
        "company": company,
        "dates": (
            flag_value(argv, "--from", "a YYYYMMDD date") or DEFAULT_FROM,
            flag_value(argv, "--to", "a YYYYMMDD date") or DEFAULT_TO,
        ),
        "keep": load_keep_list(argv),
        "url": flag_value(argv, "--url", "a Tally URL") or "http://localhost:9000",
        "max": int(raw_max) if raw_max else DEFAULT_MAX,
        "confirm": "--confirm" in argv,
        "allow_mixed_types": "--allow-mixed-types" in argv,
    }


def main() -> None:
    opts = parse_argv(sys.argv)
    company, dates = opts["company"], opts["dates"]

    url = opts["url"]

    print(f"\n  Reading the Day Book, {dates[0]} to {dates[1]} ...")
    response = read_daybook(company, "reset-enumerate", url, dates)
    vouchers = classify(enumerate_vouchers(response), opts["keep"])
    print_plan(vouchers, company, opts["keep"])

    # The plan above is printed first on purpose: a refusal that shows you
    # nothing is a refusal you cannot act on. The gate sits between the
    # plan and the first Import Data, so a dry run on a mixed-type company
    # still tells you what is there — and still refuses to delete it.
    try:
        check_mixed_types(vouchers, opts["allow_mixed_types"])
    except Stop as exc:
        if opts["confirm"]:
            raise
        print(f"\n  WOULD REFUSE: {exc}")

    planned = [v for v in vouchers if v["verdict"] == "DELETE"]
    if len(planned) > opts["max"]:
        sys.exit(
            f"\n  REFUSING TO START: {len(planned)} vouchers planned for deletion, "
            f"--max is {opts['max']}.\n"
            "  Narrow --from/--to, extend the keep-list, or raise --max deliberately."
        )

    if not opts["confirm"]:
        print_summary(vouchers, [], None, confirmed=False)
        print(
            f"\n  (dry run — nothing was sent to {company!r} but the read above. "
            "Pass --confirm to delete.)"
        )
        return

    deleted, halt = run_deletes(vouchers, company, url, dates)
    print_summary(vouchers, deleted, halt, confirmed=True)
    if halt:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        sys.exit(f"\n  HALTED: {exc}")
