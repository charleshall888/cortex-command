---
status: accepted
---

# Overnight CLI repo-root resolution by marker-validated precedence

## Context

The overnight CLI's single repo-root resolver (`cli_handler._resolve_repo_path`, the R20 resolution site) trusted `git rev-parse --show-toplevel` then `Path.cwd()`. Under launchd both signals fail: the LaunchAgent runs with `CWD=/` and a bare environment, so `git rev-parse` finds no repo and `cwd` is `/`. The resolver silently returned `/`, breaking every scheduled run (features executed against `project_root=/`) and the guardian scan — while the correct root sat unused in two places the runtime already had: `overnight-state.json:project_root` (written at session create, always absolute) and the `CORTEX_REPO_ROOT` env var that the generated plists can carry. The naive resolver consulted neither.

## Decision

The single resolution site resolves by **explicit, marker-validated precedence**:

1. valid `state.project_root` (supplied by `handle_start` from the always-absolute `--state` file),
2. valid `CORTEX_REPO_ROOT`,
3. `git rev-parse --show-toplevel`,
4. `Path.cwd()`.

"Valid" means a `.resolve()`-canonicalized, existing, non-`/` directory bearing a repo marker (`.git` or a `cortex/` directory), applied uniformly to both the state and env candidates via a single `_is_valid_repo_root` predicate. The predicate validates the **supplied candidate in place** — it does **not** walk upward toward a marker — so a stale or wrong candidate falls through to the next tier rather than climbing to a marker-bearing ancestor (a monorepo root, `$HOME/.git`) and silently selecting the wrong repo. `handle_start` threads `state.project_root`; host-wide verbs (the guardian scan) supply `None` and rely on the plist-set env var. The `git rev-parse`→`cwd` tail is retained unguarded as the run-now fallback. All resolution stays inside this one function (R20).

## Three-criteria gate clearance

- **Hard to reverse** — once `start` and the guardian depend on persisted/explicit sources, reverting to ambient CWD-resolution silently re-breaks every launchd-fired run; the precedence becomes load-bearing for scheduled execution and supervision.
- **Surprising without context** — a fresh contributor would not predict why `start` reads the repo root from the state file rather than `cwd`, nor why the marker guard deliberately does **not** walk upward the way `common._resolve_user_project_root` does.
- **Real trade-off** — the decision prefers persisted/explicit sources over ambient runtime context (the opposite of the original CWD-trusting design), accepting that resolution now depends on a correct, marker-validated state file or env var; in exchange, scheduled runs and supervision become robust to launchd's `CWD=/` and bare env without scattering resolution across callers and without plist regeneration.

## Rejected alternatives

- **Set `CWD` in the plist instead** — would fix the git/cwd tier for the scheduled parent but not the run-now or guardian paths, and re-binds correctness to plist regeneration; the precedence fix is one resolver change that covers all entry points.
- **Walk upward for a marker (mirror `common._resolve_user_project_root`)** — rejected: a walking validator applied to a stale `state.project_root`/`CORTEX_REPO_ROOT` could climb to a marker-bearing ancestor and select the wrong checkout. In-place single-candidate validation is the load-bearing safety property.
- **Resolve the root in the runner/callers** — violates R20 (single resolution site); callers supply inputs, the resolver owns precedence.

## Consequences

- `handle_start` now loads the state file and re-resolves the root for the `--state` path before threading `repo_path` into the runner; the run-now/auto-discover branch is unchanged.
- Correctness depends on `state.project_root` (or `CORTEX_REPO_ROOT`) being a real, marker-bearing directory; a poisoned value (`/`, marker-less, missing) is rejected and falls through rather than being trusted.

Background lives in `docs/overnight-operations.md`; this ADR is the canonical home for the decision and its rejected alternatives.
