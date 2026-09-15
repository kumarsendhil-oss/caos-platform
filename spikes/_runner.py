"""
Shared helper for spike scripts.

Every spike call goes through run(), which captures the request and the
response to a timestamped folder under the spike's runs/ directory. The
point is that evidence is recorded automatically — a spike result that
only exists in someone's terminal scrollback isn't evidence.

Usage from a spike script:

    from _runner import run
    run("create-ledgers", payload, url="http://localhost:9000")

Produces:

    runs/2026-09-15T14-03-22-create-ledgers/
        request.xml       what was sent, byte for byte
        response.xml      what came back
        meta.json         url, status, timing, content-type, script
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _runs_dir(script_path: str) -> Path:
    d = Path(script_path).resolve().parent / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(
    name: str,
    payload: str,
    *,
    url: str = "http://localhost:9000",
    content_type: str = "text/xml;charset=utf-8",
    timeout: int = 30,
    script: str | None = None,
) -> str | None:
    """
    POST payload to url, capture both sides to a run folder, return the
    response body (or None if the call failed).

    Failures are captured too — a connection refused is a result worth
    keeping, not an error to swallow.
    """
    script_path = script or sys.argv[0]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    out = _runs_dir(script_path) / f"{stamp}-{name}"
    out.mkdir(parents=True, exist_ok=True)

    (out / "request.xml").write_text(payload, encoding="utf-8")

    meta: dict[str, object] = {
        "name": name,
        "url": url,
        "content_type": content_type,
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": Path(script_path).name,
        "request_bytes": len(payload.encode("utf-8")),
    }

    req = urllib.request.Request(
        url,
        data=payload.encode("utf-8"),
        headers={"Content-Type": content_type},
        method="POST",
    )

    body: str | None = None
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            body = raw.decode("utf-8", errors="replace")
            meta["status"] = resp.status
            meta["response_bytes"] = len(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = raw.decode("utf-8", errors="replace")
        meta["status"] = exc.code
        meta["error"] = f"HTTPError {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        meta["status"] = None
        meta["error"] = f"{type(exc).__name__}: {exc}"
        meta["hint"] = (
            "Is TallyPrime running with a company loaded, and port 9000 open "
            "(Exchange > Data Synchronization)? Check http://localhost:9000 "
            "in a browser."
        )
    finally:
        meta["elapsed_ms"] = round((time.monotonic() - started) * 1000)

    if body is not None:
        (out / "response.xml").write_text(body, encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    status = meta.get("status")
    print(f"[{name}] -> {out.relative_to(Path(script_path).resolve().parent)}")
    print(f"  status={status}  elapsed={meta['elapsed_ms']}ms")
    if "error" in meta:
        print(f"  ERROR: {meta['error']}")
        if "hint" in meta:
            print(f"  {meta['hint']}")
    if body:
        preview = body.strip()
        print(f"  response: {preview[:400]}{'...' if len(preview) > 400 else ''}")

    return body
