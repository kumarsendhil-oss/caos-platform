"""
P0-02 — Find the GSTDUTYHEAD value Tally actually accepts.

ESTABLISHED SO FAR (runs 2026-09-15T15-10-39):
CGST and SGST were created with structurally identical payloads
differing only in GSTDUTYHEAD. A full-field diff shows exactly one
substantive difference out of ~92 fields: SGST has
GSTDUTYHEAD = "State Tax"; CGST has no value at all. Tally reported
CREATED=4, ERRORS=0 — it accepted "State Tax" and silently discarded
"Central Tax" without complaint.

So "Central Tax" is not the string Tally wants. This probes candidates
by altering CGST and reading the value back after each, which is the
only reliable signal: the import response says nothing useful.

Ordering note: "State Tax" is included deliberately, as a control. If
it sticks on CGST, the problem is purely the rejected string. If even
that fails, the problem is something about the CGST ledger itself and
the candidate list is the wrong place to look.

    python probe_dutyhead.py            # print the payloads
    python probe_dutyhead.py --send     # try each, report which stick
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Test Traders"
LEDGER = "CGST"

# Ordered least- to most-speculative. "State Tax" is the control: it is
# known to work on SGST, so if it fails here the ledger is the problem.
CANDIDATES = [
    "State Tax",          # control — known good on SGST
    "CGST",
    "Central Tax",        # the value that was silently dropped
    "CENTRAL TAX",
    "Central",
    "Integrated Tax",
]


def build_alter(name: str, duty_head: str, company: str = COMPANY) -> str:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(env, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")
    reqdesc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(reqdesc, "REPORTNAME").text = "All Masters"
    sv = ET.SubElement(reqdesc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

    reqdata = ET.SubElement(importdata, "REQUESTDATA")
    msg = ET.SubElement(reqdata, "TALLYMESSAGE")
    msg.set("xmlns:UDF", "TallyUDF")

    ledger = ET.SubElement(msg, "LEDGER", NAME=name, ACTION="Alter")
    ET.SubElement(ledger, "NAME").text = name
    ET.SubElement(ledger, "TAXTYPE").text = "GST"
    ET.SubElement(ledger, "GSTDUTYHEAD").text = duty_head

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_read(name: str, company: str = COMPANY) -> str:
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


def read_dutyhead(response: str, target: str) -> str | None:
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return None
    for ledger in root.iter():
        if ledger.tag.upper() != "LEDGER":
            continue
        name = ledger.get("NAME") or ledger.findtext("NAME")
        if name and name.strip().upper() == target.upper():
            for child in ledger:
                if child.tag.upper() == "GSTDUTYHEAD":
                    return (child.text or "").strip() or None
            return None
    return None


if __name__ == "__main__":
    if "--send" not in sys.argv:
        print(build_alter(LEDGER, CANDIDATES[0]))
        print("\n(dry run — pass --send to probe each candidate)")
        sys.exit(0)

    results: list[tuple[str, str | None]] = []
    for candidate in CANDIDATES:
        label = candidate.lower().replace(" ", "-")
        print(f"\n--- trying GSTDUTYHEAD = {candidate!r} ---")
        run(f"probe-{label}-alter", build_alter(LEDGER, candidate))
        body = run(f"probe-{label}-read", build_read(LEDGER))
        got = read_dutyhead(body, LEDGER) if body else None
        results.append((candidate, got))
        print(f"  read back: {got!r}")

    print(f"\n{'=' * 60}\nRESULTS for {LEDGER}\n{'=' * 60}")
    stuck = [(c, g) for c, g in results if g]
    for candidate, got in results:
        mark = "OK  " if got else "drop"
        print(f"  [{mark}] sent {candidate!r:18} -> read {got!r}")

    if not stuck:
        print(
            "\n  Nothing stuck, including the 'State Tax' control that works on SGST.\n"
            "  That points at the CGST ledger itself rather than the value —\n"
            "  possibly ALTER can't set this field, only CREATE can. Next step\n"
            "  would be deleting CGST and recreating it with a known-good value."
        )
    else:
        print(f"\n  Accepted: {[c for c, _ in stuck]}")
        print("  NOTE: CGST now holds whichever value stuck last — reset it before")
        print("  running the voucher test, or the tax split will be wrong.")
