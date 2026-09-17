"""Persist every real IMAP interaction to runs/, so findings cite evidence.

**Copied and adapted** from `spikes/p0-06-zoho/run_logger.py`, not imported —
same judgement call already made for P0-07, and tracked as the same
duplication (`PENDING:021`). The reason to copy rather than import is
stronger here than it was there: the P0-06 original is shaped around HTTP.
Its signature is `(label, method, url, params, body, status_code,
response_body, response_headers)` and an IMAP exchange has none of those —
no URL, no status code, no response headers. Forcing IMAP through that
signature would mean six fields permanently `None`, which makes every run
file misleading about what was actually observed.

What carries over unchanged is the *discipline*, which is the part that
matters: one JSON file per real interaction, and **credentials never
written to disk**. For P0-06 that meant omitting request headers, where the
bearer token lived. Here it means the app password is never passed to this
module at all — only the account address, which is not a secret.

Message bodies are deliberately NOT persisted. This spike needs sender,
subject, and attachment metadata (EI-01 to EI-03); the body text is not
needed to answer any open question, and the test account is meant to stay
free of anything worth protecting. Attachments are recorded by filename,
MIME type and size — never content.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).parent / "runs"


def log_imap(
    label: str,
    command: str,
    account: str,
    host: str,
    mailbox: str | None = None,
    args: dict[str, Any] | None = None,
    status: str | None = None,
    result: Any = None,
    elapsed_ms: float | None = None,
    error: str | None = None,
) -> Path:
    """Write one IMAP interaction to runs/.

    `elapsed_ms` is recorded on every call, not just where it is obviously
    interesting: EI-01 has to choose a polling interval, and that number
    can only come from measuring each command rather than timing the
    script as a whole.
    """
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    fname = RUNS_DIR / f"{ts}_{int(time.time() * 1000) % 1000:03d}_{label}.json"
    record = {
        "timestamp_utc": ts,
        "protocol": "IMAP4_SSL",
        "label": label,
        "request": {
            "command": command,
            # The account address is an identifier, not a credential. The app
            # password is never handed to this function.
            "account": account,
            "host": host,
            "mailbox": mailbox,
            "args": args,
        },
        "response": {
            "status": status,
            "result": result,
            "elapsed_ms": round(elapsed_ms, 2) if elapsed_ms is not None else None,
            "error": error,
        },
    }
    fname.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return fname
