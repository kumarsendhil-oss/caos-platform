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
def P(number, vchtype="Purchase"):
    return {"number": number, "vchtype": vchtype}


before = [P("1"), P("2"), P("3")]
try:
    rs.verify_gone(before, [P("1"), P("2")], P("3"))
    print("  [ok ] clean delete accepted")
except rs.Stop as e:
    fails.append(f"clean delete rejected: {e}")
    print(f"  [FAIL] {e}")
for label, after in [
    ("target still present", [P("1"), P("2"), P("3")]),
    ("collateral loss", [P("1")]),
    ("extra appeared", [P("1"), P("2"), P("9")]),
]:
    try:
        rs.verify_gone(before, after, P("3"))
        fails.append(f"{label} not caught")
        print(f"  [FAIL] {label} not caught")
    except rs.Stop as e:
        print(f"  [ok ] {label} -> Stop: {e}")

# ---------------------------------------------------------------------------
# Issue #48 / finding #33 — the collision that silently passed before.
#
# Every case below is built so a number-only implementation CANNOT
# distinguish the two vouchers. That is the point: these are the inputs
# the pre-#33 guard reported clean. The assertions go through the public
# guard rather than calling voucher_key() directly, so a regression in
# either the key or any of its callers surfaces here.
# ---------------------------------------------------------------------------
print("\n== verify_gone: Purchase 1 / Sales 1 collision (issue #48) ==")
MIXED = [P("1", "Purchase"), P("2", "Purchase"), P("1", "Sales")]

# 1. The correct outcome: Purchase 1 goes, Sales 1 survives. Keyed on a
#    bare number this looked like "target still present" and raised — the
#    guard was not only unsound, it was also a false alarm on success.
try:
    rs.verify_gone(MIXED, [P("2", "Purchase"), P("1", "Sales")], P("1", "Purchase"))
    print("  [ok ] Purchase 1 deleted, Sales 1 surviving is accepted (was a false halt)")
except rs.Stop as e:
    fails.append(f"correct mixed-type delete rejected: {e}")
    print(f"  [FAIL] {e}")

# 2. THE REGRESSION CASE — silent data loss. Tally takes BOTH vouchers
#    numbered 1. Keyed on bare number, `expected` and `actual` both
#    collapse {Purchase 1, Sales 1} into {"1"}, so `expected - actual` is
#    empty; and the count check passes too, because exactly one voucher
#    "disappeared" by number. Nothing caught it. Must now halt.
try:
    rs.verify_gone(MIXED, [P("2", "Purchase")], P("1", "Purchase"))
    fails.append("collateral loss of Sales 1 NOT caught — issue #48 regression")
    print("  [FAIL] collateral loss of Sales 1 not caught")
except rs.Stop as e:
    print(f"  [ok ] collateral loss of Sales 1 -> Stop: {e}")

# 3. Wrong voucher deleted: Tally took Sales 1 when Purchase 1 was
#    addressed. Number-keyed, this is indistinguishable from case 1.
try:
    rs.verify_gone(MIXED, [P("1", "Purchase"), P("2", "Purchase")], P("1", "Purchase"))
    fails.append("wrong-voucher delete NOT caught — issue #48 regression")
    print("  [FAIL] wrong-voucher delete not caught")
except rs.Stop as e:
    print(f"  [ok ] wrong voucher deleted -> Stop: {e}")

# 4. Type case must not manufacture a phantom voucher.
try:
    rs.verify_gone([P("1", "Purchase"), P("2", "Purchase")],
                   [P("1", "purchase")], P("2", "PURCHASE"))
    print("  [ok ] voucher type is compared case-insensitively")
except rs.Stop as e:
    fails.append(f"case-sensitivity regression: {e}")
    print(f"  [FAIL] {e}")

print("\n== keep-list is type-aware (issue #48) ==")
check("bare number protects every type (fail-safe, unchanged)",
      rs.keep_matches(P("1", "Sales"), {"1"}), "1")
check("Type:Number does not protect another type",
      rs.keep_matches(P("1", "Sales"), {"Purchase:1"}), None)
check("Type:Number matches its own voucher",
      rs.keep_matches(P("1", "Purchase"), {"Purchase:1"}), "Purchase:1")
check("Type:Number is case-insensitive on the type",
      rs.keep_matches(P("1", "Purchase"), {"purchase:1"}), "purchase:1")
_mixed = rs.classify(
    [dict(P("1", "Purchase"), cancelled=False, entries=4),
     dict(P("1", "Sales"), cancelled=False, entries=4)],
    {"Purchase:1"},
)
check("classify: Purchase 1 KEEP, Sales 1 DELETE under keep-list {Purchase:1}",
      [v["verdict"] for v in _mixed], ["KEEP", "DELETE"])

print("\n== mixed-type refusal (issue #48 step 1 still open) ==")
SINGLE = [P("1"), P("2")]
check("single-type company reports one type", rs.voucher_types(SINGLE), ["Purchase"])
try:
    rs.check_mixed_types(SINGLE, allowed=False)
    print("  [ok ] single-type company is not refused")
except rs.Stop as e:
    fails.append(f"single-type company refused: {e}")
    print(f"  [FAIL] {e}")
try:
    rs.check_mixed_types(MIXED, allowed=False)
    fails.append("mixed-type company NOT refused")
    print("  [FAIL] mixed-type company not refused")
except rs.Stop as e:
    print(f"  [ok ] mixed-type refused -> Stop: {e}")
try:
    rs.check_mixed_types(MIXED, allowed=True)
    print("  [ok ] --allow-mixed-types overrides the refusal")
except rs.Stop as e:
    fails.append(f"--allow-mixed-types did not override: {e}")
    print(f"  [FAIL] {e}")

print("\n== keep-file parsing ==")
kf = SPIKE / "keep-coastal-services.txt"
# Rebuilt type-qualified for issue #48. Asserted as the exact set rather
# than a count, because the failure this guards against is a keep-file
# that silently loses an entry — which a count check would also show, but
# an exact set says *which*.
check("example keep-file is type-qualified and complete",
      rs._read_keep_file(kf),
      {"Purchase:1", "Purchase:2", "Purchase:4", "Purchase:5",
       "Sales:1", "Sales:2"})
# Every entry must match the voucher it names and nothing else. A
# keep-file full of typos parses fine and protects nothing (#33).
_live = [{"number": n, "vchtype": t} for t, n in
         [("Purchase", "1"), ("Purchase", "2"), ("Purchase", "4"),
          ("Purchase", "5"), ("Sales", "1"), ("Sales", "2")]]
check("every keep-file entry matches exactly one live voucher",
      sorted(rs.keep_matches(v, rs._read_keep_file(kf)) or "MISS" for v in _live),
      ["Purchase:1", "Purchase:2", "Purchase:4", "Purchase:5",
       "Sales:1", "Sales:2"])

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
    except rs.Stop as e:
        # Mirror `__main__`, which catches Stop and exits non-zero. Without
        # this the harness cannot test any guard that halts via Stop rather
        # than sys.exit — which is every guard added for issue #48.
        code = 1
        print(f"  HALTED: {e}")
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
# Artifact names carry the voucher type: two vouchers numbered "1" would
# otherwise write into run directories differing only by timestamp (#33).
check("happy path: delete then read-back", [n for n, _ in sent],
      ["reset-enumerate", "reset-delete-Purchase-2", "reset-readback-Purchase-2"])

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

# ---------------------------------------------------------------------------
# The safety assertion that actually matters for issue #48.
#
# MIXED_ART is a real, committed Day Book read of `Coastal Services Ltd`
# taken 2026-09-16 — Purchase 1, 2, 4, 5 and Sales 1, 2, with numbers 1
# and 2 colliding across types. This is the exact company the old code
# was unsafe on. Under --confirm, with an EMPTY keep-list so that every
# deletable voucher is planned for deletion, the script must still send
# exactly one request (the enumerate) and no Import Data at all.
#
# The keep-list is empty on purpose: a passing result that depended on
# the keep-file would be testing the keep-file, not the refusal.
# ---------------------------------------------------------------------------
print("\n== mixed-type company refuses under --confirm (issue #48) ==")
MIXED_ART = (SPIKE / "runs" / "2026-09-16T13-39-42-reset-enumerate"
             / "response.xml").read_text(encoding="utf-8", errors="replace")
_live = rs.enumerate_vouchers(MIXED_ART)
check("artifact really is mixed-type", rs.voucher_types(_live), ["Purchase", "Sales"])
check("artifact really has colliding numbers",
      sorted({v["number"] for v in _live
              if sum(x["number"] == v["number"] for x in _live) > 1}),
      ["1", "2"])

sent, code = drive("mixed-confirm", [MIXED_ART],
                   ["--company", "Coastal Services Ltd", "--confirm"])
check("mixed-type + --confirm exits non-zero", code != 0, True)
check("mixed-type + --confirm sent exactly one request", len(sent), 1)
check("mixed-type + --confirm sent NO Import Data",
      any("Import Data" in pl for _, pl in sent), False)

# And the override still works, so the refusal is a gate rather than a wall.
sent, code = drive("mixed-confirm-allowed", [MIXED_ART, OK, MIXED_ART],
                   ["--company", "Coastal Services Ltd", "--confirm",
                    "--allow-mixed-types", "--keep",
                    "Purchase:1,Purchase:2,Purchase:4,Purchase:5,Sales:1"])
check("--allow-mixed-types reaches the delete path",
      any("Import Data" in pl for _, pl in sent), True)
check("--allow-mixed-types targets the type-qualified voucher",
      [n for n, _ in sent][1], "reset-delete-Sales-2")

print("\n== result ==")
print("  ALL PASS" if not fails else "  FAILURES:\n    " + "\n    ".join(fails))
sys.exit(1 if fails else 0)
