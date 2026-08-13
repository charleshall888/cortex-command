# Specification: make-cortex-dashboard-a-one-command

## Problem Statement

`cortex dashboard` cannot be launched as a bare command. It needs a cortex project as its working directory, it blocks the terminal it was typed in, it hands back a URL the operator must copy, and every repo past the first is a hand-typed `--also-root`. Worse, the page it serves carries no repo identity in the single-repo case, so an operator viewing one repo reads the product-branding string in the colophon as the repo name and concludes the `--root` flag is broken — which is what happened on 2026-08-13, when a wild-light-rooted dashboard rendering wild-light's 545 tickets was reported as showing cortex-command's backlog. This makes the dashboard one whole command it should be, and makes the page state which repo it is rendering.

## Phases

- **Phase 1: Repo identity** — the page names the repo it is showing, in every tracking mode.
- **Phase 2: Launcher** — the bare command works from anywhere, detaches, and opens the browser.

## Requirements

1. **The masthead names the tracked repo when one repo is tracked**: Start a server with a single root (`--root ~/Workspaces/wild-light --foreground --port P`); `curl -s http://127.0.0.1:P/backlog` contains the string `wild-light` inside the `<header>` element. Verified 2026-08-13 that the rendered page on HEAD contains **no** occurrence of `wild-light` under that invocation. Grounding: `cortex_command/dashboard/templates/base.html:2699-2716`. **Phase**: Repo identity

2. **Multi-repo switching is unchanged**: With two roots tracked, the rendered page still carries one anchor per repo whose `href` ends `?repo=<slug>`, and `cortex_command/dashboard/tests/test_templates.py` passes. **Phase**: Repo identity

3. **Product branding is not renamed**: After the change, `grep -c 'cortex-command · overnight dashboard' cortex_command/dashboard/templates/base.html` returns `1` and `grep -c 'cortex-command · backlog navigator' cortex_command/dashboard/templates/backlog.html` returns `1`. **Phase**: Repo identity

4. **The bare command works from a non-cortex directory**: From a directory with no `cortex/` ancestor, `CORTEX_DASHBOARD_ROOTS="$A:$B" cortex dashboard --port P --foreground` starts and serves, tracking `$A` then `$B`. Verified 2026-08-13 that on HEAD `_resolve_user_project_root()` raises `CortexProjectRootError` under exactly these conditions. Grounding: `cortex_command/dashboard/repos.py:112-145`, `cortex_command/common.py:87`. **Phase**: Launcher

5. **A fallback primary failing the `.claude/` check fails loudly**: With `CORTEX_DASHBOARD_ROOTS` whose first entry lacks `.claude/`, the process exits non-zero and stderr names that path. Silent advancement to the second entry is a defect, not a fallback. Grounding: `cortex_command/dashboard/app.py:339-345`. **Phase**: Launcher

6. **Background is the default**: `cortex dashboard --port P` returns to the shell within 20s, prints the URL on stdout, and the port accepts connections after it returns. **Phase**: Launcher

7. **`--foreground` blocks**: `cortex dashboard --port P --foreground` does not return while the port serves; terminating it stops the server. **Phase**: Launcher

8. **`--background` remains accepted as a no-op**: `cortex dashboard --background --format json --port P` — the MCP tool's exact argv per `plugins/cortex-overnight/server.py:2592` — exits 0 emitting an envelope whose `status` is `started` or `already_running`. **Phase**: Launcher

9. **The browser opens by default and is suppressed in three named cases**: A pytest asserts `webbrowser.open` is called once on a default launch, and not called when (a) `--no-open` is passed, (b) `--format json` is passed, or (c) stdout is not a TTY. Interactivity-detection precedent: `cortex_command/auth/bootstrap.py:90`. **Phase**: Launcher

10. **`just dashboard-demo` still blocks**: The `cortex dashboard` invocation at `justfile:156` carries `--foreground`. On HEAD, `grep -c foreground justfile` returns `0`. **Phase**: Launcher

11. **The JSON envelope reports every tracked root**: With `CORTEX_DASHBOARD_ROOTS` set and `--format json`, the `roots` array length equals the number of repos the server actually tracks. On HEAD it counts only flag-derived roots (`cortex_command/cli.py:530`). **Phase**: Launcher

12. **Owning docs are updated in the same phase**: `grep -c -- '--foreground' docs/dashboard.md` and `grep -c -- '--no-open' docs/dashboard.md` each return ≥1, and both surviving statements of the old blocking default are gone: `grep -c 'instead of blocking the terminal' docs/dashboard.md` returns `0` (it is `1` on HEAD) and `grep -c 'Blocks until interrupted' cortex_command/cli.py` returns `0` (it is `1` on HEAD, in the verb's own `--help` text). `cortex/requirements/observability.md`'s Dashboard section gains at least one acceptance-criteria bullet naming repo identity and one naming the launch default (`grep -c 'repo identity' cortex/requirements/observability.md` returns ≥1). Required by `docs/policies.md`. **Phase**: Launcher

## Non-Requirements

- **No root-discovery mechanism.** No filesystem scan, no config file, no repaired `allowWrite` registry. Resolved at Clarify: `CORTEX_DASHBOARD_ROOTS` already names the set, so discovery does not clear `project.md`'s Deletion-bias bar. A scan's predicate would immediately need exclusions for git worktrees, archived clones, and the seeded fixture root.
- **No colophon rename.** The strings are product branding and read correctly in a consumer repo; R3 guards them.
- **No bind-address change.** Loopback-only stands (`observability.md:107`).
- **No change to `just dashboard`.** It calls `uv run uvicorn` directly (`justfile:140`) and never reaches this verb.
- **Not an upgrade path.** The operator's install is v4.7.0 against a v4.9.3 repo; that is resolved by reinstalling, not by code here.

## Edge Cases

- `CORTEX_DASHBOARD_ROOTS` unset and cwd is not a cortex project: unchanged `CortexProjectRootError`. Correct — there is nothing to fall back to.
- `--root` passed explicitly: it wins as primary; env-derived roots append after it, preserving today's compose-don't-override contract.
- Server already running: the browser still opens. The operator asked to see the board and the running server is the board.
- Duplicate roots across flags and env: existing de-duplication in `resolve_roots` applies unchanged.
- `--no-open` together with `--foreground`: both honored; they are independent.

## Changes to Existing Behavior

- **MODIFIED** — `cortex dashboard` detaches by default instead of blocking, and opens the browser.
- **MODIFIED** — the masthead renders repo identity unconditionally rather than only when `repo_multi`.
- **MODIFIED** — `justfile:156` gains `--foreground` to preserve its blocking behavior.
- **MODIFIED** — the `started` JSON envelope's `roots` field counts env-derived roots.
- **ADDED** — `--foreground`, `--no-open`.
- **REMOVED** — nothing.

## Technical Constraints

- `webbrowser` is stdlib, so this adds nothing to `[project.dependencies]` and does not engage the distributed-CLI dependency-bounds rule (`project.md:54`).
- `resolve_roots` keeps `primary` with `require_dir=False`; the strict `.claude/` check lives in the lifespan (`app.py:339-345`). R5 depends on that split staying as it is.
- The verb must continue setting `CORTEX_REPO_ROOT` in-process only. Persisting it is forbidden by `docs/dashboard.md:87` because it silently redirects backlog creation, lifecycle verbs, and overnight writes.
- `subprocess.Popen` in `_dispatch_dashboard_background` must keep inheriting the environment, which is how `CORTEX_DASHBOARD_ROOTS` reaches the detached child today.

## Open Decisions

None. The one candidate — whether `--background` is deprecated or permanently accepted — is resolved as **permanently accepted**: the MCP plugin's argv is version-locked separately from the wheel, so a later removal would need its own coordinated change and buys nothing now.

## Proposed ADR

None. Both candidate decisions — flipping the default, and declining to build discovery — fail criterion 1 of the three-criteria gate in `cortex/adr/README.md`: each is reversible by editing one file in one PR. Recorded in this spec and in the ticket body instead.
