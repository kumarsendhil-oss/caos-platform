"""Download specific messages' attachments to a directory.

A thin extension of `email_test.py` — it reuses that module's connection,
parsing and attachment handling rather than reimplementing them, so there
is exactly one place where IMAP behaviour lives. The only thing added is
"fetch these UIDs, write their attachments there".

Written for the P0-05 cross-spike smoke test (running real, messy
documents through the OCR pipeline), but deliberately not specific to it:
UIDs and destination are arguments.

Two properties inherited from `email_test.py` and relied on here:
`SELECT` is readonly, so pulling attachments does not mark mail seen; and
the app password never reaches the run log.

    python fetch_attachments.py --uids 4 5 8 --out ../p0-05-paddleocr/real-samples
    python fetch_attachments.py --uids 4 --out ./attachments --kinds pdf image
"""

from __future__ import annotations

import argparse
import email
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from email_test import HERE, _attachments, _connect, _require, _sender_fields
from run_logger import log_imap


def _save_one(
    client: object,
    ctx: dict[str, str],
    uid: str,
    out_dir: Path,
    kinds: set[str] | None,
) -> list[dict[str, object]]:
    """Fetch one message and write its qualifying attachments to out_dir."""
    started = time.monotonic()
    status, data = client.fetch(uid.encode(), "(RFC822)")  # type: ignore[attr-defined]
    elapsed = (time.monotonic() - started) * 1000
    if status != "OK" or not data or not isinstance(data[0], tuple):
        log_imap("fetch_attachment", "FETCH", ctx["user"], ctx["host"],
                 mailbox=ctx["mailbox"], args={"uid": uid}, status=status,
                 error="no payload", elapsed_ms=elapsed)
        print(f"   ! uid {uid}: fetch returned no payload")
        return []

    msg = email.message_from_bytes(data[0][1])
    sender = _sender_fields(msg)
    # save=False: take the metadata from the shared helper, then write the
    # bytes here, so the destination is this tool's decision rather than
    # email_test's fixed attachments/ directory.
    written: list[dict[str, object]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        meta = next(
            (a for a in _attachments(msg, save=False)
             if a["filename"].endswith(Path(filename).suffix)
             and a["size_bytes"] == len(part.get_payload(decode=True) or b"")),
            None,
        )
        kind = meta["kind"] if meta else "other"
        if kinds and kind not in kinds:
            print(f"     skip {filename} ({kind}, not in --kinds)")
            continue
        payload = part.get_payload(decode=True) or b""
        target = out_dir / f"uid{uid}_{Path(filename).name}"
        target.write_bytes(payload)
        written.append({"uid": uid, "filename": target.name, "kind": kind,
                        "size_bytes": len(payload)})
        print(f"     wrote {target.name}  {kind}  {len(payload)}B")

    log_imap("fetch_attachment", "FETCH", ctx["user"], ctx["host"],
             mailbox=ctx["mailbox"], args={"uid": uid}, status=status,
             result={"subject": sender["subject"],
                     "from_address": sender["from_address"],
                     "written": written},
             elapsed_ms=elapsed)
    return written


def main() -> None:
    load_dotenv(HERE / ".env")
    parser = argparse.ArgumentParser(description="Download attachments for given UIDs.")
    parser.add_argument("--uids", nargs="+", required=True, help="IMAP UIDs")
    parser.add_argument("--out", type=Path, required=True, help="destination directory")
    parser.add_argument("--kinds", nargs="*", default=None,
                        help="only these kinds (e.g. pdf image); default all")
    args = parser.parse_args()

    ctx = {
        "host": _require("IMAP_HOST"),
        "user": _require("IMAP_USER"),
        "mailbox": os.environ.get("IMAP_MAILBOX", "INBOX").strip() or "INBOX",
    }
    password = _require("IMAP_APP_PASSWORD").replace(" ", "")
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    kinds = set(args.kinds) if args.kinds else None

    client = _connect(ctx["host"], int(os.environ.get("IMAP_PORT", "993")),
                      ctx["user"], password)
    total: list[dict[str, object]] = []
    try:
        client.select(ctx["mailbox"], readonly=True)
        for uid in args.uids:
            print(f"   uid {uid}:")
            total.extend(_save_one(client, ctx, uid, out_dir, kinds))
    finally:
        client.logout()
    print(f"\n  {len(total)} attachment(s) written to {out_dir}")


if __name__ == "__main__":
    main()
