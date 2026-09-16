# New Session Flow (`/overnight`)

## 1. Guard

`cortex overnight status`. A session whose phase is not `complete` is active: offer resume (switch to the resume flow) or abandon-and-start-fresh.

## 2. Prepare

```
cortex overnight prepare --format json
```

Read-only and safe to re-run. Non-zero exit → relay `message` and stop. Zero eligible items → report "Nothing ready for overnight execution", list `selection`'s ineligible items with reasons, suggest `/cortex-core:refine` on the highest-priority ones, stop. Otherwise present `selection` (eligible and batch counts, per-batch features, ineligible with reasons) and `plan_markdown`. Re-run with `--time-limit-hours N` or `--batch-size-cap N` to re-render.

## 3. Curate and approve

Read each selected feature's `cortex/lifecycle/{slug}/spec.md`. Unreadable → "Cannot read spec for {title}: {error}"; offer to remove it or abort.

**Suitability triage — judged once on first entry; re-renders reuse it.** Nobody watches an unattended run, so bias toward exclusion: a set-aside item is one re-add away, a bad run wastes the night. Set aside, with a one-line reason: an acceptance criterion marked `Interactive/session-dependent`; a real item under `## Open Decisions`; needs network or credentials the sandbox lacks; leans on human-visual or human-judgment verification; exploratory or under-specified. Flag a set-aside that blocks a kept feature — `launch` refuses a set that drops a kept feature's in-session blocker.

Three pools: **active** (runs), **set aside** (re-addable), **hard-ineligible** (missing artifacts, epic, blocked, merged — display-only, never re-addable).

Display the plan, then each active spec inline:

```
─────────────────────────────────────────
Spec [n/N]: {title}  (cortex/lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}
```

then the set-aside pool with reasons, then the hard-ineligible pool. An empty active pool must be obvious. Re-display all three pools before every approval prompt — what is shown is exactly what launches.

```
Approve this plan and specs?

  [A] Approve — launch exactly the active pool
  [R] Remove a feature — move an active feature out of the run
  [I] Include a set-aside item — re-add a set-aside feature   (shown only when the pool is non-empty)
  [T] Adjust time limit — change from the default 6h
  [Q] Abort — stop planning
```

`R` / `I` move one feature and re-display without re-running selection (that would re-introduce removed items; a hard-ineligible target is refused with its reason). `T` re-renders, then re-applies the existing curation so no candidate flickers between pools. `Q` → "Planning aborted", no artifacts. Remove only for substance (out of scope, not ready) — the runner scales with session size.

## 4. Launch

1. **Pre-flight.** `git status --porcelain -- cortex/lifecycle/ cortex/backlog/`. Non-empty → the worktree is cut from HEAD, so the runner cannot see these files: show the paths and offer `/commit` once; still dirty afterwards → "Commit or stash the files above, then run `/overnight` again." and stop.

2. **Bootstrap.**

   ```
   cortex overnight launch --format json --only <comma-separated active slugs> [--time-limit-hours N]
   ```

   `--only` is the active pool at `[A]` — omitting it re-selects and loses the curation. Capture `session_id`, `state_dir`, `state_path`, `worktree_path`, `extracted_specs`. Non-zero exit → relay `message` and stop; on `bootstrap_failed` also `git worktree prune` and remove the stale `$TMPDIR/overnight-worktrees/` directory named by the session id.

3. **Batch specs.** `extracted_specs` non-empty → from `worktree_path`, `git add` those paths and `/commit` with `Extract batch spec sections for overnight session {session_id}` (lands on the integration branch). Failure → note it and continue; the runner re-extracts at startup.

4. **Dashboard.** Not running → mention `cortex dashboard` (or `just dashboard` from a clone) is optional and can start anytime.

5. **Run or schedule.** Ask `[1] Run now` / `[2] Schedule for specific time` (`HH:MM` 24-hour local, or `YYYY-MM-DDTHH:MM`). Both run via Bash with `dangerouslyDisableSandbox: true`, use the captured `state_path`, and return immediately; the runner logs `session_start` itself at fire time.

   ```
   cortex overnight start --state {state_path} --time-limit 21600
   cortex overnight schedule <target-time> --state {state_path}
   ```

   `--time-limit` is seconds (`21600` = 6h; mirror any adjusted limit). Schedule registers a one-shot LaunchAgent.

6. **Report.** Run now: "Overnight session launched. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`." Scheduled: the fire time and session id from the output. Resume anytime with `/overnight resume`.
