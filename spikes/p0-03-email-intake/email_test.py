"""P0-03 — shared-inbox intake over IMAP.

Tests the mechanics EI-01 to EI-03 (PRD §5.4) depend on: connect to a
shared inbox, find new messages, and pull sender / subject / attachment
metadata off each one.

**IMAP deliberately, not the Gmail API.** ADR 0009/0010 make each practice
its own deployment, so the email provider is per-deployment configuration.
Gmail's REST API (OAuth + Cloud Pub/Sub push) would give better latency and
a cleaner push model, and it would be the right answer for a Gmail-only
product — but it transfers to nothing. A practice on Exchange would need a
second connector written from scratch. IMAP is the protocol-level common
ground, so IMAP is the layer worth measuring. The cost of that choice
(polling rather than push) is itself one of the open questions.

Nothing here should ever reference Gmail specifically. If something does,
that is a finding, not a fix — see FINDINGS.md open question 4.

Dry by default, matching P0-06 and P0-07: the first thing anyone runs is safe.

    python email_test.py                 # dry run — prints intent, connects to nothing
    python email_test.py --verify-only   # config check, no network
    python email_test.py --poll          # connect, list recent messages
    python email_test.py --poll --limit 20
    python email_test.py --poll --unseen # only messages not yet marked read
    python email_test.py --poll --save-attachments
"""

from __future__ import annotations

import argparse
import email
import imaplib
import os
import time
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from run_logger import log_imap

HERE = Path(__file__).parent
ATTACHMENT_DIR = HERE / "attachments"

REQUIRED_VARS = ("IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_APP_PASSWORD")

# EI-03 classifies attachments by type. Kept as a plain mapping rather than
# anything cleverer: the spike's job is to report what actually arrives, and
# a too-smart classifier would hide the cases that need a Task.
_KIND_BY_EXTENSION = {
    ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".tif": "image", ".tiff": "image", ".bmp": "image", ".heic": "image",
    ".xls": "spreadsheet", ".xlsx": "spreadsheet", ".csv": "spreadsheet",
    ".doc": "document", ".docx": "document", ".rtf": "document", ".odt": "document",
    ".zip": "archive", ".rar": "archive", ".7z": "archive",
    ".eml": "email", ".msg": "email",
}


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"  missing {name} — copy .env.example to .env (see README.md)")
    return value


def _decode(raw: str | None) -> str:
    """RFC 2047 headers arrive base64/quoted-printable encoded."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw.strip()


def _classify(filename: str, content_type: str) -> str:
    """EI-03's attachment type. Extension first, MIME as the fallback."""
    suffix = Path(filename).suffix.lower()
    if suffix in _KIND_BY_EXTENSION:
        return _KIND_BY_EXTENSION[suffix]
    major = (content_type or "").split("/")[0].lower()
    if major == "image":
        return "image"
    if content_type == "application/pdf":
        return "pdf"
    return "other"


def _attachments(msg: Message, save: bool) -> list[dict[str, Any]]:
    """Attachment metadata; content only written when explicitly asked for."""
    found: list[dict[str, Any]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disposition = (part.get("Content-Disposition") or "").lower()
        filename = _decode(part.get_filename())
        # Inline images (signatures, logos) are not attachments in EI-03's
        # sense but do arrive as parts — recorded, flagged, not conflated.
        if not filename and "attachment" not in disposition:
            continue
        payload = part.get_payload(decode=True) or b""
        record: dict[str, Any] = {
            "filename": filename or "<unnamed>",
            "content_type": part.get_content_type(),
            "kind": _classify(filename, part.get_content_type()),
            "size_bytes": len(payload),
            "inline": "inline" in disposition,
        }
        if save and filename:
            ATTACHMENT_DIR.mkdir(exist_ok=True)
            target = ATTACHMENT_DIR / filename
            target.write_bytes(payload)
            record["saved_to"] = str(target.relative_to(HERE))
        found.append(record)
    return found


def _sender_fields(msg: Message) -> dict[str, Any]:
    """Sender parsing for EI-02's mapping — with the awkward cases kept.

    Reply-chains and forwards are where a naive From: read goes wrong: the
    person who forwarded a client's invoice is not the client. Reply-To,
    Return-Path and the forwarding markers are recorded so FINDINGS can say
    what actually appears rather than what ought to.
    """
    display, addr = parseaddr(_decode(msg.get("From")))
    _, reply_to = parseaddr(_decode(msg.get("Reply-To")))
    _, return_path = parseaddr(_decode(msg.get("Return-Path")))
    subject = _decode(msg.get("Subject"))
    return {
        "from_display_name": display,
        "from_address": addr.lower(),
        "from_domain": addr.rsplit("@", 1)[-1].lower() if "@" in addr else None,
        "reply_to": reply_to.lower() or None,
        "return_path": return_path.lower() or None,
        "subject": subject,
        "looks_like_reply": subject.lower().startswith(("re:", "aw:", "sv:")),
        "looks_like_forward": subject.lower().startswith(("fw:", "fwd:")),
        "in_reply_to": msg.get("In-Reply-To"),
        "has_references": bool(msg.get("References")),
    }


def _summarise(msg: Message, uid: str, save: bool) -> dict[str, Any]:
    """One message, reduced to what EI-01 to EI-03 actually need."""
    try:
        received = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    except (TypeError, ValueError):
        received = None
    attachments = _attachments(msg, save)
    return {
        "uid": uid,
        "message_id": msg.get("Message-ID"),
        "date": received.isoformat() if received else None,
        **_sender_fields(msg),
        "attachment_count": len(attachments),
        "attachments": attachments,
    }


def _connect(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    """Connect and authenticate, logging both steps separately.

    Separately on purpose: a TLS failure and an auth rejection are different
    problems with different fixes, and a combined 'could not connect' hides
    which one happened.
    """
    started = time.monotonic()
    client = imaplib.IMAP4_SSL(host, port)
    connect_ms = (time.monotonic() - started) * 1000
    log_imap("connect", "IMAP4_SSL", user, host, elapsed_ms=connect_ms, status="OK")
    print(f"  [connect] {host}:{port} in {connect_ms:.0f}ms")

    started = time.monotonic()
    try:
        client.login(user, password)
    except imaplib.IMAP4.error as exc:
        log_imap("login", "LOGIN", user, host, status="FAILED", error=str(exc),
                 elapsed_ms=(time.monotonic() - started) * 1000)
        raise SystemExit(
            f"  [login] FAILED: {exc}\n"
            "  An app-specific password is required (not the account password), "
            "and 2FA must be enabled first — see README.md."
        ) from exc
    login_ms = (time.monotonic() - started) * 1000
    log_imap("login", "LOGIN", user, host, status="OK", elapsed_ms=login_ms)
    print(f"  [login]   authenticated in {login_ms:.0f}ms")
    return client


def _search(client: imaplib.IMAP4_SSL, ctx: dict[str, str], unseen: bool) -> list[bytes]:
    """SELECT then SEARCH, timed — this pair is one poll cycle's fixed cost."""
    started = time.monotonic()
    status, data = client.select(ctx["mailbox"], readonly=True)
    select_ms = (time.monotonic() - started) * 1000
    total = int(data[0]) if status == "OK" and data and data[0] else 0
    log_imap("select", "SELECT", ctx["user"], ctx["host"], mailbox=ctx["mailbox"],
             status=status, result={"message_count": total}, elapsed_ms=select_ms)
    print(f"  [select]  {ctx['mailbox']}: {total} messages, {select_ms:.0f}ms")

    # UID SEARCH, not SEARCH. Plain SEARCH returns message *sequence numbers*,
    # which are positional and renumber whenever a message is expunged — so
    # they are actively wrong as a stable identifier. This originally used
    # SEARCH and labelled the results "uid"; corrected after uid_stability.py
    # made the distinction concrete. See FINDINGS.md finding #8.
    criterion = "(UNSEEN)" if unseen else "ALL"
    started = time.monotonic()
    status, data = client.uid("SEARCH", None, criterion)
    search_ms = (time.monotonic() - started) * 1000
    uids = data[0].split() if status == "OK" and data and data[0] else []
    log_imap("search", "UID SEARCH", ctx["user"], ctx["host"], mailbox=ctx["mailbox"],
             args={"criterion": criterion}, status=status,
             result={"matched": len(uids)}, elapsed_ms=search_ms)
    print(f"  [search]  {criterion}: {len(uids)} matched, {search_ms:.0f}ms")
    return uids


def _fetch_messages(
    client: imaplib.IMAP4_SSL,
    ctx: dict[str, str],
    uids: list[bytes],
    save: bool,
) -> tuple[list[dict[str, Any]], float]:
    """FETCH each message and summarise it. Returns summaries and total ms.

    readonly=True on SELECT means fetching does not mark anything \\Seen —
    which matters, because a monitoring agent that marks mail read just by
    looking at it changes what a human sees in the shared inbox.
    """
    summaries: list[dict[str, Any]] = []
    total_ms = 0.0
    for raw_uid in uids:
        uid = raw_uid.decode()
        started = time.monotonic()
        status, data = client.uid("FETCH", raw_uid, "(RFC822)")
        fetch_ms = (time.monotonic() - started) * 1000
        total_ms += fetch_ms
        if status != "OK" or not data or not isinstance(data[0], tuple):
            log_imap("fetch", "UID FETCH", ctx["user"], ctx["host"], mailbox=ctx["mailbox"],
                     args={"uid": uid}, status=status, error="no payload",
                     elapsed_ms=fetch_ms)
            print(f"   ! uid {uid}: fetch returned no payload")
            continue
        summary = _summarise(email.message_from_bytes(data[0][1]), uid, save)
        summary["fetch_ms"] = round(fetch_ms, 1)
        summaries.append(summary)
        log_imap("fetch", "UID FETCH", ctx["user"], ctx["host"], mailbox=ctx["mailbox"],
                 args={"uid": uid}, status=status, result=summary, elapsed_ms=fetch_ms)
    return summaries, total_ms


def _print_summary(summaries: list[dict[str, Any]]) -> None:
    """Human-readable digest. The evidence is in runs/; this is for reading."""
    print(f"\n  {len(summaries)} message(s)")
    for s in summaries:
        flags = []
        if s["looks_like_reply"]:
            flags.append("reply")
        if s["looks_like_forward"]:
            flags.append("forward")
        if s["reply_to"] and s["reply_to"] != s["from_address"]:
            flags.append("reply-to differs")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(f"\n   uid {s['uid']}  {s['date'] or '<no date>'}{suffix}")
        print(f"     from:    {s['from_display_name'] or '<none>'} <{s['from_address']}>")
        print(f"     domain:  {s['from_domain']}")
        print(f"     subject: {s['subject'][:70] or '<none>'}")
        if s["attachments"]:
            for att in s["attachments"]:
                inline = " (inline)" if att["inline"] else ""
                print(f"     attach:  {att['filename']}  {att['kind']}  "
                      f"{att['content_type']}  {att['size_bytes']}B{inline}")
        else:
            print("     attach:  none")


def _print_timing(summaries: list[dict[str, Any]], fetch_ms: float, cycle_ms: float) -> None:
    """EI-01 has to pick a polling interval; this is the input to that."""
    print(f"\n  Poll cycle: {cycle_ms:.0f}ms total")
    print(f"    fetch:    {fetch_ms:.0f}ms across {len(summaries)} message(s)")
    if summaries:
        per = fetch_ms / len(summaries)
        print(f"    per msg:  {per:.0f}ms")
        print(f"    implied:  ~{per * 100 / 1000:.1f}s to fetch 100 messages")
    print("    NOTE: connect+login is per-cycle cost only if the agent reconnects "
          "each poll; a long-lived connection pays it once.")


def verify_only() -> None:
    """Config check, no network — same convention as P0-06/P0-07."""
    env_path = HERE / ".env"
    print(f"  .env present: {env_path.exists()}")
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v, "").strip()]
    print(f"  missing vars: {', '.join(missing) if missing else 'none'}")
    host = os.environ.get("IMAP_HOST", "")
    print(f"  host: {host or '<unset>'}   mailbox: "
          f"{os.environ.get('IMAP_MAILBOX', 'INBOX')}")
    if host and "gmail" in host:
        print("  note: Gmail host configured — the code path is generic IMAP; "
              "only this value is provider-specific (open question 4).")


def poll(limit: int, unseen: bool, save: bool) -> None:
    """One poll cycle against the real mailbox."""
    ctx = {
        "host": _require("IMAP_HOST"),
        "user": _require("IMAP_USER"),
        "mailbox": os.environ.get("IMAP_MAILBOX", "INBOX").strip() or "INBOX",
    }
    # Google displays app passwords in four-character groups; users paste
    # them either way, and IMAP rejects the spaced form with a bare
    # "Invalid credentials" that looks identical to a wrong password.
    password = _require("IMAP_APP_PASSWORD").replace(" ", "")
    port = int(os.environ.get("IMAP_PORT", "993"))

    cycle_started = time.monotonic()
    client = _connect(ctx["host"], port, ctx["user"], password)
    try:
        uids = _search(client, ctx, unseen)
        selected = uids[-limit:] if limit and len(uids) > limit else uids
        if len(selected) < len(uids):
            print(f"  (showing the {len(selected)} most recent of {len(uids)})")
        summaries, fetch_ms = _fetch_messages(client, ctx, selected, save)
    finally:
        client.logout()
    cycle_ms = (time.monotonic() - cycle_started) * 1000

    _print_summary(summaries)
    _print_timing(summaries, fetch_ms, cycle_ms)
    print(f"\n  evidence written to runs/ ({len(summaries) + 4} records)")


def main() -> None:
    load_dotenv(HERE / ".env")
    parser = argparse.ArgumentParser(description="P0-03 IMAP shared-inbox spike.")
    parser.add_argument("--verify-only", action="store_true", help="config check, no network")
    parser.add_argument("--poll", action="store_true", help="connect and list messages")
    parser.add_argument("--limit", type=int, default=10, help="most recent N messages")
    parser.add_argument("--unseen", action="store_true", help="only unread messages")
    parser.add_argument("--save-attachments", action="store_true",
                        help="write attachment content to attachments/ (gitignored)")
    args = parser.parse_args()

    if args.verify_only:
        verify_only()
        return
    if args.poll:
        poll(args.limit, args.unseen, args.save_attachments)
        return
    print("  P0-03 — shared-inbox intake over IMAP (EI-01 to EI-03).")
    print(f"  Would connect to {os.environ.get('IMAP_HOST', '<unset>')} as "
          f"{os.environ.get('IMAP_USER', '<unset>')}.")
    print("  (dry run — nothing sent. Pass --verify-only or --poll.)")


if __name__ == "__main__":
    main()
