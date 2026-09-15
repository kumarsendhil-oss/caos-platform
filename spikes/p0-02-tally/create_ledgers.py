"""
P0-02 — Create the test ledgers via Tally's XML import.

Creates the four ledgers the voucher-import test depends on, over the
API rather than by hand. Also tests BK-03's premise: when the
Bookkeeping Agent finds no matching ledger it raises a task, and if
ledger creation works over the API, resolving that task can be an
in-app action rather than manual entry in Tally.

    python create_ledgers.py            # print the payload, send nothing
    python create_ledgers.py --send     # send it, capture to runs/

UNVERIFIED until run. The GST tax-type fields on CGST/SGST are the part
most likely to be wrong — Tally is particular about these and its error
won't say which field it disliked. After a successful-looking run,
check the ledger in the UI (Alter > Ledger > CGST) and confirm
'Type of duty/tax' really shows GST: a missing field produces a plain
ledger that silently won't participate in GST computation.
"""

from __future__ import annotations

import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402

COMPANY = "Coastal Test Traders"


def _ledger(msg: ET.Element, name: str, parent: str, gst_duty_head: str | None = None) -> None:
    ledger = ET.SubElement(msg, "LEDGER", NAME=name, ACTION="Create")
    ET.SubElement(ledger, "NAME").text = name
    ET.SubElement(ledger, "PARENT").text = parent
    ET.SubElement(ledger, "OPENINGBALANCE").text = "0"

    if gst_duty_head:
        ET.SubElement(ledger, "ISDEEMEDPOSITIVE").text = "No"
        ET.SubElement(ledger, "TAXTYPE").text = "GST"
        ET.SubElement(ledger, "GSTDUTYHEAD").text = gst_duty_head
        ET.SubElement(ledger, "RATEOFTAXCALCULATION").text = "0"


def build(company: str = COMPANY) -> str:
    env = ET.Element("ENVELOPE")

    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(env, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")

    reqdesc = ET.SubElement(importdata, "REQUESTDESC")
    # Masters and transactions use different import reports — this must
    # be "All Masters", not "Vouchers".
    ET.SubElement(reqdesc, "REPORTNAME").text = "All Masters"
    sv = ET.SubElement(reqdesc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

    reqdata = ET.SubElement(importdata, "REQUESTDATA")
    msg = ET.SubElement(reqdata, "TALLYMESSAGE")
    msg.set("xmlns:UDF", "TallyUDF")

    _ledger(msg, "Coastal Components Pvt Ltd", "Sundry Creditors")
    _ledger(msg, "Purchase @18%", "Purchase Accounts")
    _ledger(msg, "CGST", "Duties & Taxes", gst_duty_head="Central Tax")
    _ledger(msg, "SGST", "Duties & Taxes", gst_duty_head="State Tax")

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


if __name__ == "__main__":
    payload = build()
    if "--send" in sys.argv:
        run("create-ledgers", payload)
    else:
        print(payload)
        print("\n(dry run — pass --send to POST this and capture the result)")
