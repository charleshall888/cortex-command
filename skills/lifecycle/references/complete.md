# Complete Phase

Verify tests pass, finalize git workflow, and summarize what was built.

## Protocol

### 1. Run Tests

Check for `lifecycle.config.md` and determine the test path:

- **Config exists with `test-command`**: Run the specified command.
- **Config exists without `test-command`**: Ask the user if there are tests to run.
- **No config exists**: Skip the test step. Note to the user: "No `lifecycle.config.md` found — skipping test step."

If tests are run and fail, report the failures and do not proceed to the git workflow until they are resolved.

### 2. Log Feature Complete

Append a `feature_complete` event to `lifecycle/{feature}/events.log` **before** the git workflow so the event is included in the commit:

```
{"ts": "<ISO 8601>", "event": "feature_complete", "feature": "<name>", "tasks_total": <N>, "rework_cycles": <N>}
```

- `tasks_total`: Count the total checkboxes (`- [ ]` and `- [x]`) in `lifecycle/{feature}/plan.md`.
- `rework_cycles`: Read the cycle count from `lifecycle/{feature}/review.md`. If no review phase occurred (simple tier), use `0`.

This event closes the event log for the feature.

**Backlog write-back**: If a matching backlog item was identified in Step 2 of `SKILL.md`, mark it complete and clear the session:

```bash
cortex-update-item <slug> status=complete session_id=null
```

If no backlog item was found, skip this silently.

**Backlog index sync**: After the `cortex-update-item` call (regardless of whether it succeeded, failed, or was skipped), regenerate the backlog index using this fallback chain:

1. If `cortex-update-item` was not found (`command -v cortex-update-item` failed), emit: `"WARNING: cortex-update-item not found — backlog item status may not be updated."`
2. Attempt index regeneration in order:
   - Run `test -f backlog/generate_index.py` — if it exists, run `python3 backlog/generate_index.py` and emit: `"Index regenerated via backlog/generate_index.py"`
   - Else run `command -v cortex-generate-backlog-index` — if found on PATH, run `cortex-generate-backlog-index` and emit: `"Index regenerated via cortex-generate-backlog-index"`
   - Else run `test -f ~/.local/bin/generate-backlog-index` — if that absolute path exists, run `python3 ~/.local/bin/generate-backlog-index` and emit: `"Index regenerated via ~/.local/bin/generate-backlog-index"`
   - Else emit: `"WARNING: Could not regenerate backlog index — no generate_index.py script found. Index may be stale."`

Each fallback is a separate Bash tool call using `test -f` or `command -v` to check availability before running.

### 3. Close Backlog Item

If the backlog write-back in Step 2 was skipped (no matching backlog item was identified earlier), attempt closure now:

```bash
cortex-update-item "{feature}" status=complete session_id=null
```

Handles: slug/UUID matching, in-place status update, `blocked-by` cleanup, and
parent epic auto-close. Index regeneration is performed by the explicit sync step
that follows. Exits 0 if updated; exits 1
if no match (silently acceptable — not all features originate from backlog items).

**Backlog index sync**: After the `cortex-update-item` call (regardless of whether it succeeded, failed, or was skipped), regenerate the backlog index using this fallback chain:

1. If `cortex-update-item` was not found (`command -v cortex-update-item` failed), emit: `"WARNING: cortex-update-item not found — backlog item status may not be updated."`
2. Attempt index regeneration in order:
   - Run `test -f backlog/generate_index.py` — if it exists, run `python3 backlog/generate_index.py` and emit: `"Index regenerated via backlog/generate_index.py"`
   - Else run `command -v cortex-generate-backlog-index` — if found on PATH, run `cortex-generate-backlog-index` and emit: `"Index regenerated via cortex-generate-backlog-index"`
   - Else run `test -f ~/.local/bin/generate-backlog-index` — if that absolute path exists, run `python3 ~/.local/bin/generate-backlog-index` and emit: `"Index regenerated via ~/.local/bin/generate-backlog-index"`
   - Else emit: `"WARNING: Could not regenerate backlog index — no generate_index.py script found. Index may be stale."`

Each fallback is a separate Bash tool call using `test -f` or `command -v` to check availability before running.

### 4. Git Workflow

Execute the appropriate workflow based on the current git state. Do not ask the user to choose — the correct action is determined by branch and change state.

**If there are uncommitted changes:**
Stage `lifecycle/{feature}/` artifacts alongside source changes, then use `/commit` to create the commit. If `lifecycle.config.md` specifies `commit-artifacts: false`, exclude lifecycle artifacts from staging.

**If on a feature branch (not main/master):**
Push the branch and use `/pr` to create a pull request with a summary of the feature.

**If on main/master:**
The changes are already committed to the main branch. No PR needed.

### 5. Summarize

Provide a brief summary of what was built:
- Feature name and description
- Number of tasks completed
- Key files created or modified
- Any open items or follow-up work identified during implementation or review

### 6. Lifecycle Directory

The `lifecycle/{feature}/` directory is preserved as project history. It contains the research, specification (if applicable), plan, and review (if applicable) artifacts. These may already be committed as part of the git workflow in step 2. Do not delete or archive the directory.

## Constraints

| Thought | Reality |
|---------|---------|
| "Tests are probably fine, the review already checked this" | The review checked spec compliance and code quality, not test execution. Run the tests. |
| "I'll fix failing tests later" | Failing tests mean the feature is not verified. Fix them now while context is fresh. |
| "Let me clean up the lifecycle directory" | The lifecycle directory is project documentation. Preserve it for future reference. |
