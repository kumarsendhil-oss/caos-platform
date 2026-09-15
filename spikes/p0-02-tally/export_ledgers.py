"""
P0-02 — Export ledgers, and verify the GST fields actually took.

Two jobs:

  1. Exercise the read path (TC-02) — the same Collection export that
     BK-02's fuzzy vendor matching will use to get the ledger list.
  2. Verify what create_ledgers.py actually produced. Tally's import
     reports CREATED even when it silently drops fields it didn't
     understand, so a tax ledger can come back "successful" without
     TAXTYPE or GSTDUTYHEAD set — and that only surfaces later as a
     wrong split in the voucher test. Reading back is the check the
     import response can't give you.

    python export_ledgers.py            # print the payload, send nothing
    python export_ledgers.py --send     # send it, capture, and verify

Uses an inline TDL collection to request specific fields rather than
Tally's full ledger dump — the same approach TallyAdapter will use, so
this tests the real shape rather than a convenient one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402

COMPANY = "Coastal Test Traders"

# What create_ledgers.py claimed to create. Anything missing here, or
# with the wrong GST fields, is a silent-drop that the import response
# reported as success.
EXPECTED = {
    "Coastal Components Pvt Ltd": {"parent": "Sundry Creditors", "taxtype": None},
    "Purchase @18%": {"parent": "Purchase Accounts", "taxtype": None},
    "CGST": {"parent": "Duties & Taxes", "taxtype": "GST", "gstdutyhead": "Central Tax"},
    "SGST": {"parent": "Duties & Taxes", "taxtype": "GST", "gstdutyhead": "State Tax"},
}

FIELDS = ["Name", "Parent", "TaxType", "GSTDutyHead", "PartyGSTIN", "OpeningBalance"]


def build(company: str = COMPANY) -> str:
    env = ET.Element("ENVELOPE")

    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = "CAOS Ledger Coll"

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

    tdl = ET.SubElement(desc, "TDL")
    tdlmsg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(tdlmsg, "COLLECTION", NAME="CAOS Ledger Coll", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Ledger"
    for field in FIELDS:
        ET.SubElement(coll, "NATIVEMETHOD").text = field

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def _text(elem: ET.Element, *names: str) -> str | None:
    """Tally's casing varies between request and response — try each."""
    for name in names:
        for candidate in (name, name.upper(), name.lower()):
            found = elem.find(candidate)
            if found is not None and found.text:
                return found.text.strip()
    return None


def verify(response: str) -> None:
    from tally_xml import count_illegal, sanitise

    illegal = count_illegal(response)
    if illegal:
        print(
            f"\n  Sanitised {illegal} illegal control character(s) before parsing "
            "— see spikes/tally_xml.py"
        )
    response = sanitise(response)

    try:
        root = ET.fromstring(response)
    except ET.ParseError as exc:
        print(f"\n  Could not parse response as XML even after sanitising: {exc}")
        print("  Inspect runs/<latest>/response.xml directly.")
        return

    found: dict[str, dict[str, str | None]] = {}
    for ledger in root.iter():
        if ledger.tag.upper() != "LEDGER":
            continue
        name = ledger.get("NAME") or _text(ledger, "Name")
        if not name:
            continue
        found[name.strip()] = {
            "parent": _text(ledger, "Parent"),
            "taxtype": _text(ledger, "TaxType"),
            "gstdutyhead": _text(ledger, "GSTDutyHead"),
        }

    print(f"\n  Ledgers in response: {len(found)}")

    problems = []
    for name, expected in EXPECTED.items():
        actual = found.get(name)
        if actual is None:
            problems.append(f"{name!r}: MISSING from the export")
            continue

        if expected["parent"] and actual["parent"] != expected["parent"]:
            problems.append(
                f"{name!r}: parent is {actual['parent']!r}, expected {expected['parent']!r}"
            )

        want_tax = expected.get("taxtype")
        if want_tax:
            if actual["taxtype"] != want_tax:
                problems.append(
                    f"{name!r}: TaxType is {actual['taxtype']!r}, expected {want_tax!r} "
                    "— the import reported success but dropped this field"
                )
            want_head = expected.get("gstdutyhead")
            if want_head and actual["gstdutyhead"] != want_head:
                problems.append(
                    f"{name!r}: GSTDutyHead is {actual['gstdutyhead']!r}, expected {want_head!r}"
                )

    if problems:
        print("\n  PROBLEMS:")
        for p in problems:
            print(f"    - {p}")
        print(
            "\n  Note: a field coming back empty may mean Tally uses a different\n"
            "  name for it in responses than in imports. Check response.xml before\n"
            "  concluding the import dropped it."
        )
    else:
        print("\n  All four ledgers present with the expected parent and GST fields.")


if __name__ == "__main__":
    payload = build()
    if "--send" in sys.argv:
        body = run("export-ledgers", payload)
        if body:
            verify(body)
    else:
        print(payload)
        print("\n(dry run — pass --send to POST this and capture the result)")
