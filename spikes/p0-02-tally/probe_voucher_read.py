"""
P0-02 — Find a voucher read that actually returns vouchers.

FINDING #11: `EXPORT / COLLECTION / TYPE: Voucher / FETCH *` returns
zero vouchers while Tally's Day Book shows two. The vouchers exist —
Day Book and the party's Cur Bal (43,424.00 Cr = 2 x 21,712) both
confirm it. The query is wrong, not Tally.

This blocks issue #1: TallyAdapter needs a working voucher read for
TC-02, and finding #2 (success responses are not trustworthy) makes
read-back verification mandatory rather than optional. Without a
working read there is no way to verify a post.

Tries six shapes. Each is captured, so a failure is recorded as
evidence rather than lost.

One observation worth carrying in: on the failing reads CMPINFO.COMPANY
was 1, where ledger reads showed 0. That may indicate a company-context
difference rather than a collection-type problem — variant F tests that
directly by omitting SVCURRENTCOMPANY.

    python probe_voucher_read.py            # print the payloads
    python probe_voucher_read.py --send
    python probe_voucher_read.py --send --company "Other Co"
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_xml import sanitise  # noqa: E402

# The vouchers posted yesterday live here, not in Coastal Test Traders.
COMPANY = "Coastal Services Ltd"
DATE = "20260801"


def _export(
    req_type: str,
    ident: str,
    *,
    company: str | None,
    dates: bool = True,
    tdl: ET.Element | None = None,
) -> str:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = req_type
    ET.SubElement(header, "ID").text = ident

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    if company is not None:
        ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    if dates:
        ET.SubElement(sv, "SVFROMDATE").text = DATE
        ET.SubElement(sv, "SVTODATE").text = DATE
    if tdl is not None:
        desc.append(tdl)

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def _voucher_collection_tdl(fetch_all: bool) -> ET.Element:
    tdl = ET.Element("TDL")
    msg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(msg, "COLLECTION", NAME="CAOS Vch", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Voucher"
    if fetch_all:
        ET.SubElement(coll, "FETCH").text = "*"
    else:
        for field in ("Date", "VoucherNumber", "VoucherTypeName", "PartyLedgerName", "Amount"):
            ET.SubElement(coll, "NATIVEMETHOD").text = field
    return tdl


# Ordered most- to least-likely. Day Book is Tally's own report for
# exactly this, and is the shape most third-party integrations use.
VARIANTS: list[tuple[str, str]] = [
    ("A-data-daybook", _export("DATA", "Day Book", company=COMPANY)),
    ("B-data-voucher-register", _export("DATA", "Voucher Register", company=COMPANY)),
    ("C-collection-daybook", _export("COLLECTION", "Day Book", company=COMPANY)),
    (
        "D-collection-fetch-all",
        _export("COLLECTION", "CAOS Vch", company=COMPANY, tdl=_voucher_collection_tdl(True)),
    ),
    (
        "E-collection-nativemethod",
        _export("COLLECTION", "CAOS Vch", company=COMPANY, tdl=_voucher_collection_tdl(False)),
    ),
    # No SVCURRENTCOMPANY — tests whether the company context was the
    # problem all along, per the CMPINFO.COMPANY observation above.
    ("F-daybook-no-company", _export("DATA", "Day Book", company=None)),
]


def summarise(response: str) -> tuple[int, list[str]]:
    """Count vouchers carrying real ledger entries, and name what was found."""
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        return -1, [f"unparseable: {exc}"]

    found: list[str] = []
    for vch in root.iter():
        if vch.tag.upper() != "VOUCHER":
            continue
        number = (vch.findtext("VOUCHERNUMBER") or "").strip() or "(no number)"
        party = (vch.findtext("PARTYLEDGERNAME") or "").strip()
        entries = [
            (e.findtext("LEDGERNAME") or "").strip()
            for e in vch.iter()
            if e.tag.upper() == "ALLLEDGERENTRIES.LIST"
        ]
        entries = [e for e in entries if e]
        if entries:
            found.append(f"{number} [{party}] -> {', '.join(entries)}")

    return len(found), found


if __name__ == "__main__":
    company = COMPANY
    if "--company" in sys.argv:
        company = sys.argv[sys.argv.index("--company") + 1]

    if "--send" not in sys.argv:
        for label, payload in VARIANTS:
            print(f"\n{'=' * 60}\n{label}\n{'=' * 60}\n{payload}")
        print("\n(dry run — pass --send to try each against Tally)")
        sys.exit(0)

    print(f"Expecting 2 purchase vouchers on {DATE} in {company!r}\n")

    results: list[tuple[str, int]] = []
    for label, payload in VARIANTS:
        print(f"--- {label} ---")
        body = run(f"vchread-{label}", payload)
        if not body:
            results.append((label, -1))
            print()
            continue
        count, found = summarise(body)
        results.append((label, count))
        print(f"  vouchers with ledger entries: {count}")
        for line in found[:4]:
            print(f"    {line}")
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for label, count in results:
        if count > 0:
            mark = "OK  "
        elif count == 0:
            mark = "none"
        else:
            mark = "err "
        print(f"  [{mark}] {label:28} {count}")

    working = [lbl for lbl, c in results if c > 0]
    if working:
        print(f"\n  Working shapes: {working}")
        print("  Use the first of these for TallyAdapter's voucher read (TC-02).")
    else:
        print(
            "\n  None returned vouchers. The vouchers definitely exist — Day Book\n"
            "  shows them and the party balance is 2x the voucher total. So the\n"
            "  problem is not the collection type, and the next axis to vary is\n"
            "  the date format or the export format, not the report name."
        )
