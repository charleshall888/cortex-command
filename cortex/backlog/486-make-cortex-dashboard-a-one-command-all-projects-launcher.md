---
schema_version: "1"
uuid: 1e14ba53-78b3-4f8a-a0cb-71a5c866e6e4
title: Make cortex dashboard a one-command all-projects launcher
status: refined
priority: medium
type: feature
created: 2026-08-13
updated: 2026-08-13
tags: ['dashboard', 'cli']
blocked-by: []
blocks: []
complexity: moderate
criticality: medium
spec: cortex/lifecycle/make-cortex-dashboard-a-one-command/spec.md
areas: ['dashboard']
---
## Why

Observed failure, this session: an operator ran `cortex dashboard --root ~/Workspaces/wild-light`, read `cortex-command · backlog navigator` in the colophon, and concluded `--root` was broken. It was not. The ledger rendered **545 items** against wild-light's 547 backlog files (cortex-command has 479), and the triage board listed wild-light tickets (`#236 Performant world-display architecture`). The data was correct the whole time; the page said otherwise.

The cause is that a single-repo dashboard carries **no repo identity at all** — the switcher is suppressed below two repos (`RepoRegistry.multi`), so the hardcoded product-branding string is the only repo-shaped text on the page, and it names the wrong repo.

Measured alongside it:

- Reaching all five cortex projects on this machine today requires `--root` plus four hand-typed `--also-root` flags. No discovery exists.
- The one candidate registry — `sandbox.filesystem.allowWrite` in `~/.claude/settings.local.json` — is **both stale and incomplete**: it names `pixel-art-generator` (which has no `.claude/`) and misses Team-Builder-Bot, gaggimate-barista, and hall-dental. A filesystem scan of the workspace parent finds all five.
- No `webbrowser`, `xdg-open`, or `open` call exists anywhere in `cortex_command/`, so every launch ends with the operator copying a URL out of the terminal.
- `--background` ships but is opt-in, so the default launch blocks the terminal it was typed in.

## Role

Make `cortex dashboard` with no arguments the entire launch: every cortex project on the machine tracked, the browser opened to it, the terminal returned.

## Integration

Extends the multi-root machinery already in `repos.py` (`resolve_roots`, `build_registry`, `CORTEX_DASHBOARD_ROOTS`) rather than replacing it — the primary-root fallback reads the existing env var as its source, and explicit `--root` / `--also-root` continue to compose with it.

## Edges

- **Default flip is a shipped-surface change.** `--foreground` must exist for the blocking form, and the `dashboard_open` MCP tool passes `--background --format json` — that must keep working, so `--background` stays accepted as a no-op rather than erroring.
- The primary root keeps its strict `.claude/` check, so a fallback primary inherits it — a typo in the first `CORTEX_DASHBOARD_ROOTS` entry must fail loudly naming that path, never advance silently to the second.
- Browser auto-open needs an opt-out for headless, CI, and overnight-runner contexts, and must not re-open a tab when reporting an `already_running` server.
- The colophon fix must distinguish product branding from repo identity — showing the repo name unconditionally is the fix, not renaming the product.

## Touch-points

- `cortex_command/cli.py` — dashboard verb, argparse, `_dispatch_dashboard_background`
- `cortex_command/dashboard/repos.py` — `resolve_roots` primary-root fallback
- `cortex_command/dashboard/app.py` — lifespan root resolution, `_ctx`
- `cortex_command/dashboard/templates/base.html:2699-2716` — the `{% if repo_multi %}` switcher block. Research ruled the colophon strings (`backlog.html:98`, `base.html:2787`) **out of scope**: they are product branding that reads correctly in a consumer repo.
- `docs/dashboard.md`
- `tests/test_cli_dashboard.py`, `cortex_command/dashboard/tests/test_repos.py`

## Resolved at Clarify: no discovery mechanism

The discovery question is closed — **none of the three candidates is built.** `CORTEX_DASHBOARD_ROOTS` already exists and already composes with the flags, so naming the set is a solved problem and new machinery does not clear `project.md`'s Deletion-bias bar.

What the env var genuinely cannot do today is the measured gap this ticket now targets: `resolve_roots` requires a *primary* root from `_resolve_user_project_root()`, which raises `CortexProjectRootError` when cwd is not a cortex project. So `cortex dashboard` from `~` fails **even with `CORTEX_DASHBOARD_ROOTS` exported**, and the only documented workaround — exporting `CORTEX_REPO_ROOT` — is what `docs/dashboard.md:87` forbids, because it silently redirects backlog creation, lifecycle verbs, and overnight writes.

The fix is therefore a fallback, not a discovery subsystem: when cwd resolution fails, the first `CORTEX_DASHBOARD_ROOTS` entry serves as primary. A scan was rejected because its predicate ("directories carrying `cortex/` and `.claude/`") is unbounded and would immediately need exclusions for git worktrees, archived clones, and the seeded fixture root — machinery to undo machinery. A persisted config list written by `cortex init` was rejected as unearned now, and is **strictly additive** on top of this fallback rather than a redo of it, so deferring it passes the Solution-horizon test.

## Scope

1. Primary-root fallback to the first `CORTEX_DASHBOARD_ROOTS` entry, so the no-arg command works from any directory.
2. Browser auto-open, with an opt-out for headless/CI/overnight contexts.
3. Background by default; `--foreground` for the blocking form; `--background` stays accepted as a no-op.
4. Repo identity in the masthead, so a single-repo dashboard names the repo it is rendering.
