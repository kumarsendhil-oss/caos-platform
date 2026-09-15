# Spikes

Executable spike scripts and their captured results.

This is the **working** half of the Phase 0 spikes. The written
runbooks — what to test and what each result would mean — live in
`docs/spikes/`. Scripts here implement them and record what actually
happened.

## Why runs are committed

A spike result that exists only in someone's terminal scrollback isn't
evidence. When `TallyAdapter`'s parsing gets written, it needs the real
response shape, not a description of it. When someone asks in three
months whether Tally rejects duplicate vouchers, the answer should be a
file, not a memory.

So every send captures request, response and metadata to a timestamped
folder, automatically. Failures are captured too — a connection refused
is a result worth keeping.

## Layout

```
spikes/
  _runner.py              shared: POST + capture
  p0-02-tally/
    create_ledgers.py
    runs/
      2026-09-15T14-03-22-create-ledgers/
        request.xml       what was sent, byte for byte
        response.xml      what came back
        meta.json         url, status, timing, script
```

## Running one

Every script is a dry run by default and only sends with `--send`:

```powershell
cd spikes\p0-02-tally
python create_ledgers.py            # print the payload, send nothing
python create_ledgers.py --send     # send it, capture to runs\
```

## Writing a new one

1. Put it under the relevant `p0-XX-*/` directory.
2. Build the payload in a `build()` function that takes no I/O — so it
   stays testable and printable without a live server.
3. Send via `run(name, payload)` from `_runner`, never with a bare
   `urlopen` — otherwise the result isn't captured.
4. Default to dry run. A script that fires on import will eventually
   fire when someone didn't mean it to.

## What must not go in runs/

**Only synthetic data.** Per Testing Strategy §4, no real client GSTIN,
financial documents or extracted data appears in this repo — and that
applies to captured responses as much as to test fixtures. These runs
go against a local Educational Mode instance with invented data
(`Coastal Test Traders`, GSTIN `33AAAAA0000A1Z5`).

If a spike is ever pointed at a real client's Tally company or a live
GSTIN, **do not commit the run**. Add it to `.gitignore` first, or
better, don't run spikes against production data at all — that is what
the local sandbox exists to avoid.

## Current spikes

| Directory | Runbook | Status |
|---|---|---|
| `p0-02-tally/` | `docs/spikes/P0-02-api-explorer-runbook.md` | Local Educational Mode instance set up; scripts unrun |
| — | `docs/spikes/P0-04-whitebooks-gsp-runbook.md` | No scripts yet; needs sandbox credentials |
| — | `docs/spikes/P0-06-zoho-api-runbook.md` | No scripts yet; needs sandbox credentials |

Note P0-02's runbook was written for the TallyPrime API Explorer. A
local Educational Mode install turned out to be the better sandbox —
same interface, and you can verify results in the UI. The runbook still
needs updating to reflect that, along with Educational Mode's date
restriction (postings only on the 1st, 2nd and 31st).
