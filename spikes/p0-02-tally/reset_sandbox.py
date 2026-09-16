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
    keep-list: `--keep 1,3` and/or `--keep-file PATH`. `Coastal Services
    Ltd` voucher 1 is finding #15's evidence — protect it by passing
    `--keep 1`, or `--keep-file keep-coastal-services.txt`.

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


def classify(vouchers: list[dict], keep: set[str]) -> list[dict]:
    """Attach a verdict to each voucher. Pure — sends nothing."""
    for v in vouchers:
        if not v["number"]:
            v["verdict"] = "SKIP"
            v["reason"] = "no VOUCHERNUMBER — not addressable, inspect manually"
        elif v["number"] in keep:
            v["verdict"] = "KEEP"
            v["reason"] = "matched keep-list"
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
        if not any(v["number"] == entry for v in vouchers):
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


def verify_gone(before: list[dict], after: list[dict], target: str) -> None:
    """Rule 1. The response counters are recorded, never trusted.

    Two collateral checks beyond "is the target gone", because an
    unattended tool must stop on anything it cannot explain rather than
    continue through it.
    """
    still_there = [v for v in after if v["number"] == target]
    if still_there:
        raise Stop(f"voucher {target} is still present after its delete — stopping")

    expected = {v["number"] for v in before if v["number"] != target}
    actual = {v["number"] for v in after}
    vanished = expected - actual
    if vanished:
        raise Stop(
            f"vouchers {sorted(vanished)} vanished alongside {target} — "
            "unexplained collateral, stopping"
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
    response = run(
        f"reset-delete-{number}",
        build_delete(company, voucher),
        url=url,
        timeout=HANG_SECONDS,
    )
    if response is None:
        raise Stop(f"no response deleting voucher {number} — stopping")
    if "LINEERROR" in response.upper():
        raise Stop(f"LINEERROR deleting voucher {number} — stopping (#17)")

    after = enumerate_vouchers(
        read_daybook(company, f"reset-readback-{number}", url, dates)
    )
    verify_gone(before, after, number)
    print(f"  voucher {number}: deleted and confirmed absent by read-back")
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
        done.append(voucher["number"])
    return done, None


def print_summary(
    vouchers: list[dict], deleted: list[str], halt: str | None, confirmed: bool
) -> None:
    print("\n  === Summary ===")
    if confirmed:
        print(f"  Deleted ({len(deleted)}): {deleted or '(none)'}")
    else:
        would = [v["number"] for v in vouchers if v["verdict"] == "DELETE"]
        print("  Deleted (0): dry run — nothing was sent")
        print(f"  Would delete ({len(would)}): {would or '(none)'}")

    for verdict in ("KEEP", "SKIP"):
        rows = [v for v in vouchers if v["verdict"] == verdict]
        print(f"  {verdict} ({len(rows)}):")
        for v in rows:
            label = v["number"] or "(no number)"
            print(f"    {label}: {v['reason']}")

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
    }


def main() -> None:
    opts = parse_argv(sys.argv)
    company, dates = opts["company"], opts["dates"]

    url = opts["url"]

    print(f"\n  Reading the Day Book, {dates[0]} to {dates[1]} ...")
    response = read_daybook(company, "reset-enumerate", url, dates)
    vouchers = classify(enumerate_vouchers(response), opts["keep"])
    print_plan(vouchers, company, opts["keep"])

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
