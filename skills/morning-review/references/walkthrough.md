# Morning Review Walkthrough Protocol

Detailed section-by-section protocol for the `/morning-review` skill. Follow these steps
in order after the report has been located and confirmed to exist.

---

## Section 1 — Executive Summary

Read `cortex/lifecycle/morning-report.md` (or the file it symlinks to). Locate the Executive
Summary section and extract:

- **Verdict**: the overall session outcome (e.g. "All features completed", "Partial —
  2 of 4 completed", "Session failed")
- **Feature counts**: number completed, failed, and deferred
- **Session duration**: start time, end time, and elapsed time

Display all three fields before any interaction; ask nothing here.

**Missing report handling**: If `cortex/lifecycle/morning-report.md` does not exist and
`cortex/lifecycle/sessions/` contains no subdirectories, print:

```
No morning report found. No overnight session has been run yet, or the report was not
generated. To generate one, run:

    cortex-report
```

Then stop. Do not proceed to later sections.

---

## Section 2 — Completed Features

Skip this section entirely if there are no completed features in the report.

**Load overnight metadata** (best-effort): read `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` if it
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

Record verified/skipped status per feature, then proceed immediately to Section 2a. Verified/skipped statuses are for reporting context only — they do not gate lifecycle advancement.

---

## Section 2a — Demo Setup

Skip this section entirely if any of the following hold:

### Guard 1 — Route between `demo-commands:` list and `demo-command:` single-string paths

This guard determines which of two configuration schemas is active in `cortex/lifecycle.config.md` and routes the rest of Section 2a accordingly. If `cortex/lifecycle.config.md` at the project root is missing, skip Section 2a silently. Otherwise, try the `demo-commands:` list path first; if it yields no valid entries, fall back to the `demo-command:` single-string path; if neither is configured, skip Section 2a silently.

#### `demo-commands:` list path (tried first)

Parsing rules for the `demo-commands:` list (apply these in order):

1. Read the file. Scan for the first non-commented line that, after stripping leading whitespace, exactly matches `demo-commands:` (the bare key with no inline value).
2. If found, collect the subsequent indented entries of the form `- label: "..."` / `command: "..."` as list entries, stopping at the first non-indented, non-blank line (this terminates the list).
3. For each entry, extract the `label:` and `command:` values using first-colon extraction: take everything after the first `:` character on the line, then trim leading and trailing whitespace (shell commands may contain additional `:` — e.g. `godot res://main.tscn`).
4. Reject any entry whose `command:` value contains a control character (byte < 0x20 except `\t`); silently discard that entry.
5. Reject any entry whose `command:` value is empty or whitespace-only after trimming; silently discard that entry.
6. Do NOT strip inline `#` comments from `command:` values. Shell commands may legitimately contain `#`; there is no shell parser available at this layer to distinguish comment from literal. Users are responsible for keeping list `command:` values free of trailing inline `#` comments.
7. If at least one valid entry remains, the active path is `demo-commands:` list. Proceed to Guard 2, then Guard 3, then the demo-commands: list flow below.

If `demo-commands:` was absent, or was present but yielded no valid entries, fall through to the `demo-command:` single-string check below.

#### `demo-command:` single-string path (fallback)

Skip this path (and therefore Section 2a, if the list path also did not activate — i.e. no valid entries and fall through to demo-command check also yields nothing) silently if ANY of the following hold:

- `cortex/lifecycle.config.md` exists but a non-commented `demo-command:` line is absent.
- The `demo-command:` value is empty (whitespace-only after trimming).
- The `demo-command:` value contains any control character (byte < 0x20 except `\t`).

Parsing rules for the `demo-command:` field (apply these in order):

1. Read the file. For each non-blank line, strip leading whitespace.
2. If the stripped line begins with `#`, ignore it (comment line).
3. If the stripped line begins with `demo-command:`, extract everything after the first `:` character, then strip leading and trailing whitespace from the extracted value.
4. Reject the value if it contains any control character (byte < 0x20 except `\t`); treat as if the field were unset.
5. If no matching line was found, or the extracted value is empty, treat the field as unset.
6. Do NOT strip inline `#` comments from the value — same inline-`#` rule as the list path (rule 6 above).

If a non-empty, control-character-free value is found, the active path is `demo-command:` single-string. Proceed to Guard 2, then Guard 3, then the existing single-string flow. If neither the list path nor the single-string path is active, skip Section 2a silently.

### Guard 2 — remote session

Skip Section 2a if `$SSH_CONNECTION` is set and non-empty. This catches both SSH and mosh sessions (mosh inherits `$SSH_CONNECTION` from the underlying SSH handshake).

### Guard 3 — overnight branch is missing

Skip Section 2a if `git rev-parse --verify {integration_branch}` exits non-zero, where `{integration_branch}` is read from `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` using the same jq pattern as Section 6 step 1 (`jq -r '.integration_branch' cortex/lifecycle/sessions/latest-overnight/overnight-state.json`). If `overnight-state.json` is missing or `integration_branch` is absent from it, also skip.

**If on the `demo-commands:` list path only (this third check does NOT apply to the `demo-command:` single-string path):** additionally read the `features` map from `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` and count entries whose `"status"` equals `"merged"`. If there are zero merged features, skip Section 2a silently. If `overnight-state.json` is missing the `features` key entirely, treat this as zero merged features and skip.

### Agent Reasoning

**If on the `demo-commands:` list path and all three guards above pass:** reason about which configured `demo-commands:` entry is most contextually relevant to the night's merged features, then either select one entry and proceed to the Demo offer, or skip Section 2a silently.

Constraints and inputs for the reasoning step:

1. **No additional git commands are run for this step.** The input is the completed-features list already in context from Section 2, including each feature's **Key files changed** data. Do NOT re-read `git log`, `git diff`, or any file tree.
2. Consider each configured entry's `label:` and `command:` alongside the merged features' names and **Key files changed** paths. A `demo-commands:` entry whose label or command clearly maps to the area the night's work touched is a candidate.
3. If a single entry is clearly the most relevant winner, select it and proceed to the Demo offer (`demo-commands:` list path variant) using that entry's `label` as `{selected-label}` and its `command` as `{selected-command}`.
4. If no entry is clearly relevant — the night's work does not map cleanly onto any configured demo — **skip Section 2a silently**. This suppression is absolute: do NOT fall back to the `demo-command:` single-string path even if that field is also configured in the same `cortex/lifecycle.config.md`. The list path, once active, owns the decision; the single-string fallback does not fire when the `demo-commands:` list path is active.

### Demo offer

If all guards above pass, ask the user a single yes/no question and take no further input from this section. Use the variant matching the active path:

#### `demo-commands:` list path variant

**Use this variant only if the active path is `demo-commands:` list and the Agent Reasoning step selected an entry.** Ask:

> Run `{selected-label}` demo (`{selected-command}`) from `{integration_branch}` in a fresh worktree? [y / n]

Substitute `{selected-label}` with the chosen entry's `label:` value and `{selected-command}` with its `command:` value. Paraphrasing of the prose around the placeholders is acceptable; the `{selected-label}` and `{selected-command}` placeholders themselves are load-bearing.

#### `demo-command:` single-string path variant

**Use this variant only if the active path is `demo-command:` single-string.** Ask (preserved unchanged from the pre-list-path wording):

> Spin up a demo worktree of `{integration_branch}` at `$TMPDIR/demo-{session_id}-{timestamp}` and print the launch command? [y / n]

---

For both variants: on `n` or any unparseable input, advance to Section 2b. On `y`, proceed to the shared worktree creation step below. Section 2a must not ask any follow-up questions.

### Worktree creation

On `y`:

1. Resolve the temp directory: `realpath "$TMPDIR"` and capture the output as `{resolved-tmpdir}`.
2. Build the target path: `{resolved-tmpdir}/demo-{session_id}-{timestamp}`, where `{timestamp}` is produced by `$(date -u +%Y%m%dT%H%M%SZ)`.
3. Run exactly this command:

       git -c core.hooksPath=/dev/null worktree add "{target-path}" "{integration_branch}"

   The `git -c core.hooksPath=/dev/null` prefix is mandatory — it neutralizes any tracked `post-checkout` hook (e.g., husky or lefthook) on the overnight branch. Do NOT use `--force`. Do NOT use `git -C` (uppercase); `git -c` (lowercase) is a distinct, allowed flag.
4. On non-zero exit, print the captured stderr and advance to Section 2b. Do not retry. Do not invoke any cleanup.

### Print template

After a successful worktree-add, print the block matching the active path. `{resolved-target-path}` is the absolute path from the Worktree creation step.

#### `demo-command:` single-string path variant

**Use this variant only if the active path is `demo-command:` single-string.** Print exactly this block, substituting `{resolved-target-path}` with the absolute path from the previous step and `{demo-command}` with the verbatim value extracted from `cortex/lifecycle.config.md` (already validated by the config check above to contain no control characters):

```
Demo worktree created at: {resolved-target-path}

To start the demo, run this in a separate terminal or shell:
    {demo-command}

When you're done, close the demo and remove the worktree:
    git worktree remove {resolved-target-path}
```

#### `demo-commands:` list path variant

**Use this variant only if the active path is `demo-commands:` list and the Agent Reasoning step selected an entry.** Print exactly this block, substituting `{resolved-target-path}` with the absolute path from the Worktree creation step, `{selected-label}` with the chosen entry's `label:` value, and `{selected-command}` with its `command:` value (both already validated by the list parsing rules above to contain no control characters):

```
Demo worktree created at: {resolved-target-path}

To start the demo ({selected-label}), run this in a separate terminal or shell:
    {selected-command}

When you're done, close the demo and remove the worktree:
    git worktree remove {resolved-target-path}
```

### Auto-advance

After this section completes (skipped, declined, or accepted), proceed immediately to Section 2b. Do not wait for the user to report demo completion.

### Security boundary

The agent MUST NOT execute the **selected command** (or the `demo-command:` value) itself; it is printed for the user to run manually in a separate terminal session.

---

## Section 2b — Lifecycle Advancement

Run immediately after Section 2a (or after the batch verification response if Section 2a was skipped). No additional user input is needed.

For each completed feature (same list as Section 2, same order):

1. Check whether `cortex/lifecycle/{feature}/events.log` exists.
   - If the directory or file does not exist → skip, report `no lifecycle dir`.

2. Read `cortex/lifecycle/{feature}/events.log`. If it already contains a line where
   `"event": "feature_complete"` appears → skip, report `already complete`.

3. Read the feature's tier and criticality by running
   `cortex-lifecycle-state --feature {feature}` (emits JSON applying the canonical
   rules — tier: `lifecycle_start.tier` superseded by the most recent
   `complexity_override.to`; criticality: most recent value from `lifecycle_start`
   or `criticality_override`). When a key is absent, default tier to `"simple"`
   and criticality to `"medium"`.

4. Apply the review gating check:
   - complex tier at any criticality → review required
   - any tier at high or critical criticality → review required
   - otherwise (simple/low, simple/medium) → review NOT required

5. **If review is NOT required**: write synthetic events. Count the total number of
   checkboxes in `cortex/lifecycle/{feature}/plan.md`:
   - Match all occurrences of `- [x]` and `- [ ]` (case-insensitive)
   - Sum = `tasks_total`. If `plan.md` does not exist, use `tasks_total: 0`.

   Append the following four events to `cortex/lifecycle/{feature}/events.log` (one JSON object
   per line, newline-terminated, no trailing comma). Use the current UTC time in ISO 8601
   format for all `ts` fields:

   ```json
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "implement", "to": "review"}
   {"ts": "<now>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED", "cycle": 0}
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
   {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": 0}
   ```

   Report: `advanced → complete`.

6. **If review IS required**: check `cortex/lifecycle/{feature}/events.log` for real review
   events written by the batch runner (these have `cycle >= 1`):

   a. **Both `review_verdict` (with `cycle >= 1`) AND `feature_complete` present**: the
      batch runner already completed the full review lifecycle. Skip synthetic events.
      Report: `already complete (reviewed)`.

   b. **`review_verdict` (with `cycle >= 1`) present but `feature_complete` missing**:
      partial write / crash recovery. Count checkboxes in `plan.md` as in step 5 and
      append only the remaining events:

      ```json
      {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
      {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": R}
      ```

      Where `R` is the number of `review_verdict` events with `verdict: CHANGES_REQUESTED`
      in the feature's `events.log` (0 when the only verdict was a clean `APPROVED`).
      Report: `advanced → complete (crash recovery)`.

   c. **Neither `review_verdict` (with `cycle >= 1`) nor `feature_complete` present**:
      this feature was expected to be reviewed overnight but no review occurred. Do NOT
      write synthetic APPROVED events. Report: `missing review — expected review but
      none found`.

Display the results as an inline summary before moving to Section 3:

```
Lifecycle updates:
  fix-hardcoded-personal-paths-and-identifiers    advanced → complete
  add-public-sharing-documentation-to-readme      advanced → complete
```

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
       `cortex/lifecycle/sessions/latest-overnight/overnight-events.log`.
     - Address the missed step manually (e.g., trigger review, update the
       backlog item).
     - Advance the lifecycle manually to reflect the correct state.

   Then move on to the next failed feature — skip steps 5–7 below.

5. Otherwise (the feature is not annotated as on the integration branch), ask
   the user:

   ```
   Create a backlog investigation item for this failure? [yes / skip]
   ```

6. If the user says yes (or any affirmative), resolve the active backlog backend once with
   `cortex-read-backlog-backend` (argless; it prints the resolved backend and exits 0)
   before composing or writing anything, mirroring the §6b auto-close gate. Route on the value:

   - **`cortex-backlog`** (the default arm) → invoke `/backlog-author compose` with a
     context block derived from the failure summary (pre-resolved `why:` = what failed in
     observable terms, `role:` = investigate the root cause, `integration:` = affected
     lifecycle feature, `edges:` = non-goal: re-running the overnight session), capture
     the returned body, then call `cortex-create-backlog-item --title "investigate
     <feature-slug>" --status should-have --type bug --body "<returned-body>"` to write the ticket.
   - **`none`** → skip the create with a one-line advisory that backlog investigation-item
     creation is disabled for this repo — no file lands in `cortex/backlog/`.
   - **any other value** (an external tracker) → create the equivalent item best-effort on
     the configured tracker using the config `backlog.instructions` and your judgment
     (e.g. `gh issue create`), surfacing the composed body inline if it cannot be filed.

7. If the user says skip, move on without creating a backlog item.

---

## Section 5 — Auto-Close Backlog Tickets

Backlog closure runs in Section 6b (post-merge, on confirmed-merge success only). Proceed to Section 6.

---

## Section 6 — PR Review and Merge

Run after all other sections. No per-feature confirmation is needed before locating the PR. Until a merge is confirmed, completed features' backlog tickets stay open — the work sits on the integration branch, not main.

1. Read `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` and extract `integration_branch`.
   - If the file is missing or `integration_branch` is absent/empty, skip this section
     and note: "No integration branch found — skipping PR step."

2. Run:
   ```
   gh pr list --head {integration_branch} --json number,url,state,title,isDraft
   ```
   Parse the JSON array.
   - If empty (no PR found): inform the user —
     "No PR found for `{integration_branch}`. The runner may have failed to create one.
     Use `/pr` to create it manually." Then stop.
   - If the PR's `state` is `"MERGED"`: report "PR already merged — main is up to date."
     Then stop. This exit skips Section 6a's post-merge sync, so local `main` may lag the
     out-of-band merge — run `git fetch origin main` (or pull) first, before checking any
     ticket. If this session completed any features, check each one's backlog ticket (the
     completed-feature list and its zero-padded `backlog_id`s already surfaced in Section 2
     from `overnight-state.json`); the merge normally closes them, but a rare mid-session
     write failure could leave one open. For any still open after the fetch, close it via
     Section 6b's backlog closer, then push. With no completed features this session, there
     is nothing to check.
   - If the PR's `state` is `"CLOSED"`: report "PR was closed without merging." Then stop.

3. Display the open PR (state is `"OPEN"` only — MERGED and CLOSED exit early in Step 2):
   ```
   PR:    [{url}]({url})
   Title: {title}
   State: {state}
   ```

   Then run `open {url} 2>/dev/null || true` to open the PR in the default browser.

4. If `isDraft` is true, inform the user:
   ```
   PR is in DRAFT state (zero-progress session means the overnight runner produced no merged features). Direct merge will fail because GitHub blocks draft-PR merges. Choose one: mark as ready and merge, close the PR, or skip for manual follow-up.
   ```

   Then ask the user to choose one of:
   - **mark as ready and merge**: run `gh pr ready {number}`, then `gh pr merge {number} --merge --delete-branch` (follow the success/failure handling in step 6 below).
   - **close the PR**: run `gh pr close {number}`, then display the warning:
     ```
     WARNING: the integration branch {integration_branch} and its worktree are NOT automatically deleted when you choose "close". Run `git push origin --delete {integration_branch}` and check `git worktree list` for orphan worktrees manually.
     ```
   - **skip for manual follow-up**: note in the morning-review summary: "PR left open as draft at {url} — manual follow-up required."

   After handling the draft case, skip steps 5 and 6 (merge prompt and merge action) and proceed to Section 6a only if a merge was performed via the "mark as ready and merge" option.

   If `isDraft` is false, proceed to step 5.

5. Ask the user:
   ```
   Merge this PR to main? [yes / no]
   ```

6. If yes:
   - Run: `gh pr merge {number} --merge --delete-branch`
   - On success: report "Merged. Remote branch deleted."
     - Read `worktree_path` from `cortex/lifecycle/sessions/latest-overnight/overnight-state.json`.
       If non-empty and the path exists, run: `git worktree remove --force {worktree_path}`
       - On success: report "Worktree removed."
       - On failure: report the error but do not fail the review.
       - If you spun up a demo earlier in this review, close the demo and remove its worktree using the `git worktree remove` command printed at the time.
       - If `worktree_path` is absent, empty, or the path does not exist: skip removal silently.
   - On failure: show the error message and leave the PR open for manual resolution.

7. If no: leave the PR open and note: "PR left open at {url} — merge manually when ready."

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
   cortex-git-sync-rebase cortex_command/overnight/sync-allowlist.conf
   ```

2. Handle the exit code:

   - **Exit 0**: report "Local main synced and pushed — fully up to date."
   - **Exit 1**: report "Sync encountered unresolvable conflicts. Local main is diverged — resolve manually with `git pull --rebase origin main`."
   - **Exit 2**: report "Rebase succeeded but push failed. Run `git push origin main` when network is available."

After this section, proceed to Section 6b.

---

## Section 6b — Close Backlog Tickets

Run immediately after a successful post-merge sync in Section 6a. Skip this section
entirely if the merge was declined, skipped, or the PR was already merged/closed before
this review — backlog tickets should only be closed when the merge is confirmed in the
current review session.

The per-feature auto-close below targets the local backlog engine. Before the loop,
resolve the active backend once with `` `cortex-read-backlog-backend` `` (argless; it
prints the resolved backend and exits 0). Route the per-feature close on the value:

- **`cortex-backlog`** (the default arm) → close each completed feature exactly as today,
  running the close call unchanged.
- **`none`** → skip the auto-close; for each completed feature, note a one-line advisory
  that backlog ticket closure is disabled for this repo, and continue.
- **any other value** (an external tracker) → for each completed feature, make the
  equivalent close best-effort on the configured tracker using the config
  `backlog.instructions` and your own judgment (e.g. `gh issue close`), surfacing the
  composed close if it cannot be completed so no work is lost.

The `cortex-backlog` arm runs the loop below unchanged.

No per-feature confirmation is needed before closing — the confirmed merge is
authoritative. For each completed feature (the same list as Section 2, in the same order):

1. On the `cortex-backlog` arm, run:

   ```
   cortex-update-item {backlog_id} --status complete
   ```

   Where `{backlog_id}` is the zero-padded numeric ID from `overnight-state.json`'s
   `backlog_id` field (e.g., `078` not `78`). If `backlog_id` is null, fall back to
   the lifecycle slug for fuzzy matching. Run from the repository root. The script
   exits 0 on success (item updated), exits 1 silently if no item is found, and exits 2
   when the slug is ambiguous (it writes the matching candidate list to stderr).

   On exit 2, surface that stderr candidate list to the operator and ask them to
   re-invoke the close with a disambiguated slug for that feature before continuing.

   On the `none` arm, skip this call and record a per-feature advisory that closure is
   disabled. On any other value, make the equivalent close best-effort on the external
   tracker per `backlog.instructions`.

2. Report one of the following per feature:
   - `closed #ID` — if the script printed "Parent epic also closed: ..." or the item
     was found and updated (exit 0 with a matching item)
   - `no ticket found` — if the script exited 1
   - `ambiguous slug` — if the script exited 2; surface the stderr candidate list and
     ask the operator to re-invoke with a disambiguated slug

3. If `update_item.py` printed "Parent epic also closed: {path}", append
   `(parent epic also closed)` to the line for that feature.

Present the full closure results as a summary list at the end of the review. Example:

```
Ticket closure results:
  auth-api         closed #042
  data-pipeline    no ticket found
  ui-dashboard     closed #039 (parent epic also closed)
```

After this section, the review is complete.

---

## Edge Cases

Most edge handling is specified inline per section. The cases below are stated only here:

| Situation | Action |
|-----------|--------|
| `cortex/lifecycle/sessions/` exists but report is missing | Print "Incomplete session detected — report not generated. Run: `cortex-report`" and stop |
| Single completed feature | Still use the batch prompt — consistent UX regardless of count |
| `update_item.py` exits non-zero for another reason | Report "close failed (exit {N})" for that feature and continue |
| `cortex-git-sync-rebase` not found | Report missing script, skip sync, note "install the `cortex-core` plugin" |
| Dirty `.git/rebase-merge/` detected | Script auto-aborts stale rebase, warns user, proceeds with sync |
| All conflicts auto-resolved | Report "N files auto-resolved via allowlist" |
| Agent crashes between worktree creation and command print | Worktree exists with no record for user; next sweep retries |
| Stale demo worktree from prior session in `$TMPDIR` | Removed by Step 0 garbage sweep on next morning-review (if clean) |
| Stale demo worktree from prior session contains user edits | Sweep's `git worktree remove` (no `--force`) fails; stderr printed; user can rescue manually |
| Demo worktree created but user closes session before Section 6 reminder | No cleanup until next morning-review's Step 0 sweep |
| User abandons the repo entirely (no future morning-review for it) | Stale worktrees and admin entries persist until manual cleanup or OS reboot |
