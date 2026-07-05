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

Interactive walkthrough of the morning report produced by an overnight session. Guides the user through the Executive Summary, completed features (batched with overnight metadata), deferred questions, and failed features in order. Advances completed-feature lifecycles to Complete and auto-closes backlog tickets at the end. See `${CLAUDE_SKILL_DIR}/references/walkthrough.md` for the section-by-section protocol.

## Invocation

- `/morning-review` — start the morning report walkthrough

## Flow

### Step 0: Mark Overnight Session Complete

Before locating the report, mark the current overnight session as complete if it is still in the `executing` phase.

Locate the session to update:

1. Check `~/.local/share/overnight-sessions/active-session.json`. If it exists and contains `"phase": "executing"`, use its `state_path` value as the path to `overnight-state.json`.
2. If the pointer file does not exist, is not readable, or its `phase` is not `"executing"`, fall back to resolving `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` (via the `latest-overnight` symlink).
3. If neither path resolves to a readable file, skip Step 0 entirely — do not error.

If `<resolved_state_path>` resolves to a readable file, mark the session complete by invoking the helper. It silent-skips unless phase is `executing`, so it is safe to invoke unconditionally.

- If you used the active-session pointer (the path-resolution branch above selected line 1's pointer because its `phase == "executing"`), invoke the helper WITH `--pointer` so the pointer file is unlinked on success:

  ```
  cortex-morning-review-complete-session <resolved_state_path> --pointer <pointer_path>
  ```

- If you used the `cortex/lifecycle/sessions/latest-overnight` fallback (line 2 above), invoke the helper WITHOUT `--pointer` — there is no pointer file to clean up:

  ```
  cortex-morning-review-complete-session <resolved_state_path>
  ```

Read the session ID from the resolved state file:

```
session_id="$(jq -r '.session_id' <resolved_state_path>)"
```

#### Garbage sweep: stale demo worktrees

After marking the session complete, sweep stale demo worktrees from prior overnight sessions. The sweep is narrow — it only touches `$TMPDIR` worktrees matching Section 2a's demo-worktree pattern, so it cannot collide with unrelated worktrees. The helper owns the resolution, active-session exclusion, uncommitted-state precondition, and the `git worktree remove`/`prune` ordering.

The sweep runs after `cortex-morning-review-complete-session`. Pass the resolved active session ID as the script's positional argument:

```
cortex-morning-review-gc-demo-worktrees "$session_id"
```

### Step 1: Locate Report

Check for the morning report in order:

1. `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/latest-overnight/morning-report.md` — the MC session directory (new-style worktree sessions).
2. `cortex/lifecycle/sessions/latest-overnight/morning-report.md` — reachable via a project-local `latest-overnight` symlink (if one exists)
3. `cortex/lifecycle/morning-report.md` — regular file overwritten by each overnight session's writer.

Use whichever path resolves first. If none exist, report that no morning report was found. Tell the user that no overnight session has been run yet, or the report was not generated. Suggest running `cortex-report` to generate one. Stop.

**Staleness check**: After locating the report, read the session ID from the report heading (e.g., `overnight-2026-03-27-0121`). Compare it against the session ID in the state file resolved during Step 0. If they differ, warn the user that the report may be stale and ask whether to proceed or regenerate.

If a report is found, proceed to Step 2.

### Step 2: Display Executive Summary

Read the morning report located in Step 1. Extract and display the Executive Summary section to the user: the session verdict, feature counts (completed / failed / deferred), and session duration. This is the first thing the user sees before any interaction.

### Step 3: Walk Sections in Order

Work through the report sections in sequence. Delegate the per-section interaction protocol to `${CLAUDE_SKILL_DIR}/references/walkthrough.md`:

1. **Completed Features** — display all features at once (grouped by round, enriched with overnight metadata), ask a single batch verification question
2. **Demo Setup** — if a `demo-command(s):` config is present and the session is local, offer a demo worktree from the overnight branch (walkthrough §2a owns path selection, guards, and entry reasoning).
3. **Lifecycle Advancement** — immediately after verification: append completion events to each feature's `cortex/lifecycle/{feature}/events.log`
4. **Deferred Questions** — display each question and collect a user answer; write the answer back to the corresponding `deferred/` file
5. **Failed Features** — display error summary and suggested next step; offer a should-have backlog investigation item. Walkthrough §4 owns the compose/backend-route protocol.

Skip any section that has no entries — do not display a placeholder or empty heading.

### Step 4: Auto-Close Backlog Tickets

Backlog ticket closure runs post-merge in walkthrough §6b, not here.

### Step 5: Commit Morning Review Artifacts

Before committing, run a preflight git sync:

1. Check the current branch. If it is detached HEAD or is not `main`, skip steps 2–4 and proceed directly to step 5.
2. Run `git fetch origin`. If the fetch fails (network error, no remote), surface the error and ask the user whether to continue without syncing or abort. Do not proceed silently.
3. Run `git rev-list HEAD..origin/main --count`. If the output is `0`, no pull is needed — proceed to step 5.
4. If the count is greater than `0`, run `git pull --rebase origin main`. If the rebase succeeds, proceed to step 5. If it fails (conflict or other error), surface git's output, pause, and ask the user to resolve the issue and confirm before continuing. Do not invoke `/commit` until the user confirms the branch is clean.
5. Invoke the `/commit` skill to commit all changes produced during the review:

- `cortex/lifecycle/{feature}/events.log` — newly created completion event logs
- `cortex/backlog/` — closed/archived ticket files and updated index

No additional user input is needed before committing — the review is authoritative. Let the `/commit` skill compose the message from the staged diff.

### Step 6: PR Merge

After the commit, locate the PR that the runner created for this session's integration branch, display it to the user, and offer to merge it to main. See `${CLAUDE_SKILL_DIR}/references/walkthrough.md` Section 6 for the full protocol.

After a successful merge, walkthrough Section 6a syncs local main to the remote and Section 6b closes each completed feature's ticket.

## Constraints

- Does not re-run or resume overnight sessions (use `/overnight resume`)
- Does not re-generate the morning report (use `cortex-report`)
- `overnight-state.json` is read-only except Step 0, which may write `phase: "complete"`
- Does not support resuming a partially-completed review; restart if interrupted
