# Plan: Hook-based preprocessing for test/build output

## Overview

Implement a PreToolUse hook that detects test runner commands via configurable regex patterns, wraps them in a subshell-capture pattern with exit-code-conditional filtering, and returns the filtered output via `updatedInput`. The hook script and config file live in `claude/hooks/` and are deployed automatically by the existing `just setup` symlink loop.

## Tasks

### Task 1: Create global pattern config file
- **Files**: `claude/hooks/output-filters.conf`
- **What**: Create the default pattern config with command detection regexes for common test runners, including prefix variations (uv run, python3 -m, path-prefixed invocations). Include a header comment documenting substring matching semantics and the `\b` word-boundary convention.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Each non-comment line is an ERE regex matched as a substring against the full Bash command string via `grep -qE`. Patterns should cover: `npm test`, `npx jest`, `jest`, `pytest`, `python -m pytest`, `python3 -m pytest`, `uv run pytest`, `cargo test`, `go test`, `just test`, `make test`, plus path-prefixed variants like `.venv/bin/pytest` and `./node_modules/.bin/jest`. Use `\b` for word boundaries where needed to reduce false positives (e.g., `\bjest\b` to avoid matching `jesting`).
- **Verification**: `test -f claude/hooks/output-filters.conf` exits 0; `grep -cE '^[^#]' claude/hooks/output-filters.conf` ≥ 10, pass if true.
- **Status**: [x] complete

### Task 2: Create the hook script
- **Files**: `claude/hooks/cortex-output-filter.sh`
- **What**: Create the PreToolUse hook script that reads JSON from stdin, loads patterns from config (project-local merged with global, respecting `# disable-globals`), matches the command against patterns line-by-line, and outputs JSON with `updatedInput` containing the wrapped command. The wrapped command uses the subshell-capture pattern with exit-code-conditional filtering: summary extraction on success, generous failure context on fail, failure-path fallback (tail -20) when no markers match.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: 
  - Stdin JSON shape: `{"tool_name": "Bash", "tool_input": {"command": "...", ...}, ...}`
  - Output JSON shape: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": {"command": "..."}}}`
  - `updatedInput` replaces the entire input object — must include all original fields alongside modified `command`. Parse all fields from `tool_input` via jq and re-emit them.
  - Config loading: check `$CWD/.claude/output-filters.conf` first; if it exists, read it. If first non-comment line is `# disable-globals`, use project patterns only. Otherwise merge with `~/.claude/hooks/output-filters.conf`.
  - Pattern matching: iterate non-comment, non-blank lines; for each line, `echo "$COMMAND" | grep -qE "$PATTERN"` — if grep fails (bad regex, exit 2), skip silently.
  - Wrapped command logic (prose): capture full output in a variable with stderr merged, preserve exit code in a separate variable, count total lines for the suppression note. Branch on exit code: (a) success path — grep for summary markers (`passed`, `failed`, `test result:`, `Tests:`, `ok`), take last matching line; if no match, fall back to tail -5; append suppression note. (b) failure path — grep for failure markers (`FAIL`, `FAILED`, `ERROR`, `error:`, `failures:`, `--- FAIL:`) with -B 2 -A 20 context, cap at head -200; if grep is empty (non-marker failure), fall back to tail -20; append suppression note. Exit with the preserved original exit code.
  - Follow existing hook conventions: `set -euo pipefail`, `INPUT=$(cat)`, jq for JSON parsing/output, `exit 0` always.
  - Must be executable (`chmod +x`).
- **Verification**: `test -x claude/hooks/cortex-output-filter.sh` exits 0, pass if true; `echo '{"tool_name":"Bash","tool_input":{"command":"npm test"}}' | bash claude/hooks/cortex-output-filter.sh | jq -r '.hookSpecificOutput.updatedInput.command'` produces non-null output containing "OUTPUT=", pass if true; `echo '{"tool_name":"Bash","tool_input":{"command":"echo hello"}}' | bash claude/hooks/cortex-output-filter.sh` produces empty stdout (no match), pass if empty; wrapped command preserves exit codes — extract the wrapped command for a matched input, execute it with a test that exits 1, confirm `$?` is 1.
- **Status**: [x] complete

### Task 3: Register hook in settings.json
- **Files**: `claude/settings.json`
- **What**: Add the output-filter hook as a second entry in the PreToolUse Bash matcher's hooks array, after cortex-validate-commit.sh. Use timeout 5.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Current PreToolUse section at line 245 of `claude/settings.json` has one entry with matcher `"Bash"` containing `cortex-validate-commit.sh`. Add the new hook to the same `hooks` array (same matcher entry, second position). JSON structure:
  ```
  {
    "type": "command",
    "command": "~/.claude/hooks/cortex-output-filter.sh",
    "timeout": 5
  }
  ```
- **Verification**: `python3 -c "import json; d=json.load(open('claude/settings.json')); hooks=[h['command'] for entry in d['hooks']['PreToolUse'] if entry.get('matcher')=='Bash' for h in entry['hooks']]; print(hooks)"` shows both `cortex-validate-commit.sh` and `cortex-output-filter.sh` in order, pass if both present and validate-commit is first.
- **Status**: [x] complete

### Task 4: Update agentic-layer documentation
- **Files**: `docs/agentic-layer.md`
- **What**: Add the new hook to the hooks table and update the JSON Output Contract section to document the `updatedInput` capability (which the current docs do not mention). Add the per-project `.claude/output-filters.conf` convention to the docs.
- **Depends on**: [2, 3, 5]
- **Complexity**: simple
- **Context**: The hooks table is at lines ~210-224 of `docs/agentic-layer.md`. Add a row for `cortex-output-filter.sh` with event `PreToolUse (Bash)`, description "Filter test runner output to failures/summary before context entry", scope "Claude only". The JSON Output Contract section at lines 244-260 documents only `permissionDecision: allow|deny` — add `updatedInput` as a documented field. Also add `additionalContext` which is already used by PostToolUse hooks but undocumented for PreToolUse.
- **Verification**: `grep -c 'cortex-output-filter' docs/agentic-layer.md` ≥ 1, pass if true; `grep -c 'updatedInput' docs/agentic-layer.md` ≥ 1, pass if true.
- **Status**: [x] complete

### Task 5: Add hook tests
- **Files**: `tests/test_output_filter.sh`
- **What**: Add shell-based tests for the hook script covering config-level AND runtime behavioral tests. Config tests: (a) matched command produces wrapped output, (b) non-matched command produces no output, (c) missing config degrades gracefully (exit 0, empty stdout), (d) malformed regex in config is skipped silently, (e) project config merge with global, (f) `# disable-globals` directive works. Runtime behavioral tests: (g) exit code preservation — wrapped command returns the original command's exit code (test with a command that exits 1), (h) success-path summary extraction — wrapped command with passing output shows summary line and suppression note, (i) failure-path marker filtering — wrapped command with failing output containing FAIL/ERROR markers shows filtered failure blocks, (j) failure-path fallback — wrapped command with non-zero exit and no markers (e.g., "Segmentation fault") shows last 20 lines via fallback. Tests invoke the hook script directly with crafted JSON stdin and also execute the wrapped command strings to verify runtime behavior.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Existing test patterns in `tests/` — check `tests/test_hooks.sh` or similar for the shell test convention used in this project. Tests should pipe JSON to the hook script via stdin and assert on stdout content and exit code. Use `$TMPDIR` for any temporary config files.
- **Verification**: `bash tests/test_output_filter.sh` exits 0, pass if all assertions pass.
- **Status**: [x] complete

### Task 6: Run setup and end-to-end verification
- **Files**: none (verification only)
- **What**: Run `just setup` to deploy the new hook and config via symlinks. Verify the symlinks exist and the hook is functional in the deployed location.
- **Depends on**: [1, 2, 3, 4, 5]
- **Complexity**: simple
- **Context**: `just setup` handles all symlink deployment. After setup, verify `~/.claude/hooks/cortex-output-filter.sh` and `~/.claude/hooks/output-filters.conf` exist as symlinks pointing to the repo files.
- **Verification**: `test -L ~/.claude/hooks/cortex-output-filter.sh` exits 0, pass if true; `test -L ~/.claude/hooks/output-filters.conf` exits 0, pass if true; `echo '{"tool_name":"Bash","tool_input":{"command":"pytest"}}' | bash ~/.claude/hooks/cortex-output-filter.sh | jq -r '.hookSpecificOutput.updatedInput.command'` produces non-null output, pass if non-null.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification after all tasks:
1. `just setup` completes without error
2. Symlinks exist at `~/.claude/hooks/cortex-output-filter.sh` and `~/.claude/hooks/output-filters.conf`
3. `bash tests/test_output_filter.sh` passes all assertions
4. Settings.json validation: `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0 (valid JSON)
5. Hook chain order: validate-commit before output-filter in the PreToolUse Bash array
6. Interactive session test: run a test command (e.g., `just test`) in a Claude Code session and observe filtered output with "(output filtered" suppression note
