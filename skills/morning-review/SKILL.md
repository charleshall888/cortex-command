---
name: morning-review
description: Guide the user through the morning report after an overnight session. Walks Executive Summary and report sections, collects answers to deferred questions, advances completed lifecycles to Complete, and auto-closes backlog tickets. Use when the user says "/morning-review", "morning review", or "what happened overnight".
disable-model-invocation: true
inputs: []
outputs:
  - "deferred/{feature}-q*.md — user answers appended under ## User Answer section"
  - "cortex/lifecycle/{feature}/events.log — phase_transition and feature_complete events appended for completed features"
preconditions:
  - "Morning report exists in one of: $CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/latest-overnight/morning-report.md, cortex/lifecycle/sessions/latest-overnight/morning-report.md, or cortex/lifecycle/morning-report.md"
---

# Morning Review

Interactive walkthrough of the morning report from an overnight session: Executive
Summary, completed features (batched, with overnight metadata), deferred questions, and
failed features, in order. Advances completed-feature lifecycles to Complete and
auto-closes backlog tickets at the end. See
`${CLAUDE_SKILL_DIR}/references/walkthrough.md` for the section-by-section protocol.

## Invocation

- `/morning-review` — start the morning report walkthrough

## Flow

### Step 0: Mark Overnight Session Complete

Before locating the report, mark the current overnight session complete if it's still
`executing`.

1. Check `~/.local/share/overnight-sessions/active-session.json`. If it exists with
   `"phase": "executing"`, use its `state_path` as `<resolved_state_path>` and invoke the
   helper WITH `--pointer <pointer_path>` (unlinks the pointer file on success).
2. Otherwise, fall back to `cortex/lifecycle/sessions/latest-overnight/overnight-state.json`
   (via the `latest-overnight` symlink) and invoke the helper WITHOUT `--pointer` — there's
   no pointer file to clean up.
3. If neither path resolves to a readable file, skip Step 0 — do not error.

```
cortex-morning-review-complete-session <resolved_state_path> [--pointer <pointer_path>]
```

The helper silent-skips unless phase is `executing`, so it's safe to invoke
unconditionally. Read the session ID from the resolved state file:

```
session_id="$(jq -r '.session_id' <resolved_state_path>)"
```

#### Garbage sweep: stale demo worktrees

After marking the session complete, sweep stale demo worktrees from prior sessions —
narrowly scoped to `$TMPDIR` worktrees matching Section 2a's demo pattern. The helper owns
resolution, active-session exclusion, and `git worktree remove`/`prune` ordering. Run it
after `cortex-morning-review-complete-session`, passing the resolved session ID:

```
cortex-morning-review-gc-demo-worktrees "$session_id"
```

### Step 1: Locate Report

Check for the morning report in order, using whichever path resolves first:

1. `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/latest-overnight/morning-report.md` —
   the MC session directory (new-style worktree sessions).
2. `cortex/lifecycle/sessions/latest-overnight/morning-report.md` — via a project-local
   `latest-overnight` symlink (if one exists).
3. `cortex/lifecycle/morning-report.md` — regular file overwritten by each overnight
   session's writer.

If none exist, tell the user no overnight session has been run yet, or the report wasn't
generated; suggest `cortex-report`. Stop.

**Staleness check**: read the session ID from the report heading (e.g.,
`overnight-2026-03-27-0121`) and compare it against Step 0's resolved state file. If they
differ, warn the user the report may be stale and ask whether to proceed or regenerate.

If a report is found, proceed to Step 2.

### Step 2: Display Executive Summary

Extract and display the Executive Summary from the Step-1 report — verdict, feature
counts (completed/failed/deferred), and session duration — before any interaction.

### Step 3: Walk Sections in Order

Work through the report sections in sequence, delegating the per-section protocol to
`${CLAUDE_SKILL_DIR}/references/walkthrough.md`:

1. **Completed Features** — display all at once (grouped by round, with overnight
   metadata), ask a single batch verification question.
2. **Demo Setup** — if a `demo-command(s):` config is present and the session is local,
   offer a demo worktree from the overnight branch (walkthrough §2a).
3. **Lifecycle Advancement** — immediately after verification, append completion events
   to each feature's `cortex/lifecycle/{feature}/events.log`.
4. **Deferred Questions** — display each question, collect a user answer, write it back
   to the corresponding `deferred/` file.
5. **Failed Features** — display error summary and suggested next step; offer a
   should-have backlog investigation item (walkthrough §4).

Skip any section with no entries — no placeholder or empty heading.

### Step 4: Auto-Close Backlog Tickets

Backlog ticket closure runs post-merge in walkthrough §6b, not here.

### Step 5: Commit Morning Review Artifacts

Before committing, sync with `origin/main`:

1. If the branch is detached HEAD or not `main`, skip to step 5.
2. Run `git fetch origin`. On failure, surface the error and ask whether to continue
   unsynced or abort — do not proceed silently.
3. Run `git rev-list HEAD..origin/main --count`. `0` → proceed to step 5.
4. Otherwise run `git pull --rebase origin main`. On success, proceed. On conflict or
   other error, surface git's output and get the user's confirmation that the branch is
   clean before continuing — do not invoke `/commit` until then.
5. Invoke the `/commit` skill to commit changes produced during the review
   (`cortex/lifecycle/{feature}/events.log` completion logs, `cortex/backlog/`
   closed/archived tickets and updated index). No additional confirmation is needed — the
   review is authoritative, and `/commit` composes the message from the staged diff.

### Step 6: PR Merge

After the commit, locate the PR for this session's integration branch, display it, and
offer to merge it to main. See `${CLAUDE_SKILL_DIR}/references/walkthrough.md` Section 6
for the full protocol.

After a successful merge, walkthrough Section 6a syncs local main to the remote and Section 6b closes each completed feature's ticket.

## Constraints

- Does not re-run or resume overnight sessions (use `/overnight resume`)
- Does not re-generate the morning report (use `cortex-report`)
- `overnight-state.json` is read-only except Step 0, which may write `phase: "complete"`
- Does not support resuming a partially-completed review; restart if interrupted
