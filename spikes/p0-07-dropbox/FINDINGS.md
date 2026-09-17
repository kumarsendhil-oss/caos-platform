# P0-07 — Dropbox Webhook Spike: Findings

Validates, per ADR 0003 and the Sprint Plan: the webhook → `list_folder/continue`
cursor pattern, the 10-second response window, and "App folder" scope behaviour
— against a real Dropbox API app.

**Status: no findings yet. Nothing has been run.** This file is a stub, in the
same format as `spikes/p0-02-tally/FINDINGS.md` and `spikes/p0-06-zoho/FINDINGS.md`,
so that the first live session has somewhere to write rather than inventing a
structure under time pressure.

## Setup log

- [ ] Throwaway Dropbox account created
- [ ] App registered — **scoped access, "App folder"** (not Full Dropbox, per ADR 0003)
- [ ] Permissions enabled (`files.metadata.read`, `files.content.read`) and **submitted**
- [ ] Access token generated **after** the scope change
- [ ] `.env` populated from `.env.example`
- [ ] Tunnel running, public HTTPS URL obtained
- [ ] Webhook URI registered in the app console; GET challenge passed
- [ ] Starting cursor stored (`--cursor`)
- [ ] First notification received end to end

## Open questions this spike must answer

These are the claims ADR 0003 currently takes from documentation. Each needs a
live answer, and **"it worked" is not one** — record what came back.

1. **Cursor pattern.** Does a notification really carry no file detail? Does
   `/files/list_folder/continue` return exactly the delta since the stored
   cursor? Does the returned cursor advance every time, and is re-using a stale
   cursor an error or a silent re-delivery?
2. **The 10-second window.** Is it 10 seconds? What does Dropbox do on a slow
   or failed response — retry, back off, drop? How much of the window does a
   bare acknowledgement already consume?
3. **App folder scope.** Are `path_display` / `path_lower` app-relative or
   account-absolute? What does the app see when a file is moved *out of* the
   app folder — a delete, or nothing at all? (This matters: the intake agent
   must not treat a move as a deletion of a document it already processed.)
4. **Signature verification.** Does `X-Dropbox-Signature` validate as
   HMAC-SHA256(body, app_secret)? Is it present on every notification?
5. **Payload shape.** What is actually in the notification body — which
   accounts changed, and nothing more?

## Secondary observations worth capturing while there

- Whether rapid successive changes coalesce into one notification or produce
  several (affects whether the queue needs de-duplication).
- Whether Dropbox delivers notifications for changes the app itself made
  (a self-trigger loop is a real hazard for an agent that writes back).
- Token expiry behaviour, since Dropbox now defaults to short-lived tokens.

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

## Findings

*(none yet)*
