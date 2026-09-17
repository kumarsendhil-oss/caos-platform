"""
Shared helper for P0-06 scripts: persists every real API call's request and
response to runs/, so findings trace back to actual evidence rather than
scrollback. Mirrors whatever p0-02-tally does for its own verification runs
(context.md references "live-verification runs captured" for that spike).

Deliberately logs only method/url/params/json body and the response — never
headers, so an Authorization token never ends up on disk in a run file.
"""
import json
import time
from pathlib import Path

RUNS_DIR = Path(__file__).parent / "runs"


# Response headers are safe to persist (they are Zoho's, not ours) and are the
# only place a rate-limit budget would surface — OQ-05 can't be answered without
# them, and the header *names* are exactly what's unknown, so this can't be an
# allowlist. Request headers remain unlogged entirely: that's where the
# Authorization bearer token lives.
_HEADER_DENYLIST = {"set-cookie", "authorization", "proxy-authorization"}


def _safe_headers(headers) -> dict | None:
    if headers is None:
        return None
    return {k: v for k, v in headers.items() if k.lower() not in _HEADER_DENYLIST}


def log_call(label: str, method: str, url: str, params=None, body=None,
             status_code=None, response_body=None, response_headers=None) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S")
    # microsecond suffix so multiple calls in the same second don't collide
    fname = RUNS_DIR / f"{ts}_{int(time.time() * 1000) % 1000:03d}_{label}.json"
    record = {
        "timestamp_utc": ts,
        "label": label,
        "request": {"method": method, "url": url, "params": params, "body": body},
        "response": {
            "status_code": status_code,
            "headers": _safe_headers(response_headers),
            "body": response_body,
        },
    }
    fname.write_text(json.dumps(record, indent=2, default=str))
    return fname
