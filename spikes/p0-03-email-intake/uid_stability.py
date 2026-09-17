"""Test UIDVALIDITY / UID / Message-ID stability across separate IMAP sessions.

Answers P0-03's open question 5 — the CG7-shaped one. An email-intake agent
must not re-extract, re-classify and re-file a message it has already
processed, and that needs a durable identifier. IMAP offers two candidates
and neither is unconditionally safe:

- **(UIDVALIDITY, UID)** — UIDs are unique and stable *within* a UIDVALIDITY
  epoch. RFC 3501 requires a client to detect a UIDVALIDITY change and treat
  every stored UID as meaningless when it happens. A client that stores UIDs
  and never checks UIDVALIDITY is relying on something the protocol
  explicitly does not promise.
- **Message-ID** — an RFC 5322 header, not an IMAP construct, so it survives
  mailbox-level events entirely. But it is written by the *sending* system,
  which makes it self-reported: it can be absent, malformed, or duplicated.

**Important distinction this script exists partly to demonstrate:**
`imaplib`'s `search()` and `fetch()` operate on **message sequence numbers**,
not UIDs. Sequence numbers are positional and renumber when a message is
expunged, so they are actively wrong as a dedup key. The UID variants
(`uid('SEARCH', ...)`, `uid('FETCH', ...)`) are what this script uses, and it
records both so the difference is visible rather than assumed.

Each run takes a snapshot per session and writes it to `uid_snapshots/`.
Comparison is across snapshots, so evidence accumulates over time rather than
resting on one observation.

    python uid_stability.py --sessions 3 --gap 20
    python uid_stability.py --compare-only
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import time
from typing import Any

from dotenv import load_dotenv

from email_test import HERE, _connect, _decode, _require

SNAPSHOT_DIR = HERE / "uid_snapshots"


def _uidvalidity(client: imaplib.IMAP4_SSL, mailbox: str) -> tuple[int | None, int | None]:
    """UIDVALIDITY and UIDNEXT, read via STATUS rather than inferred."""
    status, data = client.status(mailbox, "(UIDVALIDITY UIDNEXT)")
    if status != "OK" or not data:
        return None, None
    text = data[0].decode()
    parts = dict(
        zip(
            ["UIDVALIDITY", "UIDNEXT"],
            [None, None],
            strict=False,
        )
    )
    for key in parts:
        marker = f"{key} "
        if marker in text:
            tail = text.split(marker, 1)[1]
            digits = "".join(c for c in tail if c.isdigit() or c == " ").split()
            parts[key] = int(digits[0]) if digits else None
    return parts["UIDVALIDITY"], parts["UIDNEXT"]


def _message_ids(client: imaplib.IMAP4_SSL, uids: list[str]) -> dict[str, str | None]:
    """Fetch only the Message-ID header per UID — cheap, and body-free."""
    found: dict[str, str | None] = {}
    for uid in uids:
        status, data = client.uid(
            "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT)])"
        )
        if status != "OK" or not data or not isinstance(data[0], tuple):
            found[uid] = None
            continue
        msg = email.message_from_bytes(data[0][1])
        found[uid] = msg.get("Message-ID")
    return found


def _subjects(client: imaplib.IMAP4_SSL, uids: list[str]) -> dict[str, str]:
    """Subjects, purely so a human can tell which message a UID refers to."""
    out: dict[str, str] = {}
    for uid in uids:
        status, data = client.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
        if status == "OK" and data and isinstance(data[0], tuple):
            out[uid] = _decode(email.message_from_bytes(data[0][1]).get("Subject"))[:48]
        else:
            out[uid] = ""
    return out


def take_snapshot(label: str) -> dict[str, Any]:
    """One genuinely fresh session: connect, read, log out completely."""
    host = _require("IMAP_HOST")
    user = _require("IMAP_USER")
    mailbox = os.environ.get("IMAP_MAILBOX", "INBOX").strip() or "INBOX"
    password = _require("IMAP_APP_PASSWORD").replace(" ", "")

    client = _connect(host, int(os.environ.get("IMAP_PORT", "993")), user, password)
    try:
        uidvalidity, uidnext = _uidvalidity(client, mailbox)
        client.select(mailbox, readonly=True)

        # Sequence numbers (what email_test.py's search() actually returns).
        status, seq_data = client.search(None, "ALL")
        seqs = [s.decode() for s in (seq_data[0].split() if seq_data and seq_data[0] else [])]

        # UIDs — the correct identifier.
        status, uid_data = client.uid("SEARCH", None, "ALL")
        uids = [u.decode() for u in (uid_data[0].split() if uid_data and uid_data[0] else [])]

        message_ids = _message_ids(client, uids)
        subjects = _subjects(client, uids)
    finally:
        client.logout()

    snapshot = {
        "label": label,
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mailbox": mailbox,
        "uidvalidity": uidvalidity,
        "uidnext": uidnext,
        "sequence_numbers": seqs,
        "uids": uids,
        "messages": [
            {"uid": u, "message_id": message_ids.get(u), "subject": subjects.get(u, "")}
            for u in uids
        ],
    }
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{time.strftime('%Y%m%dT%H%M%S')}_{label}.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"  [snapshot] UIDVALIDITY={uidvalidity} UIDNEXT={uidnext} "
          f"seq={len(seqs)} uids={len(uids)} -> {path.name}")
    return snapshot


def _load_snapshots() -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(SNAPSHOT_DIR.glob("*.json"))
    ]


def _compare_uidvalidity(snaps: list[dict[str, Any]]) -> bool:
    values = {s["uidvalidity"] for s in snaps}
    print(f"\n  UIDVALIDITY across {len(snaps)} session(s): {sorted(values)}")
    if len(values) == 1:
        print("    -> unchanged across every session observed")
        return True
    print("    -> CHANGED. Every stored UID is invalid; fall back to Message-ID.")
    return False


def _compare_uids(snaps: list[dict[str, Any]]) -> bool:
    baseline = {m["message_id"]: m["uid"] for m in snaps[0]["messages"]}
    stable = True
    for snap in snaps[1:]:
        for msg in snap["messages"]:
            was = baseline.get(msg["message_id"])
            if was is not None and was != msg["uid"]:
                print(f"    ! UID moved: {msg['message_id']} {was} -> {msg['uid']}")
                stable = False
    print(f"  UID per message across sessions: "
          f"{'identical everywhere' if stable else 'MOVED — see above'}")
    return stable


def _compare_message_ids(snaps: list[dict[str, Any]]) -> None:
    per_session = [{m["message_id"] for m in s["messages"]} for s in snaps]
    identical = all(ids == per_session[0] for ids in per_session)
    print(f"  Message-ID set across sessions: "
          f"{'identical' if identical else 'DIFFERS between sessions'}")
    latest = snaps[-1]["messages"]
    missing = [m["uid"] for m in latest if not m["message_id"]]
    malformed = [
        m["uid"] for m in latest
        if m["message_id"] and not (
            m["message_id"].strip().startswith("<")
            and m["message_id"].strip().endswith(">")
            and "@" in m["message_id"]
        )
    ]
    seen: dict[str, str] = {}
    duplicates = []
    for m in latest:
        if m["message_id"] in seen:
            duplicates.append(m["message_id"])
        elif m["message_id"]:
            seen[m["message_id"]] = m["uid"]
    print(f"    present on {len(latest) - len(missing)}/{len(latest)} messages"
          f"   missing: {missing or 'none'}")
    print(f"    malformed (not <local@domain>): {malformed or 'none'}")
    print(f"    duplicated within the mailbox: {duplicates or 'none'}")


def _compare_sequence_numbers(snaps: list[dict[str, Any]]) -> None:
    latest = snaps[-1]
    same = latest["sequence_numbers"] == latest["uids"]
    print(f"\n  Sequence numbers vs UIDs in the latest session: "
          f"{'IDENTICAL (coincidence — see note)' if same else 'DIFFERENT'}")
    print(f"    seq: {latest['sequence_numbers']}")
    print(f"    uid: {latest['uids']}")
    if same:
        print("    NOTE: they coincide only because nothing has been expunged from this")
        print("    mailbox. An expunge renumbers sequence numbers and leaves UIDs alone,")
        print("    so relying on this coincidence is a latent bug, not a safe shortcut.")


def compare() -> None:
    snaps = _load_snapshots()
    if len(snaps) < 2:
        print(f"  only {len(snaps)} snapshot(s) — need at least 2 to compare.")
        return
    print(f"\n  Comparing {len(snaps)} sessions "
          f"({snaps[0]['taken_at']} .. {snaps[-1]['taken_at']})")
    _compare_uidvalidity(snaps)
    _compare_uids(snaps)
    _compare_message_ids(snaps)
    _compare_sequence_numbers(snaps)
    print("\n  Per-message detail (latest session):")
    for m in snaps[-1]["messages"]:
        print(f"    uid {m['uid']:>3}  {m['message_id'] or '<MISSING>'}")
        print(f"            {m['subject']}")


def main() -> None:
    load_dotenv(HERE / ".env")
    parser = argparse.ArgumentParser(description="UIDVALIDITY/UID/Message-ID stability test.")
    parser.add_argument("--sessions", type=int, default=3, help="fresh sessions to take")
    parser.add_argument("--gap", type=int, default=20, help="seconds between sessions")
    parser.add_argument("--compare-only", action="store_true", help="compare existing snapshots")
    args = parser.parse_args()

    if not args.compare_only:
        for i in range(args.sessions):
            print(f"\n  --- session {i + 1} of {args.sessions} (new connection) ---")
            take_snapshot(f"session{i + 1}")
            if i < args.sessions - 1:
                time.sleep(args.gap)
    compare()
    print()


if __name__ == "__main__":
    main()
