# P0-07 — Dropbox Webhook Live Verification

**Status:** run live on 2026-09-17 against app ID `8506691` — see `FINDINGS.md`.

Verifies the three claims ADR 0003 makes from Dropbox's documentation alone. ADR 0003 is **Accepted** and stays Accepted — this spike is not a challenge to it, it is the live check its Context section never got.

## Why this spike exists

ADR 0003's Context says the webhook model "was verified against their own API documentation." That is a real form of verification, and twice on this project it has not been enough:

- **P0-06 finding #6** — Zoho's own published example contradicted its live API.
- **P0-04** — WhiteBooks' marketing claimed a gate-free self-serve sandbox; their own onboarding doc requires two support calls.

Sprint 3 builds the Document Intake Agent directly against these mechanics. Finding a gap now costs an afternoon; finding it in Sprint 3 costs the sprint.

## What it checks

| # | ADR 0003 claim | Why it needs a live check |
|---|---|---|
| 1 | Webhook fires → call `/files/list_folder/continue` with a stored cursor to learn what changed | This is the whole intake design. The webhook carries **no file detail**, so if the cursor loop behaves differently than documented, the agent has nothing to work from |
| 2 | Acknowledge within a **10-second** response window; hand real work to a queue | The number drives a hard architectural requirement ("queue/worker from the start, not optional"). Worth confirming it is 10s, and measuring how much of it a bare acknowledgement already costs |
| 3 | **"App folder"** scope, not Full Dropbox | ADR 0003 chose the narrower scope deliberately. What the cursor reports under it — and whether paths come back app-relative — changes how the agent resolves a file |

Secondary, and cheap to capture while there: whether `X-Dropbox-Signature` verification works as documented, and what a notification payload actually contains.

## ⚠️ This spike needs something the others did not: a publicly reachable URL

**This is the one part genuinely different from P0-02 (Tally) and P0-06 (Zoho), and it is worth reading before you plan an afternoon around it.**

Those spikes are pure request/response: our script calls out, the vendor answers, nothing has to reach *us*. Dropbox webhooks invert that — **Dropbox calls you**. That means the receiver must be reachable from the public internet, which a laptop on a home or office network is not.

Practical options:

- **A tunnel (ngrok, Cloudflare Tunnel, or similar)** — simplest for local testing. Gives a public HTTPS URL forwarding to `localhost:8080`. The free tiers issue a **new URL each restart**, and Dropbox's webhook URI is configured per app in the console, so every restart means re-pasting the URI and re-passing the challenge. Budget for that friction rather than being surprised by it.
- **A small always-on host** — more setup, no URL churn. Probably not worth it for a spike.

Dropbox also requires **HTTPS** for webhook URIs and performs a one-time GET challenge before it will deliver anything. Both are handled by `webhook_test.py`, but a plain `http://` tunnel URL will simply be rejected at registration.

## Setup

1. **Create a Dropbox account for this spike.** Do **not** use the practice's real Dropbox. A throwaway personal account is correct — this spike creates and deletes test files.
2. **Register an app** at <https://www.dropbox.com/developers/apps>:
   - "Scoped access"
   - **"App folder" — NOT "Full Dropbox".** ADR 0003 decided this, and testing under the wrong scope would validate a design the platform is not going to ship. It also keeps the blast radius at one folder.
   - Name it something obviously disposable (e.g. `caos-p0-07-spike`).
3. **Permissions tab** → enable at minimum `files.metadata.read`, `files.content.read`, and `files.content.write` (needed only if you trigger changes via the API rather than the web UI), then **Submit**. Scope changes do not apply to already-issued tokens — regenerate the token after changing them, or you get confusing 401/`missing_scope` errors.
4. **Settings tab** → "Generated access token" → Generate. Copy it.
5. `cp .env.example .env` and fill in the app key, app secret, and token.
6. **Start the tunnel** (e.g. `ngrok http 8080`) and copy the HTTPS URL.
7. `python webhook_test.py --serve` — then paste `<tunnel-url>/` into the app's **Webhooks** tab. Dropbox sends the GET challenge immediately; the script echoes it and logs the exchange.
8. `python webhook_test.py --cursor` (separate terminal) to store a starting cursor.
9. **Drop a file into the app's folder** in Dropbox. Watch the receiver log the notification and the `list_folder/continue` result.

## Usage

```powershell
python webhook_test.py                 # dry run — prints intent, sends nothing
python webhook_test.py --verify-only   # config check, no network
python webhook_test.py --cursor        # fetch + store a starting cursor
python webhook_test.py --serve         # run the receiver (needs the tunnel)
```

Dry by default, matching the P0-06 convention: the first thing anyone runs is safe.

## Evidence

Every real call — outbound **and inbound** — is written to `runs/` by `run_logger.py`, one JSON file per call, same as P0-06. Inbound records carry `elapsed_ms`, because claim 2 is a timing claim and the only honest way to report it is to measure every response rather than assert the handler "feels fast".

`run_logger.py` is **copied** from `spikes/p0-06-zoho/`, not imported — see its docstring for why, and `PENDING:021` for the tracked duplication.

## Scope limits, stated up front

- **Not an OAuth spike.** It uses a generated access token. Per-client OAuth consent (the ZB-01-shaped problem) is out of scope.
- **Not a load test.** One account, one folder, a handful of files.
- **Not the platform's webhook handler.** `webhook_test.py` uses `http.server` and answers inline. The real handler needs a queue (ADR 0003's first consequence). This proves the mechanics, not the architecture.
- **The tunnel is not the deployment.** Latency measured through ngrok is not production latency — useful for "is the window 10 seconds and is acknowledgement cheap", not for a performance budget.

## What is needed to actually run this

Nothing here can execute yet. Required, in order:

1. A throwaway **Dropbox account**.
2. A registered **Dropbox API app**, App-folder scoped, with an access token.
3. A **tunnel** (ngrok account or equivalent) for a public HTTPS URL.

Steps 1–2 are the same shape of blocker P0-04 has with its WhiteBooks sandbox account: cheap, but a human has to do it.
