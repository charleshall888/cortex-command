# Research: one-command all-projects dashboard launcher

> Feature: `make-cortex-dashboard-a-one-command` · Ticket #486
> Tier: moderate · Criticality: medium
> Clarified intent: make `cortex dashboard` with no arguments launch every project named in `CORTEX_DASHBOARD_ROOTS` from any directory, in the background, with the browser opened; and make the rendered page name the repo it is showing.

## Method

Inline code reading (no dispatched agents — the session's standing no-agent rule, filed as #483). Every claim below is anchored to a path and line and was read, not inferred. Two claims were additionally executed against a live server.

## Q1 — Which callers depend on `cortex dashboard` blocking?

Exactly **one**, and it is not the one the ticket assumed.

| Caller | Invocation | Affected by a default flip? |
|---|---|---|
| `just dashboard` (`justfile:123-140`) | `uv run uvicorn cortex_command.dashboard.app:app --host … --port …` | **No** — bypasses the verb entirely, calls uvicorn directly |
| `just dashboard-demo` (`justfile:150-156`) | `uv run cortex dashboard --root "$ROOT" --port …` as its final, deliberately blocking line | **Yes** — must gain `--foreground` |
| `dashboard_open` MCP tool (`plugins/cortex-overnight/server.py:2592`) | `["dashboard", "--background", "--format", "json"]` | **No** — passes `--background` explicitly; safe provided the flag stays accepted |
| `cortex/lifecycle.config.md:14` demo-command | `just dashboard` | **No** — resolves to the uvicorn recipe above |
| Overnight liveness probe | reads the PID file via `_resolve_pid_path` | **No** — reads a file, not process shape |

This narrows the blast radius substantially from the ticket's Edges section, which named `just dashboard` as a consumer. It is not one. The single required companion edit is `justfile:156`.

## Q2 — How should browser-open be suppressed?

`webbrowser` is **stdlib**, so this adds no entry to `[project.dependencies]` and does not engage the distributed-CLI dependency-bounds constraint (`project.md:54`).

Precedent for interactivity detection already exists at `cortex_command/auth/bootstrap.py:90` (`if not sys.stdin.isatty():`). Three suppression conditions, all readable at the call site:

1. `--format json` is passed — an unambiguous machine caller. This is what keeps the MCP tool from hijacking the operator's browser when an agent calls `dashboard_open`.
2. `--no-open` is passed — the explicit operator opt-out.
3. stdout is not a TTY — headless, CI, and piped invocations.

Opening on an `already_running` result is **correct**, not a bug: the operator asked to see the board, and the running server is the board.

## Q3 — Where does repo identity belong? (This overturns the ticket.)

The ticket says to fix the hardcoded colophon strings so they name the repo being rendered. **Research does not support that fix.**

`base.html:2787` (`cortex-command · overnight dashboard`) and `backlog.html:98` (`cortex-command · backlog navigator`) are *product* branding — "the cortex-command tool's backlog navigator". In a consumer repo that reading is correct, and rewriting them to the repo name would rename the product inside every consumer's install to fix a symptom.

The actual defect is narrower and is at `base.html:2699-2716`: the repo switcher is wrapped in `{% if repo_multi %}`, so a single-repo dashboard renders **no repo identity anywhere on the page**. The colophon is then the only repo-shaped text left, which is why it got read as the answer to "which repo am I looking at".

The fix is to render repo identity unconditionally in that same masthead slot — as the existing links when `repo_multi`, as a plain static label when not. `repos`, `repo`, and `repo.label` already reach every template through `_ctx` (`app.py:101`), so no new context plumbing is needed and no route can render the shell against one repo and its panels against another.

Leave both colophon strings alone.

## Q4 — Do env-derived roots survive `--background`'s re-exec?

**Yes, by environment inheritance — but the JSON output under-reports them.**

`cli.py:530` builds `roots = [os.environ.get("CORTEX_REPO_ROOT", "")] + list(also_root or [])`, which omits anything from `CORTEX_DASHBOARD_ROOTS`. That list becomes the child's `--root` / `--also-root` argv. However `subprocess.Popen` is called without `env=` (`cli.py:634-639`), so the child inherits `CORTEX_DASHBOARD_ROOTS`, and `resolve_roots` (`repos.py:139`) reads it at lifespan. The tracked set is therefore correct.

What is wrong is the `roots` field in the `started` JSON envelope: it reports only flag-derived roots, so a machine caller inspecting it sees fewer repos than the server actually serves. Worth correcting alongside the fallback.

## Q5 — The primary-root fallback's failure mode

`resolve_roots(primary, extra)` always keeps `primary` even without a `cortex/` directory (`repos.py:137`, `require_dir=False`), but the lifespan then applies a strict check and raises `RuntimeError` when `primary.root / ".claude"` is absent (`app.py:339-345`).

So a fallback primary taken from the first `CORTEX_DASHBOARD_ROOTS` entry inherits that strictness: a typo in the first entry kills the process. Recommendation is to **fail loudly naming the offending path** rather than silently advancing to the second entry — silent advancement hides a typo behind a dashboard that looks right but is missing a repo, which is the exact failure class this ticket exists to close.

## Verified against a running server

Two claims were executed rather than read, since the ticket's central premise depended on them:

- `cortex dashboard --root ~/Workspaces/wild-light` (installed v4.7.0, port 8092) rendered a ledger of **545 items**; wild-light carries 547 `cortex/backlog/*.md` and cortex-command carries 479. The triage partial returned wild-light tickets (`#236 Performant world-display architecture`, `#247 Host sim-CPU budget…`). `--root` routes data correctly; the report of it being broken was a label problem.
- The operator's installed CLI is **v4.7.0** against a repo at **v4.9.3**. v4.7.0 has no `--background`, no `--also-root`, and no `repos.py` at all, so part of the ticket's premise ("multi-root exists but is unergonomic") is true of the repo and false of the operator's install. Shipping this feature does nothing for them until they upgrade.

## Open Questions

- **Should `--background` be documented as deprecated, or as permanently accepted?** *Deferred to Spec.* Rationale: it is a one-line argparse decision with no code consequence either way (the flag becomes a no-op regardless), and the MCP tool's argv is version-locked to the plugin rather than the wheel, so removing it later would need its own coordinated change. Not worth blocking research on.
- **Does `--port` conflict detection need to change when background is the default?** *Resolved.* No — `_port_is_serving` (`cli.py:564`) already runs on both paths, and `_dispatch_dashboard_background` already returns `already_running` rather than racing. Flipping the default changes which branch is reached first, not the branch logic.

## Touch-points confirmed

- `cortex_command/cli.py` — `--foreground` / `--no-open` argparse, default flip, `webbrowser` call, `roots` envelope fix (`:530`)
- `cortex_command/dashboard/repos.py` — `resolve_roots` primary fallback (`:112-145`)
- `cortex_command/dashboard/templates/base.html:2699-2716` — unconditional repo identity
- `justfile:156` — `--foreground` on `dashboard-demo`
- `docs/dashboard.md`, `cortex/requirements/observability.md` — owning docs, updated in the same phase per `docs/policies.md`
- `tests/test_cli_dashboard.py`, `cortex_command/dashboard/tests/test_repos.py`
