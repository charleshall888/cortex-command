# New Session Flow (`/overnight`) — Detailed Steps

## Step 1: Check for Existing Session

Call `load_state()` from `cortex_command.overnight.state` (no arguments — resolves the default path under `cortex/lifecycle/overnight-state.json`, which `bootstrap_session` maintains).

- **Found, phase other than `complete`**: an active session exists — report phase and feature count, then offer resume (switch to Resume Flow) or abandon-and-start-fresh.
- **Found, phase `complete`**: treat as no active session; proceed as new.
- **Not found**: proceed as new.

## Step 2: Pre-selection Index Regeneration

Run `cortex-generate-backlog-index` from the project root so Step 3 selects against fresh metadata. The index (`cortex/backlog/index.json`/`index.md`) is a gitignored local cache — regenerate it, but do not stage or commit it (it won't appear in the uncommitted-files pre-flight in Step 7).

**Error**: non-zero exit → "Backlog index regeneration failed (exit {code}). Fix the issue and retry `/overnight`." → halt.

## Step 3: Select Eligible Features

Run `select_overnight_batch()` from `cortex_command.overnight.backlog`; it returns a `SelectionResult` (eligible items, batches, ineligible reasons).

A feature is eligible only if, on disk:
- `cortex/lifecycle/{slug}/research.md` exists (slug = `item.lifecycle_slug` if set, else `slugify(item.title)`)
- `cortex/lifecycle/{slug}/spec.md` exists (produced by `/refine` or `/lifecycle`)
- `type:` is not `epic` — excluded at step 4, after blocked-by and before artifact checks; a blocked epic reports its blocking dependency, not the epic exclusion

Missing `plan.md` is generated automatically during the session — no pre-run `/lifecycle plan` needed.

**If no eligible items**: report "Nothing ready for overnight execution," list ineligible items with reasons, and suggest running `/lifecycle` through the plan phase on the highest-priority ones. Stop.

**Error**: `select_overnight_batch()` exception (e.g., malformed frontmatter) → "Failed to parse backlog: {error}. Check backlog file frontmatter for syntax errors." → stop.

## Step 4: Present Selection Summary

Present the selection summary to the user: eligible item/batch counts, per-batch breakdown (batch number, knowledge-domain context, feature titles), and ineligible items with reasons. Available pre-formatted as `selection.summary` on the `SelectionResult` object.

## Step 5: Render Session Plan

Run the read-only `cortex overnight prepare --format json` verb (default `--time-limit-hours 6`) via Bash — it selects eligible items and renders the plan without mutating state (no bootstrap, no worktree, no telemetry), so it's safe to re-run at the Approve gate.

```
cortex overnight prepare --format json
```

Parse the envelope: `plan_markdown` (the formatted plan — feature table, execution strategy, not-ready items, risk assessment, stop conditions — for Step 6) and `selection` (the structured summary for Step 4).

Re-run with `--time-limit-hours <N>` or `--batch-size-cap <N>` to re-render under different limits (e.g. Step 6's `[T]`).

**Error**: non-zero exit emits a JSON `error`/`message` envelope (`selection_failed`, `render_failed`) → "Failed to render session plan: {message}." → stop.

## Step 6: Unified Plan + Spec Review

Collect specs for all selected features, display the plan with specs inline, and get one approval covering both.

**Collect specs**: for each selected feature (round-then-priority order), read `cortex/lifecycle/{slug}/spec.md`.

- **Missing, unreadable, or undecodable** (binary content, encoding error — treated the same as missing): report "Cannot read spec for {feature_title}: {error}." Offer to remove the feature and continue, or abort so the user can fix the spec. On remove, update the selection and skip it below.

**Suitability triage (judged once, on first entry)**: unattended execution is the riskiest place to run work — no human is watching to catch a wrong turn — so judge each feature's fit for running unattended from its spec and set poor fits aside by default. Bias toward exclusion: a set-aside item is one re-add away, but a bad unattended run wastes the night. Re-renders reuse this judgment rather than re-judging (see `[T]`).

Set a feature aside, with a one-line plain-language reason, on:
- **Mechanical** (from the spec): an acceptance criterion marked `Interactive/session-dependent`; a genuinely unresolved item under `## Open Decisions` (`- None.` or a placeholder is not a trigger).
- **Soft** (judgment): needs network/credentials the sandbox can't reach; leans on human-visual or human-judgment verification; or is exploratory/under-specified.

**Blocker-aware**: don't set aside a feature that's the in-session blocker of one you're keeping without flagging the coupling — `launch` refuses a curated set that drops a kept feature's blocker.

Three pools result:
- **Active** — good unattended candidates; these run.
- **Set aside (suitability)** — excluded by default, always re-addable (the operator may legitimately override either signal type).
- **Hard-ineligible** — cannot run (missing research/spec, epic, blocked, branch-merged); display-only, never re-addable — a re-add attempt is refused with its reason.

**Display plan + specs**: present the Step 5 plan, then each **active** feature's spec inline (set-aside features are listed separately, not shown in full):

```
{rendered session plan}

─────────────────────────────────────────
Spec [1/{total}]: {feature_title}  (cortex/lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}
```
(repeat per active feature)

**Set-aside display**: after the active specs, list the Set Aside pool (feature + one-line reason), then the hard-ineligible pool (display-only). If the active pool is empty, make that obvious so the operator re-adds rather than approving an empty run.

**Re-display before every approval**: immediately before each approval prompt, re-display the active, Set Aside, and hard-ineligible pools in full — what's displayed and approved here is exactly what `launch` executes in Step 7.

**Approval prompt**: no recommended size ceiling — remove features only for substantive reasons (out of scope, not ready), not to keep the session small. Show `[I]` only when the Set Aside pool is non-empty:

```
Approve this plan and specs?

  [A] Approve — launch exactly the active pool
  [R] Remove a feature — move an active feature out of the run
  [I] Include a set-aside item — re-add a set-aside feature to the active pool
  [T] Adjust time limit — change from the default 6h
  [Q] Abort — stop planning
```

- **Approve (A)**: proceed to Step 7 and launch exactly the active pool.
- **Remove (R)**: ask which active feature to remove; move it out and re-display — do not re-run `prepare`'s selection (that would re-introduce removed/set-aside items).
- **Include (I)**: ask which set-aside feature to re-add; move it into the active pool and re-display. A hard-ineligible target is refused with its reason. The re-add holds through this session only — it isn't remembered for future curations.
- **Adjust time limit (T)**: ask for the new limit, re-render the plan, then re-apply the existing curation on top — don't re-judge suitability from scratch, so no candidate flickers between pools across re-renders.
- **Abort (Q)**: stop immediately, report "Planning aborted," write no artifacts.

## Step 7: Launch

On user approval, execute these steps in order:

0. **Target-repo validation** (performed by `launch` in sub-step 2): `launch` validates every backlog `repo:` path before any mutation. On an invalid path it exits non-zero with `{"error": "invalid_target_repos", "message": "...", "repos": [...]}`, writing no artifacts and marking no session `executing`. Relay the envelope's `message` verbatim, then stop.

1. **Pre-flight: uncommitted cortex/lifecycle/backlog files**: run `git status --porcelain -- cortex/lifecycle/ cortex/backlog/`.

   - **Non-empty**: block launch with:
     ```
     Uncommitted lifecycle files detected. The overnight worktree is created from HEAD, so
     these files will not be visible to the runner. Commit or stash them before launching.

     Uncommitted paths:
       {lines from git status output}
     ```
     Offer to run `/commit`. If accepted, invoke it, then re-check status — proceed to sub-step 2 if now empty; otherwise show the block message with the remaining paths and stop (don't offer `/commit` a second time). If declined, stop: "Commit or stash the files above, then run `/overnight` again."
   - **Empty**: proceed to sub-step 2.

   **Error**: unexpected `git status` failure → report and stop (can't occur in practice — Input Validation's git-repo check runs first).

2. **Bootstrap the session**: run the mutating `cortex overnight launch --format json` verb via Bash, passing the **frozen curated set** via `--only`. It fuses target-repo validation (sub-step 0), session bootstrap, and batch-spec extraction (sub-step 4) into one call.

   ```
   cortex overnight launch --format json --only <comma-separated active slugs>
   ```

   `--only` is exactly the **active pool** shown at `[A]pprove` in Step 6 — no re-selection happens between approval and execution. Omitting it falls back to full re-selection, losing operator removals/set-asides. `launch` refuses fail-loud if the active set isn't dependency-closed, naming the missing in-session blocker to re-add at the Step 6 gate.

   This atomically initializes the session (the artifacts listed in the skill's frontmatter `outputs:`) and returns a JSON envelope. Capture, for later sub-steps, without reconstructing from a hard-coded prefix or environment variable:
   - `session_id`, `state_dir` (session directory), `state_path` (pass as `--state` in sub-step 7), `worktree_path` (sub-step 4), `extracted_specs` (batch-spec paths, sub-step 4)

   **Error**: non-zero exit emits `error`/`message` (`invalid_target_repos` → handle per sub-step 0; `bootstrap_failed` → relay the envelope's `message` verbatim and stop). On `bootstrap_failed`, also clean up any orphaned worktree: `git worktree prune`, then remove the stale directory under `$TMPDIR/overnight-worktrees/` (find by modification time; the session ID is in the directory name).

3. **latest-overnight symlink**: handled by the runner on startup — the skill doesn't create it; it writes to the repo root, outside the sandbox's write allowlist in sandboxed projects.

4. **Commit extracted batch spec sections**: sub-step 2 already wrote any batch-spec sections into the worktree and returned their paths as `extracted_specs`. If non-empty, `cd` to `worktree_path`, `git add` each path (relative to the worktree), and commit via `/commit` with message `"Extract batch spec sections for overnight session {session_id}"`. This commits on the integration branch, not main. If empty, skip.

   **Error**: `git add`/`git commit` failure → "Batch spec commit failed: {error}. Proceeding without committing batch spec sections — they may be extracted during runner startup." Continue.

5. **Session start logging (deferred to the run-now branch)**: don't log `session_start` here — it's gated to the run-now branch of sub-step 7. The runner is the sole fire-time author; the schedule branch never pre-logs (its fire happens hours later, so pre-logging would produce an early/duplicate event).

6. **Launch the dashboard** (if not already running): check `${XDG_CACHE_HOME:-$HOME/.cache}/cortex/dashboard.pid` for a live PID (`kill -0 $(cat <path>)` exits 0) — if alive, skip and note the URL. Otherwise poll `GET http://localhost:8080/health` (up to 5s, 1s intervals): on success, note "Dashboard available at http://localhost:8080" in the session start message; on timeout or an unreadable PID file, report "Dashboard not detected at http://localhost:8080. Run `cortex dashboard` (installer-tier) or `just dashboard` (clone-only) in a separate terminal to enable live progress monitoring" and continue — the dashboard is optional and can be started anytime during the session.

7. **Execute the runner command**: ask run-now vs. schedule via AskUserQuestion:

    ```
    Run now or schedule for later?

      [1] Run now — launch the overnight session immediately
      [2] Schedule for specific time — delay launch until a target time
    ```

    **Run now (option 1)**: first log the prep-time `session_start` (run-now branch only) — call `log_event()` from `cortex_command.overnight.events` with `event='session_start'` (not `event_type`; event names are lowercase), `round=1`, and `details` covering session ID, feature count, and time limit; pass `log_path=state_dir / "overnight-events.log"`. **Error**: `log_event()` failure → report "Failed to log session start event: {error}." and continue (non-fatal).

    Then run via Bash with `dangerouslyDisableSandbox: true`, using the `state_path` captured in sub-step 2 (don't reconstruct it):

    ```
    cortex overnight start --state {state_path} --time-limit 21600
    ```

    `--state` takes the envelope's `state_path`; `--time-limit` is in seconds (`21600` = 6h). The runner launches detached and returns immediately.

    **Schedule for specific time (option 2)**: prompt for a target time — `HH:MM` (24-hour local) or `YYYY-MM-DDTHH:MM` (ISO 8601). Run via Bash with `dangerouslyDisableSandbox: true` (required for `launchctl`), using the same `state_path`:

    ```
    cortex overnight schedule <target-time> --state {state_path}
    ```

    Registers a one-shot LaunchAgent (no tmux) that fires the runner at the target time and returns immediately.

8. **Inform the user**: after the Bash tool returns, report the outcome:
    - **Run now**: "Overnight session launched. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`."
    - **Scheduled**: report the scheduled time and session ID from the command output; `cortex overnight status` shows the registered schedule before fire time.

    The runner tracks progress in the state file and event log. Resume at any time with `/overnight resume`.
