# Plan: make-cortex-dashboard-a-one-command

## Overview

Two independent seams carry the whole feature: the masthead gains unconditional repo identity, and the `dashboard` verb's launch surface gains a primary-root fallback, a flipped default, and a browser open. No new module, no new state, no new config — every change lands in a file that already exists, and the root list keeps its single source of truth in `CORTEX_DASHBOARD_ROOTS`.

## Outline

### Phase 1: Repo identity (tasks: 1)
**Goal**: A dashboard rendering one repo says which repo it is rendering.
**Checkpoint**: A single-root server's `/backlog` HTML contains the repo's directory name inside `<header>`, and the colophon strings are byte-identical to HEAD.

### Phase 2: Launcher (tasks: 2, 3, 4, 5)
**Goal**: `cortex dashboard` is a whole command from any directory — detached, browser open, every root tracked.
**Checkpoint**: From a non-cortex directory with `CORTEX_DASHBOARD_ROOTS` set, the bare verb returns to the shell, the port serves, and the browser opened.

## Tasks

### Task 1: Render repo identity unconditionally in the masthead
- **Files**: `cortex_command/dashboard/templates/base.html`, `cortex_command/dashboard/tests/test_templates.py`
- **What**: Lift the repo name out of the `{% if repo_multi %}` gate so the single-repo case shows it too — links when several repos are tracked, a plain static label when one is. Satisfies spec R1 and R2 without touching R3's branding strings.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The switcher block is `base.html:2699-2716`, wrapped in `{% if repo_multi %}`. Template context already carries `repos`, `repo`, `repo_multi`, and `repo_query` via `_ctx` (`app.py:101`) — no new context keys. `repo.label` is the bare directory name (`repos.py:167`). Existing CSS classes `repo-switch`, `repo-switch__label`, `repo-switch__item`, `repo-switch__item--on` are defined at `base.html:449`; reuse rather than adding a class. Do **not** touch `base.html:2787` or `backlog.html:98`.
- **Verification**: `uv run pytest cortex_command/dashboard/tests/test_templates.py -q` passes, and the added test asserts that rendering the backlog view with a one-repo registry produces HTML containing that repo's label inside the `<header>` element while a two-repo registry still emits one `?repo=<slug>` anchor per repo.
- **Status**: [ ] pending

### Task 2: Fall back to the first CORTEX_DASHBOARD_ROOTS entry as primary root
- **Files**: `cortex_command/dashboard/repos.py`, `cortex_command/dashboard/tests/test_repos.py`
- **What**: Give `resolve_roots` (or a small resolver beside it) a path for the case where cwd-based primary resolution raises, so the first env-named root becomes primary. Satisfies spec R4 and R5.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_resolve_user_project_root()` (`common.py:87`) raises `CortexProjectRootError` when `CORTEX_REPO_ROOT` is unset and no ancestor carries `cortex/`. `resolve_roots(primary, extra)` is at `repos.py:112-145` and keeps `primary` with `require_dir=False` while dropping bad extras. The strict `.claude/` check lives in the lifespan (`app.py:339-345`) and must keep raising — spec R5 requires a first-entry typo to fail loudly naming the path, never to advance silently to the second entry. `ROOTS_ENV` is `repos.py:34`. The caller is `app.py:332`.
- **Verification**: `uv run pytest cortex_command/dashboard/tests/test_repos.py -q` passes, and the added tests assert (a) with cwd resolution failing and `CORTEX_DASHBOARD_ROOTS="A:B"`, the resolved list is `[A, B]` with A primary; (b) with the env var unset and cwd resolution failing, `CortexProjectRootError` still propagates.
- **Status**: [ ] pending

### Task 3: Reshape the dashboard verb's launch surface
- **Files**: `cortex_command/cli.py`, `tests/test_cli_dashboard.py`
- **What**: Flip the default to detached, add `--foreground` and `--no-open`, open the browser subject to three suppressions, and count env-derived roots in the JSON envelope. Satisfies spec R6, R7, R8, R9, R11, and the `cli.py` half of R12.
- **Depends on**: none
- **Complexity**: moderate
- **Context**: The verb body starts near `cli.py:501`; argparse registration is `cli.py:1386-1420`; the `--background` branch is `cli.py:533-536`; `_port_is_serving` is `cli.py:564`; `_dispatch_dashboard_background` is `cli.py:580` and builds argv from `roots` at `cli.py:530` (which omits `CORTEX_DASHBOARD_ROOTS` entries — that is the R11 defect). `_JSON_SCHEMA_VERSION` comes from `cortex_command.overnight.cli_handler`. Browser open uses stdlib `webbrowser` (no dependency-bounds impact); suppress when `--format json`, when `--no-open`, or when stdout is not a TTY — interactivity-detection precedent is `auth/bootstrap.py:90`. `--background` must remain an accepted no-op: `plugins/cortex-overnight/server.py:2592` passes `["dashboard", "--background", "--format", "json"]`. The verb's argparse `description` still reads "Blocks until interrupted" (`cli.py:1392`) and must change. Keep `CORTEX_REPO_ROOT` in-process only, and keep `Popen` inheriting the environment (`cli.py:634-639`) — that inheritance is how env roots reach the detached child.

  **Callers of this command, enumerated (searched 2026-08-13, all four):** `justfile:156` — breaks on the flip, repaired by Task 4. `plugins/cortex-overnight/server.py:2592` — passes `--background` explicitly, needs no edit, and is the reason that flag must stay accepted. `justfile:123-140` (`just dashboard`) — calls `uv run uvicorn` directly and never reaches this verb. `cortex/lifecycle.config.md:14` demo-command — resolves to `just dashboard`, so likewise unaffected. Only `justfile:156` requires a change, which is why it is the sole caller carried as a dependent task rather than listed in this task's Files.
- **Verification**: `uv run pytest tests/test_cli_dashboard.py -q` passes, and the added tests assert `webbrowser.open` is called once on a default launch and not called under each of `--no-open`, `--format json`, and a non-TTY stdout; that `--background --format json` still exits 0 with a `status` of `started` or `already_running`; and that `grep -c 'Blocks until interrupted' cortex_command/cli.py` returns 0.
- **Status**: [ ] pending

### Task 4: Keep just dashboard-demo blocking
- **Files**: `justfile`
- **What**: Add `--foreground` to the `dashboard-demo` recipe's verb invocation so the recipe keeps serving instead of returning immediately once the default flips. Satisfies spec R10.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: The invocation is `justfile:156` (`uv run cortex dashboard --root "$ROOT" --port {{dashboard_port}}`), the final and deliberately blocking line of the recipe. The `dashboard` recipe at `justfile:123-140` calls `uv run uvicorn` directly and must **not** be touched — it never reaches this verb.
- **Verification**: `grep -c -- '--foreground' justfile` returns `1`, and `grep -c 'uv run uvicorn' justfile` still returns `1` (proving the untouched recipe stayed untouched).
- **Status**: [ ] pending

### Task 5: Update the owning docs
- **Files**: `docs/dashboard.md`, `cortex/requirements/observability.md`
- **What**: Document the new default and both new flags, remove the stale statement of the old blocking default, and give the Dashboard requirement acceptance criteria for repo identity and launch defaults. Satisfies spec R12.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `docs/dashboard.md` owns dashboard behavior and `cortex/requirements/observability.md` owns the area's acceptance criteria — `docs/policies.md` requires the owning doc to be updated in the same phase as the change. The stale sentence is `docs/dashboard.md:27` ("instead of blocking the terminal"), which describes `--background` as the non-blocking option. The Dashboard requirement block is `observability.md:27-39`; its loopback constraint at `observability.md:107` is unchanged by this feature and must stay.
- **Verification**: `grep -c -- '--foreground' docs/dashboard.md` ≥ 1, `grep -c -- '--no-open' docs/dashboard.md` ≥ 1, `grep -c 'instead of blocking the terminal' docs/dashboard.md` = 0, and `grep -c 'repo identity' cortex/requirements/observability.md` ≥ 1.
- **Status**: [ ] pending

## Risks

- **The default flip is user-visible and reaches every consumer repo.** Research found exactly one code caller that depends on blocking (`just dashboard-demo`, Task 4); the MCP tool passes `--background` explicitly and `just dashboard` bypasses the verb. The residual risk is operator muscle memory, not breakage, and `--foreground` is the one-flag revert.
- **Browser auto-open is the change most likely to annoy.** The three suppressions in Task 3 are the mitigation; if any context was missed, `--no-open` is the escape hatch and no state is corrupted either way.
- **Task 3 is the only task touching `cli.py`.** Deliberate — the three CLI-surface changes all edit the same verb body, so splitting them would buy serialized edits rather than parallelism.
