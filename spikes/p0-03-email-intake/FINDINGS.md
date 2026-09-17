# P0-03 — Shared Inbox Intake (IMAP): Findings

Validates the mechanics EI-01 to EI-06 (PRD §5.4) rest on: shared-inbox monitoring, sender data good enough for client mapping, and attachment extraction and classification — over **IMAP**, the provider-agnostic layer, deliberately not the Gmail API.

**Status: run live on 2026-09-17** against `work.caos@gmail.com` over IMAP, 8 messages (5 purpose-built test messages + 3 incidental Google account notices). 19 evidence records in `runs/`. Same format as `spikes/p0-02-tally/FINDINGS.md`, `spikes/p0-06-zoho/FINDINGS.md` and `spikes/p0-07-dropbox/FINDINGS.md`.

**Three of the five open questions are answered, two are partly answered.** The headline is finding #1: a forwarded message does not carry the original sender in *any* header, which breaks the obvious reading of EI-02. Open question 5 (UID/Message-ID stability) was resolved on 2026-09-17 — see the dedup-key recommendation — and resolving it surfaced finding #8, a real bug in this spike's own first implementation.

Unlike P0-02/06/07, **no ADR governs this area yet.** There is no email equivalent of ADR 0011's `BooksConnector`. That is the gap these findings should inform — and informing it is the goal, not resolving it here. A spike that proposes an architecture from one provider and one inbox would be doing exactly what ADR 0011 Amendment 2 had to correct: generalising from a single backend's behaviour.

## Setup log

- [x] 2FA enabled on `work.caos@gmail.com`
- [x] App-specific password generated and placed in `.env`
- [x] `python email_test.py --verify-only` passes
- [x] Test messages sent to the inbox (PDF, image, no-attachment, second sender, forward)
- [x] First successful `--poll` against the real inbox
- [x] Timing recorded for a poll cycle
- [x] UIDVALIDITY / UID / Message-ID stability tested across 4 fresh sessions (open question 5)
- [ ] IMAP IDLE tested (open question 1 — needs a long-running connection test)
- [ ] UID behaviour across an actual expunge (nothing has been deleted from the test mailbox)
- [ ] A second provider tested (open question 4 — portability is argued, not demonstrated)

## Answers to the open questions

Marked plainly. Nothing rounded up.

### 1. Polling latency and cost — **PARTLY ANSWERED.** Cost measured; IDLE untested.

Measured across two cycles on the same mailbox:

| | 3 messages, no attachments | 8 messages, 4 attachments |
|---|---|---|
| connect | 715 ms | 637 ms |
| login | 691 ms | 919 ms |
| select | 394 ms | 415 ms |
| search | 433 ms | 433 ms |
| fetch (total) | 1,263 ms | 5,923 ms |
| **cycle** | **3,931 ms** | **8,795 ms** |

The number that matters for EI-01 is the **fixed overhead**: connect + login + select + search is ~2.2 s in *both* runs, independent of message count. On the 3-message cycle that was 56% of the total.

**Consequence:** if the agent reconnects every poll it pays ~2.2 s per cycle to discover nothing most of the time. A 60-second poll is ~1,440 cycles/day/practice, i.e. ~53 minutes/day of pure connection setup. A long-lived connection amortises this to near zero, so **holding the connection open is not an optimisation, it is the design**.

**Still open, and deliberately not answered:** IMAP IDLE. It needs a long-running connection test this spike did not do, and the real question is not whether IDLE works but how it behaves across a NAT/proxy that silently drops idle TCP connections — which a single-session test cannot answer either. Provider throttling under sustained polling is also untested.

### 2. Attachment extraction and classification (EI-03) — **PARTLY ANSWERED.** Works on every case present; several cases were absent.

Every attachment in the inbox extracted correctly, with filename, MIME type and byte size intact:

```
uid 4  9032783280_STNR27018390414.pdf        application/pdf   699,876 B   -> pdf
uid 5  images.jpeg                           image/jpeg         31,096 B   -> image
uid 7  Sendhil_Kumar_Natarajan_31052026_...  application/pdf     47,257 B   -> pdf
uid 8  06204017127_92026_Invoice-1.PDF       application/pdf     81,313 B   -> pdf
```

Two specifics worth recording:

- **`.PDF` uppercase (uid 8) classified correctly.** The extension lookup lower-cases first. Trivial, but it is the kind of thing that silently mis-files a document, and real invoices do arrive with shouting extensions.
- **The forwarded message's attachment came through as a direct attachment** (uid 7), *not* wrapped in an `.eml` part. So EI-03 can extract from a forward without unwrapping a nested message — at least when the forward is composed by Gmail's web client.

**`Content-Type` agreed with the extension in all four cases**, so the "which do you trust when they disagree" question **was not exercised** and stays open.

**Not present in this sample, therefore untested:** inline images (signatures/logos), RFC 2047-encoded or non-ASCII filenames, attachments with no filename, `.eml`/`.msg` attachments, and multipart messages with several attachments. The extraction code has branches for inline parts and unnamed parts; **none of them were exercised by real data and should not be assumed correct.**

### 3. Sender parsing, forwards and reply-chains — **ANSWERED, and the answer is a problem.** See finding #1.

Per message, every sender field, verbatim:

```
uid 4  from: Sendhil kumar <kumar.sendhil@gmail.com>   reply_to: None  return_path: kumar.sendhil@gmail.com
uid 5  from: Sendhil kumar <kumar.sendhil@gmail.com>   reply_to: None  return_path: kumar.sendhil@gmail.com
uid 6  from: Sendhil kumar <kumar.sendhil@gmail.com>   reply_to: None  return_path: kumar.sendhil@gmail.com
uid 7  from: Sendhil kumar <kumar.sendhil@gmail.com>   reply_to: None  return_path: kumar.sendhil@gmail.com
       subject: "Fwd: HDFC Bank Combined Email Statement for May-2026"   looks_like_forward: True
uid 8  from: Integra Agro <integraagro.tn@gmail.com>   reply_to: None  return_path: integraagro.tn@gmail.com
```

**The forward (uid 7) carries the original sender in no header at all.** `From`, `Reply-To` and `Return-Path` all name the *forwarder*. A full header dump (`BODY.PEEK[HEADER]`) confirms it — every header on the message:

```
ARC-Authentication-Results, ARC-Message-Signature, ARC-Seal, Authentication-Results,
Content-Type, DKIM-Signature, Date, Delivered-To, From, In-Reply-To, MIME-Version,
Message-ID, Received, Received-SPF, References, Return-Path, Subject, To,
X-Gm-Features, X-Gm-Gg, X-Gm-Message-State, X-Google-DKIM-Signature, X-Received
```

The only traces of the original are:

```
References:   <632613283705ffe9e7-...-443d29897b93@intensemail.no-ip.org>
In-Reply-To:  <632613283705ffe9e7-...-443d29897b93@intensemail.no-ip.org>
Subject:      Fwd: HDFC Bank Combined Email Statement for May-2026
```

— a Message-ID whose *domain* (`intensemail.no-ip.org`) belongs to the originating mail system, and the bank's name as free text in the subject. **Neither is an address, and neither is reliable**: the Message-ID domain is the sender's mail provider, not the sender, and a subject line is prose.

**`Reply-To` was absent on all five test messages**, so the "Reply-To differs from From" case that ticketing systems produce **was not exercised** and remains open.

**Reply chains were not exercised** — no `Re:` message was sent, and `looks_like_reply` never fired.

**The no-reply relay case appeared incidentally** in the three Google notices (`no-reply@accounts.google.com`), where the only human-meaningful identifier is the display name `Google`.

### 4. Does anything Gmail-specific leak? — **ANSWERED for what was exercised: no leak in the code path; Gmail-specific data is present but ignored.**

Gmail-proprietary headers *are* on the wire — `X-Gm-Features`, `X-Gm-Gg`, `X-Gm-Message-State`, `X-Google-DKIM-Signature` — but nothing in `email_test.py` reads them. Every command used is plain RFC 3501: `SELECT`, `SEARCH ALL`, `SEARCH UNSEEN`, `FETCH (RFC822)`, `FETCH (BODY.PEEK[HEADER])`. The only provider-specific value in the whole spike is `IMAP_HOST` in `.env`.

**What this does and does not establish.** It establishes that the *code* has no Gmail dependency, which is a real result. It does **not** establish portability, because only one provider was tested. Specifically untested and still open: whether Gmail's `SEARCH` semantics diverge from literal IMAP search on non-trivial criteria (only `ALL` and `UNSEEN` were used), `UIDVALIDITY` stability, `\Recent`/`\Seen` handling, and whether labels-as-folders behave unlike real folders. An Exchange or Zoho Mail run is what would close this.

### 5. UID-based incremental polling (CG7's shape) — **ANSWERED, with an explicit limit on the evidence.**

Tested 2026-09-17 with `uid_stability.py` across **four genuinely separate IMAP sessions** (full connect / login / read / logout each time), snapshots in `uid_snapshots/`.

```
UIDVALIDITY across 4 sessions: [1]        UIDNEXT: 9 (all four)
UID per message:               identical everywhere
Message-ID set:                identical across all four sessions
Message-ID present:            8/8       malformed: none      duplicated: none
```

Every message, with both identifiers, from the final session:

```
uid 1  <cnY007FWaT2E9gznAlhpHQ@notifications.google.com>        Security alert
uid 2  <hjQqhbpf8uMD732GonoYsg@notifications.google.com>        2-Step Verification turned on
uid 3  <UmiNOirJknkx30rQVW8ljw@notifications.google.com>        Security alert
uid 4  <CAKym4priE-k5E9Vgm+dqeZtY7MLiEfNUtWWMNAQPgmvLpLEeBQ@mail.gmail.com>   Phone bill
uid 5  <CAKym4ppK48X167k-gWy5DJ7SufDgz-DE9iSo07oiBVPE8nErcg@mail.gmail.com>   Invoice copy
uid 6  <CAKym4pqb+KZyQHkzTi1rQxMecYcNrf9XqWnHNgDDdWVb1rtcxw@mail.gmail.com>   Pur hase bill
uid 7  <CAKym4pqKpa8SkHNifwifj6shFDRcqHVsQTryqPu8POr3crDm0g@mail.gmail.com>   Fwd: HDFC Bank...
uid 8  <CAPo-PXis8tV-F36P8rS2_twf7hKXSt7KBbZX5wFd5RSqW9aQXQ@mail.gmail.com>   EB bill
```

**What is confirmed:** UIDs are stable across reconnects, `UIDVALIDITY` did not change, and Message-ID is present, well-formed and unique on all 8 messages. Both identifiers are usable.

**What is NOT confirmed, and must not be rounded up.** The four sessions span **88 seconds**, on **one mailbox** that has never had a message expunged, and whose `UIDVALIDITY` is **1** — the value Gmail assigns a mailbox that has never been invalidated. Observing no change over 88 seconds says essentially nothing about whether `UIDVALIDITY` can change over months; RFC 3501 permits it, and a server is entitled to change it after a mailbox is deleted and recreated, or after some kinds of server-side migration. **"It never changed during the test" is not "it cannot change", and the agent must implement the RFC-required detection regardless of what this test observed.**

Also untested: whether UIDs survive an actual expunge (nothing was deleted), and behaviour on any provider other than Gmail.

### Dedup-key recommendation

For whoever designs the email-intake dedup table. A recommendation, not an implementation.

**Store both. Key on `(uidvalidity, uid)`; carry `message_id` as an independent recovery path.**

| | `(UIDVALIDITY, UID)` | `Message-ID` |
|---|---|---|
| Assigned by | the IMAP server | the *sending* mail system |
| Cheap to obtain | yes — `UID SEARCH` alone, no body fetch | needs a header fetch per message |
| Stable across reconnects | confirmed here | confirmed here |
| Survives a UIDVALIDITY change | **no, by definition** | yes |
| Guaranteed present | yes | **no** — self-reported, may be absent or malformed |
| Guaranteed unique | yes, within the epoch | **no** — a sender can reuse one |

Neither is sufficient alone, and they fail in *different* directions, which is exactly why both are worth storing:

1. **`(uidvalidity, uid)` is the working key.** It comes back from `UID SEARCH` without fetching anything, so the agent can decide "already processed?" before paying for a body fetch — which matters, given finding #4's measured fetch costs.
2. **Read and compare `UIDVALIDITY` on every session.** This is not optional hygiene; RFC 3501 requires it. On a mismatch, every stored UID for that mailbox is meaningless and must be discarded, not reused.
3. **`message_id` is the recovery path.** After a UIDVALIDITY change, re-map already-processed messages by Message-ID and rebuild the UID index, rather than re-processing the mailbox and re-filing every document a second time.
4. **Do not make `message_id` the primary key.** It is self-reported. A malformed or missing one must not be able to block ingestion, and a duplicated one must not silently suppress a genuine second document.
5. **A message with no usable Message-ID during a recovery is a Task, not a guess.** Per CG8 — re-filing a client document twice and dropping one are both wrong, and a human should choose.
6. **Never use message sequence numbers.** See finding #8.

A practical consequence for the table's shape: the natural unique constraint is on `(mailbox, uidvalidity, uid)`, with a non-unique index on `message_id` for the recovery lookup — unique on `message_id` would be wrong, because uniqueness is precisely what Message-ID does not guarantee.

## Method notes, carried over from the other spikes

- **Read back; do not trust a success response.** P0-02's Rule 1. `OK` from an IMAP command is not evidence the data is what you think.
- **Record the evidence, not the conclusion.** Every interaction goes to `runs/`; findings cite filenames.
- **Don't generalise from one specimen.** P0-02 finding #18. Here it applies per *message shape* — one PDF attachment proves nothing about multipart or forwarded mail.
- **Label what was not tested.** One provider, one inbox, polling only. Say so.

## Findings

**#1 — A forwarded message identifies the forwarder, not the original sender, and no header recovers it.** Confirmed by full header dump. `From`, `Reply-To` and `Return-Path` all name the forwarder; the original survives only as a Message-ID *domain* in `References`/`In-Reply-To` and as free text in the subject.

This is the most consequential finding here, because forwarding is not an edge case in this workflow — staff forwarding a client's invoice into the shared inbox is a routine path, and EI-01's whole premise is that mail arrives by various routes. **Keying EI-02 on `From` alone would file a forwarded client document against the staff member who forwarded it.**

Three implications for EI-02, in order of how much they change the design:

- **A forward must be detected and treated differently, not mapped.** `Subject` starting `Fwd:`/`FW:` plus a `References` domain differing from the `From` domain is a usable detector, and it is a *heuristic*, not a guarantee.
- **Recovering the original sender requires parsing the body**, where Gmail writes its `---------- Forwarded message ---------` block. That is provider-specific formatting and fragile — and this spike deliberately does not persist bodies, so it is unverified here.
- **The honest fallback is a Task.** Per CG8, a forward whose original sender cannot be established is exactly a human-judgement case. Filing it against the forwarder is the silent-wrong-answer failure P0-02 finding #2 warns about.

**#2 — Two distinct senders shared the same domain, so domain-based mapping would collapse them.** `kumar.sendhil@gmail.com` and `integraagro.tn@gmail.com` are different correspondents, both with `from_domain: gmail.com`.

Obvious in hindsight and easy to get wrong: domain-level mapping is attractive because a company's staff share a domain, and it breaks completely for clients on shared consumer mail — which, for a practice serving small Indian businesses, will be common. **EI-02 must key on the full address**, with domain as at most a weak secondary signal. The extractor records both, so the data is there; the mapping design has to not use the wrong one.

**#3 — Fixed connection overhead dominates a small poll cycle.** ~2.2 s of a 3.9 s cycle, invariant to message count. A long-lived connection is the design, not an optimisation. See open question 1.

**#4 — Fetch time scales with attachment size, but noisily, and the earlier 421 ms/message figure did not hold.** Per-message fetch times against payload size:

```
uid 6        0 B     424 ms   (no attachment)
uid 5   31,096 B     727 ms
uid 7   47,257 B     575 ms
uid 8   81,313 B     596 ms
uid 4  699,876 B   2,115 ms
```

The 700 KB PDF took ~5x the empty message. But uid 5 (31 KB, 727 ms) was *slower* than uid 8 (81 KB, 596 ms), so size is not the only factor and single samples are noisy. The provisional 421 ms/message from the text-only run rose to **740 ms/message** here — the earlier caveat that it would not hold was correct. Base64 transfer encoding inflates attachment bytes on the wire by ~33%, which this arithmetic does not separate out.

Practical consequence: **`BODY.PEEK[HEADER]` triage before full fetch is worth designing in.** Headers alone answer "is this new, who sent it, does it matter" at roughly the 424 ms floor, and the full RFC822 fetch only needs to happen for messages that pass triage.

**#5 — A zero-attachment message is handled as a normal case, not an error.** uid 6 returned `attachment_count: 0` with no exception, no warning, and a clean record. Worth stating explicitly because "no attachment" and "attachment extraction failed" must never be the same outcome to an intake agent — the first is routine, the second is a Task.

**#6 — Gmail-specific headers are present in the data but absent from the code path.** `X-Gm-Features`, `X-Gm-Gg`, `X-Gm-Message-State`, `X-Google-DKIM-Signature`. The spike reads none of them and uses only RFC 3501 commands. This supports the portability argument without demonstrating it — see open question 4.

**#8 — This spike's own first implementation used message sequence numbers and called them UIDs.** Found while answering open question 5, and worth recording rather than quietly fixing, because it is the exact bug the question exists to prevent.

`imaplib`'s `search()` and `fetch()` operate on **message sequence numbers**, not UIDs. Sequence numbers are *positional*: they are 1..N over the current mailbox contents and **renumber when a message is expunged**. The original `email_test.py` called `client.search(...)`, labelled the results `uid`, and wrote them into every run record under that name — so the earlier reporting of "uid 4 = phone bill" was a sequence number that happened to coincide.

It coincided because **nothing has ever been expunged from this mailbox**, so sequence numbers and UIDs are currently identical (`1..8` for both). That coincidence is what makes the bug dangerous: it is invisible until the first deletion, at which point stored identifiers silently point at the wrong messages, and an intake agent re-files documents against the wrong records.

Corrected to `uid('SEARCH', ...)` and `uid('FETCH', ...)`; run records now log the command as `UID SEARCH`/`UID FETCH` so the distinction is visible in the evidence. `uid_stability.py` deliberately records **both** so the equality is observable rather than assumed.

The general lesson is P0-02 finding #2's, in a new place: **the failure was silent and the output looked correct.** A mailbox with no deletions cannot distinguish the right identifier from the wrong one.

**#7 — `readonly=True` behaved as intended.** Messages remained unread after two full poll cycles that fetched every message. An agent can observe a shared inbox without changing what staff see in it.

## What is still blocked, and on whom

The remaining questions need *time and a second environment*, not another inbox:

1. **A second provider** (Exchange/M365 or Zoho Mail) to turn the portability argument into a demonstration. This should happen before an email-connector ADR is written.
2. **A long-running session** to test IMAP IDLE and provider throttling. `UIDVALIDITY` stability across reconnects is now tested, but only over an 88-second window — a longer observation would strengthen it, though no amount of observation replaces implementing the RFC-required check.
3. **Message shapes absent from this sample** — inline images, encoded filenames, `.eml` attachments, multi-attachment messages, and a `Re:` reply chain. Cheap to produce: a few more test sends.
