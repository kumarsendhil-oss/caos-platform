"""
Run logger for the P0-07 Dropbox spike.

**Copied from `spikes/p0-06-zoho/run_logger.py`, not imported.** The module is
already generic — `RUNS_DIR` resolves relative to `__file__`, and the header
denylist is not Zoho-specific — so the copy is byte-identical apart from this
docstring and the `log_webhook()` addition below. Cross-importing from another
spike's directory would couple two independent spikes' evidence trails, and
promoting it to `spikes/_run_logger.py` means editing P0-06's committed
scripts, which is a refactor rather than scaffolding. The duplication is
tracked as `PENDING:021`, following the precedent of `PENDING:011` →
`spikes/_args.py`.

What this spike needs that P0-06 did not: Dropbox is the first integration
that calls **us**. `log_call()` records outbound requests; `log_webhook()`
records inbound notifications, because for P0-07 the inbound side *is* the
finding — ADR 0003's whole claim is about what Dropbox sends and how fast we
must answer.

Header handling, and the reason it differs by direction:

  * Outbound request headers are never logged — that is where our
    `Authorization: Bearer` token lives.
  * Outbound response headers are logged; they are Dropbox's, not ours.
  * Inbound request headers ARE logged, minus the denylist, because
    `X-Dropbox-Signature` is the thing P0-07 has to verify and you cannot
    check a signature scheme you never recorded. That signature is an
    HMAC-SHA256 of the request body keyed by the app secret: it is derived
    from the secret, not the secret itself, so recording it does not leak
    the key. **The app secret itself must never be written here.**
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).parent / "runs"


# Response headers are safe to persist (they are the vendor's, not ours).
# Request headers on OUTBOUND calls remain unlogged entirely: that is where the
# Authorization bearer token lives.
_HEADER_DENYLIST = {"set-cookie", "authorization", "proxy-authorization"}


def _safe_headers(headers: Any) -> dict | None:
    if headers is None:
        return None
    return {k: v for k, v in headers.items() if k.lower() not in _HEADER_DENYLIST}


def _write(record: dict, label: str) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    # microsecond suffix so multiple calls in the same second don't collide
    fname = RUNS_DIR / f"{ts}_{int(time.time() * 1000) % 1000:03d}_{label}.json"
    fname.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return fname


def log_call(label: str, method: str, url: str, params: Any = None,
             body: Any = None, status_code: int | None = None,
             response_body: Any = None, response_headers: Any = None) -> Path:
    """Record one OUTBOUND call (us -> Dropbox)."""
    record = {
        "timestamp_utc": time.strftime("%Y%m%dT%H%M%S"),
        "direction": "outbound",
        "label": label,
        "request": {"method": method, "url": url, "params": params, "body": body},
        "response": {
            "status_code": status_code,
            "headers": _safe_headers(response_headers),
            "body": response_body,
        },
    }
    return _write(record, label)


def log_webhook(label: str, method: str, path: str, headers: Any = None,
                raw_body: str | None = None, signature_valid: bool | None = None,
                responded_status: int | None = None,
                elapsed_ms: float | None = None) -> Path:
    """Record one INBOUND notification (Dropbox -> us).

    `elapsed_ms` is the point of this function as much as the payload:
    ADR 0003 asserts a 10-second response window, and the only way to
    know whether the handler actually respects it is to measure every
    response rather than trust that acknowledging "feels fast".
    """
    record = {
        "timestamp_utc": time.strftime("%Y%m%dT%H%M%S"),
        "direction": "inbound",
        "label": label,
        "request": {
            "method": method,
            "path": path,
            # Inbound headers are recorded (minus denylist) because
            # X-Dropbox-Signature is itself under test. See module docstring.
            "headers": _safe_headers(headers),
            "raw_body": raw_body,
        },
        "verification": {"signature_valid": signature_valid},
        "response": {"status_code": responded_status, "elapsed_ms": elapsed_ms},
    }
    return _write(record, label)
