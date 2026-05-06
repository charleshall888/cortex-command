# Research: Resolve cortex_command.backlog packaged-dispatch dead branch in bin/cortex-* wrappers

Topic anchor: weigh (a) deleting the dead `Branch (a)` probe in each wrapper vs. (b) actually packaging `backlog/*.py` under `cortex_command.backlog` to make Branch (a) live, against the project's broader packaging direction. Identify any other wrappers with the same dead probe. Verify either approach preserves SKILL.md-to-bin parity and the dual-source enforcement between top-level `bin/` and the plugin's `bin/`.

## Codebase Analysis

### Affected wrappers (full enumeration)

A repo-wide grep for `cortex_command.backlog` returns **exactly the 4 canonical wrappers + 4 byte-identical mirrors** + the ticket file + lifecycle archive docs. No other wrappers carry the probe — the ticket's list is exhaustive.

Canonical (`bin/`):
- `bin/cortex-update-item:5-8`
- `bin/cortex-create-backlog-item:5-8`
- `bin/cortex-build-epic-map:5-8`
- `bin/cortex-generate-backlog-index:5-8`

Mirrors (`plugins/cortex-interactive/bin/`):
- Same four filenames; byte-identical to canonical (verified via `diff`).

Probe shape is structurally identical in all four (lines 5-8 of each):
```bash
# Branch (a): packaged form — cortex_command.backlog.<module>
if python3 -c "import cortex_command.backlog.<module>" 2>/dev/null; then
    exec python3 -m cortex_command.backlog.<module> "$@"
fi
```

`bin/cortex-resolve-backlog-item` (the 5th backlog-touching wrapper) is a **different shape** and does not carry Branch (a) — out of scope for this ticket.

### `cortex_command/` package layout

`cortex_command/` contains: `__init__.py`, `cli.py`, `common.py`, `install_guard.py`, plus submodules `overnight/`, `pipeline/`, `dashboard/`, `init/`, `tests/`. **No `backlog/` submodule** — this is the proximate cause of the dead probe.

`cortex_command/__init__.py:13-15` runs an install-in-flight guard on every import:
```python
from cortex_command.install_guard import check_in_flight_install
check_in_flight_install()
```

This guard fires `InstallInFlightError` (exit 1) when a live overnight session is in-flight (`_ACTIVE_SESSION_PATH.exists()` AND `phase != "complete"` AND live runner PID). Carve-outs: pytest, runner-child, dashboard initiator, `CORTEX_ALLOW_INSTALL_DURING_RUN=1`, cancel-bypass. **No carve-out for "user runs `cortex-update-item` from shell during a live overnight."** Adversarial finding: the guard's docstring even says "system-python invocations (e.g. `python3 backlog/update_item.py`)" should be safe — Branch (b)'s direct script form is what guard authors expected. Branch (a)'s `-m cortex_command.backlog.<x>` form invokes the guard, which would then refuse on a use case it was never designed to block.

### `backlog/*.py` modules and their imports

| Script | Imports `cortex_command.*`? | Path-shim? |
|---|---|---|
| `backlog/build_epic_map.py` | No (pure stdlib) | `sys.path.insert` to project root (lines 31-34) |
| `backlog/create_item.py` | Yes — `from cortex_command.common import slugify, atomic_write` (lines 26, 35) | Yes |
| `backlog/update_item.py` | Yes — `from cortex_command.common import TERMINAL_STATUSES, atomic_write` (line 36) | Yes — `_PROJECT_ROOT = Path(__file__).resolve().parent.parent` (lines 32-36) |
| `backlog/generate_index.py` | Yes — `from cortex_command.common import TERMINAL_STATUSES, atomic_write, detect_lifecycle_phase, normalize_status, slugify` (line 24) | Yes |

Three of four already depend on `cortex_command.common`. They are *de facto* package members already, just shelved in the wrong directory. The `_PROJECT_ROOT = Path(__file__).resolve().parent.parent` shim in `update_item.py` would become wrong post-move (parent.parent would resolve to `cortex_command/`, not the repo root) and would need rework.

### Production callers using ambient `from backlog.X import Y`

Five sites that would need updating under Option B:
- `cortex_command/overnight/outcome_router.py:322-323`: `from backlog.update_item import update_item as _backlog_update_item`, `from backlog.update_item import _find_item as _backlog_find_item`
- `cortex_command/overnight/tests/conftest.py:8,18-28`: stub installs `sys.modules["backlog.update_item"]` — a tell that the test suite is already coupled to the sibling-layout assumption
- `tests/test_backlog_worktree_routing.py:19`: `from backlog.update_item import update_item`
- `tests/test_build_epic_map.py:33`: `from backlog.build_epic_map import normalize_parent`

The `conftest.py` stub means moving to packaged form requires re-evaluating every test fixture relying on the stub, not just rewriting the 5 import lines.

### `pyproject.toml`

```toml
[tool.hatch.build.targets.wheel]
packages = ["cortex_command"]

[project.scripts]
cortex = "cortex_command.cli:main"
cortex-batch-runner = "cortex_command.overnight.batch_runner:main"
```

Hatch's `packages = ["cortex_command"]` already includes any new `cortex_command/<sub>/` subpackage — **no pyproject edit required for Option B's package-creation per se**. To go further (route wrappers as `console_scripts` entry points), four new `[project.scripts]` entries would be needed (e.g., `cortex-update-item = "cortex_command.backlog.update_item:main"`).

### `bin/cortex-check-parity` (parity gate behavior)

Verified: linter checks **script-name references only** (E001/E002/W003/W005). It does **not inspect wrapper internals**. Removing or adding Branch (a) does not violate parity. Adding a `cortex_command.backlog.*` package also does not violate parity (the package isn't a `bin/` script).

Allowlist (`bin/.parity-exceptions.md`) categories: `maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`. Forbidden rationale literals: `internal`, `misc`, `tbd`, `n/a`, `pending`, `temporary`. ≥30-char rationale required.

### Dual-source enforcement (`.githooks/pre-commit`)

`.githooks/pre-commit` Phase 4 (lines 148-176): for each plugin in `BUILD_OUTPUT_PLUGINS`, runs `just build-plugin` (rsync `bin/cortex-*` → `plugins/$p/bin/`) then `git diff --quiet -- "plugins/$p/"`. Any divergence blocks commit.

Phase 1.5: runs `just check-parity --staged` whenever a staged path matches `skills/`, `bin/cortex-`, etc.
Phase 1.6: runs `bin/cortex-invocation-report --check-shims` to verify every `bin/cortex-*` retains the `cortex-log-invocation` shim line on line 2.

**Implication:** edits land in canonical `bin/`; mirror is regenerated via `just build-plugin`; the shim line on line 2 must be preserved.

### Top-level `bin/` vs. plugin `bin/` (canonical direction)

CLAUDE.md line 18 (verbatim):
> "`bin/` - Global CLI utilities; canonical source mirrored into the `cortex-interactive` plugin's `bin/` via dual-source enforcement"

No drift today: `diff bin/cortex-{update-item,create-backlog-item,build-epic-map,generate-backlog-index} plugins/cortex-interactive/bin/cortex-...` produces empty output for all four (verified). Direction is top-level → plugin tree; never the reverse.

### Branch (a) was deliberate, not an oversight

`lifecycle/archive/publish-cortex-interactive-plugin-non-runner-skills-hooks-bin-utilities/spec.md:90`:
> "**Full Python repackaging of `backlog/*.py` into `cortex_command.backlog.*`** — deferred. Shim resolution order (see R8) is forward-compatible if a future ticket does this."

`lifecycle/archive/extract-dev-epic-map-parse-into-bin-build-epic-map/review.md:6-12` (most recent extraction review): documents that Branch (a) silently falls through "across the entire `bin/cortex-*` family" and "is not a regression."

**Key implication:** Branch (a) is intentional forward-compat scaffolding, deliberately accepted with the dead branch left in place. Recommending deletion overrides a prior accepted decision.

### Conventions

- Edit canonical `bin/cortex-*`; never edit plugin mirrors directly.
- Run `just build-plugin` after edits; stage both canonical and regenerated mirror.
- Commit via `/cortex-interactive:commit`.
- Preserve `cortex-log-invocation` shim on line 2.
- Preserve `set -euo pipefail` on line 3.
- Preserve Branch (b)'s validity predicate verbatim: `grep -q '^name = "cortex-command"' "$CORTEX_COMMAND_ROOT/pyproject.toml"`.
- Preserve Branch (c) error message: `cortex-command CLI not found — run 'cortex setup' or point CORTEX_COMMAND_ROOT at a cortex-command checkout`.

## Web Research

### The probe pattern is structurally dead given current layout

Sibling-layout `cortex_command.backlog` is **not importable** unless one of:
- `backlog/` is moved to `cortex_command/backlog/` (nested layout, what Option B does), OR
- `pyproject.toml` declares both as packages and they share a namespace, OR
- A namespace package is configured per [PEP 420](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/).

Today's `pyproject.toml` does none of these — the probe has never been live.

### `python -m module` vs. script-by-path

[PEP 338](https://peps.python.org/pep-0338/): `-m foo.bar` sets `__package__="foo"`, `__name__="foo.bar"`, and `sys.path` starts with cwd; direct script invocation prepends the script's directory and leaves `__package__` empty. `-m` is correct for code that uses package-relative imports; script-by-path is right for genuine standalone helpers.

### Editable installs

[PEP 660](https://peps.python.org/pep-0660/) and the [setuptools development mode docs](https://setuptools.pypa.io/en/latest/userguide/development_mode.html): editable installs exist precisely to solve dev-vs-prod import parity. `uv tool install -e .` is the project's chosen install vector — but the package must be **declared** in pyproject for the import to resolve. Sibling top-level dirs do not become a single dotted package by accident.

### Idiomatic alternative: `console_scripts` entry points

[Python Packaging User Guide: entry-points spec](https://packaging.python.org/specifications/entry-points/) and [Chris Warrick: Python Apps the Right Way](https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/): `console_scripts` generates the wrapper for you, dispatches directly without a probe, and editable installs guarantee importability. **However**, this presumes conventional packaging/distribution — which `requirements/project.md:54` explicitly rules out for this project (PyPI publishing is out of scope; editable install only).

### The "import probe" pattern

Probing `python -c "import X" 2>/dev/null && exec python -m X` is **not idiomatic**. Costs:
- ~80-150ms cold interpreter startup just to test importability ([Python startup overhead notes](http://essays.ajs.com/2011/02/python-subprocess-vs-ospopen-overhead.html)).
- Encodes symptom (import might fail), not cause (package isn't configured).
- Two interpreter starts per CLI invocation in success case.

### Dead-branch literature consensus

[YAGNI (Fowler)](https://martinfowler.com/bliki/Yagni.html), [Built In on dead code](https://builtin.com/software-engineering-perspectives/delete-old-dead-code-braintree): delete dead branches unless future use is concrete and imminent. Git history is the proper "forward-compat archive." However, this is a general principle — it does not automatically override a project-specific accepted decision to keep forward-compat scaffolding (see Adversarial Review §3).

## Requirements & Constraints

### `requirements/project.md`

**Simplicity principle (line 19):**
> "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

**SKILL.md-to-bin parity enforcement (line 27):**
> "`bin/cortex-*` scripts must be wired through an in-scope SKILL.md / requirements / docs / hooks / justfile / tests reference (see `bin/cortex-check-parity` for the static gate). Drift between deployed scripts and references is a pre-commit-blocking failure mode. Allowlist exceptions live at `bin/.parity-exceptions.md` with closed-enum categories and ≥30-char rationales."

**Distribution model (line 54):**
> "the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope."

### `requirements/observability.md`

`bin/cortex-*` adoption telemetry is anchored on the `cortex-log-invocation` shim line (line 2 of every wrapper). Pre-commit Phase 1.6 (`bin/cortex-invocation-report --check-shims`) enforces shim retention. **Whichever option is chosen, the shim line on line 2 must be preserved.**

### `requirements/pipeline.md`

References `cortex_command/...` packaged Python modules as the canonical pattern (`cortex_command/pipeline/review_dispatch.py`, `cortex_command/overnight/sync-allowlist.conf`, `cortex_command/overnight/smoke_test.py`). **No reference to `cortex_command.backlog`** in any requirements doc.

### `bin/.parity-exceptions.md`

Closed-enum categories: `maintainer-only-tool`, `library-internal`, `deprecated-pending-removal`. Currently exactly one entry: `cortex-archive-sample-select` (lifecycle 102, 2026-04-27).

### CLAUDE.md (repo root)

- Line 18: top-level `bin/` is canonical, mirrored to plugin tree via dual-source enforcement.
- Lines 47-49: `cortex-jcc` runs recipes in this repo's directory context; `cortex-update-item`, `cortex-generate-backlog-index`, etc. ship via the cortex-interactive plugin's `bin/`.
- Distribution: `uv tool install -e .` plus plugins via `/plugin install`. No symlinks deployed into `~/.claude/`.

## Tradeoffs & Alternatives

### Option A — Delete Branch (a) entirely

**Description:** Remove the 4-line packaged-form probe from each canonical wrapper. Run `just build-plugin` to regenerate mirrors. Each wrapper becomes a 2-branch dispatch: try `CORTEX_COMMAND_ROOT`, else error.

**Implementation complexity:** Smallest. ~16 LOC removed across 4 canonical files; mirror regenerated automatically.

**Maintainability:** Improves clarity — no dead code lying about a feature that doesn't work. **But contradicts the archived `publish-cortex-interactive-plugin` spec which deferred packaging and deliberately kept Branch (a) as forward-compat scaffolding.** The user (same person) wrote that spec.

**Performance:** Best — removes the ~80-150ms `python3 -c "..."` probe per invocation.

**Alignment:** Tactically aligned with `requirements/project.md:19` simplicity principle. Strategically conflicts with the project's accepted prior decision to keep forward-compat scaffolding. If a future ticket re-introduces packaged dispatch (e.g., as part of ticket 115's CLI port), Branch (a) would have to be re-added across all 8 files.

**Pros:** Trivial, fastest at runtime, removes dead code per YAGNI consensus.
**Cons:** Overrides a prior accepted research rejection without new technical information; bakes in the inconsistency where `cortex_command.{overnight,pipeline,dashboard,init}` are packaged but `backlog/` isn't; future packaging work must re-add the dispatch.

### Option B — Make Branch (a) live by packaging

**Description:** Move `backlog/{update_item,create_item,generate_index,build_epic_map}.py` into `cortex_command/backlog/` (with `__init__.py`). Update 5 production import sites + test conftest. Rework `_PROJECT_ROOT` shim in `update_item.py`. After `uv tool install -e .`, Branch (a) succeeds; Branch (b)'s `$CORTEX_COMMAND_ROOT/backlog/<module>.py` path no longer exists post-move and must be deleted or rewritten.

**Implementation complexity:** Largest. ~200 LOC churn across ~12 files:
- 4 file moves: `backlog/*.py` → `cortex_command/backlog/*.py`
- 1 new `cortex_command/backlog/__init__.py`
- 5 import-site rewrites: `outcome_router.py`, `conftest.py` (with stub re-evaluation), 2 test files, plus `_PROJECT_ROOT` shim rework
- 8 wrapper updates (canonical + mirrors): Branch (b) path or delete it
- Possible `pyproject.toml` `[project.scripts]` entries to short-circuit wrappers entirely
- `install_guard` interaction must be addressed (see below)

**install_guard regression:** `cortex_command/__init__.py:13-15` runs `check_in_flight_install()` on every import. During an active overnight, `python3 -m cortex_command.backlog.update_item` would raise `InstallInFlightError` (exit 1). **This breaks `cortex-update-item my-slug status=blocked` while overnight is running** — a workflow the user might routinely use. Today this works silently via Branch (b)'s `python3 backlog/update_item.py`. Resolution requires one of: (i) sixth carve-out (`CORTEX_BACKLOG_EDIT=1`?), (ii) move guard call out of `__init__.py` into actual install entry-point only, (iii) accept that backlog edits are blocked during overnight (user decision).

**Maintainability:** Best long-term — backlog scripts now follow the same pattern as overnight/pipeline/dashboard/init siblings. Single import namespace, single dispatch path.

**Performance:** Probe still costs ~80-150ms per invocation, but it succeeds — total cost similar to today's Branch (b).

**Alignment:** Best with stated project direction. `cortex_command.*` is the canonical importable namespace. Three of four `backlog/*.py` already `from cortex_command.common import ...` — they're already package-coupled.

**Pros:** Eliminates the inconsistency. Removes env-var dependency. Forward-compat for ticket 115 (port overnight runner into cortex CLI) and ticket 146 (decouple MCP from CLI imports). Honors the archived spec's accepted deferral by closing it out.
**Cons:** Largest blast radius. install_guard interaction requires explicit policy decision. `_PROJECT_ROOT` shim semantics must be carefully reworked. Test conftest stub coupling must be unwound.

### Option C — Self-discovering dispatch via `git rev-parse` (rejected)

Replaces the probe with `git rev-parse --show-toplevel` from cwd. Reaches the user's working repo, not the install location — semantic category error. `CORTEX_COMMAND_ROOT` is meant to point at *cortex-command's* checkout, not the user's project. Rejected.

### Option D — Hybrid: delete Branch (a) + auto-derive `CORTEX_COMMAND_ROOT` via walk-up from `$0` (rejected by adversarial review)

**Description (proposed by Tradeoffs agent):** Drop the dead probe. Add a small fallback before Branch (b): if `CORTEX_COMMAND_ROOT` is unset, walk up from `$0` until `pyproject.toml` with `name = "cortex-command"` is found.

**Why rejected (per Adversarial Review):**
- **Plugin-cache topology breaks the walk-up.** When invoked from `~/.claude/plugins/cache/cortex-command/cortex-interactive/<sha>/bin/cortex-update-item`, no `pyproject.toml` exists in any parent. Walk-up either fails or, worse, finds an unrelated cortex-command checkout in a parent directory and dispatches into it.
- **Doesn't actually mirror `cortex_command/cli.py:_resolve_cortex_root()`.** That function resolves through the imported package's `__file__` (editable-install-anchored), not via walk-up from `$0`. Replicating it in bash would require the same `python3 -c "..."` interpreter spin-up Option D was meant to avoid.
- **Trust-boundary downgrade.** Implicit walk-up discovery replaces opt-in `CORTEX_COMMAND_ROOT`. A user invoking from inside a hostile repo with `name = "cortex-command"` and a malicious `backlog/update_item.py` would silently dispatch into that file.
- **Throwaway logic if Option B lands.** Adds walk-up to 8 files that becomes wrong post-packaging.

**Status:** REJECTED.

### Recommended approach

**Open question** — Options A and B are both defensible; the choice depends on how much weight the user gives to:
1. The archived spec's accepted deferral (favors A — keep current shape; or B — close it out properly).
2. Whether ticket 115 ("port overnight runner into cortex CLI") or ticket 146 (MCP decoupling) is imminent (favors B — prep work).
3. The install_guard interaction (favors A — sidesteps the policy decision).
4. The "affects a lot of files; lifecycle makes sense" framing the user cited (favors B — Option B's blast radius matches that framing; Option A is too small for a lifecycle).

This question is deferred to the Spec phase user-approval gate (see Open Questions §1).

## Adversarial Review

### Failure modes / load-bearing miss in Tradeoffs agent's recommendation

**Option D's walk-up is broken in the plugin-cache install topology.** The deployed plugin install at `~/.claude/plugins/cache/cortex-command/cortex-interactive/<sha>/bin/cortex-update-item` has no `pyproject.toml` in any parent directory — that path contains only `bin/`, `hooks/`, `skills/`. Walk-up either fails or silently dispatches into an unrelated cortex-command repo if one exists higher in the path. **Option D fundamentally does not work in the deployed topology.**

**Option D doesn't actually replicate `_resolve_cortex_root()`.** That function does: (a) `CORTEX_COMMAND_ROOT`, (b) `cortex_command.__file__` from the imported package (editable-install-anchored), (c) `$HOME/.cortex` fallback. The work happens in (b), which only resolves when an editable install made `cortex_command` importable. Bash walk-up has no such anchor. The bash equivalent would still cost a `python3 -c "import cortex_command, pathlib; print(pathlib.Path(cortex_command.__file__).resolve().parent.parent)"` interpreter spin-up — the same ~80-150ms cost Option D was meant to avoid.

### Branch (a) is forward-compat scaffolding the user previously accepted

Per project memory: "Don't re-litigate rejected alternatives — Research rejections are load-bearing; a new observation re-runs the critic, not the proposal." The archived `publish-cortex-interactive-plugin` spec deferred Option B and kept Branch (a) deliberately. Recommending deletion (Option A) without **new technical information** would re-litigate that prior decision.

The adversarial review surfaces three potential "new observations" that *might* justify revisiting:
- **install_guard regression in Option B** (the guard wasn't designed to fire on backlog YAML edits during overnight).
- **Per-invocation latency** (~80-150ms probe cost).
- **No test exercises Branch (a) end-to-end** (silent drift risk regardless of choice).

Whether these qualify as "new observations" sufficient to re-run the critic vs. the proposal is a user-judgment call, not an orchestrator call.

### install_guard concern is partially mischaracterized but conclusion holds

The guard's `_check_in_flight_install_core` returns silently when no active session exists. So `python3 -m cortex_command.backlog.update_item` while no overnight runs is fine. **During an active session**, it raises `InstallInFlightError` (exit 1) with a confusing "overnight session in-flight; refusing to clobber" message — even though `update_item` is touching backlog YAML, not the package on disk.

The guard's docstring explicitly says "system-python invocations (e.g. `python3 backlog/update_item.py`)" should be safe. Branch (b)'s direct script form is what guard authors expected; Branch (a)'s `-m cortex_command.backlog.<x>` form invokes the guard. Option B introduces this regression unless explicitly addressed.

### Walk-up logic is a trust-boundary downgrade (Option C and Option D)

A user invokes the wrapper from inside a hostile git tree with a `pyproject.toml` named `cortex-command` and a malicious `backlog/update_item.py`. Implicit walk-up dispatches INTO that file. Current Branch (b) requires explicit `CORTEX_COMMAND_ROOT` (opt-in). Walk-up discovery replaces opt-in with implicit-discovery — a meaningful security regression.

### "Idiomatic" framing assumes packaging direction the project rejects

Web research's appeal to `console_scripts` entry points presumes conventional packaging/distribution. Per `requirements/project.md:54`, PyPI publishing is out of scope; the project ships editable-only. The "idiomatic" alternative is therefore not a constraint — and the cost of conformance is exactly Option B's cost.

### Mutual exclusivity assumption between Option A and Option B

Option A is *not* mutually exclusive with Option B; if Option B is on the medium-term roadmap, doing Option A now is **redundant work** that gets undone by Option B. The minimal-fix memory rule says don't add throwaway logic; instead, either commit to Option B as the lifecycle's actual scope, or do nothing and wait for Option B to be triggered by ticket 115/146.

### "Affects a lot of files; lifecycle makes sense" framing

The user said this. Option A touches ~16 LOC across 4 canonical files (~8 with mirrors). That's not "a lot of files" by lifecycle standards. Option B touches ~12 files including 5 production import sites, the install_guard policy decision, and dual-source-enforced wrapper updates. **Option B's blast radius matches the user's framing; Option A does not.**

### Latent silent-failure mode regardless of choice

There is no test that exercises Branch (a) end-to-end. If a future commit accidentally creates `cortex_command/backlog/__init__.py` (e.g., as a stub), Branch (a) would activate silently with no CI signal. Whichever option is chosen, a regression test on dispatch order is recommended.

## Open Questions

### 1. Option A vs. Option B (RESOLVED — Option B selected)

The Tradeoffs agent recommended Option D, which the Adversarial agent rejected on technical grounds (broken in plugin-cache topology, doesn't mirror `_resolve_cortex_root()`, throwaway if Option B lands, security regression). This collapsed the choice to Option A vs. Option B.

**Resolution:** User selected **Option B — package `cortex_command.backlog` properly** (2026-04-29). Package the `backlog/*.py` modules under `cortex_command.backlog`, address the `install_guard` interaction, rewrite 5 production import sites + test conftest stub, rework the `_PROJECT_ROOT` shim, and update or delete Branch (b). This closes out the archived `publish-cortex-interactive-plugin/spec.md:90` deferral and provides forward-compat for tickets 115 (CLI port) and 146 (MCP decoupling). The choice honors the user's earlier "affects a lot of files; lifecycle makes sense" framing.

### 2. install_guard policy (deferred to Spec; only relevant if Option B is chosen)

If Option B is selected: should `cortex-update-item` and siblings be allowed to invoke `python3 -m cortex_command.backlog.<mod>` during an active overnight session? Options:
- (i) Add a sixth carve-out (`CORTEX_BACKLOG_EDIT=1` set by the wrapper) — explicit policy that backlog YAML edits are safe during overnight.
- (ii) Move `check_in_flight_install()` out of `cortex_command/__init__.py` and into actual install entry-points only.
- (iii) Accept that backlog edits are blocked during overnight, surface the error helpfully.

Deferred: this is a Spec-phase question, addressed in the structured interview if Option B is chosen.

### 3. Regression test for dispatch order (deferred to Spec)

There is currently no test that exercises Branch (a) end-to-end. Whichever option is chosen, the spec should include a regression test asserting the dispatch order matches the wrapper's stated branches.

Deferred: addressed in Spec acceptance criteria.
