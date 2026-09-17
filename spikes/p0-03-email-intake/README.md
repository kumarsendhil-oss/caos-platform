# P0-03 — Shared Inbox Intake over IMAP

**Status:** run live 2026-09-17 against `work.caos@gmail.com` — 8 messages, 19 evidence records in `runs/`. See `FINDINGS.md`; the headline is that a forwarded message carries the original sender in no header at all.

Tests the mechanics EI-01 to EI-06 (PRD §5.4) depend on: monitoring a shared inbox, reading sender information well enough to map it to a client, and extracting and classifying attachments.

## Why IMAP, and not the Gmail API

This is the single most important decision in the spike, and it is deliberate rather than convenient.

ADR 0009 makes each practice its own single-tenant deployment and ADR 0010 makes per-practice customization a first-class concern. The email provider is therefore **per-deployment configuration**, not a platform-wide constant — one practice on Google Workspace, another on Microsoft 365, another on a hosted Zoho Mail is a realistic spread.

Gmail's own REST API would be the better engineering choice for a Gmail-only product. It offers OAuth rather than a password, push notification via Cloud Pub/Sub rather than polling, and server-side search. **It also transfers to nothing.** A practice on Exchange would need an entirely separate connector, written from scratch, with its own auth model and its own push mechanism — and the platform would be branching on which provider a practice runs, which is the shape CG11 exists to prevent.

IMAP is the protocol-level common ground. It is worse in isolation and better as an architecture, so IMAP is what gets measured. The cost of that choice — polling instead of push — is not hidden; it is open question 1.

**Consequence for setup:** this spike uses an **app-specific password**, not OAuth. That is a real difference from P0-06 (Zoho OAuth) and P0-07 (Dropbox tokens), and it is downstream of the portability decision rather than a shortcut around a harder auth flow.

## Setup

### 1. The test account

`work.caos@gmail.com` — **development and test only.** No real practice data, no real client mail. This spike reads a mailbox and writes attachment metadata to disk; pointing it at a practice's real shared inbox would put client documents in scope, which is out of scope here.

### 2. Enable 2FA, then generate an app password

Google requires two-step verification **before** app passwords become available. The option does not appear at all without it, which is the most common reason people can't find it.

1. **https://myaccount.google.com/security** → **2-Step Verification** → turn it on if it isn't already.
2. Then go to **https://myaccount.google.com/apppasswords**
3. Give it a name (e.g. `caos-p0-03-spike`) and click **Create**.
4. Google shows a 16-character password in four groups of four. Copy it.

Notes that save time:

- **The app-passwords page 404s or redirects if 2FA is off.** That is the symptom, not a broken link.
- **Paste it with or without spaces** — the script strips them. This matters because IMAP rejects the spaced form with a bare `Invalid credentials`, indistinguishable from a wrong password.
- **This credential grants full mailbox access.** It is not scoped the way an OAuth scope is, and it does not expire. Revoke it from the same page when the spike is done.

### 3. Configure

```powershell
# From spikes/p0-03-email-intake
Copy-Item .env.example .env
# then fill in IMAP_APP_PASSWORD
```

A practice on another provider changes `IMAP_HOST` and nothing else — that is the portability claim under test:

| Provider | `IMAP_HOST` | Port |
|---|---|---|
| Gmail / Workspace | `imap.gmail.com` | 993 |
| Outlook / Microsoft 365 | `outlook.office365.com` | 993 |
| Zoho Mail (India DC) | `imap.zoho.in` | 993 |

### 4. Put some test messages in the inbox

The spike cannot generate its own input. See *What is needed to actually run this*.

## Usage

```powershell
python email_test.py                      # dry run — prints intent, connects to nothing
python email_test.py --verify-only        # config check, no network
python email_test.py --poll               # connect, list the 10 most recent
python email_test.py --poll --limit 25
python email_test.py --poll --unseen      # only unread
python email_test.py --poll --save-attachments   # write files to attachments/ (gitignored)
```

Dry by default, matching the P0-06/P0-07 convention: the first thing anyone runs is safe.

`--poll` uses `SELECT ... readonly=True`, so **reading does not mark messages as seen**. That is deliberate beyond politeness: a monitoring agent that marks mail read merely by looking at it changes what a human sees in a shared inbox, which would be a real operational bug in EI-01.

## Evidence

Every IMAP interaction — connect, login, select, search, and each fetch — is written to `runs/` as one JSON file, same convention as P0-02/06/07.

`run_logger.py` is **copied and adapted** from `spikes/p0-06-zoho/`, not imported. Tracked as the same duplication as P0-07 (`PENDING:021`), but note the adaptation is heavier here: the P0-06 original is HTTP-shaped (`url`, `status_code`, `response_headers`), and an IMAP exchange has none of those. Forcing it through that signature would leave six fields permanently `None` and make every run file misleading about what was observed.

What carries over unchanged is the discipline: **credentials never reach disk.** For P0-06 that meant omitting request headers, where the bearer token lived. Here the app password is never passed to the logger at all — only the account address, which is not a secret.

**Message bodies are deliberately not persisted.** Sender, subject and attachment metadata answer every open question this spike has; body text answers none of them. Attachments are recorded by filename, MIME type and size — content is written only under `--save-attachments`, into a gitignored directory.

## What is needed to actually run this

Two things, both of which need a human:

1. **An app-specific password** for `work.caos@gmail.com`, per the setup above, in `.env`.
2. **Test messages in the inbox.** The spike reads a mailbox; it cannot populate one. Worth sending, to exercise the cases that actually matter:
   - one **with a PDF attachment** (the realistic invoice case)
   - one **with an image attachment** (the phone-photo-of-a-bill case)
   - one **with no attachment** (must not be misread as a failed extraction)
   - one **from a different sender address**, if possible — EI-02 maps sender to client, and one sender proves nothing about that
   - one **forwarded** message, ideally — the person who forwards a client's invoice is not the client, and that distinction is open question 3

## Scope limits, stated up front

- **Not an EI-02 implementation.** Sender-to-client mapping is learned and staff-editable per the PRD; this spike only establishes what sender data is reliably available to map *with*.
- **Not a classifier.** EI-03's attachment typing here is an extension-and-MIME lookup, deliberately thin. A smarter classifier would hide the cases that should become a Task.
- **Not a connector design.** The findings should inform an eventual email-connector ADR — the way ADR 0011 did for books systems — but this spike does not propose one.
- **Not IDLE, yet.** Only polling is measured. Whether IMAP IDLE is worth the complexity is open question 1, and answering it properly needs a long-running connection test rather than a single cycle.
- **One provider.** Only Gmail's IMAP endpoint is exercised. Portability is argued from the protocol, not demonstrated across providers — see open question 4.
