"""
P0-02 — Post one disposable voucher to validate `reset_sandbox.py`'s
delete path (PENDING:009).

**Why this exists.** The keep-list audit of 2026-09-16 established that
every voucher in both sandbox companies is cited by at least one finding
— `Coastal Services Ltd` 1, 2, 4, 5 and `Coastal Test Traders` 1–8. So
`reset_sandbox.py`'s `--confirm` path had no target it could be
validated against without destroying evidence. This posts a voucher
whose only purpose is to be deleted by that script, moments later.

**The payload is #21a's proven accounting-view shape**, structurally
byte-for-byte: `ACTION="Create"`, `DATE`/`EFFECTIVEDATE` 20260801
(Educational Mode allows the 1st, 2nd and 31st), `VOUCHERTYPENAME`,
`PARTYLEDGERNAME`, four `ALLLEDGERENTRIES.LIST`, no inventory. Two
deliberate changes, both values rather than structure:

  1. **The marker**, in both `NARRATION` and `REFERENCE` — #21a proved
     both round-trip verbatim, and a marker that survives is the only
     reliable self-identification a probe voucher has (#14 rules out
     `VOUCHERNUMBER`). Deliberately distinct from today's `GAP2-*`
     markers so a future reader cannot confuse this with them.
  2. **Distinct amounts** — 1000 / 90 / 90 / 1180 rather than the usual
     18400 / 1656 / 1656 / 21712. #21 established these values are
     stored verbatim, not derived, so this changes nothing structural.
     The gain is a second independent check: a Trial Balance delta of
     exactly 1,180 is unmistakably this voucher, where the usual amounts
     would be indistinguishable from vouchers 2 and 5.

**This script only posts and reads.** It never deletes — the delete is
`reset_sandbox.py`'s job, which is the whole point of the exercise.

    python pending009_validate.py                     # print the payload
    python pending009_validate.py --send
    python pending009_validate.py --send --company "..."

Committed rather than run from a scratchpad so its artifacts carry a
real `script` in `meta.json`. #21's artifacts read `script: null` and
the note has to apologise for it; not repeating that.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _args import company_from_argv  # noqa: E402
from _runner import run  # noqa: E402
from tally_voucher_read import build_daybook_read  # noqa: E402
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Services Ltd"
DATE = "20260801"

MARKER = "PENDING009-VALIDATION-DELETE-ME"

PARTY = "Coastal Components Pvt Ltd"
PURCHASE = "Purchase @18%"
TAXABLE = Decimal("1000.00")
CGST = Decimal("90.00")
SGST = Decimal("90.00")
TOTAL = TAXABLE + CGST + SGST  # 1180.00


def build_voucher(company: str) -> str:
    """#21a's shape, with the marker and this probe's distinct amounts."""
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(env, "BODY")
    imp = ET.SubElement(body, "IMPORTDATA")
    desc = ET.SubElement(imp, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "Vouchers"
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    data = ET.SubElement(imp, "REQUESTDATA")
    msg = ET.SubElement(data, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})

    vch = ET.SubElement(msg, "VOUCHER", VCHTYPE="Purchase", ACTION="Create")
    ET.SubElement(vch, "DATE").text = DATE
    ET.SubElement(vch, "EFFECTIVEDATE").text = DATE
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Purchase"
    ET.SubElement(vch, "PARTYLEDGERNAME").text = PARTY
    ET.SubElement(vch, "NARRATION").text = MARKER
    ET.SubElement(vch, "REFERENCE").text = MARKER

    def entry(ledger: str, amount: Decimal, debit: bool) -> None:
        e = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(e, "LEDGERNAME").text = ledger
        ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
        ET.SubElement(e, "AMOUNT").text = str(-amount if debit else amount)

    entry(PARTY, TOTAL, debit=False)
    entry(PURCHASE, TAXABLE, debit=True)
    entry("CGST", CGST, debit=True)
    entry("SGST", SGST, debit=True)

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_trial_balance(company: str) -> str:
    """#23's report read — same envelope as the Day Book, only ID changes."""
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "DATA"
    ET.SubElement(header, "ID").text = "Trial Balance"
    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    ET.SubElement(sv, "SVFROMDATE").text = DATE
    ET.SubElement(sv, "SVTODATE").text = DATE
    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def print_trial_balance(response: str) -> None:
    """Zip DSPACCNAME with DSPACCINFO by document order (#23 limitation 2),
    and read direction from the element, never the sign (#24)."""
    root = ET.fromstring(sanitise(response))
    names = [n.findtext("DSPDISPNAME", "").strip() for n in root.iter("DSPACCNAME")]
    infos = []
    for info in root.iter("DSPACCINFO"):
        dr = (info.findtext("DSPCLDRAMT/DSPCLDRAMTA") or "").strip()
        cr = (info.findtext("DSPCLCRAMT/DSPCLCRAMTA") or "").strip()
        infos.append(f"Dr {dr}" if dr else f"Cr {cr}")
    for name, amount in zip(names, infos):
        print(f"    {name:32} {amount}")


def summarise(response: str) -> list[dict]:
    """Every voucher, with the fields this validation turns on."""
    root = ET.fromstring(sanitise(response))
    out = []
    for vch in root.iter():
        if vch.tag.upper() != "VOUCHER":
            continue
        amounts = [
            (e.findtext("LEDGERNAME") or "").strip()
            + "="
            + (e.findtext("AMOUNT") or "").strip()
            for e in vch.iter()
            if e.tag.upper() in ("ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST")
        ]
        out.append(
            {
                "number": (vch.findtext("VOUCHERNUMBER") or "").strip(),
                "alterid": (vch.findtext("ALTERID") or "").strip(),
                "remoteid": vch.get("REMOTEID", ""),
                "narration": (vch.findtext("NARRATION") or "").strip(),
                "amounts": amounts,
            }
        )
    return out


def print_vouchers(vouchers: list[dict]) -> None:
    print(f"    count: {len(vouchers)}")
    for v in vouchers:
        mark = f"  <-- {v['narration']}" if v["narration"] else ""
        print(f"    vch {v['number']:>3}  ALTERID {v['alterid']:>3}  "
              f"REMOTEID {v['remoteid'][-8:]}{mark}")
        print(f"              {v['amounts']}")


def main() -> None:
    company = company_from_argv(sys.argv, COMPANY)
    payload = build_voucher(company)

    if "--send" not in sys.argv:
        print(payload)
        print(f"\n(dry run — pass --send to post to {company!r})")
        return

    print(f"\n  === Baseline, before the post: {company!r} ===")
    before = run("pending009-1-baseline-daybook",
                 build_daybook_read(company, DATE), timeout=10)
    if before is None or "LINEERROR" in before.upper():
        sys.exit("  HALTED: baseline Day Book read failed — nothing posted.")
    baseline = summarise(before)
    print_vouchers(baseline)

    tb_before = run("pending009-2-baseline-tb", build_trial_balance(company), timeout=10)
    if tb_before is None or "LINEERROR" in tb_before.upper():
        sys.exit("  HALTED: baseline Trial Balance read failed — nothing posted.")
    print_trial_balance(tb_before)

    print(f"\n  === Posting the validation voucher ({MARKER}) ===")
    resp = run("pending009-3-post", payload, timeout=10)
    if resp is None:
        sys.exit("  HALTED: no response to the post.")
    if "LINEERROR" in resp.upper():
        sys.exit("  HALTED: LINEERROR on the post (#17) — nothing to clean up.")

    print("\n  === Read-back (Rule 1 — the counters decide nothing) ===")
    after = run("pending009-4-readback-daybook",
                build_daybook_read(company, DATE), timeout=10)
    if after is None or "LINEERROR" in after.upper():
        sys.exit("  HALTED: post-post Day Book read failed.")
    now = summarise(after)
    print_vouchers(now)

    tb_after = run("pending009-5-post-tb", build_trial_balance(company), timeout=10)
    if tb_after is not None and "LINEERROR" not in tb_after.upper():
        print_trial_balance(tb_after)

    marked = [v for v in now if v["narration"] == MARKER]
    old_numbers = {v["number"] for v in baseline}
    new = [v for v in now if v["number"] not in old_numbers]

    print("\n  === Verdict ===")
    if len(now) != len(baseline) + 1:
        sys.exit(f"  HALTED: voucher count went {len(baseline)} -> {len(now)}, "
                 "expected exactly one more.")
    if len(marked) != 1:
        sys.exit(f"  HALTED: {len(marked)} vouchers carry the marker, expected 1.")
    if len(new) != 1 or new[0]["number"] != marked[0]["number"]:
        sys.exit("  HALTED: the new voucher and the marked voucher are not the same.")

    v = marked[0]
    print(f"  Posted and confirmed by read-back: voucher {v['number']!r}")
    print(f"    REMOTEID  {v['remoteid']}")
    print(f"    ALTERID   {v['alterid']}")
    print(f"    marker    {v['narration']} (NARRATION, round-tripped per #21a)")
    print(f"    amounts   {v['amounts']}")
    print(f"\n  Next: dry-run reset_sandbox.py and confirm voucher {v['number']!r} "
          "is the ONLY DELETE.")


if __name__ == "__main__":
    main()
