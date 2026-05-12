---
feature: add-upward-walking-project-root-detection-in-resolve-user-project-root
created: 2026-05-11
---

# Research: Add upward-walking project-root detection in _resolve_user_project_root()

Clarified intent: Replace the cwd-only project-root check at `cortex_command/common.py:79-80` with an upward-walking helper. Stop conditions: first `.git/` OR filesystem root. Markers (today's flat layout): `lifecycle/` OR `backlog/`. On failure, raise `CortexProjectRootError` whose message lists the searched paths (one stderr line on failure, leveraging the existing error-emission pattern in `cli.py`).

Parent context: epic #200 (`consolidate-artifacts-under-cortex-root`), decision record DR-10 in `research/consolidate-artifacts-under-cortex-root/research.md`. Strictly today's flat layout — the `cortex/` marker is the relocation epic's responsibility (#202), not this ticket.

## Codebase Analysis

### Load-bearing surface (must change)

| File | Lines | Pattern | Notes |
|---|---|---|---|
| `cortex_command/common.py` | 55–86 | resolver definition | Single source of truth. Change the cwd-only check inside `_resolve_user_project_root()` to an upward walk. ~10–15 LOC. |
| `cortex_command/overnight/daytime_pipeline.py` | 52–64 (`_check_cwd`) | `if not Path("lifecycle").is_dir(): sys.exit(1)` | Independent guard; does NOT route through the resolver. Swap to call the resolver and catch `CortexProjectRootError`. |
| `cortex_command/backlog/generate_index.py` | 24–25 | module-level `BACKLOG_DIR = Path.cwd() / "backlog"`, `LIFECYCLE_DIR = Path.cwd() / "lifecycle"` | Module-level binding evaluated at import time. Defer to call time via a function that calls the resolver, or accept that this CLI runs from project root and route through the resolver. |
| `cortex_command/backlog/update_item.py` | 442–444 (in `main()`) | `BACKLOG_DIR = Path.cwd() / "backlog"` | Function-local; swap to `_resolve_user_project_root() / "backlog"`. |
| `cortex_command/backlog/create_item.py` | 160–162 (in `main()`) | `BACKLOG_DIR = Path.cwd() / "backlog"` | Same as update_item. |

### DR-10 inclusion that does NOT need to change

| File | Reason |
|---|---|
| `cortex_command/discovery.py` (`_default_repo_root` at line 62–74) | Already resolves repo root via `git rev-parse --show-toplevel`. The helper walks via git, not via cwd-marker matching, so it has no cwd-only papercut. Recommendation: leave untouched; remove from scope. |

### Indirect beneficiaries (transparent: no edit needed)

~12 sites already route through `_resolve_user_project_root()` and will gain from-subdirectory capability the moment the resolver gains the upward walk:

- `cortex_command/cli.py:117,199` (print-root, deprecation stub)
- `cortex_command/dashboard/seed.py:180,281,650,752`
- `cortex_command/dashboard/app.py:51`
- `cortex_command/overnight/plan.py:32`
- `cortex_command/overnight/events.py:161,181`
- `cortex_command/overnight/outcome_router.py:358,415`
- `cortex_command/overnight/orchestrator.py:98,101`

This is the centralization win: editing one function expands "valid CWD" semantics across the entire CLI.

### Existing failure-emission pattern

`cli.py:200-202` catches `CortexProjectRootError` and prints `cortex --print-root: {exc}` to stderr. Enriching the exception message with the searched paths satisfies Q2's "one stderr line on failure" without adding a new logging surface.

## Design

### Helper signature

```python
def _resolve_user_project_root() -> Path:
    env_root = os.environ.get("CORTEX_REPO_ROOT")
    if env_root:
        return Path(env_root)

    cwd = Path.cwd().resolve()
    searched: list[Path] = []
    current = cwd
    while True:
        searched.append(current)
        if (current / "lifecycle").is_dir() or (current / "backlog").is_dir():
            return current
        if (current / ".git").exists():  # exists, not is_dir — worktrees use .git as a file
            break
        parent = current.parent
        if parent == current:  # filesystem root
            break
        current = parent

    raise CortexProjectRootError(
        "Run from your cortex project root, set CORTEX_REPO_ROOT, or "
        "create a new project here with `git init && cortex init` "
        "(cortex init requires a git repository). "
        f"Searched: {', '.join(str(p) for p in searched)}"
    )
```

Notes:
- `(current / ".git").exists()` instead of `.is_dir()` so git worktrees (where `.git` is a file pointing to the main checkout) still bound the walk.
- Walk stops at the FIRST `.git/` encountered, even if no cortex marker is found inside. This prevents leaking into ancestor cortex projects that live above the user's current git repo.
- `searched` is included in the error message — covers Q2's failure diagnostic in the conventional stderr-on-raise pattern.

### Marker set (Clarify Q3 = today's markers only)

`lifecycle/` OR `backlog/`. The `cortex/` marker is intentionally absent — #202 will add it in the same atomic relocation commit that creates the `cortex/` directory.

### Stop condition (Clarify Q1 = `.git/` OR filesystem root)

Two terminators:
1. **`.git/` boundary** — preferred terminator. Cortex requires a git repo (`cortex init` enforces); a `.git/` ancestor without a cortex marker means we're inside a git repo that isn't a cortex project, and walking further could leak into an unrelated ancestor cortex project.
2. **Filesystem root** — fallback when no `.git/` exists anywhere up the tree (e.g., a tmp_path test fixture without git init). Detected by `parent == current`.

### Failure-mode emission (Clarify Q2 = stderr-on-failure)

The enriched `CortexProjectRootError` message carries the searched-paths list. Existing call sites that catch it (e.g., `cli.py:200-202`) print to stderr; no new logging surface introduced.

## Tradeoffs & alternatives

### A. Walk for `.cortex-init` (existing marker file) instead of directories — rejected
`.cortex-init` is generated JSON state, not a layout marker. Coupling resolver semantics to init-handling state would invert dependencies (resolver should not depend on init). Also: today's flat layout has `lifecycle/` and `backlog/` at root before `.cortex-init` is written, so the marker set ordering matters less than the rejection rationale.

### B. Use `git rev-parse --show-toplevel` as primary, fall back to walk — rejected
Adds a subprocess dependency to a hot-path function that is pure-Python today. Subprocess failures (git not in PATH, transient fork failure) would silently degrade to cwd-only behavior — exactly the bug this ticket fixes. `discovery.py` uses this approach but it's a CLI tool with a stronger "must be in git" contract; the resolver is invoked from library code where pure-Python is preferable.

### C. Walk past `.git/` if no cortex marker found — rejected
Increases the silent wrong-root risk (a user has a nested cortex project inside an unrelated git repo, and the resolver picks the wrong one). The `.git/` boundary is the conservative choice and matches git's own behavior (sub-repos terminate parent walks).

## Test plan

Add `tests/test_resolve_user_project_root_walk.py` with `tmp_path` fixtures (no real-filesystem walks):

1. **Resolves from project root**: `tmp_path / "lifecycle"` exists; `monkeypatch.chdir(tmp_path)` → returns `tmp_path`.
2. **Resolves from `lifecycle/<feature>/` subdir**: cwd one or two levels deep under `tmp_path / "lifecycle/feature/"` → returns `tmp_path`.
3. **Resolves with `backlog/` marker only**: only `backlog/` exists → resolves correctly.
4. **`.git/` boundary terminates the walk**: cwd inside a tmp tree that contains a `.git/` ancestor but no `lifecycle/`/`backlog/` → raises with diagnostic.
5. **`.git` as file (worktree-style)** also terminates: same as (4) but `.git` is a file.
6. **Filesystem-root fallback**: cwd in a tmp tree that has no `.git/` anywhere → walks to a fixture-bounded root and raises (use a `monkeypatch.setattr` on `Path.parent` if needed to keep the test bounded, or accept that `parent == current` at the tmp_path's filesystem-relative root).
7. **`CORTEX_REPO_ROOT` env override is honored verbatim** (no walk performed).
8. **Diagnostic message lists searched paths**: assert the raised exception's message includes each visited parent.

Existing tests using `monkeypatch.chdir(repo_root)` + `lifecycle/` fixture continue to pass — the new walk degenerates to the old single-level check when cwd already has the marker.

## Considerations & risks

- **Worktree behavior**: git worktrees have `.git` as a file (not directory) pointing at the main checkout. `exists()` covers both shapes; the walk lands on the worktree's own root if it contains `lifecycle/` or `backlog/`, which is the correct semantics.
- **Performance**: bounded loop, depth typically < 10. No measurable cost.
- **Backwards compatibility**: the `CORTEX_REPO_ROOT` env-var override path is unchanged; tests that set it stay green. Tests that `monkeypatch.chdir(repo_with_lifecycle)` also stay green because the first iteration of the walk matches.
- **Forward-compat with #202**: after the relocation lands, the marker set will become `cortex/` (per epic #200, ticket #202). Until then, this helper does not look for `cortex/`. Per Q3, that swap is owned by #202.
- **Discovery.py descoping**: removing `discovery.py` from DR-10's callsite list is a research finding, not a scope expansion. The DR appears to have listed it for completeness without noting that it already walks via git-toplevel.

## Open Questions

(none — Clarify Q1/Q2/Q3 resolved the design ambiguities. Scope handoff to Spec is clean.)
