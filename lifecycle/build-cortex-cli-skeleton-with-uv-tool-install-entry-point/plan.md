# Plan: build-cortex-cli-skeleton-with-uv-tool-install-entry-point

## Overview

Rename every Python module under `claude/` (except standalone hook scripts) to a new top-level `cortex_command/` package, then add `[build-system]`, `[project.scripts]`, and hatchling wheel config to `pyproject.toml` plus an argparse-based `cortex_command/cli.py` with 5 stderr/exit-2 stubs. All five spec requirements are implemented on a feature branch with per-task commits for rollback granularity, then squash-merged into main at PR time. `claude/` directory survives for non-Python Claude Code config (settings.json, Agents.md, rules/, reference/, statusline.sh, hook scripts).

The spec's atomic-land MUST is protected by two enforcement points, both concrete: (1) **serialization of the implementation window** — Task 1 verifies and requires that no overnight runner, no scheduled tmux launch, and no parallel agent session is running while Tasks 2–14 execute, so no live process ever observes an intermediate tree state (which was the spec's runtime concern in §Technical Constraints); (2) **squash-merge at PR time** — the single PR lands on main as one commit, keeping main's `git bisect` history clean. Per-task commits on the feature branch are throwaway rollback checkpoints that never enter main's history.

## Tasks

### Task 1: Pre-flight — binary-name collision check, session pause, branch creation
- **Files**: none (read-only checks + git branch)
- **What**: Verify `cortex` binary name is unmapped on the developer PATH and Homebrew, confirm no in-flight overnight session is using the tree, disable the scheduled-session window, and create the feature branch.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run `which cortex` (expect exit 1 / no output); run `brew search cortex` and scan for entries on PATH-earlier taps; escalate to the user if a collision exists on a PATH-earlier binary. For session check, use patterns that actually match the running process tree: `pgrep -f 'overnight/runner\.sh'` catches the outer runner; `pgrep -f 'python3 -m (claude|cortex_command)\.(overnight|pipeline|dashboard)'` catches its Python subprocesses; `tmux ls 2>/dev/null | grep -E 'overnight-(start|schedule)'` catches the tmux-hosted scheduler (per `bin/overnight-schedule:173` — ticket 112 launchagent migration is parked, so launchd is NOT the scheduler on this machine). If any match is found, stop the session by killing the tmux window (`tmux kill-session -t <name>`) or the runner PID; there is no `bin/overnight-stop` binary. Also cancel any pending scheduled launches: inspect `bin/overnight-schedule --status` (or the tmux session list) and if a scheduled window is pending within the implementation window, either advance-kill its tmux session or reschedule it past Task 14. Create the feature branch: `git checkout -b feat/114-cortex-cli-skeleton`. See spec §Technical Constraints (binary-name pre-check, pause overnight sessions) and §Edge Cases (in-flight overnight session).
- **Verification**: Run `which cortex; echo "exit=$?"` — pass if `exit=1` (no binary) OR the located path is on a tap the user has explicitly confirmed is acceptable. Run `pgrep -f 'overnight/runner\.sh'; echo "exit=$?"` and `pgrep -f 'python3 -m (claude\.overnight|cortex_command\.overnight)'; echo "exit=$?"` and `tmux ls 2>/dev/null | grep -cE 'overnight-(start|schedule)'` — pass if all three show no matches (exit=1 for pgrep; count=0 for tmux). Run `git branch --show-current` — pass if output = `feat/114-cortex-cli-skeleton`. Forward-scheduled tmux session cancellation is Interactive/session-dependent: it depends on whether the developer has pre-queued a session and the acceptable reschedule target date.
- **Status**: [x] completed

### Task 2: Move Python subtrees with `git mv` to `cortex_command/`
- **Files**: `claude/common.py` → `cortex_command/common.py`; `claude/overnight/` → `cortex_command/overnight/`; `claude/pipeline/` → `cortex_command/pipeline/`; `claude/dashboard/` → `cortex_command/dashboard/`; `claude/tests/` → `cortex_command/tests/`
- **What**: Preserve git history by using `git mv` (one invocation per subtree) rather than `cp` + `rm`. All co-located non-`.py` files (prompts/, templates/, per-subpackage `tests/`, `__init__.py`) move with their parent.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Five `git mv` invocations. The existing `__init__.py` files at `claude/pipeline/__init__.py`, `claude/dashboard/__init__.py`, `claude/overnight/__init__.py`, `claude/tests/__init__.py` carry over unchanged. Do NOT move `claude/hooks/` — it has no `from claude.*` imports anywhere (verified: `grep -r 'from claude\.hooks\|import claude\.hooks' --include='*.py' .` returns no matches) and `claude/hooks/cortex-sync-permissions.py` is a standalone Claude Code hook per spec §Technical Constraints. Do NOT touch `claude/settings.json`, `claude/Agents.md`, `claude/rules/`, `claude/reference/`, `claude/statusline.sh`, `claude/statusline.ps1`. After the `git mv` block, commit on the feature branch with subject "Move Python subtrees to cortex_command/ package root".
- **Verification**: Run `find . -type d -name cortex_command -path '*/cortex_command' -maxdepth 2 | grep -cx './cortex_command'` — pass if output = `1`. Run `ls claude/settings.json claude/Agents.md claude/statusline.sh && ls claude/rules/ claude/reference/` — pass if both commands exit 0 with non-empty `rules/` and `reference/` listings.
- **Status**: [x] completed (421d0a0)

### Task 3: Create `cortex_command/__init__.py`
- **Files**: `cortex_command/__init__.py` (new, empty)
- **What**: Declare `cortex_command` as a regular (non-namespace) package to avoid the PEP 420 ambiguity the previous `claude/` root had and to give hatchling a deterministic package root.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Empty file. The existing `__init__.py` files inside subpackages (`cortex_command/overnight/__init__.py`, `cortex_command/pipeline/__init__.py`, etc.) are preserved from the `git mv` in Task 2.
- **Verification**: `test -f cortex_command/__init__.py; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [x] completed (0394d91)

### Task 4: Rewrite `from claude.X` / `import claude.X` statements to `cortex_command.X` across `.py`, `.md`, and `.sh` files
- **Files**: All `.py`, `.md`, and `.sh` files containing the matched patterns. Known universe includes: `backlog/update_item.py`, `backlog/create_item.py`, `backlog/generate_index.py`, every Python file inside the now-moved `cortex_command/` tree, every test file referencing it, AND the Markdown files where `from claude.X import Y` appears as prose inside fenced code blocks that get rendered into live orchestrator prompts (verified sites: `cortex_command/overnight/prompts/orchestrator-round.md` lines 37, 182, 191, 242, 311, 324, 325 post-Task-2; `skills/overnight/SKILL.md` lines 50, 67, 95, 159, 187, 200, 204, 249, 274, 276, 397; `skills/critical-review/SKILL.md:255` has `from cortex_command.common import atomic_write`; `skills/morning-review/references/walkthrough.md`). Enumerate up-front with `grep -rlE '(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.md' --include='*.sh' .` and list the output.
- **What**: Substitute `from claude.{overnight|pipeline|common|dashboard|hooks|tests}` → `from cortex_command.{...}` and `import claude.{overnight|pipeline|common|dashboard|hooks|tests}` → `import cortex_command.{...}` in-place. `tests` is added to the subpackage list because `claude/tests/_stubs.py` is imported from multiple test files. Markdown files are included because the orchestrator prompt renders its fenced Python blocks to an agent that executes them — a stale `from claude.X` string is a live runtime error, not documentation rot.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: Substitution pattern: `sed -E -i '' 's/(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)/\1 cortex_command.\2/g' <files>` (macOS; empty `-i ''` argument). This pattern is single-line and works against Python import statements and markdown-embedded Python imports alike — both are one-per-line in practice. For the narrow case of a wrapped import like `from cortex_command.pipeline import (\n    foo,\n    bar\n)`, the `from cortex_command.pipeline` fragment is still on a single line so the pattern matches. Note: `claude.common` is a module (not a subpackage) so `from cortex_command.common import X` is in scope — the pattern covers it. After substitution, run `python3 -c "import cortex_command.common, cortex_command.overnight, cortex_command.pipeline, cortex_command.dashboard"` as a smoke test. Commit on feature branch: "Rewrite Python imports to cortex_command.* across py, md, sh".
- **Verification**: Run `grep -rnE '(from|import) claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.md' --include='*.sh' .; echo "exit=$?"` — pass if `exit=1` (no matches across the expanded extension set). Run `python3 -c "import cortex_command.common, cortex_command.overnight, cortex_command.pipeline, cortex_command.dashboard"; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [x] completed (1fd81d4)

### Task 5: Rewrite `python3 -m claude.X` invocations across `.py`, `.sh`, `.md`, `.toml`, `.txt`, and `justfile`
- **Files**: Everything matched by the grep — known sites: `justfile` (lines 615, 621, 659, 663 for `-m` invocations; 655 uvicorn is Task 7 scope), `hooks/cortex-scan-lifecycle.sh:379` (`python3 -m cortex_command.pipeline.metrics`), `docs/overnight-operations.md` (multiple `-m` refs in commands), various backlog markdown files with `-m claude.X` invocation examples, and any `python3 -m claude.*` in the moved `cortex_command/overnight/*` shell scripts. Enumerate with `grep -rlE 'python3 -m claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' .`. Note: bare-prose `claude.X` in `skills/overnight/SKILL.md` and `cortex_command/overnight/prompts/orchestrator-round.md` is covered by Task 4's expanded `.md` scope and Task 8's full-file audit, not this task.
- **What**: Substitute `python3 -m claude.{subpkg}` → `python3 -m cortex_command.{subpkg}` in place.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: Same sed pattern as Task 4, scoped to the broader file extensions. Task 4 (import statements, including `.md` prose imports) ran first so that the import graph is valid before prose and docs follow. Commit: "Rewrite -m claude invocations across shell, markdown, and config".
- **Verification**: Run `grep -rnE 'python3 -m claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' .; echo "exit=$?"` — pass if `exit=1`.
- **Status**: [ ] pending

### Task 6: Rewrite `unittest.mock.patch("claude.X.Y")` strings across test files using a multi-line-aware Python helper
- **Files**: Every `.py` file matched by `grep -rlE 'unittest\.mock\.patch|\bpatch\s*\(' --include='*.py' . | xargs grep -l "claude\.\(overnight\|pipeline\|common\|dashboard\|hooks\|tests\)"`. Live count against the current tree: ~236 single-line matches across ~18 files (verified during Plan phase). ADDITIONAL scope — multi-line wrapped `patch(\n    "claude.X.Y",\n    ...)` idioms pervasive in `claude/pipeline/tests/test_merge_recovery.py` (lines 97-103, 113-119, 129-135, 177-188, 221-232) and `claude/pipeline/tests/test_merge_ci.py` (lines 45-50). A line-scoped sed misses these; count pre-implementation with `python3 -c "import re, pathlib; p=re.compile(r'patch\s*\(\s*([\"\\'])claude\.', re.MULTILINE|re.DOTALL); print(sum(len(p.findall(f.read_text())) for f in pathlib.Path('.').rglob('*.py')))"`.
- **What**: Substitute every occurrence of `patch("claude.{subpkg}...")` / `patch('claude.{subpkg}...')` → `patch("cortex_command.{subpkg}...")` / `patch('cortex_command.{subpkg}...')`, INCLUDING multi-line invocations where the opening quote may be on a different line than `patch(`. Also handles `patch.object` and `patch.dict` if any callsite uses those with dotted-path strings.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**: Do NOT use line-scoped sed here — line-scoped tools (`sed -i '' -e "s/.../.../g"`, `grep -E ...`) cannot match patterns that span newlines, and the spec §Edge Cases note on 286 occurrences is a significant undercount against the true multi-line surface. Use a Python helper per file:

  ```
  # Pattern reference (not code to copy — illustrative of the shape):
  # re.compile(r'(patch(?:\.object|\.dict)?\s*\(\s*)(["\'])claude\.(overnight|pipeline|common|dashboard|hooks|tests)',
  #            re.MULTILINE | re.DOTALL)
  ```

  The `re.DOTALL` + `re.MULTILINE` combination consumes newlines inside the `\s*` gap between `patch(` and the opening quote. Apply with `re.sub` to each file's contents, write back atomically via the repo's `claude.common.atomic_write` (or `tempfile.NamedTemporaryFile` + `os.replace` if running pre-Task-4 on the old import path). Alternatively use `perl -0777 -pe 's/.../.../gs'` per file, which slurps the whole file and treats `.` as matching newlines. Commit: "Rewrite mock.patch strings to cortex_command namespace (multi-line aware)".
- **Verification**: Use a multi-line-aware grep by piping through `tr`-delete-newlines or by using `pcregrep -M` or by a Python one-liner: `python3 -c "import re, pathlib; p=re.compile(r'patch(?:\.object|\.dict)?\s*\(\s*[\"\\']claude\.(overnight|pipeline|common|dashboard|hooks|tests)', re.MULTILINE|re.DOTALL); hits=[(str(f), len(p.findall(f.read_text()))) for f in pathlib.Path('.').rglob('*.py') if p.search(f.read_text())]; print(hits); import sys; sys.exit(1 if hits else 0)"` — pass if `exit=0` (empty `hits` list). A line-scoped grep is NOT acceptable as the sole check for this task because it systematically undercounts multi-line idioms.
- **Status**: [ ] pending

### Task 7: Update non-module runtime-string references — uvicorn, settings.json, docstrings, AND slash-separated directory paths
- **Files**: Four categories:
  - (a) **uvicorn colon-syntax**: `justfile` line 655.
  - (b) **`claude/settings.json` permission allow rule** (line ~99; file stays at original path per spec, contents change).
  - (c) **Python docstrings, argparse `prog=` / `usage=` strings, Sphinx roles** containing `claude.{subpkg}` as prose: at minimum `cortex_command/pipeline/metrics.py:~1026` (`prog="python3 -m cortex_command.pipeline.metrics"`), `cortex_command/overnight/auth.py:~322` (`prog="python3 -m cortex_command.overnight.auth"`), `cortex_command/common.py:~456/464/474` (three `Usage: python3 -m cortex_command.common …` stderr messages), `cortex_command/dashboard/data.py:~286` (double-backtick Sphinx `` ``claude.pipeline.metrics.parse_events()`` ``), `cortex_command/overnight/batch_runner.py:~3` (`` :mod:`claude.overnight.orchestrator` ``). Enumerate any remaining with `grep -rnE 'claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .` post Tasks 4–6 and rewrite every match that is not a test-fixture literal.
  - (d) **Slash-separated directory-path literals**: `bin/overnight-start:16` (`RUNNER="$REPO_ROOT/claude/overnight/runner.sh"` → `$REPO_ROOT/cortex_command/overnight/runner.sh`), `bin/git-sync-rebase.sh:15` (sync-allowlist path), `justfile` lines that reference `claude/dashboard/.pid` / `claude/overnight/` / `claude/dashboard/` / `claude/pipeline/` as filesystem paths (not module dotted paths), `cortex_command/overnight/runner.sh:~68` (`PROMPT_TEMPLATE="$REPO_ROOT/claude/overnight/prompts/orchestrator-round.md"`), `README.md` lines ~161-162 (directory table). Enumerate with `grep -rnE 'claude/(overnight|pipeline|common|dashboard|hooks|tests)/' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' .`.
- **What**: Substitute (a) `uv run uvicorn claude.dashboard.app:app` → `uv run uvicorn cortex_command.dashboard.app:app`. (b) `"Bash(python3 -m claude.*)"` → `"Bash(python3 -m cortex_command.*)"`. (c) `claude.{subpkg}` → `cortex_command.{subpkg}` in prose docstrings/`prog=`/`usage=`/Sphinx roles. (d) `claude/{subpkg}/` → `cortex_command/{subpkg}/` in every slash-path literal enumerated, EXCEPT paths that refer to non-Python `claude/` config that survives (`claude/settings.json`, `claude/Agents.md`, `claude/rules/`, `claude/reference/`, `claude/statusline.sh`, `claude/hooks/`) — those keep their existing slash paths.
- **Depends on**: [6]
- **Complexity**: complex
- **Context**: `claude/settings.json` stays at its existing path (spec §Changes to Existing Behavior — FILE stays; CONTENTS change). Validate JSON after editing: `python3 -c "import json; json.loads(open('claude/settings.json').read())"`. For category (d), use a discrimination step: the pattern `claude/(overnight|pipeline|common|dashboard|hooks|tests)/` MUST NOT match `claude/hooks/` (preserved), `claude/rules/` (preserved), `claude/reference/` (preserved) — the enumerated subpackage list intentionally omits those. For category (c), Python docstrings/`prog=` strings can be rewritten with the same sed as earlier tasks scoped to `.py` files (the earlier grep at line 4's `--include='*.py'` covers them, but Task 4's pattern requires `(from|import)` prefix, so docstrings survived). Apply `sed -E -i '' 's/claude\.(overnight|pipeline|common|dashboard|hooks|tests)/cortex_command.\1/g' <matched files>` scoped to `.py` only, then manually audit anything Task 4 would have touched if the prefix pattern had been loose. Commit: "Rewrite non-module runtime-string claude references (uvicorn, settings, docstrings, slash paths)".
- **Verification**: Run `grep -rnE 'uvicorn claude\.' --include='*.py' --include='*.sh' --include='*.md' --include='justfile' --include='*.toml' .; echo "exit=$?"` — pass if `exit=1`. Run `grep -c 'Bash(python3 -m claude\.' claude/settings.json` — pass if output = `0`. Run `grep -c 'Bash(python3 -m cortex_command\.' claude/settings.json` — pass if output ≥ `1`. Run `python3 -c "import json; json.loads(open('claude/settings.json').read())"; echo "exit=$?"` — pass if `exit=0`. Run `grep -rnE 'claude\.(overnight|pipeline|common|dashboard|hooks|tests)' --include='*.py' .; echo "exit=$?"` — pass if `exit=1` (no residual dotted prose refs in Python sources). Run `grep -rnE 'claude/(overnight|pipeline|common|dashboard|tests)/' --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='justfile' --include='*.toml' --include='*.txt' . | grep -vE 'claude/settings\.json|claude/Agents\.md|claude/rules/|claude/reference/|claude/statusline|claude/hooks/(?!overnight|pipeline)'; echo "exit=$?"` — pass if output is empty (no residual slash-path refs to moved subtrees).
- **Status**: [ ] pending

### Task 8: Full-file audit and semantic rewrite of `skills/overnight/SKILL.md`
- **Files**: `skills/overnight/SKILL.md`
- **What**: Two-part rewrite of the SKILL.md file: (1) mechanical substitution of every remaining `claude.{subpkg}` token that survived the earlier sed cascade (prose references at lines ~50, 67, 95, 159, 187, 200, 204, 249, 274, 276, 397 — any bare `claude.overnight.X` or `claude.pipeline.X` text that wasn't covered by Task 4's `from/import` pattern or Task 5's `-m` prefix pattern); (2) semantic rewrite of the paragraph at line 46 (and any adjacent paragraphs it references) where the current text asserts `claude.overnight.*` modules "are not installed globally" — this premise is invalidated by the rename + `uv tool install`.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: Order the two parts: (1) mechanical substitution first (a `sed -E -i '' 's/claude\.(overnight|pipeline|common|dashboard|hooks|tests)/cortex_command.\1/g' skills/overnight/SKILL.md` is safe since Tasks 4 and 5 already ran — any residual match IS bare prose), (2) then semantic rewrite of the line-46 paragraph's meaning. Part 1 is a pure token substitution; part 2 is a paragraph-level rewrite. Part 1's sed is needed because the per-task AC for this task requires `grep -c 'claude\.overnight' SKILL.md = 0`, which a paragraph-only rewrite cannot satisfy. Commit: "Audit skills/overnight/SKILL.md and rewrite post-CLI install paragraph".
- **Verification**: Run `grep -c 'cortex_command' skills/overnight/SKILL.md` — pass if output ≥ `1` (rename landed). Run `grep -c 'claude\.overnight\|claude\.pipeline\|claude\.common\|claude\.dashboard' skills/overnight/SKILL.md` — pass if output = `0` (no residual dotted references). Run `grep -c 'not installed globally' skills/overnight/SKILL.md` — pass if output = `0` (invalidated claim removed).
- **Status**: [ ] pending

### Task 9: Update `pyproject.toml` testpaths to `cortex_command/...`
- **Files**: `pyproject.toml`
- **What**: Change `[tool.pytest.ini_options].testpaths = ["tests", "claude/dashboard/tests", "claude/pipeline/tests", "claude/overnight/tests"]` to `["tests", "cortex_command/dashboard/tests", "cortex_command/pipeline/tests", "cortex_command/overnight/tests"]`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Single-line edit in existing `[tool.pytest.ini_options]` block. The `pythonpath = ["."]` line stays — tests still need the repo root on sys.path for imports to resolve during pytest collection. Commit: "Update pyproject testpaths to cortex_command subpackages".
- **Verification**: Run `python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml').read()); assert d['tool']['pytest']['ini_options']['testpaths']==['tests','cortex_command/dashboard/tests','cortex_command/pipeline/tests','cortex_command/overnight/tests']"; echo "exit=$?"` — pass if `exit=0`.
- **Status**: [x] completed (1d5abd1)

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
- **Status**: [x] completed (30781cb)

### Task 11: Create `cortex_command/cli.py` with argparse + 5 stub subcommands
- **Files**: `cortex_command/cli.py` (new)
- **What**: Implement the `main()` entry point that the `cortex` console script invokes. Builds an `argparse.ArgumentParser` with 5 subparsers (`overnight`, `mcp-server`, `setup`, `init`, `upgrade`), each with both `help=` and `description=` strings. Each subparser's handler prints `"not yet implemented: cortex <name>"` to stderr and calls `sys.exit(2)`. Top-level parser has an `epilog=` that documents the `uv run` scoping constraint and the `--force` reinstall requirement.
- **Depends on**: [3, 7]
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

### Task 14: Clean `dist/`, build wheel, verify data-file presence, install editable, verify `cortex --help`
- **Files**: none (verification-only; produces `dist/cortex_command-*.whl` as a side effect of `uv build`)
- **What**: Validate Req 2 (wheel + data files) and Req 3 (console entry point resolves) with three steps: clean any prior build output, build fresh, then install and smoke-test.
- **Depends on**: [10, 11, 12, 13]
- **Complexity**: simple
- **Context**: Clean step first — `rm -rf dist/` — so that `sorted(glob.glob('dist/cortex_command-*.whl'))[-1]` cannot accidentally select a stale wheel from a prior experiment (the version stays at `0.1.0` across this ticket; the sort alone is not sufficient protection). Wheel content check is a Python one-liner using `zipfile`. The install step (`uv tool install -e . --force`) writes to `~/.local/share/uv/tools/` which is outside the sandbox allow list; the resulting `cortex --help` verification is a developer-shell manual check per spec Req 3 AC (Interactive/session-dependent). The `--force` flag is required because this may be the first install OR a re-install over a previous run; the flag is idempotent.
- **Verification**:
  - `rm -rf dist/; uv build; echo "exit=$?"` — pass if last line = `exit=0`.
  - `python3 -c "import zipfile, glob; whls=sorted(glob.glob('dist/cortex_command-*.whl')); assert len(whls)==1, f'expected exactly one wheel, got {len(whls)}'; z=zipfile.ZipFile(whls[-1]); names=z.namelist(); assert any(n.startswith('cortex_command/') for n in names); assert any(n.startswith('cortex_command/overnight/prompts/') and n.endswith('.md') for n in names), 'prompt files missing from wheel'; assert any(n.startswith('cortex_command/dashboard/templates/') for n in names), 'dashboard templates missing from wheel'"; echo "exit=$?"` — pass if `exit=0`.
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
- **Squash-merge PR vs. single hand-crafted commit**: spec explicitly allows either ("Single-commit / single-PR atomic land: … in a single commit (or single PR merged as one squash commit)"). Plan uses squash-merge because per-task commits on the feature branch give rollback granularity during implementation. The runtime concern the spec's atomic-land MUST protects against (an overnight session observing intermediate state) is handled by Task 1's serialization guard, not by the merge strategy — so "squash-merge at PR time" here is about keeping main's bisect history clean, with developer-discipline enforcement (one click, once). If the user later decides even one-click discipline is too risky, the alternative is to configure GitHub branch-protection to disable merge-commit and rebase-merge repo-wide (a one-time settings change) — not captured as a plan task since it's out-of-scope repo config.
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
