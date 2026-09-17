"""
P0-06 task 3 — Dev Readiness Checklist item OQ-05: what is Zoho Books'
*actual*, currently-enforced rate limit for this org and plan tier?

The checklist says "confirm against live docs". This spike has twice found
live behaviour diverging from Zoho's own documentation (FINDINGS.md #6, and
the inter-state tax rejection), so docs alone are not an acceptable answer
here either — the only trustworthy result is a limit we actually hit.

Method: burst read-only `GET /organizations` calls (the cheapest endpoint
that still counts against the quota — no writes, no state change) as fast as
the network allows, recording every status code, the wall-clock offset, and
every response header, until either a 429 arrives or --max is reached.

Logging deviates *slightly* from the one-file-per-call convention, on
purpose: a 150-request burst would bury runs/ under 150 near-identical
files. Instead the first response, every non-200, and a full per-request
summary (status, elapsed, headers) are persisted — so nothing that carries
information is lost, and the aggregate remains reproducible evidence.

Usage:
    python rate_limit_probe.py              # dry run, describes the plan
    python rate_limit_probe.py --run        # fire the burst
    python rate_limit_probe.py --run --max 300
"""
from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from run_logger import log_call
from zoho_client import API_BASE, ORG_ID, TIMEOUT, get_access_token

# Header names that would carry a quota budget if Zoho sends one at all.
# Substring match, because the actual names are exactly what is unknown.
_INTERESTING = ("rate", "limit", "remaining", "reset", "retry", "quota", "throttl")


def interesting_headers(headers) -> dict:
    return {k: v for k, v in headers.items()
            if any(token in k.lower() for token in _INTERESTING)}


def burst(token: str, max_requests: int) -> list[dict]:
    """Fire reads until a non-200 shows up or max_requests is reached."""
    url = f"{API_BASE}/organizations"
    params = {"organization_id": ORG_ID}
    hdrs = {"Authorization": f"Zoho-oauthtoken {token}"}
    session = requests.Session()
    records: list[dict] = []
    started = time.monotonic()

    for i in range(1, max_requests + 1):
        sent_at = time.monotonic() - started
        resp = session.get(url, headers=hdrs, params=params, timeout=TIMEOUT)
        record = {
            "n": i,
            "sent_at_s": round(sent_at, 3),
            "elapsed_s": round(time.monotonic() - started, 3),
            "status_code": resp.status_code,
            "interesting_headers": interesting_headers(resp.headers),
            "all_header_names": sorted(resp.headers.keys()),
        }
        # Zoho can return HTTP 200 with an error body (FINDINGS.md #1) — a
        # quota rejection could plausibly arrive that way too, so check both.
        try:
            body = resp.json()
        except ValueError:
            body = {"_non_json_body": resp.text[:500]}
        record["body_code"] = body.get("code") if isinstance(body, dict) else None

        if i == 1 or resp.status_code != 200 or record["body_code"] not in (0, None):
            log_call(f"rate_probe_{i:03d}_http{resp.status_code}", "GET", url,
                     params=params, status_code=resp.status_code,
                     response_body=body, response_headers=resp.headers)

        records.append(record)
        print(f"  #{i:3d}  HTTP {resp.status_code}  body_code={record['body_code']}  "
              f"t={record['elapsed_s']}s", flush=True)

        if resp.status_code != 200 or record["body_code"] not in (0, None):
            print(f"\nStopped at request {i}: HTTP {resp.status_code}, "
                  f"body code {record['body_code']}")
            print("Response body:", body)
            print("Headers on the rejection:", dict(resp.headers))
            break

    return records


def concurrent_burst(token: str, max_requests: int, workers: int) -> list[dict]:
    """
    Same probe, fired from a thread pool.

    Serial requests topped out around 2.7-4 req/s (~165-250/min) purely on
    round-trip latency, which was not enough to trip anything. If Zoho
    enforces a per-minute ceiling at all, reaching it needs concurrency
    rather than more total requests.
    """
    url = f"{API_BASE}/organizations"
    params = {"organization_id": ORG_ID}
    hdrs = {"Authorization": f"Zoho-oauthtoken {token}"}
    started = time.monotonic()
    stop = threading.Event()
    records: list[dict] = []
    lock = threading.Lock()

    def one(n: int) -> None:
        if stop.is_set():
            return
        session = _LOCAL.__dict__.setdefault("session", requests.Session())
        resp = session.get(url, headers=hdrs, params=params, timeout=TIMEOUT)
        try:
            body = resp.json()
        except ValueError:
            body = {"_non_json_body": resp.text[:500]}
        body_code = body.get("code") if isinstance(body, dict) else None
        record = {
            "n": n,
            "sent_at_s": None,
            "elapsed_s": round(time.monotonic() - started, 3),
            "status_code": resp.status_code,
            "interesting_headers": interesting_headers(resp.headers),
            "all_header_names": sorted(resp.headers.keys()),
            "body_code": body_code,
        }
        with lock:
            records.append(record)
        if resp.status_code != 200 or body_code not in (0, None):
            stop.set()
            log_call(f"rate_probe_conc_{n:03d}_http{resp.status_code}", "GET", url,
                     params=params, status_code=resp.status_code,
                     response_body=body, response_headers=resp.headers)
            print(f"\n!! REJECTION at request {n}: HTTP {resp.status_code}, "
                  f"body code {body_code}")
            print("   body:", body)
            print("   headers:", dict(resp.headers))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, range(1, max_requests + 1)))

    records.sort(key=lambda r: r["elapsed_s"])
    duration = records[-1]["elapsed_s"] if records else 0
    print(f"  {len(records)} requests in {duration}s "
          f"({round(len(records) / duration, 1) if duration else '-'} req/s, "
          f"{round(len(records) / duration * 60) if duration else '-'} req/min)")
    return records


_LOCAL = threading.local()


def summarise(records: list[dict]) -> None:
    total = len(records)
    duration = records[-1]["elapsed_s"] if records else 0
    ok = sum(1 for r in records if r["status_code"] == 200)
    rejected = [r for r in records if r["status_code"] != 200]

    print("\n=== rate-limit probe summary ===")
    print(f"  requests sent     : {total}")
    print(f"  wall clock        : {duration}s  "
          f"({round(total / duration, 1) if duration else '-'} req/s)")
    print(f"  HTTP 200          : {ok}")
    print(f"  non-200           : {len(rejected)}")
    if rejected:
        first = rejected[0]
        print(f"  first rejection at: request #{first['n']} ({first['elapsed_s']}s in)")
        print(f"  status / body code: {first['status_code']} / {first['body_code']}")
        print(f"  headers of note   : {first['interesting_headers']}")
    else:
        print("  NO rejection observed within this burst.")

    seen = sorted({k for r in records for k in r["interesting_headers"]})
    print(f"  quota-ish headers seen across the burst: {seen or 'NONE'}")
    if records:
        print(f"  all header names on request #1: {records[0]['all_header_names']}")

    path = log_call("rate_probe_summary", "GET", f"{API_BASE}/organizations",
                    params={"organization_id": ORG_ID},
                    status_code=None,
                    response_body={"records": records,
                                   "requests": total, "duration_s": duration,
                                   "http_200": ok, "non_200": len(rejected)})
    print(f"  full per-request record written to {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="actually fire the burst")
    parser.add_argument("--max", type=int, default=150,
                        help="hard cap on requests (default 150)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="parallel workers (1 = the original serial burst)")
    args = parser.parse_args()

    if not args.run:
        print(f"Dry run — would fire up to {args.max} read-only GET /organizations "
              "calls as fast as possible, stopping at the first non-200, and record "
              "every response header. No writes.")
        return

    print(f"Bursting up to {args.max} read-only calls...\n")
    token = get_access_token()
    records = (burst(token, args.max) if args.concurrency == 1
               else concurrent_burst(token, args.max, args.concurrency))
    summarise(records)


if __name__ == "__main__":
    main()
