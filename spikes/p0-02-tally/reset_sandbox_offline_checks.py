"""
Offline checks for reset_sandbox.py — sends nothing, needs no Tally.

`reset_sandbox.py` is the only destructive script in this directory, so
its guards are the thing most worth having evidence for, and the live
sandbox is the worst place to get that evidence. Everything here runs
against committed run artifacts and a stubbed transport:

  * date conversion and its rejections
  * enumeration against a real Day Book response, including the
    cancelled and inventory-view vouchers the plainer parser drops
  * keep-list parsing and classification
  * `verify_gone()`'s three halt conditions
  * argv guards, as real subprocesses
  * the delete payload's attributes against #28's proven request.xml
  * the dry-run and `--max` paths, asserting zero `Import Data` sent
  * every halt path under `--confirm`, with a stubbed transport

    python reset_sandbox_offline_checks.py

Run it after touching reset_sandbox.py. It is not pytest — the spikes
directory has no suite, and this needs the committed artifacts beside
it. Non-zero exit means a guard regressed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SPIKE = Path(__file__).resolve().parent
ROOT = SPIKE.parent.parent
sys.path.insert(0, str(SPIKE))
sys.path.insert(0, str(ROOT / "spikes"))
import reset_sandbox as rs  # noqa: E402 — sys.path is set up just above

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")

print("\n== tally_date ==")
check("20260801", rs.tally_date("20260801"), "01-Aug-2026")
check("20260131", rs.tally_date("20260131"), "31-Jan-2026")
check("20261231", rs.tally_date("20261231"), "31-Dec-2026")
for bad in ("2026-08-01", "", "2026081", "20261301"):
    try:
        rs.tally_date(bad)
        fails.append(f"tally_date({bad!r}) did not raise")
        print(f"  [FAIL] {bad!r} did not raise")
    except rs.Stop as e:
        print(f"  [ok ] {bad!r} -> Stop({e})")

print("\n== enumerate_vouchers against real artifacts ==")
art = SPIKE / "runs" / "2026-09-16T10-15-00-delete-attempt-success" / "readback.xml"
vs = rs.enumerate_vouchers(art.read_text(encoding="utf-8", errors="replace"))
print("  vouchers found:")
for v in vs:
    print(f"    {v['number']!r} {v['date']} {v['vchtype']} "
          f"entries={v['entries']} amount={v['amount']} cancelled={v['cancelled']}")
check("count (post-delete readback, #28 says 4)", len(vs), 4)
check("numbers", sorted(v["number"] for v in vs), ["1", "2", "4", "5"])
check("no renumbering: 3 absent", "3" in {v["number"] for v in vs}, False)

print("\n== classify / keep-list ==")
c = rs.classify([dict(v) for v in vs], {"1"})
by = {v["number"]: (v["verdict"], v["reason"]) for v in c}
for n, (verd, why) in sorted(by.items()):
    print(f"  voucher {n}: {verd} {why}")
check("voucher 1 kept", by["1"][0], "KEEP")
check("voucher 4 (cancelled per #26) is SKIP", by["4"][0], "SKIP")
check("voucher 2 deletable", by["2"][0], "DELETE")

print("\n== verify_gone ==")
before = [{"number": "1"}, {"number": "2"}, {"number": "3"}]
try:
    rs.verify_gone(before, [{"number": "1"}, {"number": "2"}], "3")
    print("  [ok ] clean delete accepted")
except rs.Stop as e:
    fails.append(f"clean delete rejected: {e}")
    print(f"  [FAIL] {e}")
for label, after in [
    ("target still present", [{"number": "1"}, {"number": "2"}, {"number": "3"}]),
    ("collateral loss", [{"number":"1"}]),
    ("extra appeared", [{"number": "1"}, {"number": "2"}, {"number": "9"}]),
]:
    try:
        rs.verify_gone(before, after, "3")
        fails.append(f"{label} not caught")
        print(f"  [FAIL] {label} not caught")
    except rs.Stop as e:
        print(f"  [ok ] {label} -> Stop: {e}")

print("\n== keep-file parsing ==")
kf = SPIKE / "keep-coastal-services.txt"
check("example keep-file", rs._read_keep_file(kf), {"1"})

print("\n== argv guards (subprocess, no network reached) ==")
cases = [
    (["--company"], "--company requires"),
    (["--company", "--confirm"], "got the flag"),
    ([], "--company is required"),
    (["--company", "X", "--bogus"], "unknown flag"),
    (["--company", "X", "--max", "lots"], "--max requires a number"),
    (["--company", "X", "--keep-file", "nope.txt"], "does not exist"),
]
for argv, expect in cases:
    p = subprocess.run([sys.executable, str(SPIKE / "reset_sandbox.py"), *argv],
                       capture_output=True, text=True, cwd=SPIKE, timeout=60)
    out = (p.stdout + p.stderr).strip().replace("\n", " | ")
    ok = expect in out and p.returncode != 0
    print(f"  [{'ok ' if ok else 'FAIL'}] {argv} -> rc={p.returncode} {out[:120]}")
    if not ok:
        fails.append(f"argv {argv}: {out[:200]}")


print("\n== delete payload vs #28's proven request ==")
RUN = SPIKE / "runs" / "2026-09-16T10-15-00-delete-attempt-success"
ART = (RUN / "readback.xml").read_text(encoding="utf-8", errors="replace")
PROVEN = (RUN / "request.xml").read_text(encoding="utf-8")


def _attrs(x):
    m = re.search(r"<VOUCHER ([^>]*)>", x)
    return dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))


mine = rs.build_delete("Coastal Services Ltd",
                       {"number": "3", "date": "20260801", "vchtype": "Purchase"})
print(f"  proven: {_attrs(PROVEN)}")
print(f"  mine  : {_attrs(mine)}")
check("delete attributes match #28 exactly", _attrs(mine), _attrs(PROVEN))
# #26 attempt 1 was rejected for an empty body; #28's success carried one.
check("body is non-empty", "<NARRATION />" not in mine and "<NARRATION>" in mine, True)


def drive(label, responses, argv):
    """Run main() with a stubbed transport. Returns (requests sent, exit code)."""
    seq, sent = list(responses), []

    def fake_run(name, payload, *, url="", timeout=None, **kw):
        sent.append((name, payload))
        return seq.pop(0) if seq else None

    real, rs.run = rs.run, fake_run
    sys.argv = ["reset_sandbox.py", *argv]
    code = 0
    try:
        rs.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        print(f"  exit: {e}")
    finally:
        rs.run = real
    print(f"  requests: {[n for n, _ in sent]}")
    return sent, code


print("\n== dry run sends no Import Data ==")
sent, _ = drive("dry", [ART], ["--company", "Coastal Services Ltd", "--keep", "1"])
check("dry run request count", len(sent), 1)
check("dry run sent no Import Data", any("Import Data" in pl for _, pl in sent), False)

print("\n== --max refuses before sending any Import Data ==")
sent, code = drive("max", [ART], ["--company", "C", "--max", "1", "--confirm"])
check("--max exits non-zero", code != 0, True)
check("--max sent no Import Data", any("Import Data" in pl for _, pl in sent), False)

print("\n== --confirm paths (stubbed transport) ==")
# Remove voucher 2's element the way a real delete does: survivors keep their
# numbers and the sequence gets a hole (#28), rather than renumbering.
_gone2 = "".join(b for b in re.split(r"(?=<VOUCHER )", ART)
                 if "<VOUCHERNUMBER>2</VOUCHERNUMBER>" not in b)
CONFIRM = ["--company", "C", "--keep", "1,5", "--confirm"]
OK = "<ENVELOPE><DELETED>1</DELETED></ENVELOPE>"

sent, code = drive("happy", [ART, OK, _gone2], CONFIRM)
check("happy path exits 0", code, 0)
check("happy path: delete then read-back", [n for n, _ in sent],
      ["reset-enumerate", "reset-delete-2", "reset-readback-2"])

for label, responses, expect_calls in [
    # Rule 1: the counters said DELETED 1 and the voucher is still there.
    ("still present after a 'successful' delete", [ART, OK, ART], 3),
    # #17: a LINEERROR outranks every counter.
    ("LINEERROR with zero counters",
     [ART, "<ENVELOPE><LINEERROR>Cannot delete unnamed object: VOUCHER!</LINEERROR>"
           "<ERRORS>0</ERRORS></ENVELOPE>", ART], 2),
    # A hang surfaces as no response, and must not be retried.
    ("no response to the delete", [ART, None, ART], 2),
]:
    print(f"\n  -- {label}")
    sent, code = drive(label, responses, CONFIRM)
    check(f"{label}: halts non-zero", code != 0, True)
    check(f"{label}: stopped without retrying", len(sent), expect_calls)

print("\n== result ==")
print("  ALL PASS" if not fails else "  FAILURES:\n    " + "\n    ".join(fails))
sys.exit(1 if fails else 0)
