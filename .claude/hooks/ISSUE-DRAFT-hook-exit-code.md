# Issue draft — hooks with `shell: "powershell"` return exit 2 but are recorded as exit 1 and fail open (Windows)

> **Status: DRAFT — not filed anywhere.** Written 2026-09-15, revised same day,
> from a live session in this repo. Review before submitting upstream.

**Suggested title:** Hooks with `shell: "powershell"` exit 2 but are recorded as exit 1 on Windows — blocking hooks silently fail open (`shell: "bash"` works)

**Affects both `PreToolUse` and `PostToolUse`.** Not specific to one hook event,
one tool, or one script.

---

## The question for a maintainer

**The bug is localized to the `"shell": "powershell"` hook path.** The same
script, returning the same exit code 2, blocks correctly under
`"shell": "bash"` and fails open under `"shell": "powershell"` (A/B test in
"Localization" below). So:

1. **Where in the PowerShell hook path does an exit code of 2 become a
   reported 1?** The script returns 2, its stderr survives the trip intact, and
   `durationMs` is realistic — the process ran to completion. Only the exit
   status is wrong, and only under `powershell`.
2. **Which binary does `"shell": "powershell"` spawn?** This machine has both
   Windows PowerShell 5.1 and PowerShell 7.6.6 installed (paths in the
   environment table below). Nothing observable from inside a session reveals
   which the harness launches. Answering this decides whether the
   PowerShell-7-specific theory in "Speculation" is applicable or irrelevant.

## Summary

A `PreToolUse` hook that returns exit code **2** — the documented "block the
tool call" signal — is recorded by Claude Code as exit code **1**. Exit 1 is
classified as `hook_non_blocking_error`, so the tool call proceeds.

The hook's stderr *is* captured and surfaced, which makes the failure easy to
miss: the block message appears in the UI, so the hook looks like it worked,
while the command runs anyway.

The same script, invoked directly with the same JSON payload on stdin, returns
exit code 2 correctly every time. The discrepancy appears only in the harness
invocation path.

Observed **15 out of 15 times** in a single session, across both the `Bash` and
`PowerShell` tool surfaces. It never blocked successfully once.

## Impact

Any hook written as a safety guard silently does not guard. In this repo the
hook blocks force-pushes and `.git` deletion. During the session that surfaced
this, `git push --force` and `echo git push --force` both executed *after* the
hook had matched them and written its block message. The force-push reached
`git` and failed only because the repo has no remote configured. With a remote
present, it would have pushed.

## Environment

| | |
|---|---|
| OS | Windows 11 Pro, `Microsoft Windows [Version 10.0.22631.6199]` |
| Claude Code (`claude --version`) | `2.1.226 (Claude Code)` |
| Claude Code (recorded in session transcript) | `2.1.266` |
| Install method | `native` (`~/.local/bin/claude`), per `installMethod` in `~/.claude.json` |
| Entrypoint | `claude-desktop` |
| Python (hook interpreter) | `3.14.3` |
| Permission mode during observations | `auto` |

### PowerShell — both installed

| Command | Resolves to | Version |
|---|---|---|
| `powershell` | `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` | `5.1.22621.6133` |
| `pwsh` | `C:\Program Files\PowerShell\7\pwsh.exe` | `7.6.6` |

**Which of these the harness spawns for `"shell": "powershell"` is UNKNOWN.**
It is not observable from inside a session — the hook payload, the transcript
records, and the tool results contain no interpreter identity. An earlier
revision of this draft asserted 5.1; that was an unfounded inference from a
manual `powershell` invocation in a Bash shell, not an observation of harness
behaviour, and has been removed.

Issue #90077 (see below) reports that `"shell": "powershell"` spawns `pwsh`.
If that is accurate, hooks on this machine run under **7.6.6**. I have not
confirmed it.

**Version discrepancy:** `claude --version` reports `2.1.226`, while every
transcript entry from the same session records `"version":"2.1.266"`. Both are
reported as-is; I could not determine which reflects the binary that executed
the hooks.

## Hook configuration

`.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "shell": "powershell",
            "command": "python \"$env:CLAUDE_PROJECT_DIR/.claude/hooks/guard_dangerous_bash.py\""
          }
        ]
      }
    ]
  }
}
```

The script reads the payload from stdin, matches the command against a regex
list, and on a match writes to stderr and returns 2:

```python
def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    for pattern, message in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(f"[blocked] {message}\nCommand was: {command}\n")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Reproduction

### Observed — this produced the evidence below

1. On Windows, configure the `PreToolUse` hook above with `"shell": "powershell"`.
2. Have the hook script return 2 for some command pattern.
3. Issue a matching command through the `Bash` tool.
4. **Expected:** the tool call is blocked.
   **Actual:** the hook's stderr appears, the transcript records
   `hook_non_blocking_error` with `"exitCode":1`, and the command executes.

### Suggested minimal reproduction — NOT VERIFIED IN THIS ENVIRONMENT

This would isolate the behaviour from anything repo-specific, but I was
**unable to test it**: registering an additional hook was blocked by the local
permission classifier, so this script was never run through the harness. It is
a proposal, not evidence.

```python
#!/usr/bin/env python3
"""Minimal PreToolUse repro: exit 2 on a sentinel string, else exit 0."""
import json
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    if "REPRO_SENTINEL_12345" in command:
        sys.stderr.write("[repro] blocking on sentinel\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Register as a `PreToolUse` hook with `"shell": "powershell"`, then run
`echo REPRO_SENTINEL_12345` through the Bash tool. If the bug reproduces, the
sentinel prints instead of the call being blocked.

## Evidence

### The key contrast

**Direct invocation returns 2, correctly.** Verified four ways, all consistent:

```
$ python .claude/hooks/guard_dangerous_bash.py < payload.json
[blocked] Refusing a force-push (including --force-with-lease). Confirm with the user first.
Command was: echo git push --force
HOOK_EXIT=2
```

Also verified via PowerShell with `$LASTEXITCODE` (returned `2`), and across
5 consecutive runs (all `2`).

**Harness invocation records 1.** One full transcript record, verbatim:

```json
{"type":"hook_non_blocking_error",
 "hookName":"PreToolUse:Bash",
 "toolUseID":"toolu_01FtQPLhyE1g81W9oZF5rMXp",
 "hookEvent":"PreToolUse",
 "stderr":"Failed with non-blocking status code: [blocked] Refusing a force-push (including --force-with-lease). Confirm with the user first.\r\nCommand was: echo git push --force",
 "stdout":"",
 "exitCode":1,
 "command":"python \"$env:CLAUDE_PROJECT_DIR/.claude/hooks/guard_dangerous_bash.py\"",
 "durationMs":629}
```

The command `echo git push --force` executed and printed its output.

Note that `stderr` is populated and `durationMs` is realistic — the hook
process ran and completed normally. Only the exit status is wrong. This
distinguishes the bug from an interpreter that failed to launch.

### Aggregate, one session transcript

| Measure | Count |
|---|---|
| Distinct tool calls where the hook matched and returned 2 | **15** |
| ...recorded as `hook_non_blocking_error` with `"exitCode":1` | **15** |
| ...recorded with `"exitCode":2` | **0** |
| Genuine `hook_blocking_error` events | **0** |
| Breakdown: `PreToolUse:Bash` | 13 |
| Breakdown: `PreToolUse:PowerShell` | 2 |

Every observation is `exitCode 1`. No successful block was recorded while the
hook was configured this way. **Both tool surfaces are affected**, so this is
not specific to the `Bash` tool.

To be precise about what varies: `hookName` records which *tool* triggered the
hook (`Bash` or `PowerShell`). In all 15 cases the *hook itself* was configured
`"shell": "powershell"`. The hook shell — not the tool — is the variable that
matters, as the next section shows.

## Localization — it is the PowerShell hook path

Changing **only the hook's shell** fixes it.

`"shell": "powershell"` → `"shell": "bash"` (the `$env:CLAUDE_PROJECT_DIR`
reference also has to become `$CLAUDE_PROJECT_DIR`, since that is PowerShell
variable syntax):

```json
{
  "type": "command",
  "shell": "bash",
  "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_dangerous_bash.py\""
}
```

Test payload: `echo git push -f.` — harmless, matches the hook's force-push
regex, and deliberately chosen to evade this repo's `permissions.deny` rules so
the hook is the only thing that can act on it.

**Result under `bash`: correctly blocked.** Verbatim:

```
PreToolUse:Bash hook error: [python "$CLAUDE_PROJECT_DIR/.claude/hooks/guard_dangerous_bash.py"]: [blocked] Refusing a force-push (including --force-with-lease). Confirm with the user first.
Command was: echo git push -f.
```

The command did not execute. Compare the `powershell` path, where the identical
script and payload produced `hook_non_blocking_error`, `"exitCode":1`, and the
command ran.

**Confound ruled out.** `python` exits 2 when it cannot open a script file, so a
broken path under `bash` would *also* produce a spurious "block". Two
independent checks confirm the script really ran:

1. The stderr is the script's own `[blocked] Refusing a force-push...` text. A
   missing-file error would read `can't open file`.
2. The hook appends every payload it receives to a debug log; the log gained an
   entry for exactly this invocation:
   `{"tool_name": "Bash", "command": "echo git push -f.", "hook_event": "PreToolUse"}`

### Confirmed independently on `PostToolUse`, with a different script

The same A/B was run on this repo's `PostToolUse` hook
(`post_edit_python.py`, matcher `Edit|Write`), which returns 2 when an edited
file under `services/api` contains a `TODO`/`FIXME`/`HACK`/`XXX`/
`NotImplementedError` with no `STUB(...)` marker.

Test: write `services/api/app/_stub_hook_test.py` containing a bare
`# TODO: fix later`. Direct invocation confirms the hook detects it and returns
2:

```
[stub-tracking] app\_stub_hook_test.py has stub/incomplete markers with no tracked reference:
  line 3: # TODO: fix later
DIRECT_EXIT=2
```

| Hook `shell` | Result | Transcript record |
|---|---|---|
| `"powershell"` | **Not blocked** — write succeeded silently, no error surfaced | `hook_non_blocking_error`, `"exitCode":1` |
| `"bash"` | **Blocked** — error fed back correctly | `hook_blocking_error`, **no `exitCode` field** |

Verbatim, under `bash`:

```
PostToolUse:Write hook blocking error from command: "python "$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_python.py"": [python "$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_python.py"]: [stub-tracking] app\_stub_hook_test.py has stub/incomplete markers with no tracked reference:
  line 3: # TODO: fix later
```

Note this is a **different script, different hook event, different matcher, and
a different exit-2 trigger** than the `PreToolUse` case — yet an identical
signature. That rules out anything specific to one script.

**Transcript shape difference.** Across the whole session: 16
`hook_non_blocking_error` attachments (every one `"exitCode":1`, all under
`powershell`) versus exactly 1 `hook_blocking_error` attachment (under `bash`).
The blocking record carries **no `exitCode` field at all**, so `exitCode`
appears to be recorded only on the non-blocking path.

**One thing this test does not establish.** It shows exit 2 blocks under `bash`
— correct behaviour — but it does not isolate whether the `bash` path honours
`2` specifically or treats *any* non-zero exit as blocking. Distinguishing
those needs a hook that exits 1 on purpose; registering an extra hook for that
was blocked by the local permission classifier, so it remains untested.

**Transcript note.** The successful block produced **no** new hook attachment
record. The harness appears to emit `hook_non_blocking_error` attachments — the
records carrying `exitCode` — only on the failing-classification path;
successful blocks surface inline as a tool error instead. So there is no
"`exitCode: 2`" record to show, and the transcript still contains exactly the
15 `exitCode: 1` entries from before the change. The absence of a new record is
itself the observation.

## Investigated and ruled out: #90077

[anthropics/claude-code#90077](https://github.com/anthropics/claude-code/issues/90077)
(open) — *"Hooks with shell: "powershell" spawn pwsh with no powershell.exe
fallback, so hooks silently never run on a stock Windows box."*

It reports that `"shell": "powershell"` spawns `pwsh`, which is absent on stock
Windows (which ships only `powershell.exe` 5.1), with no fallback — so the
interpreter never launches and the hook fails open. Its diagnostic steps are
`where pwsh` and `$PSVersionTable.PSVersion`.

**Ruled out as the root cause on this machine**, for two independent reasons:

1. `pwsh` **is** installed here — `7.6.6` at `C:\Program Files\PowerShell\7\pwsh.exe`.
   The missing-interpreter mechanism cannot apply.
2. The hook demonstrably **runs**: it emits its own stderr text and reports a
   realistic `durationMs` (484–629 ms across records). A hook whose interpreter
   failed to launch would produce neither.

Worth keeping as context: #90077 documents that the **hook** path and the
**tool** path resolve interpreters differently on Windows. That difference is
directly relevant to the open question at the top of this report, even though
its specific failure mechanism is not what is happening here.

## Possibly related — verified to exist, not confirmed duplicates

Both report the *same spurious exit-1 signature* on Windows, on the tool path
rather than the hook path:

- [#60664](https://github.com/anthropics/claude-code/issues/60664) (closed as
  duplicate of [#55727](https://github.com/anthropics/claude-code/issues/55727))
  — *"Windows: PowerShell tool returns Exit 1 silently — pwsh works fine outside
  CC."* PowerShell tool returns exit 1 with no output for trivial commands;
  works when invoked through Bash. Reporter hypothesises failed shell-snapshot
  generation.
- [#94196](https://github.com/anthropics/claude-code/issues/94196) (open) —
  *"Bash/PowerShell tool fails instantly on Windows — exit code 1, zero
  stdout/stderr, every command."* Described as a regression.

**Common thread:** Claude Code on Windows reporting a spurious exit code 1 when
spawning child shell processes, with the real exit status lost.

**Important difference:** in both of those, the child produces *no output at
all* and *every* command fails. Here the hook runs normally and its stderr is
captured intact — only the exit code is wrong, and non-matching commands
correctly return 0. So this may be a narrower manifestation of a shared
child-process-spawn defect, or an unrelated bug that happens to surface the
same exit code. I have not established which.

## Speculation — conditional on the interpreter question

The captured `stderr` uses `\r\n` (CRLF) line endings, consistent with a
PowerShell wrapper.

If hooks run under **PowerShell 7.3+** (which #90077 implies, and which would
mean 7.6.6 here), then `$PSNativeCommandUseErrorActionPreference` is a
candidate mechanism: when enabled, a native command writing to stderr can be
promoted to a terminating error, which can change what exit status the caller
observes.

If hooks run under **Windows PowerShell 5.1**, that mechanism does not exist
and this theory is inapplicable.

I have tested neither, and a direct `powershell` (5.1) invocation of the same
script propagated `2` correctly. Flagging it only as a lead that becomes
checkable once the interpreter question is settled.

The harness's own wrapper text — `"Failed with non-blocking status code: ..."`
— suggests the exit code was already non-2 by the time the harness classified
it.

## Expected behaviour

A `PreToolUse` hook exiting 2 should block the tool call, per the hooks
documentation. Either the exit code should propagate as 2, or a hook whose exit
status the harness cannot trust should fail **closed** rather than open — a
guard hook that silently permits is worse than one that errors loudly.

## Workarounds

1. **Set the hook's `"shell"` to `"bash"`** (requires Git Bash, and any
   `$env:VAR` references in the command must become `$VAR`). This restored
   correct blocking on this machine — see "Localization" above. This repo has
   kept the change.
2. **`permissions.deny` rules** in `.claude/settings.json` are enforced by the
   core permission engine and do not depend on hook exit codes at all. They
   blocked every command shape tested here, reliably. This is the stronger
   layer and is worth having regardless of (1).

Anyone relying on a `PreToolUse` hook with `"shell": "powershell"` as a safety
control on Windows should treat it as **non-functional** until this is fixed —
it will display its block message and permit the command anyway.
