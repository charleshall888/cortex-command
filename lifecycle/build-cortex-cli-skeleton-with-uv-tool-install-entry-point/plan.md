# Plan: build-cortex-cli-skeleton-with-uv-tool-install-entry-point

## Overview

Rename every Python module under `claude/` (except standalone hook scripts) to a new top-level `cortex_command/` package, then add `[build-system]`, `[project.scripts]`, and hatchling wheel config to `pyproject.toml` plus an argparse-based `cortex_command/cli.py` with 5 stderr/exit-2 stubs. All five spec requirements land on a single feature branch that squash-merges into main as one commit (honoring the atomic-land invariant); per-task commits live only on the feature branch to give incremental checkpoints. `claude/` directory survives for non-Python Claude Code config (settings.json, Agents.md, rules/, reference/, statusline.sh, hook scripts).

## Tasks

### Task 1: Pre-flight — binary-name collision check, session pause, branch creation
- **Files**: none (read-only checks + git branch)
- **What**: Verify `cortex` binary name is unmapped on the developer PATH and Homebrew, pause any in-flight overnight session to avoid a `uv.lock` race during the rename commit, and create the feature branch that the remaining tasks build on.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run `which cortex` (expect exit 1 / no output); run `brew search cortex` and scan for entries on PATH-earlier taps; escalate to the user if a collision exists on a PATH-earlier binary. Check `ps aux | grep -E 'overnight-(start|schedule|run)'` and `launchctl list | grep cortex` for active runners; stop them via the corresponding `overnight-*` stop command or `launchctl unload` before proceeding. Create the feature branch: `git checkout -b feat/114-cortex-cli-skeleton`. See spec §Technical Constraints (binary-name pre-check, pause overnight sessions) and §Edge Cases (in-flight overnight session).
- **Verification**: Run `which cortex; echo "exit=$?"` — pass if `exit=1` (no binary) OR the located path is on a tap the user has explicitly confirmed is acceptable. Run `git branch --show-current` — pass if output = `feat/114-cortex-cli-skeleton`. Overnight-session pause is Interactive/session-dependent: it depends on the developer's local launchd/runner state at the exact moment of the rename commit.
- **Status**: [ ] pending

### Task 2: Move Python subtrees with `git mv` to `cortex_command/`
- **Files**: `claude/common.py` → `cortex_command/common.py`; `claude/overnight/` → `cortex_command/overnight/`; `claude/pipeline/` → `cortex_command/pipeline/`; `claude/dashboard/` → `cortex_command/dashboard/`; `claude/tests/` → `cortex_command/tests/`
- **What**: Preserve git history by using `git mv` (one invocation per subtree) rather than `cp` + `rm`. All co-located non-`.py` files (prompts/, templates/, per-subpackage `tests/`, `__init__.py`) move with their parent.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Five `git mv` invocations. The existing `__init__.py` files at `claude/pipeline/__init__.py`, `claude/dashboard/__init__.py`, `claude/overnight/__init__.py`, `claude/tests/__init__.py` carry over unchanged. Do NOT move `claude/hooks/` — it has no `from claude.*` imports anywhere (verified: `grep -r 'from claude\.hooks\|import claude\.hooks' --include='*.py' .` returns no matches) and `claude/hooks/cortex-sync-permissions.py` is a standalone Claude Code hook per spec §Technical Constraints. Do NOT touch `claude/settings.json`, `claude/Agents.md`, `claude/rules/`, `claude/reference/`, `claude/statusline.sh`, `claude/statusline.ps1`. After the `git mv` block, commit on the feature branch with subject "Move Python subtrees to cortex_command/ package root".
- **Verification**: Run `find . -type d -name cortex_command -path '*/cortex_command' -maxdepth 2 | grep -cx './cortex_command'` — pass if output = `1`. Run `ls claude/settings.json claude/Agents.md claude/statusline.sh && ls claude/rules/ claude/reference/` — pass if both commands exit 0 with non-empty `rules/` and `reference/` listings.
- **Status**: [ ] pending

### Task 3: Create `cortex_command/__init__.py`
- **Files**: `cortex_command/__init__.py` (new, empty)
- **What**: Declare `cortex_command` as a regular (non-namespace) package to avoid the PEP 420 ambiguity the previous `claude/` root had and to give hatchling a deterministic package root.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Empty file. The existing `__init__.py` files inside subpackages (`cortex_command/overnight/__init__.py`, `cortex_command/pipeline/__init__.py`, etc.) are preserved from the `git mv` in Task 2.
- **Verification**: `test -f cortex_command/__init__.py; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [ ] pending

### Task 4: Rewrite `from claude.X` / `import claude.X` statements to `cortex_command.X` across all `.py` files
- **Files**: All `.py` files in the repo containing the matched patterns. Known universe (from Codebase Analysis): `backlog/update_item.py`, `backlog/create_item.py`, `backlog/generate_index.py`, plus every Python file inside the now-moved `cortex_command/` tree and every test file referencing it — roughly 100+ files. Enumerate up-front with `grep -rlE '(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .` and list the output.
- **What**: Substitute `from claude.{overnight|pipeline|common|dashboard|hooks|tests}` → `from cortex_command.{...}` and `import claude.{overnight|pipeline|common|dashboard|hooks|tests}` → `import cortex_command.{...}` in-place. `tests` is added to the subpackage list because `claude/tests/_stubs.py` is imported from multiple test files (verified: `grep -rl 'from claude\.tests' --include='*.py' .` shows three importers).
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: The safe substitution pattern is `sed -E -i '' 's/(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)/\1 cortex_command.\2/g' <files>` on macOS (empty `-i ''` argument). Note: `claude.common` is a module (not a subpackage) so `from claude.common import X` is in scope — the pattern covers it. After substitution, run `python3 -c "import cortex_command.common, cortex_command.overnight, cortex_command.pipeline, cortex_command.dashboard"` as a smoke test. Commit on feature branch: "Rewrite Python imports to cortex_command.* namespace".
- **Verification**: Run `grep -rnE '(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .; echo "exit=$?"` — pass if `exit=1` (no matches). Run `python3 -c "import cortex_command.common, cortex_command.overnight, cortex_command.pipeline, cortex_command.dashboard"; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [ ] pending

### Task 5: Rewrite `python3 -m claude.X` invocations across `.py`, `.sh`, `.md`, `.toml`, `.txt`, and `justfile`
- **Files**: Everything matched by the grep — known sites: `justfile` (5 lines: 615, 621, 655 uvicorn, 659, 663), `claude/overnight/runner.sh` (pre-rename; lives at `cortex_command/overnight/runner.sh` post Task 2) lines referencing `-m claude.*`, `hooks/cortex-scan-lifecycle.sh:379` (`python3 -m claude.pipeline.metrics`), orchestrator prompts (`cortex_command/overnight/prompts/orchestrator-round.md` — 7 refs post Task 2), `docs/overnight-operations.md` (7 refs), `skills/overnight/SKILL.md` (12 refs), various backlog markdown files. Enumerate with `grep -rlE 'python3 -m claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' .`.
- **What**: Substitute `python3 -m claude.{subpkg}` → `python3 -m cortex_command.{subpkg}` in place.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: Same sed pattern as Task 4, scoped to the broader file extensions. Task 4 (import statements) ran first so that the import graph is valid before prose and docs follow. Commit: "Rewrite -m claude invocations across shell, markdown, and config".
- **Verification**: Run `grep -rnE 'python3 -m claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' .; echo "exit=$?"` — pass if `exit=1`.
- **Status**: [ ] pending

### Task 6: Rewrite `unittest.mock.patch("claude.X.Y")` strings across test files
- **Files**: Every `.py` file matched by `grep -rlE 'unittest\.mock\.patch\s*\(\s*["'\'']claude\.(overnight|pipeline|common|dashboard|hooks|tests)|patch\s*\(\s*["'\'']claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .`. Live count against the current tree: ~236 matches across ~18 files (verified during Plan phase — spec's 286/28 estimate was from an earlier research pass).
- **What**: Substitute every occurrence of `patch("claude.{subpkg}...")` and `patch('claude.{subpkg}...')` → `patch("cortex_command.{subpkg}...")` / `patch('cortex_command.{subpkg}...')`. These are runtime-resolved string targets; missing any occurrence causes `just test` to fail with `AttributeError` or `ModuleNotFoundError`.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**: sed pattern must handle both quote styles: `sed -E -i '' -e "s/patch\((\s*)([\"'])claude\.(overnight|pipeline|common|dashboard|hooks|tests)/patch(\1\2cortex_command.\3/g"` on each matched file. An alternative is a short Python helper using `re.sub` per file — either is acceptable. Commit: "Rewrite mock.patch strings to cortex_command namespace".
- **Verification**: Run `grep -rnE 'unittest\.mock\.patch\s*\(\s*["'\'']claude\.(overnight|pipeline|common|dashboard|hooks|tests)|patch\s*\(\s*["'\'']claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .; echo "exit=$?"` — pass if `exit=1`.
- **Status**: [ ] pending

### Task 7: Update non-module runtime-string references (uvicorn colon-syntax, settings.json allow rule, docstring examples)
- **Files**: `justfile` line 655 (uvicorn), `cortex_command/dashboard/app.py` line 11 (docstring example — post Task 2 path), `claude/settings.json` line ~99 (permission allow rule), plus any argparse `usage=` / `prog=` strings or docstrings that embed `python3 -m claude.*` as prose (enumerate with `grep -rn 'claude\.\(overnight\|pipeline\|common\|dashboard\|hooks\|tests\)' --include='*.py' .` post Tasks 4–6 and inspect remaining matches for prose-only uses).
- **What**: Substitute `uv run uvicorn claude.dashboard.app:app` → `uv run uvicorn cortex_command.dashboard.app:app` in `justfile`. Substitute `"Bash(python3 -m claude.*)"` → `"Bash(python3 -m cortex_command.*)"` in `claude/settings.json`. Substitute any remaining `claude.<subpkg>` prose strings in docstrings or argparse metadata.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: `claude/settings.json` stays at its existing path (preserved per spec §Changes to Existing Behavior — the FILE stays; its CONTENTS change). Validate the JSON after editing: `python3 -c "import json; json.loads(open('claude/settings.json').read())"`. For the uvicorn line, the exact replacement is the full justfile recipe body — edit in place. Commit: "Rewrite runtime-string claude.* references (uvicorn, settings, docstrings)".
- **Verification**: Run `grep -rnE 'uvicorn claude\.' --include='*.py' --include='*.sh' --include='*.md' --include='justfile' --include='*.toml' .; echo "exit=$?"` — pass if `exit=1`. Run `grep -c 'Bash(python3 -m claude\.' claude/settings.json` — pass if output = `0`. Run `grep -c 'Bash(python3 -m cortex_command\.' claude/settings.json` — pass if output ≥ `1`. Run `python3 -c "import json; json.loads(open('claude/settings.json').read())"; echo "exit=$?"` — pass if `exit=0` (settings JSON remains valid).
- **Status**: [ ] pending

### Task 8: Semantic rewrite of `skills/overnight/SKILL.md:46` paragraph
- **Files**: `skills/overnight/SKILL.md`
- **What**: Replace the current paragraph (which asserts `claude.overnight.*` modules "are not installed globally") with text that reflects the new reality — `cortex_command.overnight.*` modules ARE globally installable via `uv tool install -e .`, and the `cortex` binary invokes them directly. This is a meaning-level rewrite, not a token substitution (see spec §Edge Cases — `skills/overnight/SKILL.md:46` paragraph premise is invalidated).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Read the paragraph around line 46 first; identify the load-bearing claim ("not installed globally" or similar phrasing) and rewrite it to describe the new invocation surface without dangling references to the old state. Keep the paragraph's purpose intact (explaining how skills invoke the overnight module) while updating the mechanism. Commit: "Rewrite skills/overnight/SKILL.md:46 paragraph for post-CLI install path".
- **Verification**: Run `grep -cE 'not installed globally|installed as a package|PYTHONPATH' skills/overnight/SKILL.md` — pass if output describes the current (post-rewrite) state. Specifically: `grep -c 'cortex_command' skills/overnight/SKILL.md` — pass if output ≥ `1` AND `grep -c 'claude\.overnight' skills/overnight/SKILL.md` — pass if output = `0`.
- **Status**: [ ] pending

### Task 9: Update `pyproject.toml` testpaths to `cortex_command/...`
- **Files**: `pyproject.toml`
- **What**: Change `[tool.pytest.ini_options].testpaths = ["tests", "claude/dashboard/tests", "claude/pipeline/tests", "claude/overnight/tests"]` to `["tests", "cortex_command/dashboard/tests", "cortex_command/pipeline/tests", "cortex_command/overnight/tests"]`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Single-line edit in existing `[tool.pytest.ini_options]` block. The `pythonpath = ["."]` line stays — tests still need the repo root on sys.path for imports to resolve during pytest collection. Commit: "Update pyproject testpaths to cortex_command subpackages".
- **Verification**: Run `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['tool']['pytest']['ini_options']['testpaths']==['tests','cortex_command/dashboard/tests','cortex_command/pipeline/tests','cortex_command/overnight/tests']"; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [ ] pending

### Task 10: Add `[build-system]`, `[project.scripts]`, `[tool.hatch.build.targets.wheel]` atomically in `pyproject.toml`
- **Files**: `pyproject.toml`
- **What**: Single edit that adds all three sections in one pass (per spec §Technical Constraints — "Atomic `pyproject.toml` edit"). Declares hatchling as the build backend, wires `cortex = "cortex_command.cli:main"` as the console script, and specifies the wheel package root as `["cortex_command"]`.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**:
  - `[build-system]` block: `requires = ["hatchling>=1.27"]`, `build-backend = "hatchling.build"` (per spec §Technical Constraints — hatchling ≥1.27, no unbounded upper pin).
  - `[project.scripts]` block: `cortex = "cortex_command.cli:main"` (colon-syntax per PEP 621).
  - `[tool.hatch.build.targets.wheel]` block: `packages = ["cortex_command"]`. Do NOT add `exclude = [...]` or `only-include = [...]` — hatchling's default `default_global_exclude` is `["*.py[cdo]", "/dist"]` so prompts/ and templates/ ship naturally (spec §Technical Constraints).
  - `[tool.uv] package = false` MUST NOT be set — editable install of the project into `.venv` via `uv sync` resolves to the same physical source tree as `PYTHONPATH=$REPO_ROOT`, so coexistence is harmless (spec §Edge Cases — `uv sync` behavior change).
  - Commit: "Add build-system, project.scripts, and hatch wheel config".
- **Verification**:
  - `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['build-system']['build-backend']=='hatchling.build'; assert any(r.startswith('hatchling>=') for r in d['build-system']['requires'])"; echo "exit=$?"` — pass if `exit=0`.
  - `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['project']['scripts']['cortex']=='cortex_command.cli:main'"; echo "exit=$?"` — pass if `exit=0`.
  - `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['tool']['hatch']['build']['targets']['wheel']['packages']==['cortex_command']"; echo "exit=$?"` — pass if `exit=0`.
  - `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d.get('tool',{}).get('uv',{}).get('package') is not False"; echo "exit=$?"` — pass if `exit=0` (no `[tool.uv] package = false`).
- **Status**: [ ] pending

### Task 11: Create `cortex_command/cli.py` with argparse + 5 stub subcommands
- **Files**: `cortex_command/cli.py` (new)
- **What**: Implement the `main()` entry point that the `cortex` console script invokes. Builds an `argparse.ArgumentParser` with 5 subparsers (`overnight`, `mcp-server`, `setup`, `init`, `upgrade`), each with both `help=` and `description=` strings. Each subparser's handler prints `"not yet implemented: cortex <name>"` to stderr and calls `sys.exit(2)`. Top-level parser has an `epilog=` that documents the `uv run` scoping constraint and the `--force` reinstall requirement.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Module signature: `main(argv: list[str] | None = None) -> int`, dispatched as `main()` from the console script. Use `sys.argv` when `argv is None`. Pattern reference: existing argparse CLI in `cortex_command/common.py` (post Task 2 path, line ~469 pre-rename) and `cortex_command/overnight/batch_runner.py`. Each subparser: `sub = subparsers.add_parser("overnight", help="...", description="...")`; attach `sub.set_defaults(func=<stub_callable>)` where the stub writes to stderr and exits 2. Do NOT import from `cortex_command.overnight` or other subpackages — stubs must NOT invoke subprocesses per spec §Technical Constraints ("No subprocess calls inside stubs"). `help=` and `description=` strings are one-liners the implementer can draft (e.g., for `overnight`: `help="Run the autonomous overnight session"`, `description="Launch or manage the overnight autonomous runner."`). Top-level epilog should mention: (a) `cortex` invokes `uv run` against the user's project (not the tool's venv); (b) adding `[project.scripts]` entries requires `uv tool install -e . --force`; (c) first-time setup requires `uv tool update-shell` once. Commit: "Add cortex CLI entry point with 5 stub subcommands".
- **Verification**:
  - `python3 -m cortex_command.cli --help 2>&1 | grep -cE '(overnight|mcp-server|setup|init|upgrade)'` — pass if output ≥ `5`.
  - `python3 -m cortex_command.cli overnight 2>&1 1>/dev/null | grep -c 'not yet implemented: cortex overnight'` — pass if output = `1`.
  - `python3 -m cortex_command.cli overnight; echo "exit=$?"` — pass if last line = `exit=2`.
  - Same exit-2 + stderr-substring shape for `mcp-server`, `setup`, `init`, `upgrade` (loop in a small shell script or pytest).
  - `python3 -m cortex_command.cli --help 2>&1 | grep -cE 'uv run|--force'` — pass if output ≥ `2` (epilog documents both constraints).
- **Status**: [ ] pending

### Task 12: Add README "Distribution" section
- **Files**: `README.md` (add section) OR `docs/distribution.md` (new file). Plan recommends the README section — spec AC allows either, and README is more discoverable.
- **What**: Document the four constraints surfaced by research: (a) cortex's internal `uv run` operates on the user's project, not the tool's venv; (b) users should NOT `uv tool uninstall uv`; (c) adding or renaming `[project.scripts]` entries requires `uv tool install -e . --force`; (d) `uv tool update-shell` is a one-time PATH setup step after first `uv tool install`.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: README section heading: `## Distribution` or `## Installation`. Each of the four points should be a single sentence, not expanded prose. The section also serves as the canonical reference for the `cortex --help` epilog so keep the wording terse and aligned. Commit: "Document cortex distribution constraints in README".
- **Verification**:
  - `grep -lE 'uv run.*user.*project|tool.*venv' README.md docs/distribution.md 2>/dev/null | head -1 | grep -q .; echo "exit=$?"` — pass if `exit=0` (either file matches).
  - Spot-check for all four points: `grep -cE 'uv run|uv tool uninstall|--force|uv tool update-shell' README.md docs/distribution.md 2>/dev/null | awk -F: '{s+=$2} END {print s}'` — pass if output ≥ `4`.
- **Status**: [ ] pending

### Task 13: Run `just test` and verify full suite passes against renamed packages
- **Files**: none (verification-only)
- **What**: End-to-end validation that the rename + build-system + CLI additions leave the test suite green.
- **Depends on**: [4, 5, 6, 7, 9, 10, 11]
- **Complexity**: simple
- **Context**: `just test` runs pytest with `pythonpath = ["."]` + the four testpaths (now pointed at `cortex_command/...`). Any missed `claude.X` reference (import, `-m` invocation, mock.patch string, runtime docstring) will surface here as collection error, import error, or assertion failure. If failures occur, diagnose against the specific AC greps from Tasks 4–7 and re-run targeted subsets (e.g., `just test cortex_command/pipeline/tests/`) rather than re-doing the rename.
- **Verification**: `just test; echo "exit=$?"` — pass if last line = `exit=0`.
- **Status**: [ ] pending

### Task 14: Build wheel, verify data-file presence, install editable, verify `cortex --help`
- **Files**: none (verification-only; produces `dist/cortex_command-*.whl` as a side effect of `uv build`)
- **What**: Validate Req 2 (wheel + data files) and Req 3 (console entry point resolves) with two commands plus a post-install `cortex --help` check.
- **Depends on**: [10, 11, 12, 13]
- **Complexity**: simple
- **Context**: Wheel content check is a Python one-liner using `zipfile`. The install step (`uv tool install -e . --force`) writes to `~/.local/share/uv/tools/` which is outside the sandbox allow list; the resulting `cortex --help` verification is a developer-shell manual check per spec Req 3 AC (Interactive/session-dependent). The `--force` flag is required because this may be the first install OR a re-install over a previous run; the flag is idempotent.
- **Verification**:
  - `uv build; echo "exit=$?"` — pass if last line = `exit=0`.
  - `python3 -c "import zipfile, glob; z=zipfile.ZipFile(sorted(glob.glob('dist/cortex_command-*.whl'))[-1]); names=z.namelist(); assert any(n.startswith('cortex_command/') for n in names); assert any(n.startswith('cortex_command/overnight/prompts/') and n.endswith('.md') for n in names), 'prompt files missing from wheel'; assert any(n.startswith('cortex_command/dashboard/templates/') for n in names), 'dashboard templates missing from wheel'"; echo "exit=$?"` — pass if `exit=0`.
  - Post-install `cortex --help` resolution is Interactive/session-dependent: `uv tool install -e . --force` writes to `~/.local/share/uv/tools/` outside the sandbox allow list, so the `which cortex` + `cortex --help | grep -cE '(overnight|mcp-server|setup|init|upgrade)' ≥ 5` check is executed manually by the developer in their shell and recorded in the task's exit report.
- **Status**: [ ] pending

## Verification Strategy

End-to-end validation runs in three layers after the feature branch is complete:

1. **Per-task verification** (above): each task has grep-based or command-based ACs that confirm that task's substitution was exhaustive or its artifact landed correctly.
2. **Full test suite** (Task 13): `just test` exercises every Python import and mock.patch path against the renamed tree. A silently-missed `claude.X` reference fails loudly here.
3. **Wheel + install gate** (Task 14): `uv build` proves the build-system declaration is coherent, the wheel inspection proves data files ship, and the manual `uv tool install -e . --force` + `cortex --help` proves the end-to-end developer experience works.

After Task 14 passes, open a PR from `feat/114-cortex-cli-skeleton` to `main` and **squash-merge** to land the five requirements as a single atomic commit on main, per spec §Technical Constraints ("Single-commit / single-PR atomic land"). The feature branch's per-task commits give incremental rollback points during implementation but do not contaminate main's history.

Post-merge smoke: confirm main's next overnight session picks up cleanly by checking that `just overnight-smoke-test` (or equivalent invocation) exits 0 against the post-rename tree. If it fails, the most likely cause is a missed `claude.X` reference in a file extension not covered by the grep pattern; re-run the Req 1 greps against the main branch to locate.

## Veto Surface

- **`claude/tests/` inclusion in the rename scope**: the spec's narrow grep pattern (`claude.(overnight|pipeline|common|dashboard|hooks)`) does not include `tests`, but `claude/tests/_stubs.py` is imported from three test conftests and `claude/tests/` is unambiguously Python module code (not Claude Code config). The plan moves it to `cortex_command/tests/` to honor the Req 1 rationale ("Rename Python modules from `claude/*` to `cortex_command/*`"). If the user prefers to keep `claude/tests/` in place, Task 2 drops one `git mv` and Tasks 4–6 drop the `tests` alternation — but `claude.tests` imports will then need separate handling. Plan recommends the broader move.
- **Squash-merge PR vs. single hand-crafted commit**: spec explicitly allows either ("Single-commit / single-PR atomic land: … in a single commit (or single PR merged as one squash commit)"). Plan uses squash-merge because per-task commits on the feature branch give rollback granularity during implementation. If the user prefers a single hand-crafted commit (no feature branch), Tasks 2–12 stage changes without committing and Task 14 would collapse to one `/commit` invocation — but verification between tasks loses its per-commit rollback point.
- **Live mock.patch count vs. spec estimate**: spec cites 286/28 (mock.patch occurrences / files). The plan verified a live count of ~236/~18 at Plan time. The plan's Task 6 AC is grep-based rather than count-based, so the discrepancy is not a correctness concern, but the spec's historical numbers will be inconsistent with the eventual implementation report.
- **`docs/distribution.md` vs. `README.md` for Req 5**: spec AC allows either; plan recommends the README section (more discoverable; no new file; keeps the CLI epilog and the repo-level doc co-located). Revisit if the README's scope makes a new dedicated file preferable.

## Scope Boundaries

The Non-Requirements in the spec are authoritative. Briefly, this plan does NOT:

- Implement any of the 5 subcommand bodies (deferred to tickets 115, 116, 117, 119; `upgrade` to 118).
- Add `cortex --version` or `cortex doctor` (explicitly deferred per spec §Open Decisions — none).
- Migrate `$REPO_ROOT` / `PYTHONPATH` / `.venv` runner semantics to `uv tool install`-ed semantics (ticket 115).
- Rename files inside `claude/` that are symlinked to `~/.claude/*` (settings.json, Agents.md, rules/, reference/, statusline.sh, shell hooks, cortex-sync-permissions.py).
- Propagate the `claude/settings.json:99` permission-rule rename to users' merged `~/.claude/settings.json` (users re-run `/setup-merge`).
- Add shell completion (no `cortex --install-completion`, no argcomplete hook).
- Update frozen historical artifacts (`lifecycle/*/events.log`, past retros).
- Modify `claude/settings.json`'s `excludedCommands` array to add `uv:*` or `cortex:*` (per spec §Technical Constraints).
