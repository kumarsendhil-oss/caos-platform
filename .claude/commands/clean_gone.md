---
description: Cleans up all git branches marked as [gone] (branches that have been deleted on the remote but still exist locally), including removing associated worktrees.
---

## Your Task

You need to execute the following bash commands to clean up stale local
branches that have been deleted from the remote repository.

> **Project override.** This shadows the `commit-commands` plugin's
> version of `clean_gone`, which detects `[gone]` with `git branch -v`.
> `-v` never prints `[gone]` markers — only `-vv` does — so the plugin
> version's grep matches nothing and it reports "no cleanup was needed"
> whether or not stale branches exist. That is a silent false negative:
> it looks like a clean result. Observed on this repo 2026-09-16, where
> `-v` found nothing and `-vv` confirmed there was genuinely nothing to
> find — the right answer by luck, not by working. Keep the `-vv` and
> the prune below if this file is ever re-synced from upstream.

## Commands to Execute

1. **First, prune stale remote-tracking refs — required, not optional**
   Execute this command:
   ```bash
   git fetch --prune
   ```

   `[gone]` means "the remote-tracking ref is absent". Git only learns a
   remote branch was deleted when the tracking ref is pruned, so without
   this the markers reflect whenever someone last fetched. A branch
   deleted on the remote an hour ago will not be marked `[gone]` until
   this runs, and a branch already deleted locally-but-not-pruned can
   still look live.

2. **Next, list branches to identify any with [gone] status**
   Execute this command:
   ```bash
   git branch -vv
   ```

   Note: `-vv` (not `-v`) is what prints the tracking-branch column that
   carries the `[gone]` marker. Branches with a '+' prefix have
   associated worktrees and must have their worktrees removed before
   deletion.

3. **Next, identify worktrees that need to be removed for [gone] branches**
   Execute this command:
   ```bash
   git worktree list
   ```

4. **Report the list before deleting anything**

   Show the user which branches are about to be deleted and wait for
   confirmation. Step 5 uses `git branch -D`, a force delete that
   ignores merge status — an unmerged commit on a `[gone]` branch is
   gone with it, recoverable only via reflog. For each branch, report
   whether it is merged into the default branch:

   ```bash
   git branch --merged main --list "<branch>"        # empty output = NOT merged
   git rev-list --count main.."<branch>"             # commits not on main
   ```

   A `[gone]` branch that is not merged is the case worth pausing on:
   the remote branch was deleted while local work on it was never
   integrated.

5. **Finally, remove worktrees and delete [gone] branches (handles both regular and worktree branches)**
   Execute this command:
   ```bash
   # Process all [gone] branches, removing '+' prefix if present
   git branch -vv | grep '\[gone\]' | sed 's/^[+* ]//' | awk '{print $1}' | while read branch; do
     echo "Processing branch: $branch"
     # Find and remove worktree if it exists
     worktree=$(git worktree list | grep "\\[$branch\\]" | awk '{print $1}')
     if [ ! -z "$worktree" ] && [ "$worktree" != "$(git rev-parse --show-toplevel)" ]; then
       echo "  Removing worktree: $worktree"
       git worktree remove --force "$worktree"
     fi
     # Delete the branch
     echo "  Deleting branch: $branch"
     git branch -D "$branch"
   done
   ```

## Expected Behavior

After executing these commands, you will:

- Prune stale remote-tracking refs so `[gone]` reflects the remote's
  actual current state
- See a list of all local branches with their tracking status
- Identify and remove any worktrees associated with `[gone]` branches
- Report what will be deleted, and whether each branch is merged, before
  deleting
- Delete all branches marked as `[gone]`
- Provide feedback on which worktrees and branches were removed

If no branches are marked as `[gone]`, report that no cleanup was
needed — and say that the prune ran, so the result is current rather
than an artifact of a stale fetch.
