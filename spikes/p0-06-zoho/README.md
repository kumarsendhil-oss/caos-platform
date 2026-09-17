# P0-06 — Zoho Books Sandbox Spike

## Setup

```bash
cp .env.example .env
# fill in ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET from the Self Client's
# Client Secret tab, and ZOHO_GRANT_CODE from its Generate Code tab
# (grant codes expire in minutes — fill this in right before running)

pip install requests python-dotenv
```

## Run order

1. `python get_tokens.py` — one-time, exchanges the grant code for
   tokens, saves them to `tokens.json` (gitignored).
2. `python refresh_and_test.py` — run this anytime after; it refreshes
   the access token and does a couple of read calls to confirm
   connectivity.

Write-side probes (each takes `--send`/`--run`; without it they dry-run
and make no writes):

3. `python post_bill.py --send` — reverse-charge Bill (FINDINGS.md #5-#7).
4. `python forward_charge_test.py --send [--dup-variants]` — forward-charge
   Bill, intra- and inter-state, plus the BK-08 duplicate-guard probe
   (#8, #9, #10).
5. `python post_journal.py --send` — Journal posting and its differences
   from Bills (#12).
6. `python rate_limit_probe.py --run --max N [--concurrency N]` — bursts
   read-only calls to find the rate limit (#11). **Tripping it blocks the
   whole org for an hour** (`Retry-After: 3600`), so don't run this
   casually or before other spike work.

All of them share `zoho_client.py` for the request path and token refresh,
so every call lands in `runs/` the same way.

## Notes

- Data center is **India** (`ZOHO_DC=in`) — confirmed from the org's
  "Edition: India" label. All URLs (console, token endpoint, API base)
  must match this DC.
- `tokens.json` and `.env` both hold live credentials — add both to
  `.gitignore` before this folder goes anywhere near a commit.
- `runs/` holds the raw request/response for every real API call made by
  `post_bill.py`, one timestamped JSON file per call — never headers or
  tokens, safe to commit alongside FINDINGS.md as evidence.
- Log anything surprising in `FINDINGS.md`, same pattern as
  `p0-02-tally/FINDINGS.md`.
