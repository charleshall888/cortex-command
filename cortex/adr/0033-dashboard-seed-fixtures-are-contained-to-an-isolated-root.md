---
status: proposed
---

# 0033 — Dashboard seed fixtures are contained to an isolated root

_Decision date: 2026-07-27 (#414 — enrich the dashboard seed fixtures with board- and reader-shaped variety)._

## Context

`cortex-dashboard-seed` was built to populate the operator's **real** repository, so that fixtures would appear in their real dashboard alongside real work (`seed.py:4`). It is not a developer-only script: it ships as a console entry point (`pyproject.toml:75`) via the `[dashboard]` and `[all]` extras, so its default target is reached by every consumer install.

That purpose is the direct cause of every defect the ticket's research found:

- It clobbers canonical live paths under `cortex/lifecycle/`, including files that are git-tracked — `--clean` unlinks `pipeline-state.json`, `pipeline-events.log`, and `metrics.json` unconditionally, so cleaning a never-seeded repo deletes tracked files.
- It destroys the single-active-session symlink `overnight/plan.py:588-592` maintains at `cortex/lifecycle/overnight-state.json`, replacing it with a regular file that `clean_all` never restores.
- It writes a fake session with `"phase": "executing"` and no `runner.pid` (`seed.py:166`), which `recovery.py:77-79` treats as needing recovery and `guardian.py:49-62` enumerates on a launchd timer — an unattended process acting on demo data.
- Its output has already leaked into this repo's git history: `0040d55c` untracked five seeded backlog items by hand, and `cortex/lifecycle/pipeline-state.json` is tracked and 100% seed output.
- It forced a numeric ID reservation. `create_item._get_next_id` excludes 990–999 from `max(ids)` but not from assignment, so once a real backlog reaches 989 the allocator returns `990` forever — a permanent ceiling, reproduced empirically and dated to roughly early-2027 for this repo.

#231 already identified the structural fix ("Fix B") and deferred it with the explicit trigger *"if dashboard-seed grows beyond test scaffolding"*. Enriching the corpus from five one-line fixtures to a board- and reader-shaped set is that trigger firing.

## Decision

**The seeder writes to a per-user fixture root by default and never to the project repository.**

- The default target is `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/dashboard-seed/`, resolved fresh on each call, mirroring the precedent in `cortex_command/init/install_state.py:24-31`. A `--root PATH` flag overrides it. No writer resolves the project root on its own: `write_overnight_state` and `write_overnight_events` take an explicit root rather than calling `_resolve_user_project_root()` internally, and `--clean` is scoped to the same resolved root.
- **Viewing is dashboard-scoped, not environment-scoped.** `cortex dashboard` gains its own `--root PATH` flag which sets `CORTEX_REPO_ROOT` **in-process** before `uvicorn.run(...)`, exactly as `cli.py:493-496` already sets `DASHBOARD_PORT` in-process. The operator is never instructed to export or inline-prefix that variable. A `just dashboard-demo` recipe seeds and serves in one invocation.
- **The 990–999 ID reservation is deleted, not replaced.** Containment removes the collision it guarded against, so no seed-identity mechanism — manifest, filename token, tag lookup, or high-offset band — ships in its place. To stop deletion from silently jumping a contaminated repo's sequence, the allocator ignores files matching the pre-containment seed-fixture naming, and a documented `--sweep-legacy` path removes them.

Accepted because the alternative is a shipped console script that writes unreviewed state into every consumer's repository.

## Trade-offs

All three losses are real and were accepted knowingly.

**1. Fixtures no longer appear beside real work.** The seeder's original selling point is gone: the operator's own dashboard shows only their own corpus, and viewing the fixtures costs a distinct command against a distinct root. `just dashboard-demo` collapses that back to one invocation, but it does not restore the commingled view — and completing containment before the enrichment lands leaves a window where the operator has lost even the five bare fixtures.

**2. The zero-code alternative was rejected.** Telling the operator to set `CORTEX_REPO_ROOT` to the fixture root requires no code change at all, and was still declined. That variable is the unvalidated root funnel for 43 non-test modules (`common.py:87-89` returns it with no existence or marker check), and a seeded fixture root satisfies both it and `overnight/cli_handler.py`'s independent `_is_valid_repo_root`, because it contains a bare `cortex/` directory. Any persistence beyond a single command therefore silently redirects backlog creation, lifecycle verbs, and overnight writes into a throwaway tree. A dashboard-local flag costs a small code change and confines the redirect to one process; the env-var route costs nothing and risks everything downstream of it.

**3. Containment is forward-looking only.** It fixes nothing already on disk. Repos that ran the pre-containment seeder still carry stray `99[0-9]-seed-*.md` files, and deleting the reservation stops hiding them from `max(ids)` — left unhandled, the next real ticket in such a repo allocates `995` and the sequence never returns. Those operators need the one-time `--sweep-legacy` migration, which is a manual step this decision cannot remove.

## Alternatives considered

**Ship a seed-identity mechanism instead of containment.** Six candidates were weighed — manifest file, filename token, tag-based allocator lookup, high-offset band, UUID namespace, and a refusal guard. Each answers "how do we tell fixtures apart from real items once they are commingled?", a question containment deletes rather than answers. Rejected on deletion bias: keeping any of them requires justifying a mechanism whose premise is gone.

**Add a refusal guard on the project root** (the Rails `ProtectedEnvironmentError` pattern). Rejected: the isolated-root default already prevents the failure, so the guard would enter without independent named evidence (`project.md:41`).

**Harden `_resolve_user_project_root` with validation.** Rejected as a separate concern. The dashboard-local `--root` flag removes *this* ticket's reliance on `CORTEX_REPO_ROOT`; hardening the shared funnel against 43 other callers' misuse has its own blast radius and belongs to its own ticket.
