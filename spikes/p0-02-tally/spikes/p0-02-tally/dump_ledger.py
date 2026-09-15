"""
P0-02 — Dump one ledger with every field Tally knows about.

WHY: export_ledgers.py asks for specific fields by name via
NATIVEMETHOD, which only works if we already know what Tally calls
them. CGST came back with TaxType set but GSTDutyHead empty, and we
can't tell whether the import dropped the field or Tally simply names
it something else in responses.

Guessing is the wrong tool here. The TDL Reference Manual can't settle
it either — it's Tally.ERP 9 era and predates GST (85 VAT references,
no GSTDUTYHEAD). So: ask Tally. Export the object with no field filter
and read the names Tally itself emits.

Three request shapes are tried because it isn't documented which one
TallyPrime accepts for a full object dump. Each is captured separately,
so a rejection is recorded as evidence rather than lost.

    python dump_ledger.py                 # print all three payloads
    python dump_ledger.py --send          # send all three, capture each
    python dump_ledger.py --send --name SGST
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Test Traders"


def _envelope(req_type: str, id_value: str, company: str) -> ET.Element:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = req_type
    ET.SubElement(header, "ID").text = id_value
    return env


def _desc(env: ET.Element, company: str) -> ET.Element:
    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    return desc


def build_object(name: str, company: str = COMPANY) -> str:
    """Attempt 1 — export a single Object by name."""
    env = _envelope("OBJECT", "Ledger", company)
    desc = _desc(env, company)
    sv = desc.find("STATICVARIABLES")
    ET.SubElement(sv, "SVOBJECTNAME").text = name
    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_collection_fetch_all(name: str, company: str = COMPANY) -> str:
    """Attempt 2 — a Collection with FETCH * (all fields) filtered to one ledger."""
    env = _envelope("COLLECTION", "CAOS Ledger Dump", company)
    desc = _desc(env, company)

    tdl = ET.SubElement(desc, "TDL")
    tdlmsg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(tdlmsg, "COLLECTION", NAME="CAOS Ledger Dump", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Ledger"
    ET.SubElement(coll, "FETCH").text = "*"
    ET.SubElement(coll, "FILTER").text = "CAOSLedgerName"

    system = ET.SubElement(tdlmsg, "SYSTEM", TYPE="Formulae", NAME="CAOSLedgerName")
    system.text = f'$Name = "{name}"'

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_list_of_ledgers(company: str = COMPANY) -> str:
    """Attempt 3 — Tally's own built-in 'List of Ledgers' report, unfiltered."""
    env = _envelope("COLLECTION", "List of Ledgers", company)
    _desc(env, company)
    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def report_fields(response: str, target: str) -> None:
    """List every tag Tally emitted for the target ledger."""
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        print(f"    (not parseable: {exc})")
        return

    for ledger in root.iter():
        if ledger.tag.upper() != "LEDGER":
            continue
        name = ledger.get("NAME") or ledger.findtext("NAME") or ledger.findtext("Name")
        if not name or name.strip().upper() != target.upper():
            continue

        print(f"    Fields Tally emits for {name.strip()!r}:")
        for child in ledger:
            text = (child.text or "").strip()
            if text:
                print(f"      {child.tag} = {text[:70]}")
        # Anything GST-ish is what we're actually hunting for.
        gstish = [c.tag for c in ledger if "GST" in c.tag.upper() or "TAX" in c.tag.upper()]
        if gstish:
            print(f"    GST/tax-related tags: {', '.join(gstish)}")
        else:
            print("    No GST/tax-related tags present at all.")
        return

    print(f"    {target!r} not found in this response.")


if __name__ == "__main__":
    target = "CGST"
    if "--name" in sys.argv:
        target = sys.argv[sys.argv.index("--name") + 1]

    attempts = [
        ("object", build_object(target)),
        ("collection-fetch-all", build_collection_fetch_all(target)),
        ("list-of-ledgers", build_list_of_ledgers()),
    ]

    if "--send" not in sys.argv:
        for label, payload in attempts:
            print(f"\n{'=' * 60}\n{label}\n{'=' * 60}\n{payload}")
        print("\n(dry run — pass --send to POST these and capture the results)")
        sys.exit(0)

    for label, payload in attempts:
        print(f"\n--- attempt: {label} ---")
        body = run(f"dump-ledger-{label}", payload)
        if body:
            report_fields(body, target)
