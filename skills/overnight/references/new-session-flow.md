# New Session Flow (`/overnight`)

## 1. Guard

Run `cortex overnight status`. A session whose phase is not `complete` is active: offer to resume it (switch to the resume flow) or abandon it and start fresh.

## 2. Prepare

```
cortex overnight prepare --format json
```

Reads only; safe to re-run. Non-zero exit → show `message` and stop. No eligible items → report "Nothing ready for overnight execution", list the ineligible items in `selection` with reasons, suggest `/cortex-core:refine` on the top ones, and stop. Otherwise show `selection` (counts, features per batch, ineligible items and reasons) and `plan_markdown`. To re-render, re-run with `--time-limit-hours N` or `--batch-size-cap N`.

## 3. Curate and approve

Read each selected feature's `cortex/lifecycle/{slug}/spec.md`. Unreadable → "Cannot read spec for {title}: {error}"; offer to remove it or abort.

**Suitability triage.** Judge once, on first entry; re-renders reuse the result. Nobody watches the run, so lean toward excluding: a set-aside item is easy to re-add, a bad run wastes the night. Set a feature aside, with a one-line reason, when it:

- has an acceptance criterion marked `Interactive/session-dependent`
- has a real item under `## Open Decisions`
- needs network or credentials the sandbox lacks
- needs a human to look at or judge the result
- is exploratory or under-specified

Flag a set-aside that blocks a kept feature: `launch` refuses a set that leaves out a kept feature's in-session blocker.

Three pools: **active** (runs), **set aside** (re-addable), **hard-ineligible** (missing artifacts, epic, blocked, merged — shown only, never re-addable).

Show the plan, then each active spec inline:

```
─────────────────────────────────────────
Spec [n/N]: {title}  (cortex/lifecycle/{slug}/spec.md)
─────────────────────────────────────────
{spec content}
```

then the set-aside pool with reasons, then the hard-ineligible pool. Make an empty active pool obvious. Show all three pools before every approval prompt: what is shown is what launches.

```
Approve this plan and specs?

  [A] Approve — launch exactly the active pool
  [R] Remove a feature — move an active feature out of the run
  [I] Include a set-aside item — re-add a set-aside feature   (shown only when the pool is non-empty)
  [T] Adjust time limit — change from the default 6h
  [Q] Abort — stop planning
```

- `R` / `I` move one feature and show the pools again. Do not re-run selection; that would bring back removed items. Refuse a hard-ineligible target and give its reason.
- `T` re-renders, then re-applies the current curation so no feature changes pool.
- `Q` → "Planning aborted", no artifacts.

Remove a feature only for substance (out of scope, not ready); the runner scales with session size.

## 4. Launch

1. **Pre-flight.** `git status --porcelain -- cortex/lifecycle/ cortex/backlog/`. Non-empty → the worktree is cut from HEAD, so the runner cannot see these files. Show the paths and offer `/commit` once. Still dirty → "Commit or stash the files above, then run `/overnight` again." and stop.

2. **Bootstrap.**

   ```
   cortex overnight launch --format json --only <comma-separated active slugs> [--time-limit-hours N]
   ```

   `--only` is the active pool at `[A]`; without it the command re-selects and the curation is lost. Capture `session_id`, `state_dir`, `state_path`, `worktree_path`, `extracted_specs`. Non-zero exit → show `message` and stop. On `bootstrap_failed` also run `git worktree prune` and remove the stale `$TMPDIR/overnight-worktrees/` directory named by the session id.

3. **Batch specs.** If `extracted_specs` is non-empty: from `worktree_path`, `git add` those paths and `/commit` with `Extract batch spec sections for overnight session {session_id}` (lands on the integration branch). Failure → note it and go on; the runner re-extracts at startup.

4. **Dashboard.** Not running → mention `cortex dashboard` (or `just dashboard` from a clone) is optional and can start anytime.

5. **Run or schedule.** Ask `[1] Run now` / `[2] Schedule for specific time` (`HH:MM` 24-hour local, or `YYYY-MM-DDTHH:MM`). Both run via Bash with `dangerouslyDisableSandbox: true`, use the captured `state_path`, and return at once. The runner logs `session_start` itself when it starts.

   ```
   cortex overnight start --state {state_path} --time-limit 21600
   cortex overnight schedule <target-time> --state {state_path}
   ```

   `--time-limit` is in seconds (`21600` = 6h); match any adjusted limit. Schedule registers a one-shot LaunchAgent.

6. **Report.** Run now: "Overnight session launched. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`." Scheduled: the fire time and session id from the output. Resume anytime with `/overnight resume`.
