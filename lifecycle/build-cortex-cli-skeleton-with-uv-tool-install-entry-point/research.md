# Research: Build cortex CLI skeleton with uv tool install entry point

> Add `[build-system]` to `pyproject.toml`, declare a `cortex` console entry point
> in a new Python package, and scaffold placeholder implementations for
> subcommands `overnight`, `mcp-server`, `setup`, `init`, `upgrade` that return
> "not yet implemented". Verify `uv tool install -e .` produces a working
> `cortex --help` on PATH. Document the "`cortex`'s internal `uv run` operates on
> the user's project, not on the tool's own venv" constraint. Skeleton only — no
> subcommand implementations, no `cortex upgrade` logic.

## Epic Reference

Parent epic: [[113-distribute-cortex-command-as-cli-plus-plugin-marketplace]]. Epic research lives at [`research/overnight-layer-distribution/research.md`](../../research/overnight-layer-distribution/research.md) (decision records DR-1, DR-4, DR-5) and the CLI packaging report [`research/overnight-layer-distribution/_cli-packaging-report.md`](../../research/overnight-layer-distribution/_cli-packaging-report.md); this ticket is the foundational packaging wiring that every other ticket in epic 113 (115–125) depends on.

## Codebase Analysis

### Current `pyproject.toml` is a virtual workspace

`pyproject.toml` (20 lines total) has no `[build-system]`, no `[project.scripts]`, no entry points. `uv.lock:151` declares `source = { virtual = "." }` — the project is not installable today. Grep across the repo returns zero matches for `[project.scripts]`, `console_scripts`, or `entry_points`.

```toml
[project]
name = "cortex-command"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["claude-agent-sdk", "fastapi", "uvicorn[standard]", "jinja2", "markdown"]

[tool.pytest.ini_options]
testpaths = ["tests", "claude/dashboard/tests", "claude/pipeline/tests", "claude/overnight/tests"]
pythonpath = ["."]

[dependency-groups]
dev = ["pytest>=8.0"]
```

`pythonpath = ["."]` is how `from cortex_command.overnight.*` imports resolve during tests — a pytest-only shim, not a package install.

### Python layout is flat under `claude/`, no src-layout, no top-level `__init__.py`

- `claude/common.py` (~500 lines; its own `python3 -m claude.common` CLI at `claude/common.py:453-492` using argparse)
- `claude/overnight/` — 24 `.py` + `runner.sh` + `prompts/*.md`; `__init__.py` re-exports ~35 symbols
- `claude/pipeline/` — 13 `.py` + `prompts/*.md`; `__init__.py` docstring-only
- `claude/dashboard/` — `app.py`, `data.py`, `poller.py`, `templates/` (Jinja2), `tests/`
- `claude/hooks/` — Python + shell hooks
- `backlog/*.py` — three standalone scripts (`create_item.py`, `update_item.py`, `generate_index.py`) with manual `sys.path.insert(0, _PROJECT_ROOT)` preludes

**`claude/` has no top-level `__init__.py`** — `from cortex_command.overnight import *` currently works via implicit namespace packages (PEP 420), backed by `pythonpath = ["."]` in pyproject. There are 292+ `from claude.(overnight|pipeline|common)` hits across 100+ files; this import graph is load-bearing across `runner.sh`, orchestrator prompts, worker dispatch, and every test.

Every existing Python CLI in the repo uses **argparse**. Notable sites: `claude/common.py:469-492`, `claude/overnight/batch_runner.py`, `claude/overnight/daytime_pipeline.py`, `claude/overnight/integration_recovery.py`, `claude/overnight/map_results.py`, `claude/pipeline/metrics.py`, `bin/audit-doc`, `bin/count-tokens`, `backlog/update_item.py`. No `click` or `typer` anywhere.

### Existing CLI delivery surface — `bin/` + `just deploy-bin`

`justfile:132-143` enumerates current symlinks deployed to `~/.local/bin/`:

```
bin/count-tokens, bin/audit-doc, backlog/update_item.py,
backlog/create_item.py, backlog/generate_index.py, bin/jcc,
bin/overnight-start, bin/overnight-status, bin/overnight-schedule,
bin/git-sync-rebase.sh
```

These are symlinked on `just deploy-bin` — the convention CLAUDE.md documents (`New global utilities follow the deploy-bin pattern`). `cortex` supersedes this pattern for its own binary (installed via `uv tool install`, not symlink) but does **not** retire the pattern — existing bash scripts stay.

### How Python is currently invoked

Three paths, all relevant to the `uv run` constraint this ticket must document:

1. **Runner (venv-activated)**: `claude/overnight/runner.sh:35-40` sources `$REPO_ROOT/.venv/bin/activate`, exports `PYTHONPATH="$REPO_ROOT"`, then runs `python3 -m claude.overnight.*`.
2. **justfile (`uv run`)**: `justfile:615-663` uses `uv run python3 -m claude.overnight.status`, `uv run uvicorn claude.dashboard.app:app`, `uv run pytest`, etc.
3. **PEP 723 shebang**: `bin/audit-doc:1` and `bin/count-tokens:1` use `#!/usr/bin/env -S uv run --script` with an inline `# /// script` block declaring per-file deps.

`PYTHONPATH` and `.venv/` are baked in across ~20 sites (runner.sh, `skills/overnight/SKILL.md:46`, multiple test harnesses). Ticket 115 is the owner of migrating those assumptions to `uv tool install`-ed semantics; this skeleton ticket must coexist without breaking them.

### Placement options for the `cortex` CLI package

All four are valid wire-up points; all require `[build-system]` + `[project.scripts]` + a `[tool.hatch.build.targets.wheel].packages = [...]` declaration. Trade-offs are covered in Tradeoffs & Alternatives.

| Option | Entry point string | Wheel `packages=` | Import-graph churn |
|--------|--------------------|-------------------|--------------------|
| (a) `claude/cortex/` submodule | `cortex = "claude.cortex.cli:main"` | `["claude"]` | 0 files |
| (b) `src/cortex/` + keep `claude/` flat | `cortex = "cortex.cli:main"` | `["src/cortex", "claude"]` | 0 files (both trees shipped) |
| (c) Top-level `cortex/` flat | `cortex = "cortex.cli:main"` | `["cortex", "claude"]` | 0 files |
| (d) Single `claude/cli.py` | `cortex = "claude.cli:main"` | `["claude"]` | 0 files |

### Test / verification surface

No prior art for testing a console-script entry point post-`uv tool install`. The closest pattern is `subprocess.run(["cortex", "--help"])` + assert exit code/substring. Alternative that avoids polluting `~/.local/share/uv/tools/`: `uv build` → unpack wheel → `pip install --target=tmpdir` → run binary. Three pytest roots already registered in `testpaths`; new tests would land at `tests/test_cortex_cli_skeleton.py` or mirror the per-subpackage pattern under the chosen CLI package dir.

### Downstream integration surface (do not design here — ticket 115+ does)

| Ticket | Consumer of the skeleton |
|--------|-------------------------|
| 115 | `cortex overnight {start,status,cancel,logs}` replaces `bin/overnight-{start,status,schedule}` and `claude/overnight/runner.sh` |
| 116 | `cortex mcp-server` exposes `start_run`/`status`/`logs`/`cancel` (DR-1 IPC) |
| 117 | `cortex setup` deploys `~/.claude/{hooks,rules,reference,notify.sh,statusline.sh}` + `~/.local/bin/*` |
| 118 | `curl \| sh` bootstrap + `cortex upgrade` logic |
| 119 | `cortex init` per-repo scaffolder (shadcn-style) |
| 120–122 | Plugins call `cortex` via PATH |
| 125 | Homebrew tap wraps the bootstrap |

### Conventions

Commit style: imperative, capitalized, no period, ≤72 chars subject — enforced by `hooks/cortex-validate-commit.sh`. Always via `/commit` skill (`CLAUDE.md`). Python style: no linter enforced; house style includes `from __future__ import annotations`, PEP 8. Tests: pytest with three configured roots. Hook scripts executable. Settings JSON must stay valid JSON.

## Web Research

### uv#9518 is intentional — `[build-system]` is mandatory

`uv#9518` was **closed 2024-12-02 as won't-fix**, not a regression to work around. From the uv docs (`docs.astral.sh/uv/concepts/projects/config/`):

> "If a build system is defined, uv will build and install the project into the project environment. If a build system is not defined, uv will not attempt to build or install the project itself, just its dependencies."

There is no "minimum that survives `uv sync`" without `[build-system]` — the absence IS the signal that the project is not a package. Adding `[build-system]` is therefore both necessary and sufficient for `uv tool install -e .` to produce an editable install.

Minimum viable hatchling block:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Setuptools equivalent (aider's choice):
```toml
[build-system]
requires = ["setuptools>=68", "setuptools_scm[toml]>=8"]
build-backend = "setuptools.build_meta"
```

### `[project.scripts]` entry-point syntax

```toml
[project.scripts]
cortex = "module.path:callable"
```

Callable takes no args — reads `sys.argv` itself (typical for argparse/click/typer).

Live-reload behavior: source changes auto-apply under `uv tool install -e`. **Entry-point additions / renames require `uv tool uninstall cortex-command && uv tool install -e .`** (or `--force`) — this is a user-facing footgun that `cortex --help` should mention.

### `uv tool update-shell`

After first `uv tool install`, uv prints a warning if its bin dir is not on PATH. It does **not** auto-modify shell rc files. User runs `uv tool update-shell` once; supported shells are bash, zsh, fish, PowerShell.

### `uv run` discovery semantics (the doc constraint this ticket owns)

`uv run` walks up from CWD to find `pyproject.toml`/`uv.toml`/`.venv`. When cortex is `uv tool install`-ed, its own `pyproject.toml` lives in uv's tool directory (`~/.local/share/uv/tools/cortex-command/` on macOS/Linux) — unreachable by walking up from a normal user CWD. So cortex's internal `uv run` calls naturally operate on the user's project, not the tool's venv. This is the same reason `ruff` and `black` installed via `uv tool install` format user-project files correctly.

Scoping knobs available to cortex subcommands that need to constrain `uv run` explicitly:

| Variable | Since | Purpose |
|----------|-------|---------|
| `UV_PROJECT` | 0.4.4 | Pin the project directory explicitly |
| `UV_PROJECT_ENVIRONMENT` | 0.4.4 | Pin the venv within that project |
| `UV_WORKING_DIR` | 0.9.14 | Change CWD before run |
| `UV_ISOLATED` | 0.8.14 | Avoid discovering any `pyproject.toml`/`uv.toml` |

Anti-patterns to document:

- **Do NOT** set `UV_PROJECT_ENVIRONMENT` globally in cortex's process env — it leaks to nested `uv run` subprocesses and breaks discovery.
- **Do NOT** `os.chdir` to cortex's install dir before calling `uv run`; pass `cwd=user_project_dir` to subprocess explicitly.
- **Do** set `UV_PROJECT=...` explicitly if you ever run cortex from inside its own source tree in dev mode (otherwise cortex's pyproject wins over the user's).

### Framework comparison

| Dimension | argparse | click | typer |
|-----------|----------|-------|-------|
| Stdlib | yes | no | no |
| Runtime deps | 0 | 1 (click) | ~10 pkgs, ~25 MB (click + rich + shellingham + typing_extensions + markdown-it-py + mdurl + pygments + colorama) |
| Subcommand API | `subparsers.add_parser(...)` + hand-wire dispatch | `@cli.command()` decorator | `app.command()` using type hints |
| Nested groups | verbose (nested `add_subparsers()` trees) | `@cli.group()` one decorator | `app.add_typer(sub_app)` |
| Shell completion | via `argcomplete` (bash/zsh, extra install) | `_PROG_COMPLETE=zsh_source` per-shell source dance | `cortex --install-completion` auto-installs bash/zsh/fish/powershell |
| Help output | plain, verbose boilerplate | good, grouped | rich-formatted by default |
| Docstring as help | no (you set `description=__doc__`) | yes (auto-extracts) | yes (auto-extracts) |
| Maturity | stdlib | Pallets, 12+ years | active; API has churned more than click |

**aider uses argparse** — the CLI-packaging-report and Agent 2 both confirm. aider's Jan 2025 transition was purely distribution (moving to `uv tool install`), not a CLI-framework rewrite.

### Exit-code convention for "not implemented" stubs

`print("not yet implemented", file=sys.stderr); sys.exit(2)` is the most common UNIX contract — semantically honest, detectable by wrapper scripts, matches argparse's usage-error convention. `NotImplementedError` renders a traceback (user-hostile); `exit 0` lies about success.

### aider precedent summary

- `[build-system]`: `setuptools>=68` + `setuptools_scm`
- `[project.scripts]`: `aider = "aider.main:main"`
- Framework: **argparse**
- Bootstrap package (`aider-install`): calls `uv tool install --force --python python3.12 --with pip aider-chat@latest` + `uv tool update-shell` via `uv.find_uv_bin()`

### URLs (all fetched unless noted)

- https://github.com/astral-sh/uv/issues/9518 — build-system "regression" is intentional
- https://github.com/astral-sh/uv/pull/5454 — uv tool install -e landed 2024-07-26
- https://docs.astral.sh/uv/concepts/projects/config/ — build-system behavior
- https://docs.astral.sh/uv/concepts/tools/ and https://docs.astral.sh/uv/guides/tools/
- https://docs.astral.sh/uv/reference/environment/ — UV_* variables
- https://aider.chat/2025/01/15/uv.html
- https://github.com/Aider-AI/aider/blob/main/pyproject.toml
- https://github.com/Aider-AI/aider-install
- https://typer.tiangolo.com/features/
- https://click.palletsprojects.com/en/stable/shell-completion/ (403 on fetch; info from search excerpts)

## Requirements & Constraints

### `requirements/project.md`

Out of Scope, verbatim:

> - Dotfiles and machine configuration (terminals, shells, prompts, fonts, git) — those belong in machine-config
> - Application code or libraries — those belong in their own repos
> - **Published packages or reusable modules for others**
> - Setup automation for new machines (owned by machine-config)

Framing: "Primarily personal tooling, shared publicly for others to clone or fork." Epic research DR-8 proposes updating this clause; that update has not landed.

Complexity bar: "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

Quality bar: "Tests pass and the feature works as specced. ROI matters."

File-based state (constraint on ticket 117+, not this skeleton): "Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files. No database or server."

### `CLAUDE.md`

Binding conventions:

- "Always commit using the `/commit` skill — never run `git commit` manually"
- "New global utilities follow the deploy-bin pattern: logic goes in `bin/`, deployed to `~/.local/bin/` via `just deploy-bin`, skills invoke the binary by name"

The skeleton introduces a **different** delivery shape (`uv tool install` rather than `bin/` symlink). DR-5 of epic research endorses this; the deploy-bin convention stays for existing bash scripts (`jcc`, `overnight-*`).

### `requirements/pipeline.md`, `observability.md`, `remote-access.md`, `multi-agent.md`

No binding constraint on introducing a new top-level Python package with a `cortex` console entry point. These docs govern runtime behavior of existing subsystems, which ticket 115+ will migrate.

### `lifecycle.config.md`

`test-command: just test`, `commit-artifacts: true`. Review criteria: "New config files must follow the symlink pattern" (doesn't apply — cortex binary is not a config file). "Settings JSON must remain valid JSON" (applies if ticket touches settings.json, which it shouldn't).

### `claude/rules/sandbox-behaviors.md` (informational for 117+)

`excludedCommands = ["gh:*", "git:*", "WebFetch", "WebSearch"]`. Do **not** add long-lived-subtree tools. Skeleton ticket does not touch this; flagging for ticket 115+ (do not add `uv:*` or `cortex:*` to excludedCommands).

## Tradeoffs & Alternatives

### Axis 1 — CLI framework

- **argparse**: stdlib, 0 deps, matches every existing CLI in the repo (`claude/common.py`, all `claude/overnight/*.py` CLIs, `bin/audit-doc`, `bin/count-tokens`). aider's precedent (cited throughout the epic research) uses argparse. Skeleton is 5 flat subcommands with stderr stubs — ~30 LOC of argparse.
- **click**: 1 transitive dep, nested-group ergonomics for future `cortex overnight start`. Shell-completion requires per-shell source-the-file dance.
- **typer**: ~10 transitive deps, `--install-completion` auto-installs for bash/zsh/fish/powershell (biggest ergonomic win in theory). Heavy for a skeleton.

**Tradeoff**: Agent 4 originally recommended click for nested-group ergonomics; Agent 5 (adversarial) pushed back that the nesting requirement belongs to ticket 115 and is speculative today — aider (the cited precedent) uses argparse. The argparse floor is consistent with every other CLI in the repo; migration cost later (if nesting arrives) is ~2 hours of rewriting the dispatcher for 5 subcommands.

**Research recommendation**: **argparse** for this skeleton. Revisit framework choice in ticket 115 when the actual nesting structure is known. This matches the "simpler solution is correct" project.md bar and the existing in-repo convention. Defer to user in Spec if user prefers to commit to click now.

### Axis 2 — Package layout / location

| Option | Path | Wheel declaration | Trade-off |
|--------|------|-------------------|-----------|
| (a) | `claude/cortex/` | `packages = ["claude"]` | Zero import-graph churn; single-tree wheel. But see Adversarial #1 — ships `claude/` as distribution content, collides with Anthropic-owned PyPI `claude`. |
| (b) | `src/cortex/` + keep `claude/` flat | `packages = ["src/cortex", "claude"]` | Two-tree wheel; src-layout isolates CLI from runner internals. Still ships `claude/`. |
| (c) | top-level `cortex/` | `packages = ["cortex", "claude"]` | Two-tree wheel; two top-level packages at repo root. |
| (d) | `claude/cli.py` single module | `packages = ["claude"]` | Simplest; CLI name (`cortex`) and module path (`claude.cli`) diverge. |
| (e) | Rename `claude/` → `cortex_command/` first | `packages = ["cortex_command"]` | Solves the PyPI collision. 292+ import edits, large migration, out of this ticket's scope by default. |

**Research recommendation**: defer to Spec. The PyPI `claude` collision (see Adversarial #1) is the biggest decision. Four paths forward:

1. Rename `claude/` → `cortex_command/` **now** (in this ticket), accepting the 292+ edit scope expansion.
2. Rename in ticket 115 (which already scopes `$REPO_ROOT`/`PYTHONPATH` migration).
3. Accept collision risk with explicit documentation — we don't install PyPI `claude` as a dep, and our `claude-agent-sdk` is a different import path, so collision requires a user action.
4. Ship via option (a) `claude/cortex/` for the skeleton and rename later. Lowest skeleton churn; highest future debt.

The adversarial recommendation is #1 (rename now, before adding `[build-system]`). The minimum-churn recommendation is #4. This is a user decision in Spec.

### Axis 3 — Module name

Follows from Axis 2. If `claude/` stays: `claude.cortex.cli:main` or `claude.cli:main`. If renamed: `cortex_command.cli:main` or `cortex.cli:main`.

### Axis 4 — Build backend

- **hatchling**: Astral's default, recommended by uv docs. Handles PEP 621 metadata natively, fastest builds. But see Adversarial #2 — hatchling's auto-detection requires explicit configuration when the package root has no `__init__.py`, and data-file inclusion (templates, prompts) needs `[tool.hatch.build.targets.wheel.force-include]` or `include = ["claude/**/*"]` for non-`.py` files.
- **setuptools**: aider's choice. PEP 621-compliant via `[build-system] build-backend = "setuptools.build_meta"`. Strongest fallback; slower; `packages = find:` convention.
- **flit_core**: too lean for multi-package wheel (would need to carry `claude/*` tree).

**Research recommendation**: **hatchling** with explicit `[tool.hatch.build.targets.wheel]` config — do **not** rely on auto-detection. Pin `requires = ["hatchling>=1.27"]` (not unbounded). The skeleton ticket must either verify wheel contents (adversarial #2) or scope explicitly to "entry-point works" without data-file inclusion.

### Axis 5 — Placeholder behavior

- **(a) `print(...); exit 0`**: lies about success. Any CI wrapper treating exit 0 as done will silently believe the subcommand worked.
- **(b) `print(..., file=sys.stderr); sys.exit(2)`**: correct UNIX contract; detectable; exit 2 matches argparse usage-error convention. Wrapper-friendly.
- **(c) `raise NotImplementedError`**: traceback output is user-hostile.

**Research recommendation**: **(b)** — stderr + `sys.exit(2)` with message `"not yet implemented: cortex <subcommand>"`.

### Axis 6 — `--help` source

For argparse: set `description=` per subparser, explicit `help=` on each subparser. The docstring-auto-extract pattern is click/typer-specific and does not apply to argparse.

**Research recommendation**: explicit `description=` strings in argparse subparsers (if argparse wins Axis 1). One-line-per-subcommand is sufficient for the skeleton.

### Combined research recommendation

Add `[build-system]` + `[project.scripts]` with **argparse** as the framework, layout option **(a) `claude/cortex/`** for minimum skeleton churn (with the PyPI collision risk acknowledged and routed to Spec as a decision), **hatchling** as the build backend with explicit wheel config, **stderr + exit 2** for placeholders, **`description=` strings** for help. Document the `uv run` constraint in both `README.md` and the `cortex --help` epilog. Defer the `claude/` rename timing to Spec.

## Adversarial Review

### The PyPI `claude` name is owned by Anthropic

https://pypi.org/project/claude/ is a real, Anthropic-owned package (v0.4.11, June 2025; author Lina Tawfik). Option (a) from Axis 2 ships a wheel whose top-level import root is `claude`. If any user installs PyPI `claude` into the same environment as our `cortex-command` wheel, PEP 420 namespace resolution may silently mix contents, or the PyPI package wins and every `from cortex_command.overnight import *` breaks with `ModuleNotFoundError`. `claude-agent-sdk` is already a direct dep and is a distinct import path — but if Anthropic ever publishes a non-trivial `claude` module as a transitive dep (direct or via `claude-agent-sdk`), we break silently.

**Mitigation**: rename `claude/` → `cortex_command/` (Axis 2 option e) before adding `[build-system]`. The "minimum churn" recommendation is a trap — minimum churn today at the cost of a namespace collision later where debugging is opaque.

### Hatchling + PEP 420 + data files is not zero-config

`claude/` has no `__init__.py`; hatchling raises `ValueError: Unable to determine which files to ship inside the wheel` without explicit `[tool.hatch.build.targets.wheel] packages = ["claude"]` (pypa/hatch#1763 and discussions/819). That declaration works — but it ships `claude/` as a **regular package** in the wheel, not a namespace package. Post-install, `claude/` is a conventional package root that shadows any other namespace contributor.

Further: hatchling's auto-detection skips non-`.py` files. `claude/dashboard/templates/` (Jinja2), `claude/overnight/prompts/*.md`, `claude/pipeline/prompts/*.md` will not be in the wheel without explicit `[tool.hatch.build.targets.wheel.force-include]` or a glob `include = ["claude/**/*"]`. If they're missing, the dashboard 404s at runtime after `uv tool install`. **None of the non-adversarial agents flagged data-file inclusion as a skeleton concern.**

**Mitigation**: CI step — `uv build` → unpack → assert every `templates/`, `prompts/`, `tests/` subtree is present. Alternatively, scope the skeleton explicitly to "entry-point works" and defer wheel-content completeness to ticket 115.

### Editable tool install breaks silently when the repo moves

`uv tool install -e .` writes a `.pth` pointing at the source tree (uv#16306). If the user moves/deletes the repo, or has two clones (main + worktree) and runs `uv tool install -e .` from the wrong one, `cortex --help` silently fails from `$HOME`. No summary addressed this.

**Mitigation**: add a minimal `cortex --version` at the skeleton stage that prints the install-source path and warns if it does not match `$CORTEX_COMMAND_ROOT`. This is ~10 LOC and pays for itself the first time it surfaces a broken clone. Note: this is scope-expansion vs. the ticket's literal scope; Spec decides.

### Entry-point reinstall footgun

`uv tool install -e .` live-reloads source edits but not `[project.scripts]` edits. Adding a second top-level entry point (e.g., `cortexd`) requires `uv tool uninstall cortex-command && uv tool install -e . --force`. The skeleton should surface this in docs loudly — no summary called it out as a user-facing doc item.

### `uv tool install /path` ignores target pyproject's `[tool.uv]`

Per uv#15529: `uv tool install /path/to/dir` uses the user's CWD for tool configuration, not the target's. If ticket 115+ adds `[tool.uv.sources]` pinning a dev dep, the recommended install sequence becomes "`cd` into the repo first, then `uv tool install -e .`". Non-obvious; the skeleton should bake this into docs now.

### `PYTHONPATH=$REPO_ROOT` + tool venv can double-load modules

The runner exports `PYTHONPATH=$REPO_ROOT` and activates `.venv`. Once cortex is tool-installed, a user who runs `just overnight-run` has two code sources in `sys.path`: the tool venv's editable pointer + the repo venv's activation + PYTHONPATH. For `importlib.resources`, module-level singletons, or path-based config discovery (the dashboard uses path-based template lookup), sys.path ordering produces nondeterministic behavior.

Adding `[build-system]` to `pyproject.toml` changes `uv sync` behavior — `uv sync` will now attempt to install the project itself into `.venv` (as a regular install, not editable), racing the editable tool install.

**Mitigation**: verify `uv sync` before and after the skeleton. If it starts installing the project into `.venv`, set `[tool.uv] package = false` to suppress, or document that the project is installed in two places and which one wins per invocation mode.

### Binary name `cortex` may collide

`brew search cortex` returns multiple hits (gpu-telemetry `cortex`, NVIDIA `cortex-daemon`, crypto-wallet `cortex`). None are in our users' typical PATH, but worth a pre-implementation check. Low-frequency collision; high-cost rename if it hits.

### Future CWD-based `uv run` is a latent attack vector (ticket 117+, not 114)

Once `cortex setup` or `cortex init` (future subcommands) call `uv run` / `uv sync` against the user's CWD, a user running these inside a cloned-from-stranger repo gets arbitrary-code-execution via PEP 517 build backends. This is not a skeleton concern; the skeleton must ensure placeholders **do not call `uv run` or `subprocess.run(["uv", ...])`** even as stubs. Exit 2 without touching subprocess.

### Click-vs-argparse is projection

Agent 4 recommended click projecting onto ticket 115's nested groups. Ticket 115 is research-phase; nesting may not land the way Agent 4 imagined. aider (Agent 4's precedent for every other decision) uses argparse. Research rejections being load-bearing (per user feedback memory) cuts both ways — Agent 4's argparse rejection is speculative, not research-grounded.

**Mitigation**: use argparse for the skeleton; revisit in ticket 115 when the actual nesting shape is known. Migration cost from argparse to click for 5 flat subcommands is ~2 hours of rewriting the dispatcher — far smaller than the regret cost of click-now-and-later-wanting-minimal-deps.

### `project.md` "earn its place" bar not met explicitly

A bash `bin/cortex` script that dispatches to `uv run python -m claude.cortex.<subcommand>` is strictly simpler than `[build-system]` + entry-point machinery, and preserves the existing deploy-bin convention. The ticket reads as if `uv tool install` was chosen because it's the epic's premise, not because it was weighed against the bash-dispatcher alternative. This is a valid adversarial pushback; the epic research (DR-4) does explicitly weigh and reject PyInstaller / Homebrew-primary / pipx / bash — but the "bash dispatcher" alternative is not in that list. Spec should confirm the user accepts the epic's premise for this ticket.

## Open Questions

These are genuine decisions the Spec phase must resolve. Each is either explicitly deferred with rationale or resolved inline — none are bare.

1. **Package rename timing (Adversarial #1)**: rename `claude/` → `cortex_command/` now (this ticket), defer to ticket 115, or accept collision risk with docs? **Deferred to Spec — this is a load-bearing scope decision with 292+ file impact.** Research recommendation: rename now, before adding `[build-system]`. Minimum-churn alternative: defer and ship `claude/cortex/` submodule.

2. **CLI framework choice**: argparse (research + adversarial recommendation; matches every existing in-repo CLI and aider precedent) or click (Agent 4's original rec; nested-group ergonomics for ticket 115)? **Deferred to Spec — user preference call.** Research recommendation: argparse.

3. **Wheel-content scope for skeleton verification (Adversarial #2)**: does this ticket verify only that `cortex --help` resolves, or also that `claude/dashboard/templates/`, `claude/overnight/prompts/`, `claude/pipeline/prompts/` ship in the wheel? **Deferred to Spec.** Research recommendation: scope the skeleton to "entry-point works"; defer wheel-content completeness test to ticket 115's migration work (which must handle it anyway).

4. **Test strategy**: durable pytest test using `uv build` + unpack, or one-shot manual verification documented in the spec? **Deferred to Spec.** Research recommendation: durable pytest test, sandbox-friendly (no `uv tool install` during tests; use `uv build` + unpack or `pip install --target=tmp`).

5. **`uv run` doc placement**: README.md section only, or README + `cortex --help` epilog (argparse `epilog=`) + `docs/distribution.md`? **Deferred to Spec.** Research recommendation: README.md "Distribution" section + `cortex --help` epilog (argparse `epilog=` on the top-level parser) — docs must be visible at both the repository and CLI-interaction surfaces.

6. **`cortex --version` / `cortex doctor` at skeleton stage (Adversarial #3)**: include in skeleton as a diagnostic for broken clones, or defer? **Deferred to Spec.** Research recommendation: include a minimal `--version` that prints the install-source path — ~10 LOC, pays for itself when debugging tool-install drift.

7. **`[tool.uv] package = false` (Adversarial #6)**: verify `uv sync` behavior before vs. after `[build-system]` is added; if `uv sync` installs the project into `.venv` and that causes PYTHONPATH/tool-venv collisions, set `package = false`. **Resolved inline — procedural** — the verification is part of implementation; the setting is contingent on the verification outcome.

8. **Binary-name collision check**: `brew search cortex`, `which cortex` on common macOS setups before baking the name into skills. **Resolved inline — procedural** — quick pre-implementation check; if hit, escalate to user before proceeding.

9. **Exit-code footgun — `--help` should mention entry-point reinstall requirement**: the `cortex --help` epilog should note that changes to `[project.scripts]` require `uv tool install -e . --force`. **Resolved inline** — include in the `--help` epilog text alongside the `uv run` constraint note.
