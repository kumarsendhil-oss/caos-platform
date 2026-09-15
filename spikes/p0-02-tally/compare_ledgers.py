"""
P0-02 — Diff two ledgers' full field sets.

WHY: create_ledgers.py sent CGST and SGST with structurally identical
payloads differing only in GSTDUTYHEAD ("Central Tax" vs "State Tax").
SGST came back with its value set; CGST came back empty. Two
near-identical records where one worked is the cleanest diagnostic
available — so diff them rather than theorise.

dump_ledger.py established that the working request shape is a
Collection with FETCH * and a name filter, so this reuses that.

    python compare_ledgers.py                    # print the payload
    python compare_ledgers.py --send             # CGST vs SGST
    python compare_ledgers.py --send --a X --b Y
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Test Traders"


def build_dump(name: str, company: str = COMPANY) -> str:
    """Collection + FETCH * + name filter — the shape dump_ledger.py proved works."""
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = "CAOS Ledger Dump"

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

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


def extract(response: str, target: str) -> dict[str, str]:
    """Every tag/value Tally emitted for one ledger, including nested lists."""
    fields: dict[str, str] = {}
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        print(f"  (not parseable: {exc})")
        return fields

    for ledger in root.iter():
        if ledger.tag.upper() != "LEDGER":
            continue
        name = ledger.get("NAME") or ledger.findtext("NAME") or ledger.findtext("Name")
        if not name or name.strip().upper() != target.upper():
            continue

        for child in ledger:
            text = (child.text or "").strip()
            if text:
                fields[child.tag] = text
            # Nested .LIST structures are where Tally puts GST config —
            # flatten one level so they show up in the diff.
            for grandchild in child:
                gtext = (grandchild.text or "").strip()
                if gtext:
                    fields[f"{child.tag}/{grandchild.tag}"] = gtext
        return fields

    return fields


def diff(a_name: str, a: dict[str, str], b_name: str, b: dict[str, str]) -> None:
    print(f"\n{'=' * 64}")
    print(f"DIFF: {a_name} vs {b_name}")
    print("=" * 64)
    print(f"  {a_name}: {len(a)} non-empty fields")
    print(f"  {b_name}: {len(b)} non-empty fields")

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    differing = sorted(k for k in set(a) & set(b) if a[k] != b[k])

    if only_a:
        print(f"\n  Set on {a_name} but ABSENT on {b_name}:")
        for k in only_a:
            print(f"    {k} = {a[k][:60]}")
    if only_b:
        print(f"\n  Set on {b_name} but ABSENT on {a_name}:")
        for k in only_b:
            print(f"    {k} = {b[k][:60]}")
    if differing:
        print("\n  Present on both, different values:")
        for k in differing:
            print(f"    {k}:")
            print(f"      {a_name} = {a[k][:60]}")
            print(f"      {b_name} = {b[k][:60]}")
    if not (only_a or only_b or differing):
        print("\n  Identical — which would mean the earlier difference was a read artefact.")


if __name__ == "__main__":
    a_name = sys.argv[sys.argv.index("--a") + 1] if "--a" in sys.argv else "CGST"
    b_name = sys.argv[sys.argv.index("--b") + 1] if "--b" in sys.argv else "SGST"

    if "--send" not in sys.argv:
        print(build_dump(a_name))
        print("\n(dry run — pass --send to dump both and diff them)")
        sys.exit(0)

    print(f"--- dumping {a_name} ---")
    a_body = run(f"compare-{a_name.lower()}", build_dump(a_name))
    print(f"\n--- dumping {b_name} ---")
    b_body = run(f"compare-{b_name.lower()}", build_dump(b_name))

    if a_body and b_body:
        diff(a_name, extract(a_body, a_name), b_name, extract(b_body, b_name))
