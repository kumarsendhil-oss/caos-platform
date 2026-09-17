# P0-07 — Dropbox Webhook Spike: Findings

Validates, per ADR 0003 and the Sprint Plan: the webhook → `list_folder/continue`
cursor pattern, the 10-second response window, and "App folder" scope behaviour
— against a real Dropbox API app.

**Status: run live on 2026-09-17.** App ID `8506691`, app key `ry9r10pvpoly0a3`,
App-folder scoped, throwaway account. Three real notifications received end to
end. 12 evidence files in `runs/`.

**ADR 0003 stays Accepted.** All three claims it took from documentation are
confirmed by live behaviour. Two of its *consequences* need a detail added, and
one hazard it does not mention was observed directly (finding #6).

## Setup log

- [x] Throwaway Dropbox account created
- [x] App registered — **scoped access, "App folder"** (not Full Dropbox, per ADR 0003)
- [x] Permissions enabled (`files.metadata.read`, `files.content.read`, `files.content.write`) and **submitted**
- [x] Access token generated **after** the scope change
- [x] `.env` populated from `.env.example`
- [x] Tunnel running, public HTTPS URL obtained (`ngrok`, free tier)
- [x] Webhook URI registered in the app console; GET challenge passed
- [x] Starting cursor stored (`--cursor`)
- [x] First notification received end to end

`files.content.write` is **added to the checklist above** — it is not in the
README's setup step 3, but any spike that triggers its own changes needs it.

## Answers to the open questions

### 1. Cursor pattern — **CONFIRMED**

The notification carries no file detail whatsoever. Verbatim body
(`runs/20260917T134329_136_webhook_notify.json`):

```json
{"delta": {"users": [2437473139]}, "list_folder": {"accounts": ["dbid:AAA8TTodwsdEPsIboXYCmA-o2EihjvfnW8U"]}}
```

That is the entire payload: which account changed, nothing more. The design in
ADR 0003 is not merely advisable, it is the only option — there is nothing else
to act on.

`/files/list_folder/continue` returned exactly the delta. After overwriting
`p0-07-test.txt` (`runs/20260917T134406_836_list_folder_continue.json`):

```json
{
  "entries": [
    {
      ".tag": "file",
      "client_modified": "2026-09-17T08:14:03Z",
      "content_hash": "dcfbd0a27381b821aadbf2f6cf046d8c112d0fd9a98621ff634bbc8d549f9e85",
      "id": "id:HmlHGAcb3c8AAAAAAAAABQ",
      "is_downloadable": true,
      "name": "p0-07-test.txt",
      "path_display": "/p0-07-test.txt",
      "path_lower": "/p0-07-test.txt",
      "property_groups": [],
      "rev": "0165ba95df84d02000000038740bda3",
      "server_modified": "2026-09-17T08:14:04Z",
      "size": 35
    }
  ],
  "has_more": false
}
```

**The cursor advances.** The follow-up delete returned only the delete and did
*not* re-report the file (`runs/20260917T134429_879_list_folder_continue.json`):

```json
{
  "entries": [
    {
      ".tag": "deleted",
      "name": "p0-07-test.txt",
      "path_display": "/p0-07-test.txt",
      "path_lower": "/p0-07-test.txt"
    }
  ],
  "has_more": false
}
```

This is the specific thing the previous version of this file flagged as
unproven — a single notification proves nothing about cursor advancement, since
a stale cursor would look identical on the first call. Two consecutive
notifications, each returning only its own delta, is the evidence.

Note the `deleted` entry shape: **no `id`, no `rev`, no `content_hash`** — only
the path and name. An intake agent cannot resolve a deletion by file ID from the
delta alone; it must have stored the path→ID mapping when it first saw the file.

### 2. The 10-second window — **CONFIRMED, and acknowledgement is effectively free**

Measured acknowledgement times across all three notifications
(`elapsed_ms`, from the inbound records):

| Notification | Source IP | `signature_valid` | Ack time |
|---|---|---|---|
| upload (trigger 1) | `54.237.177.69` | `true` | **1.067 ms** |
| overwrite (trigger 2) | `34.225.110.50` | `true` | **0.401 ms** |
| delete (trigger 3) | `34.225.110.50` | `true` | **0.378 ms** |

A bare acknowledgement consumes **0.004%–0.011%** of a 10-second window. The
script's >10% warning never came close to firing. ADR 0003's "queue/worker from
the start" consequence is correct, and the reason is now concrete: the budget is
not tight for the *acknowledgement*, it is tight for anything the handler might
be tempted to do inline — a single OCR call or Tally round-trip would blow it.

**Not tested: Dropbox's retry/back-off behaviour on a slow or failed response.**
Every response here was a fast 200. Whether Dropbox retries, backs off, or drops
a notification after a timeout or a 500 is **unanswered**, and the question in
the previous version of this file stands. That matters for the queue design — if
Dropbox does not retry, a dropped notification means permanently missed
documents, and the agent needs a periodic reconciling `list_folder` sweep as a
backstop. Worth a follow-up spike before Sprint 3 commits to webhook-only intake.

### 3. App folder scope — **CONFIRMED app-relative**

`path_display` and `path_lower` both came back as **`/p0-07-test.txt`** — the
app folder is the root. The account-absolute path (`/Apps/<app-name>/...`) never
appears in any response. An intake agent under App-folder scope can treat the
returned path as directly usable and must not attempt to strip a prefix.

**Not tested: what the app sees when a file is moved *out* of the app folder.**
The previous version of this file raised this and it remains open. Given that the
`deleted` entry carries no ID, the concern it flagged — that the agent must not
treat a move as a deletion of a document it already processed — is, if anything,
sharper than before: a move-out and a delete may be indistinguishable in the
delta. Flagging as **inconclusive**, not resolved.

### 4. Signature verification — **CONFIRMED**

`X-Dropbox-Signature` was present on all three notifications and validated as
HMAC-SHA256(raw body, app secret) using `hmac.compare_digest` — `signature_valid:
true` in every inbound record, with no false negatives and no missing header.

The one-time GET challenge also behaved exactly as documented
(`runs/20260917T133332_190_webhook_verify.json`): `User-Agent:
DropboxWebhooks/1.0` from `162.125.47.73`, echoed in **0.39 ms**, and the console
row flipped to Enabled. Note the challenge carries **no signature** —
`signature_valid` is `null` for it, correctly, since there is no body to sign. A
production handler must therefore treat GET and POST as separate trust paths and
must not assume "every Dropbox request is signed".

### 5. Payload shape — **CONFIRMED**

See finding #1. Accounts changed, nothing more.

## Findings

**#1 — The notification payload is account-level, not file-level.** Confirmed
verbatim. No file detail, no change type, no count.

**#2 — The cursor genuinely advances per notification.** Two consecutive
deltas, each disjoint. This is the claim the stub explicitly refused to accept
on one specimen; it now has two.

**#3 — Acknowledgement costs ~0.4–1.1 ms, four orders of magnitude inside the
window.** The 10-second limit is real but is not a constraint on acknowledging;
it is a constraint on *not working inline*.

**#4 — Deleted entries carry no ID or rev.** Path and name only. The agent must
persist its own path→ID mapping or it cannot reconcile a deletion against a
document it has already processed.

**#5 — The GET challenge is unsigned.** GET and POST are separate trust paths.

**#6 — Dropbox delivers notifications for changes the app itself made.** All
three triggers here were writes by this app's own token, and every one produced
a notification. This is the self-trigger hazard the stub listed as a secondary
question, and it is **real, not theoretical**. Any agent that writes back into
the watched folder — a processed-document marker, a renamed file, a generated
working paper — will wake itself up. Sprint 3 needs either a write-back location
outside the watched folder or an explicit ignore-list keyed on `rev`/`content_hash`.
This is the single most actionable finding here and ADR 0003 does not mention it.

**#7 — Short-lived tokens make this spike's setup materially harder than P0-02
or P0-06.** Dropbox now defaults generated access tokens to ~4 hours, and
scope changes do not apply to already-issued tokens, so the correct order is
Permissions → Submit → *then* generate. Getting this out of order produces two
different errors that look similar but are not:

- `400 ... "Your app (ID: …) is not permitted … does not have the required scope"` — the **app** lacks the scope.
- `401 {".tag": "missing_scope", "required_scope": "files.metadata.read"}` — the app has it; the **token predates it**.

Distinguishing these two is what turned a stuck loop into a one-step fix during
this run. Worth writing into the README's setup section verbatim. For Sprint 3
the practical consequence is that the Document Intake Agent must use the OAuth
refresh-token flow, not a generated access token — a 4-hour credential is not
operable unattended.

## Method notes, carried over from the other two spikes

These were learned the hard way in P0-02 and P0-06 and apply here unchanged:

- **Read back; do not trust a success response.** P0-02's Rule 1. A `200` is
  not evidence the thing happened.
- **Record the evidence, not the conclusion.** Every call goes to `runs/` via
  `run_logger.py`; findings cite artifact filenames.
- **Don't generalise from one specimen.** P0-02 finding #18's "minimum case,
  not the representative one" applies to a single test file too.
- **Label what was not tested.** A scope limit stated up front is worth more
  than a finding that quietly over-claims.

## What this run did not cover

Stated plainly, in the spirit of the note above:

- **Retry/back-off on a slow or failed response** (see #2) — the most
  consequential gap.
- **Move out of the app folder** (see #3).
- **Stale-cursor reuse.** The first notification's `list_folder/continue` failed
  at the token layer before the cursor was consulted, so the pre-upload cursor
  was only ever *successfully* used once. Whether replaying an already-consumed
  cursor errors or silently re-delivers is **not** answered by this run, despite
  it superficially looking like it was.
- **Coalescing of rapid successive changes.** The three triggers were 30+
  seconds apart and each produced its own notification. Nothing here says what
  happens to ten changes in one second.
- **One file, one folder, one account.** Not a load test, per the README.
- **Tunnel latency is not production latency.** The sub-millisecond figures are
  handler time, measured inside the receiver, and exclude the ngrok hop.

## Operational notes from this run

- **ngrok as shipped by winget is too old.** `Ngrok.Ngrok` installs 3.3.1;
  ngrok's service rejects agents below 3.20.0 (`ERR_NGROK_121`). `ngrok update`
  fixes it. Budget for this.
- **The free-tier URL changes on every restart**, as the README warns. A webhook
  URI registered against a previous tunnel is silently dead — Dropbox does not
  re-challenge an existing row, so the only symptom is nothing arriving. Remove
  and re-add the URI to force a fresh challenge.
- **`webhook_test.py --serve` needs `python -u`** (or a flush) when stdout is
  redirected to a file. Without it `serve.log` stays empty however many
  notifications arrive, which reads exactly like a failure. The `runs/` records
  are written independently and were unaffected.
- **The receiver reads `.env` once at import.** After rotating a token, the
  server must be restarted; otherwise the inbound notification is acknowledged
  correctly and the outbound `list_folder/continue` fails `expired_access_token`
  — visible in `runs/20260917T134329_974_list_folder_continue.json`, which is a
  real record of exactly that mistake rather than a Dropbox behaviour.
