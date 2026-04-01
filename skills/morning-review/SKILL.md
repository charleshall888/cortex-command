---
name: morning-review
description: Guide the user through the morning report after an overnight session. Displays the Executive Summary, walks each report section in order, collects answers to deferred questions, advances completed-feature lifecycles to Complete, and auto-closes backlog tickets at the end. Use when the user says "/morning-review", "morning review", "review overnight", "morning report walkthrough", or "what happened overnight".
disable-model-invocation: true
inputs: []
outputs:
  - "deferred/{feature}-q*.md — user answers appended under ## User Answer section"
  - "lifecycle/{feature}/events.log — phase_transition and feature_complete events appended for completed features"
preconditions:
  - "Morning report exists in one of: $CORTEX_COMMAND_ROOT/lifecycle/sessions/latest-overnight/morning-report.md, lifecycle/sessions/latest-overnight/morning-report.md, or lifecycle/morning-report.md"
---

# Morning Review

Interactive walkthrough of the morning report produced by an overnight session. Guides the user through the Executive Summary, completed features (batched with overnight metadata), deferred questions, and failed features in order. Advances completed-feature lifecycles to Complete and auto-closes backlog tickets at the end. See `references/walkthrough.md` for the section-by-section protocol.

## Invocation

- `/morning-review` — start the morning report walkthrough

## Flow

### Step 0: Mark Overnight Session Complete

Before locating the report, mark the current overnight session as complete if it is still in the `executing` phase.

Locate the session to update:

1. Check `~/.local/share/overnight-sessions/active-session.json`. If it exists and contains `"phase": "executing"`, use its `state_path` value as the path to `overnight-state.json`.
2. If the pointer file does not exist, is not readable, or its `phase` is not `"executing"`, fall back to resolving `lifecycle/sessions/latest-overnight/overnight-state.json` (via the `latest-overnight` symlink).
3. If neither path resolves to a readable file, skip Step 0 entirely — do not error.

If a session is found with `phase == "executing"`, write `phase: "complete"` to it:

```
python3 -c "
import json, os, tempfile, pathlib

state_path = pathlib.Path('<resolved_state_path>')
data = json.loads(state_path.read_text())
if data.get('phase') != 'executing':
    exit(0)
data['phase'] = 'complete'
tmp = tempfile.NamedTemporaryFile(mode='w', dir=state_path.parent, delete=False, suffix='.tmp')
json.dump(data, tmp, indent=2)
tmp.flush()
os.fsync(tmp.fileno())
tmp.close()
os.rename(tmp.name, state_path)
"
```

After updating `overnight-state.json`, also update the pointer file's `phase` field to `"complete"` using the same atomic pattern (read → update `phase` key → write via tmp + rename). Skip pointer update if Step 0 used the fallback path (no pointer file).

Skip Step 0 entirely if no session is found or the session phase is already terminal (anything other than `"executing"`).

### Step 1: Locate Report

Check for the morning report in order:

1. `$CORTEX_COMMAND_ROOT/lifecycle/sessions/latest-overnight/morning-report.md` — the MC session directory (new-style worktree sessions).
2. `lifecycle/sessions/latest-overnight/morning-report.md` — reachable via a project-local `latest-overnight` symlink (if one exists)
3. `lifecycle/morning-report.md` — exists as a file or symlink (old-style sessions)

Use whichever path resolves first. If none exist, report that no morning report was found. Tell the user that no overnight session has been run yet, or the report was not generated. Suggest running `python3 -m claude.overnight.report` to generate one. Stop.

**Staleness check**: After locating the report, read the session ID from the report heading (e.g., `overnight-2026-03-27-0121`). Compare it against the session ID in the state file resolved during Step 0. If they differ, warn the user that the report may be stale and ask whether to proceed or regenerate.

If a report is found, proceed to Step 2.

### Step 2: Display Executive Summary

Read the morning report located in Step 1. Extract and display the Executive Summary section to the user: the session verdict, feature counts (completed / failed / deferred), and session duration. This is the first thing the user sees before any interaction.

### Step 3: Walk Sections in Order

Work through the report sections in sequence. Delegate the per-section interaction protocol to `references/walkthrough.md`:

1. **Completed Features** — display all features at once (grouped by round, enriched with overnight metadata), ask a single batch verification question
2. **Lifecycle Advancement** — immediately after verification: append completion events to each feature's `lifecycle/{feature}/events.log`
3. **Deferred Questions** — display each question and collect a user answer; write the answer back to the corresponding `deferred/` file
4. **Failed Features** — display error summary and suggested next step; offer to create a backlog investigation item (should-have)

Skip any section that has no entries — do not display a placeholder or empty heading.

### Step 4: Auto-Close Backlog Tickets

After all sections are walked, close each completed feature's backlog ticket. No per-feature confirmation is needed.

**Slug resolution**: The overnight state stores lifecycle slugs (e.g., `enemy-chase-ai-upgrade-simpleenemy-to-characterbody2d-with-direct-steering`) which are longer than backlog file slugs (e.g., `036-enemy-chase-ai`). The `update-item` script accepts backlog file slugs or numeric IDs — not lifecycle slugs.

To resolve: read each feature's `backlog_id` field from `overnight-state.json` (the state file located in Step 0). Pass the zero-padded numeric ID to `update-item`:

```
update-item 078 status=complete
```

**Important**: IDs must be zero-padded to 3 digits (e.g., `078` not `78`). Unpadded IDs return "Item not found".

If `backlog_id` is not set for a feature, fall back to passing the lifecycle slug — `update-item` does substring matching and may still find a match.

For each feature report one of:
- `closed #ID` — ticket was found and updated
- `no ticket found` — `update_item.py` exited 1 (item not found or already terminal)

Report the results as a summary list before proceeding to Step 5.

### Step 5: Commit Morning Review Artifacts

Before committing, run a preflight git sync:

1. Check the current branch. If it is detached HEAD or is not `main`, skip steps 2–4 and proceed directly to step 5.
2. Run `git fetch origin`. If the fetch fails (network error, no remote), surface the error and ask the user whether to continue without syncing or abort. Do not proceed silently.
3. Run `git rev-list HEAD..origin/main --count`. If the output is `0`, no pull is needed — proceed to step 5.
4. If the count is greater than `0`, run `git pull --rebase origin main`. If the rebase succeeds, proceed to step 5. If it fails (conflict or other error), surface git's output, pause, and ask the user to resolve the issue and confirm before continuing. Do not invoke `/commit` until the user confirms the branch is clean.
5. Invoke the `/commit` skill to commit all changes produced during the review:

- `lifecycle/{feature}/events.log` — newly created completion event logs
- `backlog/` — closed/archived ticket files and updated index

No additional user input is needed before committing — the review is authoritative. Let the `/commit` skill compose the message from the staged diff.

### Step 6: PR Merge

After the commit, locate the PR that the runner created for this session's integration branch, display it to the user, and offer to merge it to main. See `references/walkthrough.md` Section 6 for the full protocol.

## Constraints

- Does not re-run or resume overnight sessions (use `/overnight resume`)
- Does not re-generate the morning report (use `python3 -m claude.overnight.report`)
- Reads `overnight-state.json` for metadata from the session directory (resolved via `lifecycle/sessions/latest-overnight/` symlink for new-style worktree sessions, or directly from `lifecycle/overnight-state.json` for old-style sessions); Step 0 may write `phase: "complete"` to it — all other steps are read-only
- Does not support resuming a partially-completed review; restart if interrupted
