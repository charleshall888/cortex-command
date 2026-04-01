# Plan: Security & Share-Readiness Audit

## Overview

Harden the repo's code execution paths (shell variable injection, eval, python3 -c interpolation) and improve share-readiness (auto-detect clone path, verify-setup recipe, README tweaks). Security fixes use in-place heredoc conversion for python3 -c calls — no new abstraction layer. Each inline Python call is converted to a single-quoted heredoc that reads values from environment variables, eliminating shell-to-Python string interpolation.

## Tasks

### Task 1: Fix shell variable injection in scan-lifecycle.sh
- **Files**: `hooks/scan-lifecycle.sh`
- **What**: Quote SESSION_ID in the export statement to prevent metacharacter expansion when the env file is sourced.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Line 10 currently reads `echo "export LIFECYCLE_SESSION_ID=$SESSION_ID" >> "$CLAUDE_ENV_FILE"`. SESSION_ID is a UUID from jq extraction at line 8. Change to single-quote wrapping: `echo "export LIFECYCLE_SESSION_ID='$SESSION_ID'" >> "$CLAUDE_ENV_FILE"`.
- **Verification**: Read the modified line. Confirm SESSION_ID is wrapped in single quotes inside the export statement.
- **Status**: [x] done

### Task 2: Replace eval with bash -c in runner.sh
- **Files**: `claude/overnight/runner.sh`
- **What**: Replace the `eval "$TEST_COMMAND"` call in the integration gate block with `bash -c "$TEST_COMMAND"`. This is a code style improvement (not a significant security fix) — both interpret the string as shell code, but `bash -c` avoids eval's double-expansion in the same shell.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Search for `eval "$TEST_COMMAND"` in the integration gate section. Replace with `bash -c "$TEST_COMMAND"`. Add `echo "Running integration gate: $TEST_COMMAND" >&2` before the subshell for logging.
- **Verification**: Grep for `eval.*TEST_COMMAND` in runner.sh — zero matches. Confirm the integration gate block structure is intact.
- **Status**: [x] done

### Task 3: Fix shell=True in merge.py
- **Files**: `claude/pipeline/merge.py`
- **What**: Replace `subprocess.run(test_command, shell=True, ...)` with `subprocess.run(["sh", "-c", test_command], ...)` for consistency.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `run_tests()` function in merge.py. The `subprocess.run()` call uses `shell=True` with `test_command` as a bare string. Change to array form `["sh", "-c", test_command]` and remove `shell=True`. Preserve the existing guard for empty/None test_command.
- **Verification**: Grep for `shell=True` in `claude/pipeline/merge.py` — zero matches. Run `just test` to confirm existing tests pass.
- **Status**: [x] done

### Task 4: Convert runner.sh python3 -c calls to heredoc + env vars (state reads)
- **Files**: `claude/overnight/runner.sh`
- **What**: Convert all `python3 -c` calls that read from STATE_PATH to use single-quoted heredocs with env var passing. The pattern change: from `RESULT=$(python3 -c "import json; state = json.load(open('$STATE_PATH')); print(state['key'])")` to `RESULT=$(STATE_PATH="$STATE_PATH" python3 <<'PYEOF'\nimport json, os\nstate = json.load(open(os.environ['STATE_PATH']))\nprint(state['key'])\nPYEOF\n)`. Skip calls that already use env vars correctly (e.g., the log_event helper).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Search for `open('$STATE_PATH')` and `open('$` patterns in runner.sh. These are the state-reading calls. Each one interpolates the file path into a Python string literal. Convert each to: (a) prefix the `python3` invocation with env var assignments (`STATE_PATH="$STATE_PATH"`), (b) use a heredoc with single-quoted delimiter (`<<'PYEOF'`) so the shell does NOT interpolate inside the Python code, (c) replace `open('$STATE_PATH')` with `open(os.environ['STATE_PATH'])` in the Python body. Some calls also interpolate `$FEATURE` or other variables into JSON field lookups — pass those as env vars too.
- **Verification**: Multiline grep for `open\('\\$` in runner.sh — zero matches. Grep for `'\\$STATE_PATH'` inside python3 -c blocks — zero matches.
- **Status**: [x] done

### Task 5: Convert runner.sh python3 -c calls to heredoc + env vars (writes, PR URLs, remaining)
- **Files**: `claude/overnight/runner.sh`
- **What**: Convert the remaining unsafe `python3 -c` calls — active-session pointer writes, state transitions, report generation, PR URL handling, integration branch iteration, and any other calls that interpolate shell variables into Python string literals. Same pattern as Task 4: heredoc + env vars.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Search for patterns like `'$REPO_PATH'`, `'$PR_URL'`, `'$EVENTS_PATH'`, `'$SESSION_ID'`, `'$TARGET_PROJECT_ROOT'`, `'$HOME_PROJECT_ROOT'` inside python3 blocks. These are the remaining injection points. Active-session writes (4 copies of a read-modify-write-via-tempfile pattern) should each be converted in place. PR URL handling embeds `$REPO_PATH` and `$PR_URL` in Python dict literals. Also check for any `sed` substitutions that embed file paths (see Task 6). Exclude calls that already pass data exclusively via env vars (e.g., the log_event body at the `log_event` function which reads from `os.environ`).
- **Verification**: Grep multiline for `'\$[A-Z_]+_PATH'` and `'\$[A-Z_]+_URL'` inside python3 blocks — zero matches. All python3 heredoc blocks should use `os.environ[]` for variable access.
- **Status**: [x] done

### Task 6: Fix fill_prompt sed injection and log_event ast.literal_eval
- **Files**: `claude/overnight/runner.sh`
- **What**: Two targeted fixes: (a) The `fill_prompt` function uses `sed -e "s|{state_path}|$STATE_PATH|g"` with `|` as delimiter — if any path contains `|`, the substitution breaks. Switch to a Python-based template fill or use a delimiter unlikely in paths (e.g., ASCII SOH `\x01`). (b) The `log_event` function's callers pass `LOG_DETAILS` as Python dict syntax (`"{'session_id': '$SESSION_ID', ...}"`). The function uses `ast.literal_eval` to parse it. Switch to JSON format — callers pass `'{"session_id": "'"$SESSION_ID"'", ...}'` and the function uses `json.loads` instead of `ast.literal_eval`. This is more robust and doesn't require callers to know Python literal syntax.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Search for `fill_prompt` function definition and its `sed` calls. Search for `ast.literal_eval` in the log_event function body. For fill_prompt: all callers that pass file paths need to be checked — ensure the new delimiter doesn't appear in their values. For log_event: find all callers that set `LOG_DETAILS` and convert from Python dict syntax to JSON. The callers are: the stall_timeout event, the orchestrator_failed event, and potentially others. Note: `$SESSION_ID` is a UUID (safe for JSON), `$age_secs` and `$ROUND` are integers.
- **Verification**: Grep for `ast.literal_eval` in runner.sh — zero matches. Grep for `sed.*\$STATE_PATH` in fill_prompt — the delimiter should not be `|`. All LOG_DETAILS values should be valid JSON strings.
- **Status**: [x] done

### Task 7: Auto-detect clone path in just setup
- **Files**: `justfile`
- **What**: Add path auto-detection to the `deploy-config` recipe. Write a `~/.claude/settings.local.json` file that overrides the `sandbox.filesystem.allowWrite` array with the correct path derived from the clone location. Must merge with any existing settings.local.json content.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `deploy-config` recipe symlinks settings.json. The tracked `allowWrite` path is `~/cortex-command/lifecycle/sessions/`. Claude Code shallow-merges `settings.local.json` over `settings.json` at the top-level key level. Merge strategy: if `~/.claude/settings.local.json` exists, read it with `jq`, deep-set `.sandbox.filesystem.allowWrite` to `["$(pwd)/lifecycle/sessions/"]`, and write back. If it doesn't exist, create it with just the sandbox override. Use `jq` for JSON manipulation (already available as a dependency). Handle paths with spaces by quoting.
- **Verification**: Run `just deploy-config` and read `~/.claude/settings.local.json` — should contain the correct `allowWrite` path. Run it again — result should be identical (idempotent). `git status` should show no changes to `claude/settings.json`.
- **Status**: [x] done

### Task 8: Print CORTEX_COMMAND_ROOT in setup
- **Files**: `justfile`
- **What**: Add a final message to the `setup` recipe that prints the `export CORTEX_COMMAND_ROOT="..."` line with the correct path.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: The `setup` recipe runs sub-recipes sequentially. After the last step, add echo lines that print: the export line with the correct path, a note about adding it to shell config, and a suggestion to run `just verify-setup`.
- **Verification**: Read the modified setup recipe and confirm the echo block is present with `$(pwd)` or equivalent for path.
- **Status**: [x] done

### Task 9: Add just verify-setup recipe
- **Files**: `justfile`
- **What**: Create a `verify-setup` recipe that checks: (a) all symlinks valid via `just check-symlinks`, (b) Python 3.12+ available, (c) uv available, (d) claude CLI available, (e) CORTEX_COMMAND_ROOT set and points to this repo. Tests are not run by default (heavyweight) — add a separate `verify-setup-full` recipe that also runs `just test`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The existing `check-symlinks` recipe validates symlink integrity. The new recipe calls it first, then adds checks for each prerequisite. Each check prints a pass/fail indicator and actionable error message. Python version check: `python3 -c "import sys; assert sys.version_info >= (3, 12)"`. uv check: `command -v uv`. claude check: `command -v claude`. CORTEX_COMMAND_ROOT check: test that the env var is set and equals `$(pwd)`.
- **Verification**: Run `just verify-setup` — should pass all checks on current machine. Temporarily unset CORTEX_COMMAND_ROOT and re-run — should report the specific failure with remediation.
- **Status**: [x] done

### Task 10: README cross-platform note
- **Files**: `README.md`
- **What**: Add a brief note after the Prerequisites section directing Linux/Windows users to `docs/setup.md`.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: Current README assumes macOS (brew commands, zsh references). Add a 1-2 line note: "These instructions target macOS. For Linux or Windows setup, see [`docs/setup.md`](docs/setup.md)."
- **Verification**: Read the modified README. Confirm the note appears before Quick Start and links correctly.
- **Status**: [x] done

## Verification Strategy

1. Run `just test` — all existing tests pass (no regressions).
2. Run `just verify-setup` — new recipe passes on current machine.
3. Multiline grep runner.sh for `open\('\$` or `'\$[A-Z_]` inside python3 blocks — zero matches with shell variable interpolation inside Python strings.
4. Grep for `eval.*TEST_COMMAND` in runner.sh — zero matches.
5. Grep for `shell=True` in merge.py — zero matches.
6. Grep for `ast.literal_eval` in runner.sh — zero matches.
7. Read scan-lifecycle.sh line 10 — SESSION_ID is quoted.
8. Run `just deploy-config` — `settings.local.json` contains correct path, `settings.json` unchanged.
