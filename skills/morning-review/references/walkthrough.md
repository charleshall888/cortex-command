# Morning Review Walkthrough Protocol

Detailed section-by-section protocol for the `/morning-review` skill. Follow these steps
in order after the report has been located and confirmed to exist.

---

## Section 1 — Executive Summary

Read `lifecycle/morning-report.md` (or the file it symlinks to). Locate the Executive
Summary section and extract:

- **Verdict**: the overall session outcome (e.g. "All features completed", "Partial —
  2 of 4 completed", "Session failed")
- **Feature counts**: number completed, failed, and deferred
- **Session duration**: start time, end time, and elapsed time

Display all three fields to the user before any interaction. This is the first output the
user sees. Do not ask questions or prompt for input during this step.

**Missing report handling**: If `lifecycle/morning-report.md` does not exist and
`lifecycle/sessions/` contains no subdirectories, print:

```
No morning report found. No overnight session has been run yet, or the report was not
generated. To generate one, run:

    python3 -m claude.overnight.report
```

Then stop. Do not proceed to later sections.

---

## Section 2 — Completed Features

Skip this section entirely if there are no completed features in the report.

**Load overnight metadata** (best-effort): read `lifecycle/sessions/latest-overnight/overnight-state.json` if it
exists. Parse the `features` map for `round_assigned`, `started_at`, and `completed_at`
per feature name. If the file is missing or a field is absent, omit that field from the
display — do not error.

**Display all features at once**, organized by round:

- Determine the unique set of round numbers across all completed features. If every
  feature shares the same round (or `round_assigned` is unavailable), omit round
  sub-headings entirely. If there are multiple rounds, emit `### Round N` before each
  group (ascending round order; within a round, preserve the report's feature order).
- For each feature, display a metadata line followed by its verification block:

  ```
  ### {feature-name}
  **Round:** N  |  **Duration:** Xm Ys  |  **Files changed:** N
  ```

  Then the verbatim "How to try" / verification commands block from the morning report.

  Duration is `completed_at − started_at` in human-readable form (`Xh Ym` or `Xm Ys`).
  "Files changed" is the count of bullet items in the feature's "Key files changed" list
  in the morning report. Omit any metadata field whose source value is null or missing.

**After all features are displayed, ask one question:**

```
Which features have you verified? ("all", "none", or a space/comma-separated list of names)
```

Parse the response:
- `"all"`, `"yes"`, `"done"`, `"y"` → mark every feature verified
- `"none"`, `"skip"`, `"s"`, `"no"` → mark every feature skipped
- Otherwise → treat as a feature-name list (space- or comma-separated); mark named ones
  verified, rest skipped. Fuzzy matching is acceptable (prefix or substring,
  case-insensitive).

Record verified/skipped status per feature, then proceed immediately to Section 2a (which may be skipped — see its guard clauses; if skipped, advance directly to Section 2b).
Verified/skipped statuses are for reporting context only — they do not gate lifecycle
advancement.

---

## Section 2a — Demo Setup

Skip this section entirely if any of the following hold:

### Guard 1 — `demo-command` is not configured

Skip Section 2a silently if ANY of the following hold:

- `lifecycle.config.md` at the project root is missing.
- `lifecycle.config.md` exists but a non-commented `demo-command:` line is absent.
- The `demo-command:` value is empty (whitespace-only after trimming).
- The `demo-command:` value contains any control character (byte < 0x20 except `\t`).

Parsing rules for the `demo-command:` field (apply these in order):

1. Read the file. For each non-blank line, strip leading whitespace.
2. If the stripped line begins with `#`, ignore it (comment line).
3. If the stripped line begins with `demo-command:`, extract everything after the first `:` character, then strip leading and trailing whitespace from the extracted value.
4. Reject the value if it contains any control character (byte < 0x20 except `\t`); treat as if the field were unset.
5. If no matching line was found, or the extracted value is empty, treat the field as unset.
6. Do NOT strip inline `#` comments from the value. Shell commands may legitimately contain `#`; there is no shell parser available at this layer to distinguish comment from literal. Users are responsible for keeping `demo-command` values free of trailing inline `#` comments.

> Implementer note (not user-facing): extract the value with `sed -n 's/^[[:space:]]*demo-command:[[:space:]]*//p'` or equivalent. Do NOT use `awk -F: '{print $2}'` — it discards everything after the second `:` and breaks on values like `godot res://main.tscn` (returning `//` instead of the verbatim command).

### Guard 2 — remote session

Skip Section 2a if `$SSH_CONNECTION` is set and non-empty. This catches both SSH and mosh sessions (mosh inherits `$SSH_CONNECTION` from the underlying SSH handshake).

### Guard 3 — overnight branch is missing

Skip Section 2a if `git rev-parse --verify {integration_branch}` exits non-zero, where `{integration_branch}` is read from `lifecycle/sessions/latest-overnight/overnight-state.json` using the same jq pattern as Section 6 step 1 (`jq -r '.integration_branch' lifecycle/sessions/latest-overnight/overnight-state.json`). If `overnight-state.json` is missing or `integration_branch` is absent from it, also skip.

<!-- SECTION-2A-CONTENT-INSERT: Task 5 appends the active-flow content here. -->

---

## Section 2b — Lifecycle Advancement

Run immediately after Section 2a (or after the batch verification response if Section 2a was skipped). No additional user input is needed.

For each completed feature (same list as Section 2, same order):

1. Check whether `lifecycle/{feature}/events.log` exists.
   - If the directory or file does not exist → skip, report `no lifecycle dir`.

2. Read `lifecycle/{feature}/events.log`. If it already contains a line where
   `"event": "feature_complete"` appears → skip, report `already complete`.

3. Read the feature's tier and criticality from `lifecycle/{feature}/events.log`:
   - **Tier**: scan for the last JSON line containing a `"tier"` field (from
     `lifecycle_start` or `complexity_override` events). If none found, default to
     `"simple"`. This mirrors `read_tier()` from `claude.common`.
   - **Criticality**: scan for the last JSON line containing a `"criticality"` field.
     If none found, default to `"medium"`. This mirrors `read_criticality()` from
     `claude.common`.

4. Apply the review gating check using the logic from `requires_review(tier, criticality)`
   in `claude.common`:
   - complex tier at any criticality → review required
   - any tier at high or critical criticality → review required
   - otherwise (simple/low, simple/medium) → review NOT required

5. **If review is NOT required**: write synthetic events. Count the total number of
   checkboxes in `lifecycle/{feature}/plan.md`:
   - Match all occurrences of `- [x]` and `- [ ]` (case-insensitive)
   - Sum = `tasks_total`. If `plan.md` does not exist, use `tasks_total: 0`.

   Append the following four events to `lifecycle/{feature}/events.log` (one JSON object
   per line, newline-terminated, no trailing comma). Use the current UTC time in ISO 8601
   format for all `ts` fields:

   ```json
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "implement", "to": "review"}
   {"ts": "<now>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED", "cycle": 0}
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
   {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": 0}
   ```

   Report: `advanced → complete`.

6. **If review IS required**: check `lifecycle/{feature}/events.log` for real review
   events written by the batch runner (these have `cycle >= 1`):

   a. **Both `review_verdict` (with `cycle >= 1`) AND `feature_complete` present**: the
      batch runner already completed the full review lifecycle. Skip synthetic events.
      Report: `already complete (reviewed)`.

   b. **`review_verdict` (with `cycle >= 1`) present but `feature_complete` missing**:
      partial write / crash recovery. Count checkboxes in `plan.md` as in step 5 and
      append only the remaining events:

      ```json
      {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
      {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": C}
      ```

      Where `C` is the cycle number from the last `review_verdict` event.
      Report: `advanced → complete (crash recovery)`.

   c. **Neither `review_verdict` (with `cycle >= 1`) nor `feature_complete` present**:
      this feature was expected to be reviewed overnight but no review occurred. Do NOT
      write synthetic APPROVED events. Report: `missing review — expected review but
      none found`.

Display the results as an inline summary before moving to Section 2c:

```
Lifecycle updates:
  fix-hardcoded-personal-paths-and-identifiers    advanced → complete
  add-public-sharing-documentation-to-readme      advanced → complete
```

---

## Section 2c — Requirements Drift Updates

After lifecycle advancement, scan each completed feature's `lifecycle/{feature}/events.log` for `requirements_updated` events. If none are found across any feature, skip this section entirely.

For each `requirements_updated` event found:

1. Read the event's `file`, `section`, and `content` fields.
2. Verify the update was actually applied by checking the named file for the content. If the file doesn't contain the expected content (e.g., overnight crash before write), flag it as `not applied — manual update needed`.

Display as a summary block:

```
Requirements updates (auto-applied during review):
  close-exfiltration-channels → requirements/project.md § Quality Attributes
    Added: Defense-in-depth for permissions...
  add-rate-limiting → requirements/pipeline.md § Architectural Constraints
    Added: Rate limiting for external API calls...
```

This block is informational — the updates were already applied during the review phase. The morning review surfaces them so the user is aware of changes to requirements docs.

---

## Section 3 — Deferred Questions

Skip this section entirely if there are no deferred question files matching
`deferred/{feature}-q*.md`.

For each deferred question file (iterate with: `deferred/{feature}-q*.md` for each
feature that appears in the report's deferred section, in report order; then within a
feature, walk files in filename sort order):

1. Display the feature name and question filename as a heading.
2. Read the file. Display:
   - The question text (from the body or a `question:` frontmatter field)
   - What the overnight lead tried (from a `tried:` or `## What was tried` section)
   - What is needed to unblock (from a `needed:` or `## What's needed` section)
3. Ask the user:

   ```
   Your answer (or "skip" to leave this question unanswered):
   ```

4. If the user provides an answer (anything other than "skip"/"s"/"later"), append the
   following block to the end of the file:

   ```
   ## User Answer (YYYY-MM-DD)

   {user's answer verbatim}
   ```

   Use today's date in `YYYY-MM-DD` format. Append after any existing content, separated
   by a blank line. Do not modify the YAML frontmatter or any existing sections.

5. If the file already contains one or more `## User Answer` sections, append the new
   answer block after the last existing one (same format, newer date).

6. If the user skips, leave the file unchanged.

**Deferred answer example:**

Suppose `deferred/auth-api-q1.md` contains:

```
---
feature: auth-api
question: "Should the token refresh endpoint accept POST or PUT?"
tried: "Implemented as POST; reviewer flagged ambiguity."
needed: "Product owner decision on HTTP verb semantics."
---

The auth-api implementation used POST for the token refresh endpoint but the API
design doc is silent on this choice. A decision is needed before the endpoint
ships.
```

After the user answers "Use POST — aligns with the existing /login endpoint", the file
becomes:

```
---
feature: auth-api
question: "Should the token refresh endpoint accept POST or PUT?"
tried: "Implemented as POST; reviewer flagged ambiguity."
needed: "Product owner decision on HTTP verb semantics."
---

The auth-api implementation used POST for the token refresh endpoint but the API
design doc is silent on this choice. A decision is needed before the endpoint
ships.

## User Answer (2026-02-25)

Use POST — aligns with the existing /login endpoint
```

---

## Section 4 — Failed Features

Skip this section entirely if there are no failed features in the report.

For each failed feature (in the order listed in the report):

1. Display the feature name as a heading.
2. Display the error summary from the report.
3. Display the suggested next step from the report (if present).
4. **Check for the integration branch annotation.** If the feature's report entry
   contains the text `Feature is on the integration branch`, this feature was
   successfully merged before a post-merge step failed — it is already on the
   integration branch. In this case:

   - State that the feature is already on the integration branch and was merged
     successfully.
   - Do **not** ask about creating an investigation or re-run ticket for the
     feature itself — creating one would duplicate work that already landed.
   - Instead, instruct the user to:
     - Verify the feature is present on the integration branch.
     - Identify which post-merge step failed by checking
       `lifecycle/sessions/latest-overnight/overnight-events.log`.
     - Address the missed step manually (e.g., trigger review, update the
       backlog item).
     - Advance the lifecycle manually to reflect the correct state.

   Then move on to the next failed feature — skip steps 5–7 below.

5. Otherwise (the feature is not annotated as on the integration branch), ask
   the user:

   ```
   Create a backlog investigation item for this failure? [yes / skip]
   ```

6. If the user says yes (or any affirmative), invoke `/backlog add` prefilled with:
   - **Title**: `Investigate failure: {feature-name}`
   - **Description**: the error summary and suggested next step from the report
   - **Tags**: `overnight-failure`, `investigation`

   Present the prefilled values to the user and let the `/backlog add` skill handle
   confirmation and file creation.

7. If the user says skip, move on without creating a backlog item.

---

## Section 5 — Auto-Close Backlog Tickets

Run after all sections above are complete. No per-feature confirmation is needed.

For each completed feature (the same list as Section 2, in the same order):

1. Run:

   ```
   update-item {backlog_id} status=complete
   ```

   Where `{backlog_id}` is the zero-padded numeric ID from `overnight-state.json`'s
   `backlog_id` field (e.g., `078` not `78`). If `backlog_id` is null, fall back to
   the lifecycle slug for fuzzy matching. Run from the repository root. The script
   exits 0 on success (item updated) and exits 1 silently if no item is found.

2. Report one of the following per feature:
   - `closed #ID` — if the script printed "Parent epic also closed: ..." or the item
     was found and updated (exit 0 with a matching item)
   - `no ticket found` — if the script exited 1

3. If `update_item.py` printed "Parent epic also closed: {path}", append
   `(parent epic also closed)` to the line for that feature.

Present the full closure results as a summary list at the end of the review. Example:

```
Ticket closure results:
  auth-api         closed #042
  data-pipeline    no ticket found
  ui-dashboard     closed #039 (parent epic also closed)
```

After printing the summary, proceed to Section 6.

---

## Section 6 — PR Review and Merge

Run after all other sections. No per-feature confirmation is needed before locating the PR.

1. Read `lifecycle/sessions/latest-overnight/overnight-state.json` and extract `integration_branch`.
   - If the file is missing or `integration_branch` is absent/empty, skip this section
     and note: "No integration branch found — skipping PR step."

2. Run:
   ```
   gh pr list --head {integration_branch} --json number,url,state,title
   ```
   Parse the JSON array.
   - If empty (no PR found): inform the user —
     "No PR found for `{integration_branch}`. The runner may have failed to create one.
     Use `/pr` to create it manually." Then stop.
   - If the PR's `state` is `"MERGED"`: report "PR already merged — main is up to date."
     Then stop.
   - If the PR's `state` is `"CLOSED"`: report "PR was closed without merging." Then stop.

3. Display the open PR (state is `"OPEN"` only — MERGED and CLOSED exit early in Step 2):
   ```
   PR:    [{url}]({url})
   Title: {title}
   State: {state}
   ```

   Then run `open {url} 2>/dev/null || true` to open the PR in the default browser.

4. Ask the user:
   ```
   Merge this PR to main? [yes / no]
   ```

5. If yes:
   - Run: `gh pr merge {number} --merge --delete-branch`
   - On success: report "Merged. Remote branch deleted."
     - Read `worktree_path` from `lifecycle/sessions/latest-overnight/overnight-state.json`.
       If non-empty and the path exists, run: `git worktree remove --force {worktree_path}`
       - On success: report "Worktree removed."
       - On failure: report the error but do not fail the review.
       - If `worktree_path` is absent, empty, or the path does not exist: skip removal silently.
   - On failure: show the error message and leave the PR open for manual resolution.

6. If no: leave the PR open and note: "PR left open at {url} — merge manually when ready."

After this section, proceed to Section 6a if a merge was performed.

---

## Section 6a — Post-merge sync

Run immediately after a successful merge in Section 6 (step 5, on success path). If the
merge was skipped, the PR was already merged, or the user declined to merge, skip this
section entirely.

After the PR merge, local main has local-only commits (morning report, review artifacts)
while remote main has the PR merge commit. This step reconciles the two.

1. Run:
   ```
   git-sync-rebase.sh claude/overnight/sync-allowlist.conf
   ```

2. Handle the exit code:

   - **Exit 0**: report "Local main synced and pushed — fully up to date."
   - **Exit 1**: report "Sync encountered unresolvable conflicts. Local main is diverged — resolve manually with `git pull --rebase origin main`."
   - **Exit 2**: report "Rebase succeeded but push failed. Run `git push origin main` when network is available."

After this section, the review is complete.

---

## Edge Cases

| Situation | Action |
|-----------|--------|
| No morning report at `lifecycle/morning-report.md` | Print missing-report message (Section 1) and stop |
| `lifecycle/sessions/` exists but report is missing | Print "Incomplete session detected — report not generated. Run: `python3 -m claude.overnight.report`" and stop |
| No completed features | Skip Sections 2, 2b, and 5 entirely |
| No deferred question files | Skip Section 3 entirely |
| No failed features | Skip Section 4 entirely |
| Single completed feature | Still use the batch prompt — consistent UX regardless of count |
| All features in same round | Omit `### Round N` sub-headings to reduce noise |
| `overnight-state.json` missing | Display features flat (no round grouping or duration) |
| `started_at` or `completed_at` null | Omit Duration field for that feature |
| `feature_complete` already in events.log | Report `already complete`; do not append events |
| `lifecycle/{feature}/` dir missing | Report `no lifecycle dir`; skip advancement |
| `plan.md` missing | Use `tasks_total: 0` in `feature_complete` event |
| No tier in events.log | Default to `"simple"` (mirrors `read_tier()`) |
| No criticality in events.log | Default to `"medium"` (mirrors `read_criticality()`) |
| Review-required feature with real review_verdict + feature_complete | Report `already complete (reviewed)`; skip synthetic events |
| Review-required feature with review_verdict but no feature_complete | Crash recovery: write remaining events to complete the lifecycle |
| Review-required feature with no review events | Error state: report `missing review`; do NOT write synthetic APPROVED |
| Multiple deferred files for one feature | Walk all of them in filename sort order within Section 3 |
| Deferred file already has `## User Answer` section | Append new answer block after the last existing one |
| `update_item.py` exits 1 (no item found) | Report "no ticket found" — not an error |
| `update_item.py` exits non-zero for another reason | Report "close failed (exit {N})" for that feature and continue |
| `overnight-state.json` has no `integration_branch` | Skip Section 6 with a note |
| `gh pr list` returns empty array | Inform user, suggest `/pr` to create manually |
| PR state is MERGED | Report already merged, skip merge prompt |
| PR state is CLOSED | Report closed without merging, skip merge prompt |
| `gh pr merge` fails | Show error, leave PR open for manual resolution |
| `open` command fails | Run `open {url} 2>/dev/null || true` — review continues |
| `worktree_path` in state doesn't exist on disk | Skip worktree removal silently, continue |
| `git-sync-rebase.sh` exits 0 | Report synced and pushed — fully up to date |
| `git-sync-rebase.sh` exits 1 (unresolvable conflicts) | Report diverged — resolve manually with `git pull --rebase origin main` |
| `git-sync-rebase.sh` exits 2 (push failed) | Report rebase succeeded — run `git push origin main` when network available |
| Merge was declined or skipped | Skip Section 6a entirely |
| `git-sync-rebase.sh` not found | Report missing script, skip sync, note "run `just deploy-bin` to install" |
| Dirty `.git/rebase-merge/` detected | Script auto-aborts stale rebase, warns user, proceeds with sync |
| Push fails after rebase | Report error, note local main is clean but not pushed |
| All conflicts auto-resolved | Report "N files auto-resolved via allowlist" |
