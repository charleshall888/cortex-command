# Specification: Route Python-layer backlog writes through worktree checkout

> **Epic context**: This ticket is scoped from epic 126 (orchestrator-worktree-escape). See [research/orchestrator-worktree-escape/research.md](../../research/orchestrator-worktree-escape/research.md) for broader context on the class of home-repo-vs-worktree escape bugs; this ticket fixes only the Python-layer backlog-write component.

## Problem Statement

The overnight runner's Python-layer backlog-write code paths currently resolve file-write targets using process `cwd` or an `integration_branches` dict (repo→branch map), bypassing the per-session worktree checkout. Two concrete defects were observed in session `overnight-2026-04-21-1708` (a home-repo-only session): new followup items from `create_followup_backlog_items()` landed as untracked files in the home repo and were silently clobbered three hours later by a `/discovery` run that reused the same numeric IDs; `session_id` frontmatter mutations landed both on the integration branch (via a post-loop cp) AND as uncommitted working-tree changes on home-repo `main`. The second defect leaves "zombie" uncommitted state on main until an operator cleans it up; the first produces permanent content loss. Both failure modes trace to the same architectural drift — Python helpers discovering their write path from cwd or from `integration_branches` rather than from `state.worktree_path` — and are fixed by threading the worktree-scoped backlog directory through the call chain explicitly.

## Requirements

1. **`create_followup_backlog_items()` accepts an explicit worktree-scoped backlog directory from every caller**: The two nominal callers (`claude/overnight/report.py:1435`, `claude/overnight/report.py:1525`) and the SIGINT trap caller (`claude/overnight/runner.sh:507-521`) pass a `backlog_dir` argument resolved from `state.worktree_path` rather than relying on the default `Path("backlog")`.
   - Acceptance (static grep): `grep -n "create_followup_backlog_items(data" claude/overnight/report.py claude/overnight/runner.sh` shows every invocation passing a second argument; no invocation relies on the default.
   - Acceptance (code read): `create_followup_backlog_items()` signature at `claude/overnight/report.py:272` no longer defaults `backlog_dir` to `Path("backlog")` — the parameter becomes required (no default), and callers pass an absolute path.

2. **`orchestrator.py:143` is fixed to source the backlog directory from `state.worktree_path`**: The current line `outcome_router.set_backlog_dir(Path(next(iter(integration_branches))) / "backlog")` is replaced with a lookup that uses `overnight_state.worktree_path`. `worktree_path` is the scalar field at `claude/overnight/state.py:244`, populated for every session by `plan.py:bootstrap_session`.
   - Acceptance (static grep): `grep -n "set_backlog_dir" claude/overnight/orchestrator.py` shows the line references `worktree_path`, not `integration_branches`.
   - Acceptance (integration): During a home-repo overnight session run against a fixture, `outcome_router._backlog_dir` equals `{worktree_path}/backlog`, verified by capturing the value in a test.

3. **The import-time `BACKLOG_DIR` module-level globals in `backlog/update_item.py` (line 38) and `backlog/create_item.py` (line 37) are replaced with an explicit `backlog_dir` argument threaded through the write entry points and their cascade helpers**: `update_item()`, `_remove_uuid_from_blocked_by()`, and `_check_and_close_parent()` in `update_item.py`, and `create_item()` in `create_item.py`, all accept a `backlog_dir` argument. The cascade helpers in `update_item.py` receive `backlog_dir` from their caller inside `update_item()` — the thread-through is mandatory, not defaulted.

   **No silent cwd fallback at the internal API level**: When `backlog_dir` is absent/None on any of these functions, they raise `TypeError` (or equivalent). The cwd-relative fallback (`Path.cwd() / "backlog"`) is isolated to the `update-item` / `create-item` interactive CLI entry points (their `main()` / argv-parsing layer), where the operator explicitly expects cwd-relative behavior. This prevents a missed internal thread-through from silently re-creating the home-repo write path the ticket exists to eliminate.

   - Acceptance (static grep): `grep -n "BACKLOG_DIR" backlog/update_item.py backlog/create_item.py` returns zero module-level uses inside `update_item()`, `_remove_uuid_from_blocked_by()`, `_check_and_close_parent()`, or `create_item()`. A module-level constant may survive only inside the CLI `main()` / argv layer.
   - Acceptance (code read): Each of the four named functions accepts and uses `backlog_dir` explicitly. A unit-style check confirms each function raises when called with `backlog_dir=None` — the default cannot silently fall back to cwd inside the internal API.
   - Acceptance (code read): The CLI entry points (`update_item.py:main` and `create_item.py:main` or equivalent) resolve `Path.cwd() / "backlog"` from argv / environment at the top of `main()` and pass it explicitly into the internal functions. This is the only cwd-based resolution in the module.

4. **A second `git add backlog/; git commit` block is added to `claude/overnight/runner.sh` in two places — once in the nominal flow after `generate_and_write_report`, and once in the SIGINT trap before `exit 130`**: The nominal block captures newly-created followup items written by `create_followup_backlog_items()` (which run AFTER the existing artifact commit at `runner.sh:1001-1014`). The trap-path block captures followups written by the trap's own `create_followup_backlog_items` call at approximately `runner.sh:513`. Both blocks are subshells cd'd to `$WORKTREE_PATH`, run `git add backlog/`, check `git diff --cached --quiet`, and commit with a distinguishable message (e.g., `"Overnight session ${SESSION_ID}: record followup backlog items"`). If nothing is staged the commit is skipped.

   **Success guard**: In the nominal flow, the second-commit block fires ONLY when `generate_and_write_report` exited 0. On non-zero exit (which is currently swallowed by `|| echo "Warning: morning report generation failed"` at `runner.sh:1198`/`:1214`), the second-commit block is skipped — avoiding a misleadingly-named commit over a partial followup set. The skip is logged as a `followup_commit_skipped` event to `lifecycle/pipeline-events.log` with reason `report_gen_failed`.

   - Acceptance (static grep): `grep -cn 'Overnight session.*record followup' claude/overnight/runner.sh` returns 2.
   - Acceptance (static grep): `grep -n 'generate_and_write_report' claude/overnight/runner.sh` shows one new commit block immediately follows the report-generation call site with an explicit exit-code check (e.g., `if [[ $report_gen_rc -eq 0 ]]; then ...`).
   - Acceptance (static grep): `grep -n 'create_followup_backlog_items' claude/overnight/runner.sh` shows a second new commit block inside the trap, placed after the trap's `create_followup_backlog_items` call and before `exit 130`.
   - Acceptance (integration): After a simulated session that creates a followup item in the nominal flow, `git log worktree-branch -- backlog/` on the integration branch shows a commit whose message matches the "record followup" pattern and whose diff includes the newly-created file.
   - Acceptance (integration): After a simulated session that creates a followup item via the SIGINT trap (SIGINT fired during the round loop), `git log worktree-branch -- backlog/` on the integration branch shows a trap-path commit whose diff includes the trap-written file.

5. **`create_followup_backlog_items()` sets `session_id` to the originating session ID, not hardcoded `null`**: The hardcode at `claude/overnight/report.py:345` is replaced with `os.environ.get("LIFECYCLE_SESSION_ID", "manual")`, matching the pattern already established at `claude/overnight/outcome_router.py:409` and `backlog/update_item.py:358`. If the env var is unset (e.g., the trap fires before the round loop), the sentinel `"manual"` is written — consistent with the existing convention.
   - Acceptance (static grep): `grep -n 'session_id: null' claude/overnight/report.py` returns zero matches inside `create_followup_backlog_items`.
   - Acceptance (static grep): `grep -n "LIFECYCLE_SESSION_ID" claude/overnight/report.py` shows the function reads the env var.

6. **`orchestrator.py:137-156`'s state-load failure gains observability without changing control flow**: On `load_state` exception, the existing `except Exception:` block continues to set the five dicts (`spec_paths`, `backlog_ids`, `recovery_attempts_map`, `repo_path_map`, `integration_branches`) to empty defaults — preserving the session's ability to continue the round loop. A new `state_load_failed` event is appended to `lifecycle/pipeline-events.log` with the exception type and message before the fallback values are set. Silent misdirection of backlog writes to `outcome_router._PROJECT_ROOT / "backlog"` still happens on corruption — the fix here is purely telemetry; a true session-pause primitive is deferred to a separate hardening ticket.
   - Acceptance (static grep): `grep -n 'state_load_failed' claude/overnight/orchestrator.py` returns the new event emission inside the except block.
   - Acceptance (code read): The `except Exception:` at `orchestrator.py:150-156` logs the event and still sets the five empty-dict defaults. Control flow is unchanged.
   - Acceptance (integration): With `lifecycle/overnight-state.json` deliberately corrupted during a test run, `lifecycle/pipeline-events.log` contains a `state_load_failed` event for that run; the session's round loop continues (existing behavior).

7. **A simulated failed session leaves no uncommitted backlog-file changes in the home-repo working tree**: After a test that starts a session, writes `session_id` mutations to backlog items via `_write_back_to_backlog` during the round loop, then fails, the home-repo `backlog/` directory has no modifications.
   - Acceptance (integration): After the simulated failed session, `git status --porcelain backlog/` run from the home repo returns empty output.
   - Acceptance (integration): Running `git diff -- backlog/` from the home repo after the failed session produces no output.

8. **The `update-item` and `create-item` binaries remain usable in interactive (non-session) contexts**: When invoked from a shell (e.g., by an operator or a skill), the binaries fall back to `Path.cwd() / "backlog"` at the CLI entry point — not at the internal-API level. The fallback is implemented inside each binary's `main()` function; it is NOT gated on env vars like `LIFECYCLE_SESSION_ID` or `STATE_PATH` (consistent with the Non-Requirements prohibition on env-var-based worktree signaling).
   - Acceptance (integration): `update-item <some-item> status=in_progress` executed from a fresh shell with `LIFECYCLE_SESSION_ID` unset and `STATE_PATH` unset writes to `$(pwd)/backlog/<item>.md`.
   - Acceptance (integration): `update-item <some-item> status=in_progress` executed from a shell where `LIFECYCLE_SESSION_ID` happens to be set still writes to `$(pwd)/backlog/<item>.md` — the env var is purely informational for session-id attribution, not routing.
   - Acceptance (code read): CLI `main()` functions in `update_item.py` and `create_item.py` compute `Path.cwd() / "backlog"` once at argv-processing time and pass it into internal functions explicitly.

9. **Morning-report rendering is unchanged modulo the session_id attribution fix**: The morning report's output for followup items includes the same titles, IDs, and structured body content it produces today, with the single expected difference that followup items now carry the originating session ID instead of `null` (Requirement 5).
   - Acceptance (integration): Running the morning-report generator on a fixture session produces output byte-identical to a pre-change baseline for the same fixture, modulo the one expected change for followup-item `session_id` values (from `null` to the fixture's session id).
   - Acceptance (code read): No changes to the morning-report rendering code in `report.py` beyond the `session_id` hardcode fix at line 345.

## Non-Requirements

- **Cross-repo followup routing is explicitly out of scope.** Per-feature routing of followups to their own repo's worktree is a follow-up ticket. This ticket's fix applies uniformly to whatever `state.worktree_path` resolves to:
  - For **home-repo-only sessions** (the failure population observed in session 1708): `state.worktree_path` = the home-repo worktree. Fix routes followups there. This is the primary case the ticket addresses.
  - For **mixed sessions (home-repo + cross-repo features)**: per `plan.py:487-488`, `state.worktree_path` = the home-repo worktree. Fix routes followups there. Same behavior as home-repo-only.
  - For **pure wild-light sessions (cross-repo only, no home-repo features)**: per `plan.py:489-494`, `state.worktree_path` = the cross-repo worktree. Fix routes followups to the cross-repo worktree — which is where today's cwd-based code (after `runner.sh:595`'s `cd "$WORKTREE_PATH"`) also routes them in the nominal path. Behavior is unchanged for this session class; fix adds the R4 commit block so the writes land on that repo's integration branch.
  - The spec does NOT attempt to route followups to the home-repo worktree for pure wild-light sessions via `integration_worktrees[project_root]` — that routing is a follow-up ticket.
- **Session-pause primitive for state-corruption is not added.** R6 adds telemetry only (`state_load_failed` event). The silent-misdirection defect on state corruption (writes route to `outcome_router._PROJECT_ROOT / "backlog"` = the cortex-command repo) is a pre-existing latent bug that survives this ticket. A separate hardening ticket will implement a true session-pause mechanism.
- **Auto-deleting integration branches on session failure is not added.** Integration branches persist by design per `requirements/pipeline.md:133`. The original backlog item's "discarded cleanly on a failed or closed branch" framing is reinterpreted here as "does not pollute local main while the branch remains unmerged" — a branch is discarded by operator action (e.g., `git branch -D` after closing the PR), not automatically.
- **The runner's orchestrator-prompt disambiguation is out of scope.** Sibling ticket in epic 126.
- **The git pre-commit hook that rejects commits to main during an overnight session is out of scope.** Sibling ticket in epic 126.
- **Morning-report commit un-silence is out of scope.** Sibling ticket in epic 126.
- **PR-creation gating is out of scope.** Separate ticket.
- **Retroactive cleanup of already-lost content from session 1708 (IDs 101/102/103) is out of scope.** Content is permanently lost; recovery is a separate operator-driven task.
- **Dashboard, statusline, and other read-only observability code are not modified.** They already read backlog frontmatter correctly; no change needed.
- **New env vars for worktree-path signaling are not introduced.** Web research and the adversarial review both flagged env-var-based worktree signaling as a leaky mechanism (`GIT_DIR`/`GIT_WORK_TREE` class of footgun). The fix uses explicit function arguments and the existing `state.worktree_path` / `load_state()` surface. R8 specifically avoids env-var-based discriminators for the interactive-vs-session split; it is purely argument-based.
- **Transient state-read-failure handling is not added.** If `load_state` fails due to a transient condition (filesystem hiccup, truncated JSON from a crashed concurrent save, dashboard reader holding the file open), the session will continue with empty defaults the same as today. R6 adds observability of these events but does not add retry or transient-vs-persistent classification.

## Edge Cases

- **SIGINT trap fires before the round loop starts**: The trap at `runner.sh:507-521` calls `create_followup_backlog_items()` with a worktree path resolved from the already-populated `$WORKTREE_PATH` shell variable (set at `runner.sh:243-247`). The worktree exists on disk (created by `plan.py:bootstrap_session` before `runner.sh` starts). `LIFECYCLE_SESSION_ID` may be unset at this point — the new item's `session_id` falls back to `"manual"` per Requirement 5. The new trap-path second-commit block (Requirement 4) runs immediately after the trap's `create_followup_backlog_items` call and before `exit 130`, capturing the followups on the integration branch.

- **`state.worktree_path` is None or empty**: Should not occur for a session started via `plan.py:bootstrap_session`, which always sets it. If it somehow is unset at the point where the fix resolves a backlog directory, the code raises (per Requirement 3's "no silent fallback" rule) rather than defaulting to cwd. A subsequent ticket will add fallback semantics if needed.

- **Worktree directory does not exist on disk at write time**: If the worktree was torn down before the Python write runs (e.g., in an interrupted cleanup path), `atomic_write` will fail when creating its tempfile in the missing parent directory. Expected: raise the filesystem error; the runner's existing error handling paths decide next steps. Do NOT silently fall back to the home repo.

- **Interactive `update-item` invocation from home-repo cwd during an active overnight session**: An operator running `update-item 095 status=complete` from the home repo hits `$(pwd)/backlog/095-*.md` regardless of any env-var state leak (per Requirement 8). Session-internal callers pass the worktree path explicitly; interactive callers rely on the CLI's own cwd-relative resolver at `main()`. The two paths do not interfere.

- **Non-CLI in-session callers of `update-item` (e.g., `/commit` hook, skills)**: When these callers invoke `update-item` as a subprocess from within an overnight-spawned Claude, the subprocess's cwd determines routing — same as any CLI invocation. This matches the existing behavior (today's code also uses process cwd); the fix does not change it. If a hook running inside a session needs worktree-scoped writes, it must `cd` to the worktree before calling `update-item` — this is a pre-existing convention the ticket does not alter.

- **`_find_item()` in `update_item.py` finds no match**: Unchanged from today. Returns `None` and the caller handles it. `_find_item` now takes `backlog_dir` explicitly per Requirement 3.

- **`LIFECYCLE_SESSION_ID` env var set but not overnight-scoped** (e.g., stale export in a user shell): `create_followup_backlog_items()` writes that env value as the `session_id` on new items. Out-of-band invocations are a pre-existing concern; fix is no worse than status quo. Because R8 does NOT use `LIFECYCLE_SESSION_ID` as a routing discriminator, this stale-env leak affects only session-id attribution (R5 behavior), not the write-target path (R8 is argument-based).

- **`generate_index.py` subprocess after a write**: The subprocess's cwd is the parent's cwd. Session callers must either `cd` to the worktree before spawning the subprocess, or pass an explicit `--backlog-dir` flag if the CLI gains one. Minimal change: ensure the outcome_router call site spawns `generate_index.py` with `cwd=backlog_dir.parent` or equivalent. If the index regenerates into the wrong directory, the index drift is recoverable by a subsequent regeneration; it is not a data-loss path.

- **Report generation fails midway through writing followup items**: R4's success guard ensures the second-commit block skips on non-zero exit from `generate_and_write_report`, and a `followup_commit_skipped` event is logged with reason `report_gen_failed`. Any partially-written followups remain in the worktree until the worktree is cleaned up, at which point they are discarded — consistent with "branch is abandoned" semantics. Partial-commit risk is avoided.

- **Pure wild-light session during R4 execution**: `$WORKTREE_PATH` in `runner.sh` is the cross-repo worktree (per `plan.py:489-494`). R4's `cd "$WORKTREE_PATH"; git add backlog/; git commit` runs inside the cross-repo worktree and commits to the cross-repo integration branch. This is intentional for this session class and consistent with the Non-Requirements' pure-wild-light carve-out.

## Changes to Existing Behavior

- **MODIFIED**: `claude/overnight/report.py:272` — `create_followup_backlog_items()` signature: `backlog_dir` becomes a required parameter (no default). All callers updated.
- **MODIFIED**: `claude/overnight/report.py:345` — `session_id: null` hardcode replaced with `os.environ.get("LIFECYCLE_SESSION_ID", "manual")`.
- **MODIFIED**: `claude/overnight/orchestrator.py:143` — `set_backlog_dir` sources from `overnight_state.worktree_path`, not `integration_branches`.
- **MODIFIED**: `claude/overnight/orchestrator.py:150-156` — `except Exception:` block now logs a `state_load_failed` event before setting the five empty-dict defaults. Control flow is unchanged.
- **MODIFIED**: `backlog/update_item.py` — `update_item()`, `_remove_uuid_from_blocked_by()`, and `_check_and_close_parent()` take a required `backlog_dir` argument; raise when it is absent/None at the internal API level. The module-level `BACKLOG_DIR` constant survives ONLY inside the CLI `main()` argv-processing layer.
- **MODIFIED**: `backlog/create_item.py` — `create_item()` takes a required `backlog_dir` argument; raises when absent/None at the internal API level. `BACKLOG_DIR` module-level constant survives ONLY inside the CLI `main()` layer.
- **MODIFIED**: `claude/overnight/outcome_router.py:382-427` — `_write_back_to_backlog()` passes `backlog_dir` explicitly to each `update_item` call (and implicitly to cascades via that argument).
- **ADDED**: `claude/overnight/runner.sh` — a new subshell block after `generate_and_write_report` invocation, gated on report-generation exit code: `cd "$WORKTREE_PATH"; git add backlog/; git diff --cached --quiet || git commit -m "Overnight session ${SESSION_ID}: record followup backlog items"`.
- **ADDED**: `claude/overnight/runner.sh` — a second new subshell block inside the SIGINT trap at `runner.sh:507-521`, placed after the existing `create_followup_backlog_items` call and before `exit 130`, with the same `cd "$WORKTREE_PATH"; git add; git commit` logic.
- **ADDED**: `claude/overnight/orchestrator.py` — a new `state_load_failed` event type logged to `lifecycle/pipeline-events.log` on state-corruption.
- **ADDED**: `claude/overnight/runner.sh` — a new `followup_commit_skipped` event emitted when the nominal-flow second-commit block is skipped due to report-generation failure.

## Technical Constraints

- All file writes preserve atomic-write discipline: `claude/common.py:382-395`'s `atomic_write()` (tempfile + `os.replace()`). No direct writes.
- `git -C` is never introduced; all git operations run from the worktree's cwd via subshell `cd` (consistent with `claude/rules/sandbox-behaviors.md`).
- Compound commands are not introduced in shell changes; the new commit blocks use subshells, not `&&`-chained commands.
- The `update-item` / `create-item` binaries are symlinks to the Python modules; changes to the modules must preserve the interactive-CLI contract (Requirement 8).
- The new `state_load_failed` and `followup_commit_skipped` events follow the existing NDJSON event schema in `lifecycle/pipeline-events.log`.
- Line numbers cited above reflect current main (`git rev-parse HEAD` at spec time). Implementation may see minor drift; the spec's requirements are anchored to function names and grep patterns, not exact line numbers.

## Open Decisions

- None. All scope decisions were resolved during the §2 interview and the critical-review disposition step; implementation-level details (exact line placement for the new commit blocks within `runner.sh`, exact function-signature changes for cascade helpers, exit-code-check syntax for the success guard) are Plan phase concerns, not spec-time decisions.
