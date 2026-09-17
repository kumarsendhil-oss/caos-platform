# P0-03 — Shared Inbox Intake (IMAP): Findings

Validates the mechanics EI-01 to EI-06 (PRD §5.4) rest on: shared-inbox monitoring, sender data good enough for client mapping, and attachment extraction and classification — over **IMAP**, the provider-agnostic layer, deliberately not the Gmail API.

**Status: no findings yet. Nothing has been run.** This file is a stub, in the same format as `spikes/p0-02-tally/FINDINGS.md`, `spikes/p0-06-zoho/FINDINGS.md` and `spikes/p0-07-dropbox/FINDINGS.md`, so the first live session has somewhere to write rather than inventing a structure under time pressure.

Unlike P0-02/06/07, **no ADR governs this area yet.** There is no email equivalent of ADR 0011's `BooksConnector`. That is the gap these findings should inform — and informing it is the goal, not resolving it here. A spike that proposes an architecture from one provider and one inbox would be doing exactly what ADR 0011 Amendment 2 had to correct: generalising from a single backend's behaviour.

## Setup log

- [ ] 2FA enabled on `work.caos@gmail.com`
- [ ] App-specific password generated and placed in `.env`
- [ ] `python email_test.py --verify-only` passes
- [ ] Test messages sent to the inbox (PDF, image, no-attachment, second sender, forward)
- [ ] First successful `--poll` against the real inbox
- [ ] Timing recorded for a poll cycle

## Open questions this spike must answer

Each needs a real answer, and **"it worked" is not one** — record what came back.

1. **Does polling give acceptable latency for EI-01, or is IDLE/push needed?**
   IMAP's cost relative to a provider-native push API is that nothing tells you mail arrived; you ask. The question is what interval is acceptable and what it costs. Record: how long a full poll cycle takes (connect, login, select, search, fetch), how much of that is fixed overhead versus per-message, and whether the fixed cost is paid per cycle or amortised by holding the connection open.
   Then the judgement: a 60-second poll on a shared inbox is ~1,440 cycles/day per practice — is that acceptable to the provider, and to the platform? **IMAP IDLE is the alternative** and is *not* tested here (it needs a long-running connection test). Whether it is worth the complexity — and how it behaves through a NAT/proxy that drops idle connections — is the follow-up.

2. **How reliably can attachments be extracted and classified via IMAP alone (EI-03)?**
   Specifically, and these fail differently: multipart messages where the invoice is one part among several; **inline images** (email signatures, logos) which are parts but are not attachments in EI-03's sense and would be noise if conflated; attachments with RFC 2047-encoded filenames (non-ASCII, or long names split across header lines); attachments with no filename at all; and `.eml`/`.msg` attachments, i.e. a forwarded mail carrying the real document one level down.
   Also: does `Content-Type` agree with the file extension, and which should be trusted when they disagree?

3. **What does sender parsing actually look like on real messages — including reply-chains and forwards?**
   EI-02 maps sender to client. The straightforward case is a client emailing from their own address. The cases that break it:
   - **Forwards.** Staff forwarding a client's invoice makes `From:` the staff member. The real sender is inside the body or in the attached original. Mapping on `From:` alone would file the document against the wrong client — or against no client, which is the better failure.
   - **Reply chains.** `Re:` threads where the current sender is not the party the document relates to.
   - **`Reply-To` differing from `From:`** — common with ticketing systems and accounting software that mails on a vendor's behalf.
   - **Shared/generic sender domains.** `accounts@` at a shared-services provider covering several clients; the domain maps to a provider, not a client.
   - **Display-name-only identity**, where the address is a no-reply relay and the only human-meaningful identifier is the display name.
   Record which of these appear and what fields are populated in each. The deliverable is what EI-02 can *safely* key on, not a mapping.

4. **Does anything Gmail-specific leak into what should be a generic IMAP path?** *(the architecture question)*
   The claim under test is that a practice on Exchange changes `IMAP_HOST` and nothing else. Things that would falsify it: Gmail's `X-GM-*` extensions or labels-as-folders behaving unlike real IMAP folders; `SEARCH` semantics differing (Gmail's search is famously not literal IMAP search); UID stability across sessions; `\Recent` and `\Seen` flag handling; whether `[Gmail]/All Mail` alters what `INBOX` returns.
   **Record any place the code or the observed behaviour depends on the provider** — that list is the actual input to an eventual email-connector ADR. An empty list is a finding; so is a long one.

5. **Is UID-based incremental polling reliable enough to avoid re-processing?** *(added — CG7's shape)*
   A monitoring agent must not process the same message twice. IMAP offers `UIDVALIDITY` plus `UID` for this, but `UIDVALIDITY` can change and invalidate stored UIDs. Whether that happens in practice, and what the agent does when it does, is a duplicate-prevention question of exactly the kind CG7 exists for.

## Secondary observations worth capturing while there

- Whether `readonly=True` genuinely leaves `\Seen` untouched (the script assumes it; worth confirming, since an agent that marks mail read by observing it is an operational bug).
- What the provider does under repeated rapid polling — throttling, connection limits, or a `TOO many simultaneous connections` style error.
- Whether message size affects fetch time enough to matter (a 10MB scanned PDF versus a text-only message).
- Whether `BODY.PEEK[HEADER]` would let a poll cycle triage cheaply before fetching full messages — relevant if fetch dominates the cycle.
- What a message with **no** `Date:` header, or an unparseable one, does to ordering.

## Method notes, carried over from the other spikes

- **Read back; do not trust a success response.** P0-02's Rule 1. `OK` from an IMAP command is not evidence the data is what you think.
- **Record the evidence, not the conclusion.** Every interaction goes to `runs/`; findings cite filenames.
- **Don't generalise from one specimen.** P0-02 finding #18. Here it applies per *message shape* — one PDF attachment proves nothing about multipart or forwarded mail.
- **Label what was not tested.** One provider, one inbox, polling only. Say so.

## What is blocked, and on whom

1. **An app-specific password** for `work.caos@gmail.com` (2FA must be enabled first).
2. **Test messages in the inbox** — the spike reads a mailbox and cannot populate one. The varied set matters more than the count: PDF attachment, image attachment, no attachment, a second sender address, and a forwarded message.

Both are the same shape of blocker as P0-07's Dropbox app and P0-04's WhiteBooks account: cheap, but a human has to do them.

## Findings

*(none yet)*
