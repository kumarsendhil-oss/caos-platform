"""
P0-07 — Dropbox webhook live verification.

Verifies the three things ADR 0003 asserts from documentation alone:

  1. **The cursor pattern.** A webhook fires with no file detail; the app then
     calls `/files/list_folder/continue` with a stored cursor to learn *what*
     changed. ADR 0003's entire intake design rests on this.
  2. **The 10-second response window.** Measured on every inbound request
     rather than assumed, since the design's "acknowledge, then hand off to a
     queue" rule exists to respect it.
  3. **"App folder" scope behaviour.** ADR 0003 deliberately chose App folder
     over Full Dropbox; what the cursor actually reports under that scope —
     and whether paths are app-relative — is the part worth seeing rather
     than inferring.

Nothing here is a design proposal. It is the smallest thing that can make
those three claims either hold or fail, against a real app.

Usage (PowerShell), and read README.md first — this spike needs a publicly
reachable URL, which the other spikes did not:

    python webhook_test.py --verify-only     # no network; checks config
    python webhook_test.py --cursor          # fetch + store a starting cursor
    python webhook_test.py --serve           # run the webhook receiver

Dry by default: with no flags it prints what it *would* do and exits 0,
matching the P0-06 scripts' convention so the first thing anyone runs is
safe.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

from run_logger import log_call, log_webhook

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

API = "https://api.dropboxapi.com/2"
CURSOR_FILE = HERE / "cursor.json"

# ADR 0003's stated constraint. Recorded as a constant so the receiver can
# warn when it gets anywhere near it, rather than only failing in production.
RESPONSE_WINDOW_SECONDS = 10


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"error: {name} is not set. Copy .env.example to .env — see README.md")
    return value


def _post(label: str, endpoint: str, body: dict) -> dict:
    """One Dropbox RPC call, logged. Never logs our request headers."""
    token = _require("DROPBOX_ACCESS_TOKEN")
    url = f"{API}{endpoint}"
    started = time.time()
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    try:
        parsed = resp.json()
    except ValueError:
        parsed = {"_raw": resp.text}
    log_call(label, "POST", url, body=body, status_code=resp.status_code,
             response_body=parsed, response_headers=resp.headers)
    print(f"  [{label}] {resp.status_code} in {int((time.time() - started) * 1000)}ms")
    return parsed


def fetch_cursor() -> str:
    """Claim 1, first half — get a starting cursor for the app folder.

    `get_latest_cursor` returns a cursor without the file list, which is
    exactly what a webhook-driven app wants at startup: a marker to diff
    *from*, not a full listing to process.
    """
    body = {
        "path": "",  # app-folder root; under App folder scope this is the app's own tree
        "recursive": True,
        "include_deleted": False,
    }
    result = _post("get_latest_cursor", "/files/list_folder/get_latest_cursor", body)
    cursor = result.get("cursor")
    if not cursor:
        sys.exit(f"no cursor in response — see runs/. Response: {result}")
    CURSOR_FILE.write_text(json.dumps({"cursor": cursor}, indent=2), encoding="utf-8")
    print(f"  cursor stored in {CURSOR_FILE.name} ({len(cursor)} chars)")
    return cursor


def load_cursor() -> str | None:
    if not CURSOR_FILE.is_file():
        return None
    return json.loads(CURSOR_FILE.read_text(encoding="utf-8")).get("cursor")


def continue_from_cursor(cursor: str) -> dict:
    """Claim 1, second half — the call ADR 0003 names explicitly.

    Stores the returned cursor back, because the pattern is only correct if
    each notification advances the marker. A spike that re-uses the same
    cursor would "work" while proving nothing about the real loop.
    """
    result = _post("list_folder_continue", "/files/list_folder/continue",
                   {"cursor": cursor})
    entries = result.get("entries", [])
    print(f"  {len(entries)} entrie(s); has_more={result.get('has_more')}")
    for entry in entries:
        print(f"    {entry.get('.tag'):9} {entry.get('path_display')}")
    if result.get("cursor"):
        CURSOR_FILE.write_text(json.dumps({"cursor": result["cursor"]}, indent=2),
                               encoding="utf-8")
    return result


def _signature_ok(raw: bytes, provided: str | None) -> bool:
    """Dropbox signs each notification: HMAC-SHA256(body, app_secret).

    Verified here rather than skipped, because an intake endpoint that
    accepts unsigned POSTs is an open door into the practice's document
    pipeline. Security Standard §2 — validation is server-side, always.
    """
    if not provided:
        return False
    secret = _require("DROPBOX_APP_SECRET").encode()
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


class Handler(BaseHTTPRequestHandler):
    """Minimal receiver. Deliberately NOT how the platform should do this."""

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming
        """Dropbox's one-time endpoint verification: echo back `challenge`."""
        started = time.time()
        params = parse_qs(urlparse(self.path).query)
        challenge = (params.get("challenge") or [""])[0]
        body = challenge.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        # Dropbox's documented anti-abuse headers for the verification echo.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
        elapsed = (time.time() - started) * 1000
        log_webhook("webhook_verify", "GET", self.path, headers=dict(self.headers),
                    raw_body=challenge, responded_status=200, elapsed_ms=elapsed)
        print(f"  [verify] echoed challenge in {elapsed:.1f}ms")

    def do_POST(self) -> None:  # noqa: N802
        """A change notification. Acknowledge FIRST, then look at it.

        The ordering is the point of the experiment: ADR 0003 says respond
        inside 10 seconds and hand off real work. Here the acknowledgement
        is sent before any API call, and the elapsed time is recorded so the
        margin is a measurement rather than a belief.
        """
        started = time.time()
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        valid = _signature_ok(raw, self.headers.get("X-Dropbox-Signature"))

        self.send_response(200)
        self.end_headers()
        elapsed = (time.time() - started) * 1000

        log_webhook("webhook_notify", "POST", self.path, headers=dict(self.headers),
                    raw_body=raw.decode("utf-8", "replace"), signature_valid=valid,
                    responded_status=200, elapsed_ms=elapsed)
        print(f"  [notify] acknowledged in {elapsed:.1f}ms  signature_valid={valid}")
        if elapsed > RESPONSE_WINDOW_SECONDS * 1000 * 0.1:
            print(f"    NOTE: >10% of the {RESPONSE_WINDOW_SECONDS}s window used "
                  "on acknowledgement alone — worth a finding.")

        if not valid:
            print("    REFUSING to act on an unsigned/mis-signed notification.")
            return
        cursor = load_cursor()
        if not cursor:
            print("    no stored cursor — run --cursor first. Nothing to continue from.")
            return
        continue_from_cursor(cursor)

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence the default stderr access log; run_logger is the record."""


def serve(port: int) -> None:
    print(f"\n  Listening on 0.0.0.0:{port} — point your Dropbox app's webhook URI here.")
    print("  This must be reachable from the public internet (see README.md).")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()  # noqa: S104


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cursor", action="store_true",
                        help="fetch and store a starting cursor")
    parser.add_argument("--serve", action="store_true", help="run the webhook receiver")
    parser.add_argument("--verify-only", action="store_true",
                        help="check configuration; send nothing")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.verify_only:
        missing = [n for n in ("DROPBOX_ACCESS_TOKEN", "DROPBOX_APP_SECRET")
                   if not os.environ.get(n)]
        print(f"  .env present: {(HERE / '.env').is_file()}")
        print(f"  missing vars: {missing or 'none'}")
        print(f"  stored cursor: {'yes' if load_cursor() else 'no'}")
        return
    if args.cursor:
        fetch_cursor()
        return
    if args.serve:
        serve(args.port)
        return

    print(__doc__)
    print("  (dry run — nothing sent. Pass --cursor, --serve or --verify-only.)")


if __name__ == "__main__":
    main()
