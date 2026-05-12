# Review: build-cortex-cli-skeleton-with-uv-tool-install-entry-point

## Stage 1: Spec Compliance

### Requirement 1: Rename Python modules from `claude/*` to `cortex_command/*`
- **Expected**: New package root at `cortex_command/` (regular package with `__init__.py`); every Python import path, `-m` invocation, `mock.patch` string, uvicorn colon-syntax, permission allow rule, and documentation prose substituted from `claude.X` → `cortex_command.X` and `claude/X/` → `cortex_command/X/` (except preserved Claude Code config: `settings.json`, `Agents.md`, `rules/`, `reference/`, `statusline.sh`, `hooks/`).
- **Actual**: `cortex_command/` exists as a regular package (empty `__init__.py` at `cortex_command/__init__.py`, 0 bytes). All greps required by the ACs return exit 1 (no matches) for: `(from|import) claude.X`, `python3 -m claude.X`, `mock.patch("claude.X.Y")`. Imports smoke-tests pass (`python3 -c "import cortex_command.common, cortex_command.overnight, cortex_command.pipeline, cortex_command.dashboard"` exits 0). `claude/settings.json` permission allow rule updated to `Bash(python3 -m cortex_command.*)` (line 99). Preserved config verified at original paths (`claude/settings.json`, `claude/Agents.md`, `claude/statusline.sh`, non-empty `claude/rules/` and `claude/reference/`). `just test` reports 3/3 suites green. The `uvicorn claude.` grep returns matches ONLY inside `lifecycle/build-cortex-cli-skeleton-.../spec.md|plan.md|research.md` and `retros/2026-04-21-2121.md` — these are meta-discussion of the rename itself and fall under spec §Non-Requirements ("Updating committed historical lifecycle artifacts ... that contain stale `claude.*` references — historical logs are frozen-in-time records").
- **Verdict**: PASS
- **Notes**: Task 2 also moved `claude/tests/` → `cortex_command/tests/` (the Veto Surface in plan.md flagged this as a broader-than-spec choice for `tests` subpackage). This is consistent with plan's recommendation and `_stubs.py` imports resolve.

### Requirement 2: Add `[build-system]` + hatchling + wheel target to `pyproject.toml`; wheel ships data files
- **Expected**: `[build-system]` with `requires = ["hatchling>=..."]` and `build-backend = "hatchling.build"`; `[tool.hatch.build.targets.wheel].packages = ["cortex_command"]`; `uv build` produces a wheel containing `cortex_command/overnight/prompts/*.md` and `cortex_command/dashboard/templates/*`.
- **Actual**: `pyproject.toml` lines 1-3 declare `requires = ["hatchling>=1.27"]` + `build-backend = "hatchling.build"`. Lines 20-21 declare `[tool.hatch.build.targets.wheel]` with `packages = ["cortex_command"]`. All three TOML ACs (build-backend, hatchling requires, wheel packages) verified via `tomllib` assertion exit 0. Wheel content inspection (`python3 -c "import zipfile..."`) confirms `cortex_command/` tree, `cortex_command/overnight/prompts/*.md`, and `cortex_command/dashboard/templates/` all present in `dist/cortex_command-0.1.0-py3-none-any.whl`. No `[tool.uv] package = false` — verified.
- **Verdict**: PASS

### Requirement 3: Declare `cortex` console entry point; `cortex --help` works after install
- **Expected**: `[project.scripts].cortex = "cortex_command.cli:main"`; after `uv tool install -e . --force`, `which cortex` resolves and `cortex --help` lists 5 subcommands.
- **Actual**: `pyproject.toml` line 17-18 declares `[project.scripts] cortex = "cortex_command.cli:main"`. TOML AC verified. `which cortex` returns `/Users/charlie.hall/.local/bin/cortex`. `cortex --help` output enumerates all 5 subcommands (overnight, mcp-server, setup, init, upgrade) and includes the epilog with `uv run` + `--force` + `uv tool update-shell` notes.
- **Verdict**: PASS

### Requirement 4: argparse-based `cortex_command/cli.py` with 5 subcommands (exit 2 + stderr stubs; both `help=` and `description=`)
- **Expected**: `cortex_command/cli.py` with argparse `main()` dispatcher; each of 5 subparsers has `help=` (shown in top-level `--help`) and `description=` (shown in `cortex <sub> --help`); each stub prints `"not yet implemented: cortex <subcmd>"` to stderr and exits 2; top-level epilog mentions `uv run` scoping + `--force` reinstall requirement.
- **Actual**: `cortex_command/cli.py` present (101 lines). `main(argv)` builds an `argparse.ArgumentParser` with `RawDescriptionHelpFormatter`, attaches 5 subparsers each via `subparsers.add_parser(..., help=..., description=...)` and `set_defaults(func=_make_stub(name))`. Verified:
  - `python3 -m cortex_command.cli --help` lists all 5 subcommands (grep count = 7, ≥ 5).
  - Each subcommand exit code = 2 and stderr contains `"not yet implemented: cortex <sub>"` — confirmed by shell loop for `overnight`, `mcp-server`, `setup`, `init`, `upgrade`.
  - `python3 -m cortex_command.cli overnight --help` contains the description string `"Launch or manage the overnight autonomous runner"` (count = 1).
  - Epilog grep matches `uv run|--force` count = 2 (meets ≥ 2 AC).
  - No subprocess imports in cli.py (per spec §Technical Constraints).
- **Verdict**: PARTIAL
- **Notes**: Spec Req 4 AC names `tests/test_cortex_cli_skeleton.py` as the location where the per-subcommand exit-code + stderr assertions are "Automated in ... `subprocess.run(...)`". No such regression test file was committed; verification was performed via ad-hoc shell loop (consistent with Task 11's plan wording "loop in a small shell script or pytest"). Behavior is correct today but there is no pinned regression for future tickets that modify `cli.py`. Downstream tickets (115-119) will replace each stub body, so a pinned regression that asserts "not yet implemented" would be discarded progressively — but the *pre-implementation* pinned shape (help output listing 5 commands, argparse usage-error on no-arg) is a reasonable thing to keep.

### Requirement 5: Document `uv run` constraint and entry-point reinstall footgun
- **Expected**: `README.md` or `docs/distribution.md` describes four constraints: (a) `uv run` scope; (b) don't `uv tool uninstall uv`; (c) `[project.scripts]` changes require `uv tool install -e . --force`; (d) `uv tool update-shell` one-time setup. `cortex --help` epilog mentions `uv run` and `--force`.
- **Actual**: `README.md` lines 172-180 add a `## Distribution` section with all four bullet points. Grep `'uv run.*user.*project|tool.*venv'` matches (README has "operates on the user's current project, not cortex's own tool venv"). Grep `'uv run|uv tool uninstall|--force|uv tool update-shell'` count = 4 in README. CLI epilog (lines 16-26 of cli.py) covers `uv run` scoping, `uv tool install -e . --force`, and `uv tool update-shell` — epilog grep `'uv run|--force'` returns 2 in `cortex --help` output.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- `requirements/project.md` §Project Boundaries → Out of Scope lists "Published packages or reusable modules for others" as a hard boundary. Ticket 114 adds `[build-system]` + `[project.scripts]` to `pyproject.toml`, producing a distributable wheel (`dist/cortex_command-0.1.0-py3-none-any.whl`). The wheel is installable via `uv tool install -e .` (editable, local), not published to PyPI, but the machinery to publish (hatchling build backend, versioned wheel, console script entry point) is now in place. The ticket body (`backlog/114-cortex-cli-skeleton.md`) reconciles this as "installable locally, not published," but `requirements/project.md` does not yet reflect the nuance — as written, a future reader would conclude that adding a wheel target is out-of-scope.
**Update needed**: `requirements/project.md`

## Suggested Requirements Update

**File**: `requirements/project.md`
**Section**: `### Out of Scope` (under `## Project Boundaries`)
**Content**:
```
- Published packages or reusable modules for others — the `cortex` CLI ships as a local editable install (`uv tool install -e .`) for self-hosted use; publishing to PyPI or other registries is out of scope.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `cortex_command/cli.py` follows project idioms — snake_case module, `main(argv: list[str] | None = None) -> int` signature matching `cortex_command/overnight/auth.py:_main` and the project's other argparse CLIs. Private helpers prefixed with `_` (`_make_stub`, `_build_parser`). Subcommand names use hyphens (`mcp-server`) per the spec and POSIX convention. Epilog constant `EPILOG` uppercase module-level.
- **Error handling**: Appropriate. Stub handlers print to `sys.stderr` and call `sys.exit(2)` (argparse usage-error convention per spec §Technical Constraints — "Placeholder semantics"). No `raise NotImplementedError` (spec flags as user-hostile). No subprocess invocations inside stubs (spec §Technical Constraints — "No subprocess calls inside stubs"). `main()` handles the no-argument case by printing help to stderr and returning 2 (reasonable default; argparse doesn't enforce a required subcommand here, but the behavior is usage-error-shaped).
- **Test coverage**: All three `just test` suites pass (test-pipeline, test-overnight, tests — "3/3 passed"). Plan's Verification Strategy Layer 1 (per-task AC greps) confirmed. Layer 2 (`just test`) green. Layer 3 (`uv build` + wheel-content inspection + `uv tool install -e . --force` + `cortex --help`) all pass. **Gap**: no automated regression test for the CLI skeleton itself — `tests/test_cortex_cli_skeleton.py` named in spec Req 4 AC is absent. See Req 4 PARTIAL note.
- **Pattern consistency**: Argparse usage matches existing `cortex_command/pipeline/metrics.py:1025` and `cortex_command/overnight/auth.py:321` patterns (same `prog=`, `description=`, `parse_args(argv)` idiom, exit-code return). `RawDescriptionHelpFormatter` chosen to preserve the epilog's multi-line formatting — matches the spec's requirement that the epilog content be readable in `--help`. `_make_stub` closure pattern is local to this file but idiomatic for argparse handlers that share structure.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["Req 4 PARTIAL: tests/test_cortex_cli_skeleton.py named in spec AC was not created — CLI behavior verified via shell loop but no pinned regression for future ticket-115+ edits to cli.py. Low-priority follow-up, not a blocker."], "requirements_drift": "detected"}
```
