# Morning Review Walkthrough Protocol

Section-by-section protocol for `/morning-review`, followed in order once the report is
located and confirmed to exist.

---

## Section 1 — Executive Summary

Read `cortex/lifecycle/morning-report.md` (or the file it symlinks to). Extract and
display, before any interaction:

- **Verdict** — overall session outcome (e.g. "All features completed", "Partial —
  2 of 4 completed", "Session failed")
- **Feature counts** — completed, failed, deferred
- **Session duration** — start time, end time, elapsed time

**Missing report**: if `cortex/lifecycle/morning-report.md` doesn't exist and
`cortex/lifecycle/sessions/` has no subdirectories, print:

```
No morning report found. No overnight session has been run yet, or the report was not
generated. To generate one, run:

    cortex-report
```

Then stop — do not proceed to later sections.

---

## Section 2 — Completed Features

Skip this section if there are no completed features in the report.

**Load overnight metadata** (best-effort): read
`cortex/lifecycle/sessions/latest-overnight/overnight-state.json` if present, and pull
`round_assigned`, `started_at`, `completed_at` per feature from its `features` map. Omit
any field that's missing or absent — don't error.

**Display all features at once**, organized by round: if every feature shares a round (or
`round_assigned` is unavailable), omit round sub-headings; otherwise emit `### Round N`
before each group (ascending order, report's feature order within a round). For each
feature:

```
### {feature-name}
**Round:** N  |  **Duration:** Xm Ys  |  **Files changed:** N
```

followed by the verbatim "How to try" / verification block from the report. Duration is
`completed_at − started_at` (`Xh Ym` or `Xm Ys`); "Files changed" is the bullet count in
the feature's "Key files changed" list. Omit any field whose source value is null or
missing.

**After all features are displayed, ask one question:**

```
Which features have you verified? ("all", "none", or a space/comma-separated list of names)
```

Parse the response: `"all"`/`"yes"`/`"done"`/`"y"` → all verified; `"none"`/`"skip"`/`"s"`/
`"no"` → all skipped; otherwise treat as a feature-name list (fuzzy match: prefix or
substring, case-insensitive) — named ones verified, rest skipped.

Record status per feature and proceed immediately to Section 2a. Verified/skipped is
reporting context only — it does not gate lifecycle advancement.

---

## Section 2a — Demo Setup

Skip this section if any of the following hold:

### Guard 1 — resolve the active config path

Read `cortex/lifecycle.config.md` at the project root; if missing, skip Section 2a
silently. Try `demo-commands:` (a list) first, falling back to `demo-command:` (a single
string) if the list is absent or has no valid entries; if neither is configured, skip
silently.

**`demo-commands:` list** — find the bare `demo-commands:` key and read its indented
`- label: "..."` / `command: "..."` entries until the first non-indented, non-blank line.
Extract `label:`/`command:` via first-colon split (commands may contain their own `:`,
e.g. `godot res://main.tscn`). Discard entries whose `command:` is empty/whitespace-only
or contains a control character (byte < 0x20 except `\t`); don't strip inline `#` — no
shell parser here can tell comment from literal, so `command:` values must stay free of
trailing `#` comments. At least one surviving entry activates this path.

**`demo-command:` single string** (fallback) — find a non-commented `demo-command:` line,
extract everything after the first `:`, trim whitespace; same rejection rules as above. A
valid value activates this path.

If neither path is active, skip silently. Otherwise proceed to Guard 2.

### Guard 2 — remote session

Skip Section 2a if `$SSH_CONNECTION` is set and non-empty (covers SSH and mosh, since mosh
inherits it from the SSH handshake).

### Guard 3 — overnight branch is missing

Skip Section 2a if `git rev-parse --verify {integration_branch}` exits non-zero, where
`{integration_branch}` comes from
`cortex/lifecycle/sessions/latest-overnight/overnight-state.json` (same
`jq -r '.integration_branch'` read as Section 6 step 1). A missing file or field also
skips.

**List path only:** additionally count `features` entries in the same state file with
`"status": "merged"`. Zero merged features (or a missing `features` key) skips Section 2a
silently.

### Agent Reasoning (list path only)

If all guards pass on the list path, pick the configured entry whose `label:`/`command:`
best matches the night's merged features and their **Key files changed** (already in
context from Section 2 — do not re-run `git log`, `git diff`, or any file-tree read). If
one entry is a clear winner, select it and proceed to the Demo offer. If none maps
cleanly, skip Section 2a silently — do not fall back to the single-string path even if
it's also configured; once the list path is active, it owns the decision.

### Demo offer

Ask a single yes/no question, using the variant for the active path. No follow-up
questions.

- **List path:** `Run {selected-label} demo ({selected-command}) from {integration_branch}
  in a fresh worktree? [y / n]` — substitute the selected entry's label/command.
- **Single-string path:** `Spin up a demo worktree of {integration_branch} at
  $TMPDIR/demo-{session_id}-{timestamp} and print the launch command? [y / n]`

On `n` or unparseable input, advance to Section 2b. On `y`, continue below.

### Worktree creation

1. `{resolved-tmpdir}` = `realpath "$TMPDIR"`.
2. Target path = `{resolved-tmpdir}/demo-{session_id}-{timestamp}`, with `{timestamp}`
   from `$(date -u +%Y%m%dT%H%M%SZ)`.
3. Run exactly: `git -c core.hooksPath=/dev/null worktree add "{target-path}"
   "{integration_branch}"`. The `-c core.hooksPath=/dev/null` neutralizes any tracked
   `post-checkout` hook (husky, lefthook) on the overnight branch. No `--force`; `-c`
   (lowercase), not `-C`.
4. On non-zero exit, print stderr and advance to Section 2b — no retry, no cleanup.

### Print template

After a successful worktree-add, print this block, substituting `{resolved-target-path}`
with the absolute path from the previous step and `{command}` with `{demo-command}`
(single-string path) or `{selected-command}` (list path) — both already validated
control-character-free above. On the list path only, append ` ({selected-label})` after
"the demo" on the second line.

```
Demo worktree created at: {resolved-target-path}

To start the demo, run this in a separate terminal or shell:
    {command}

When you're done, close the demo and remove the worktree:
    git worktree remove {resolved-target-path}
```

Regardless of outcome (skipped, declined, or accepted), proceed immediately to Section 2b
after this section — do not wait for the user to report demo completion. Do not execute
the selected command (or the `demo-command:` value) yourself; it is printed for the user
to run manually in a separate terminal.

---

## Section 2b — Lifecycle Advancement

Run immediately after Section 2a (or after the batch verification response if 2a was
skipped). No additional user input needed.

For each completed feature (same list and order as Section 2):

1. If `cortex/lifecycle/{feature}/events.log` doesn't exist, skip — report
   `no lifecycle dir`.
2. If it already contains a `"event": "feature_complete"` line, skip — report
   `already complete`.
3. Get tier/criticality via `cortex-lifecycle-state --feature {feature}` (tier:
   `lifecycle_start.tier` superseded by the most recent `complexity_override.to`;
   criticality: most recent of `lifecycle_start` or `criticality_override`; default tier
   `"simple"`, criticality `"medium"` when absent).
4. Gate: complex tier at any criticality, or any tier at high/critical criticality →
   review required. Otherwise (simple/low, simple/medium) → not required.

5. **Review not required**: count `- [x]`/`- [ ]` checkboxes in `plan.md`
   (case-insensitive) as `tasks_total` (`0` if `plan.md` is missing). Append four events
   to `events.log` (one JSON object per line, newline-terminated, current UTC ISO 8601
   `ts`):

   ```json
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "implement", "to": "review"}
   {"ts": "<now>", "event": "review_verdict", "feature": "<name>", "verdict": "APPROVED", "cycle": 0}
   {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
   {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": 0}
   ```

   Report: `advanced → complete`.

6. **Review required**: check `events.log` for real review events from the batch runner
   (`cycle >= 1`):

   a. **`review_verdict` (cycle ≥ 1) and `feature_complete` both present** — the batch
      runner already completed the review lifecycle. Skip synthetic events. Report:
      `already complete (reviewed)`.

   b. **`review_verdict` (cycle ≥ 1) present, `feature_complete` missing** — crash
      recovery: count checkboxes as in step 5 and append only:

      ```json
      {"ts": "<now>", "event": "phase_transition", "feature": "<name>", "from": "review", "to": "complete"}
      {"ts": "<now>", "event": "feature_complete", "feature": "<name>", "tasks_total": N, "rework_cycles": R}
      ```

      `R` = count of `review_verdict` events with `verdict: CHANGES_REQUESTED` (`0` if the
      only verdict was a clean `APPROVED`). Report: `advanced → complete (crash
      recovery)`.

   c. **Neither present** — the feature was expected to be reviewed overnight but wasn't.
      Do NOT write synthetic APPROVED events. Report: `missing review — expected review
      but none found`.

Display an inline summary before moving to Section 3:

```
Lifecycle updates:
  fix-hardcoded-personal-paths-and-identifiers    advanced → complete
```

---

## Section 3 — Deferred Questions

Skip this section if there are no files matching `deferred/{feature}-q*.md`.

For each deferred question file (report order by feature, then filename sort order
within a feature):

1. Display the feature name and question filename as a heading.
2. Display the question text (body or `question:` frontmatter), what was tried (`tried:`
   or `## What was tried`), and what's needed to unblock (`needed:` or
   `## What's needed`).
3. Ask: `Your answer (or "skip" to leave this question unanswered):`
4. On an answer (anything but "skip"/"s"/"later"), append to the file — after any
   existing content, separated by a blank line, without touching frontmatter or existing
   sections:

   ```
   ## User Answer (YYYY-MM-DD)

   {user's answer verbatim}
   ```

   Use today's date. If the file already has one or more `## User Answer` sections,
   append after the last one.

5. On skip, leave the file unchanged.

---

## Section 4 — Failed Features

Skip this section if there are no failed features in the report.

For each failed feature (report order):

1. Display the feature name as a heading, its error summary, and its suggested next step
   (if present).
2. **Integration-branch annotation.** If the report entry contains `Feature is on the
   integration branch`, the feature merged successfully before a post-merge step failed.
   State that it's already on the integration branch and merged; do **not** offer an
   investigation or re-run ticket — that would duplicate landed work. Instead tell the
   user to verify the feature is present, identify the failed post-merge step via
   `cortex/lifecycle/sessions/latest-overnight/overnight-events.log`, address it manually
   (e.g. trigger review, update the backlog item), and advance the lifecycle manually.
   Move to the next failed feature — skip steps 3–4 below.
3. Otherwise, ask: `Create a backlog investigation item for this failure? [yes / skip]`
4. On yes, resolve the active backlog backend once with `cortex-read-backlog-backend`
   before composing or writing anything — same call as the §6b auto-close gate. Route on
   the value:

   - **`cortex-backlog`** (default) → invoke `/backlog-author compose` with a context
     block from the failure summary (`why:` = what failed observably, `role:` =
     investigate root cause, `integration:` = affected feature, `edges:` = non-goal:
     re-running the overnight session); capture the returned body and call
     `cortex-create-backlog-item --title "investigate <feature-slug>" --status
     should-have --type bug --body "<returned-body>"`.
   - **`none`** → skip the create with a one-line advisory that backlog investigation-item
     creation is disabled for this repo — no file lands in `cortex/backlog/`.
   - **any other value** (external tracker) → create the equivalent item best-effort using
     `backlog.instructions` and your judgment (e.g. `gh issue create`), surfacing the
     composed body inline if it can't be filed.

   On skip, move on without creating anything.

---

## Section 5 — Auto-Close Backlog Tickets

Backlog closure runs in Section 6b (post-merge, on confirmed-merge success only). Proceed
to Section 6.

---

## Section 6 — PR Review and Merge

Run after all other sections; no per-feature confirmation needed before locating the PR.
Until a merge is confirmed, completed features' backlog tickets stay open — the work sits
on the integration branch, not main.

1. Read `integration_branch` from
   `cortex/lifecycle/sessions/latest-overnight/overnight-state.json`. If the file is
   missing or the field is absent/empty, skip this section: "No integration branch
   found — skipping PR step."

2. Run `gh pr list --head {integration_branch} --json number,url,state,title,isDraft` and
   parse the array.
   - Empty → "No PR found for `{integration_branch}`. The runner may have failed to
     create one. Use `/pr` to create it manually." Stop.
   - `state == "MERGED"` → "PR already merged — main is up to date." Stop. This skips
     Section 6a's sync, so local `main` may lag the out-of-band merge — `git fetch origin
     main` (or pull) first. If features completed this session, check their backlog
     tickets (Section 2's `backlog_id`s); a rare write failure could leave one open
     despite the merge — close it via Section 6b's closer, then push.
   - `state == "CLOSED"` → "PR was closed without merging." Stop.

3. Display the open PR (only `"OPEN"` reaches here):
   ```
   PR:    [{url}]({url})
   Title: {title}
   State: {state}
   ```
   Run `open {url} 2>/dev/null || true` to open it in the browser.

4. If `isDraft`, tell the user the PR is in DRAFT state (a zero-progress session produced
   no merged features) and a direct merge will fail — GitHub blocks draft-PR merges.
   Offer:
   - **mark as ready and merge**: `gh pr ready {number}`, then `gh pr merge {number}
     --merge --delete-branch` (step 6's success/failure handling applies).
   - **close the PR**: `gh pr close {number}`, then warn: "WARNING: closing does NOT
     delete the integration branch {integration_branch} or its worktree. Run `git push
     origin --delete {integration_branch}` and check `git worktree list` for orphans
     manually."
   - **skip for manual follow-up**: note "PR left open as draft at {url} — manual
     follow-up required."

   After the draft case, skip steps 5–6 and proceed to Section 6a only if a merge
   happened via "mark as ready and merge". If not draft, proceed to step 5.

5. Ask: `Merge this PR to main? [yes / no]`

6. On yes: run `gh pr merge {number} --merge --delete-branch`.
   - Success → "Merged. Remote branch deleted." If `worktree_path` (from
     `overnight-state.json`) is non-empty and exists, run `git worktree remove --force
     {worktree_path}` — report success or the error either way without failing the
     review; skip silently if absent/missing. Close any demo worktree from earlier in
     this review the same way, using the command printed at the time.
   - Failure → show the error and leave the PR open for manual resolution.

   On no: leave the PR open — "PR left open at {url} — merge manually when ready."

After this section, proceed to Section 6a if a merge was performed.

---

## Section 6a — Post-merge sync

Run immediately after a successful merge in Section 6. Skip if the merge was
skipped, declined, or the PR was already merged.

After the PR merge, local main has local-only commits (morning report, review artifacts)
while remote main has the merge commit; this step reconciles the two.

1. Run `cortex-git-sync-rebase cortex_command/overnight/sync-allowlist.conf`.
2. Handle the exit code:
   - **0**: "Local main synced and pushed — fully up to date."
   - **1**: "Sync encountered unresolvable conflicts. Local main is diverged — resolve
     manually with `git pull --rebase origin main`."
   - **2**: "Rebase succeeded but push failed. Run `git push origin main` when network is
     available."

After this section, proceed to Section 6b.

---

## Section 6b — Close Backlog Tickets

Run immediately after a successful post-merge sync in Section 6a. Skip this section
entirely if the merge was declined, skipped, or the PR was already merged/closed before
this review — tickets close only when the merge is confirmed in the current session.

The per-feature close targets the local backlog engine. Before the loop, resolve the
active backend once with `cortex-read-backlog-backend` (argless; prints the resolved
backend, exits 0):

- **`cortex-backlog`** (default) → run the loop below unchanged.
- **`none`** → skip the auto-close; note a one-line advisory per feature that backlog
  ticket closure is disabled for this repo.
- **any other value** (external tracker) → make the equivalent close best-effort per
  `backlog.instructions` and your judgment (e.g. `gh issue close`), surfacing the
  composed close if it can't complete so no work is lost.

No per-feature confirmation is needed before closing — the confirmed merge is
authoritative. For each completed feature (same list and order as Section 2), on the
`cortex-backlog` arm run:

```
cortex-update-item {backlog_id} --status complete
```

`{backlog_id}` is the zero-padded numeric ID from `overnight-state.json`'s `backlog_id`
field (e.g. `078`, not `78`); fall back to the lifecycle slug for fuzzy matching if it's
null. Run from the repository root.

Report per feature: `closed #ID` (exit 0; append `(parent epic also closed)` if the
script printed that), `no ticket found` (exit 1), or `ambiguous slug` (exit 2 — surface
the stderr candidate list and ask the operator to re-invoke with a disambiguated slug).

Present the full results as a summary at the end of the review:

```
Ticket closure results:
  auth-api         closed #042
  data-pipeline    no ticket found
```

After this section, the review is complete.

---

## Edge Cases

Most edge handling is specified inline per section. The cases below are stated only here:

| Situation | Action |
|-----------|--------|
| `cortex/lifecycle/sessions/` exists but report is missing | Print "Incomplete session detected — report not generated. Run: `cortex-report`" and stop |
| Single completed feature | Use the batch prompt anyway — consistent UX regardless of count |
| `update_item.py` exits non-zero for another reason | Report "close failed (exit {N})" and continue |
| `cortex-git-sync-rebase` not found | Report the missing script, skip sync, note "install the `cortex-core` plugin" |
| Dirty `.git/rebase-merge/` detected | Script auto-aborts the stale rebase, warns, proceeds with sync |
| All conflicts auto-resolved | Report "N files auto-resolved via allowlist" |
| Agent crashes between worktree creation and command print | Worktree exists with no record for the user; next sweep retries |
| Stale demo worktree from a prior session in `$TMPDIR` | Removed by Step 0's garbage sweep on next morning-review (if clean) |
| Stale demo worktree contains user edits | Sweep's `git worktree remove` (no `--force`) fails; stderr printed; rescue manually |
| Demo worktree created but session closes before the Section 6 reminder | No cleanup until next morning-review's Step 0 sweep |
| User abandons the repo (no future morning-review) | Stale worktrees/admin entries persist until manual cleanup or reboot |
