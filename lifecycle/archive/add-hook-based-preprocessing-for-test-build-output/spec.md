# Specification: Hook-based preprocessing for test/build output

## Problem Statement

Test runner output can be thousands of lines, all of which enter Claude's context window untruncated via Bash tool results. This wastes context capacity on dot-progress, per-test timing, and passing test details — information with no diagnostic value. Overnight sessions are especially affected: N features each running test suites multiplies the waste. A deterministic, pre-context filter reduces token consumption without model judgment. The system must be a global framework that any project can extend with project-specific patterns (Godot, Android/Gradle, etc.).

## Requirements

1. **PreToolUse hook intercepts test commands**: A PreToolUse hook registered on `Bash` detects test runner commands by matching the command string against a configurable pattern list using substring matching (`grep -qE`). Non-matching commands pass through unmodified. Acceptance criteria: `grep -c 'cortex-output-filter' ~/.claude/settings.json` ≥ 1, pass if true; `grep -c 'PreToolUse' ~/.claude/settings.json` shows the hook registered in the Bash matcher chain.

2. **Exit-code-conditional filtering**: The hook rewrites matched commands using the subshell-capture pattern. On success (exit 0), output is filtered to the runner's summary line plus a suppression note. On failure (exit != 0), output is filtered to failure blocks with generous context (grep -B 2 -A 20 per failure marker, head -200 total). **Failure-path fallback**: when exit != 0 but the failure grep produces empty output (no markers matched — e.g., segfault, OOM, syntax error), fall back to the last 20 lines of output plus a suppression note. This ensures the agent always receives diagnostic context for failed commands. Acceptance criteria: Interactive/session-dependent — hook behavior is only observable within a Claude Code session where PreToolUse hooks fire. Verify by running a matched test command and confirming the output contains "(output filtered" on pass, or contains failure blocks with surrounding context on fail. For the fallback: a command that exits non-zero with no marker text (e.g., `exit 1` after printing non-marker output) should show the last 20 lines.

3. **Exit code preservation**: The original command's exit code is returned to Claude regardless of filtering. The filter pipe does not corrupt the exit code. Acceptance criteria: `echo '{"tool_name":"Bash","tool_input":{"command":"exit 1"}}' | bash claude/hooks/cortex-output-filter.sh; echo $?` exits 0 (hook itself always exits 0); the `updatedInput.command` in the JSON output, when executed, preserves the original exit code. Testable via: `bash -c 'OUTPUT=$(exit 1 2>&1); EXIT=$?; exit $EXIT'; echo $?` returns 1.

4. **Global default pattern file**: A default pattern config ships at `~/.claude/hooks/output-filters.conf` (deployed via symlink from `claude/hooks/output-filters.conf`). Contains command patterns for common test runners, including prefix variations for common invocation styles. Default patterns must cover: `npm test`, `npx jest`, `jest`, `pytest`, `python -m pytest`, `python3 -m pytest`, `uv run pytest`, `cargo test`, `go test`, `just test`, `make test`. Patterns should also cover path-prefixed invocations (e.g., `.venv/bin/pytest`, `./node_modules/.bin/jest`). Acceptance criteria: `test -f ~/.claude/hooks/output-filters.conf` exits 0; `grep -cE '^[^#]' ~/.claude/hooks/output-filters.conf` ≥ 10, pass if true.

5. **Per-project override (merge mode)**: Projects can place a `.claude/output-filters.conf` file at their project root. By default, project patterns are **merged** with global patterns (project patterns extend the global set). Projects that need full control can include a `# disable-globals` directive as the first non-comment line to suppress global patterns entirely. Acceptance criteria: `echo 'my-custom-test' > /tmp/test-project/.claude/output-filters.conf` then `echo '{"tool_name":"Bash","tool_input":{"command":"my-custom-test"}}' | CWD=/tmp/test-project bash claude/hooks/cortex-output-filter.sh | jq -r '.hookSpecificOutput.updatedInput.command'` produces a wrapped command (not null), pass if non-null. For disable-globals: `printf '# disable-globals\nmy-test' > /tmp/test-project/.claude/output-filters.conf` then matching against a global-only pattern (e.g., `npm test`) should NOT produce a wrapped command.

6. **Hook coexistence**: The new hook is registered after `cortex-validate-commit.sh` in the PreToolUse chain for the `Bash` matcher. If validate-commit denies the command, the output filter hook never runs. Acceptance criteria: in `claude/settings.json`, the output-filter hook entry appears after the validate-commit entry within the same PreToolUse Bash matcher. Verify: `python3 -c "import json; d=json.load(open('claude/settings.json')); hooks=[h['command'] for entry in d['hooks']['PreToolUse'] if entry.get('matcher')=='Bash' for h in entry['hooks']]; assert hooks.index('cortex-validate-commit') < hooks.index('cortex-output-filter')"` — pass if no assertion error. (Exact command names may vary by final path.)

7. **Graceful degradation**: If the hook script encounters an error (missing config file, jq failure, malformed pattern), it exits 0 with no JSON output — the original command runs unmodified. Malformed patterns are isolated: the hook iterates patterns line-by-line (not `grep -f`) so a bad regex on one line does not disable matching for other patterns. Acceptance criteria: `echo '{"tool_name":"Bash","tool_input":{"command":"npm test"}}' | OUTPUT_FILTERS_CONF=/nonexistent bash claude/hooks/cortex-output-filter.sh` exits 0 and produces no JSON output (empty stdout), pass if exit code = 0 and stdout is empty.

8. **All-pass summary extraction**: When exit code is 0 and the failure grep produces empty output, the hook extracts the runner's summary line using a built-in summary pattern (grep for common summary markers: "passed", "failed", "test result:", "Tests:", "ok"). If no summary line is found, falls back to the last 5 lines of output. Always appends "(output filtered — N lines suppressed)". Acceptance criteria: Interactive/session-dependent — the summary extraction runs inside the wrapped command at Claude Code runtime. Unit-testable by executing the wrapped command pattern directly: `OUTPUT=$(echo -e "...\n...\n34 passed, 0 failed" 2>&1); EXIT=0; echo "$OUTPUT" | grep -E 'passed|failed|test result:' | tail -1` produces the summary line, pass if non-empty.

## Non-Requirements

- **Linter/build filtering in v1**: The framework supports any command type via config, but v1 ships with test runner patterns only. Linter and build patterns can be added later via config updates, not code changes.
- **PostToolUse output replacement**: Not viable for standard tools — the API only supports `additionalContext` (additive), not output replacement. The design uses PreToolUse `updatedInput` exclusively.
- **Model-based compression**: No LLM judgment is involved. All filtering is deterministic grep/head/tail.
- **Prompt-level brevity instructions**: Separate epic tickets (050, 052-054). This hook is independent.
- **Interactive command detection**: v1 does not attempt to detect and skip interactive/watch-mode commands (e.g., `vitest --watch`). These are uncommon in automated contexts and the filter would produce degraded but not broken output.
- **Configurable failure markers / summary patterns in v1**: Failure markers and summary patterns are built-in with sensible defaults. Per-project customization of markers is deferred to a future version. The config file contains command detection patterns only.

## Edge Cases

- **No matching command**: Command doesn't match any pattern → hook returns no JSON output → original command runs unmodified.
- **All tests pass, empty grep**: Failure grep returns nothing → hook falls through to summary extraction → shows summary line or last 5 lines with suppression note.
- **Non-marker failure (segfault, OOM, syntax error)**: Exit code != 0 but failure grep returns nothing → failure-path fallback → shows last 20 lines of output with suppression note. Agent always gets diagnostic context.
- **Very large output**: Subshell capture buffers in memory. Extremely large output (>100MB) could cause issues. Mitigated by head -200 on failure output and tail on success — the pipe processes lines incrementally. Accepted trade-off for v1: pipe-based streaming would sacrifice exit code preservation (R3).
- **Compound commands**: `npm test && npm run lint` — the hook wraps the entire command string in the subshell-capture pattern. The exit code reflects the compound command's exit code (the last command's if using `&&`). This is acceptable — the filter applies to the combined output. Note: test-specific failure markers may match lint output; this is a minor false positive that produces slightly over-filtered output, not broken behavior.
- **Already-piped commands**: `npm test | grep something` — wrapping adds another layer. The outer capture sees the already-piped output. Harmless but may produce unexpected filtering. Pattern matching is substring-based, so `npm test | tail` would match `npm test` — the consequence is filtered output from an already-filtered command, which is degraded but not broken.
- **Missing jq**: The hook uses jq to parse stdin and format JSON output. If jq is missing, the hook exits 0 (graceful degradation) and the command runs unmodified.
- **Config file missing**: Both global and project config missing → hook exits 0 silently → no filtering.
- **Malformed regex in config**: A bad pattern on one line does not affect other patterns — the hook matches line-by-line, not with `grep -f`. The malformed line is silently skipped.
- **False positives from substring matching**: A pattern like `jest` matches `grep jest package.json`. The consequence is filtered output from a non-test command — the fallback paths (summary extraction or failure-path tail) ensure output is not lost, just slightly reformatted. Pattern authors can use `\b` word boundaries for precision.

## Changes to Existing Behavior

- [ADDED: PreToolUse hook on Bash] — new hook in the PreToolUse chain that modifies test runner commands before execution. All other Bash commands are unaffected.
- [MODIFIED: PreToolUse Bash chain in settings.json] — adds a second hook entry after cortex-validate-commit.sh. The validate-commit hook is unmodified.
- [ADDED: Global config file] — new file `claude/hooks/output-filters.conf` deployed to `~/.claude/hooks/output-filters.conf` via symlink.
- [ADDED: Per-project config convention] — `.claude/output-filters.conf` as the project-local extension/override path.

## Technical Constraints

- **PreToolUse `updatedInput` replaces the entire input object**: The hook must include all fields from the original input (e.g., `command`, `description`, `timeout`) alongside the modified `command`. Fields not included are dropped.
- **Hook ordering**: PreToolUse hooks within the same matcher run in registration order. If any hook returns `deny`, subsequent hooks are skipped. The output filter must be registered after validate-commit.
- **Symlink deployment**: The hook script and config file live in `claude/hooks/` and are deployed to `~/.claude/hooks/` via the existing `just setup` symlink pattern.
- **Sandbox compatibility**: The hook script is on the sandbox read-allow path (`~/.claude/hooks/`). It does not write to any restricted paths. `$TMPDIR` is available if temporary files are needed, but the subshell-capture approach avoids temp files.
- **Hook timeout**: The hook itself (command detection + JSON output) completes in milliseconds. The timeout in settings.json applies to the hook script execution, not the wrapped command. Set to 5s (consistent with validate-commit).
- **Config file format**: Simple line-based format. Lines starting with `#` are comments. Blank lines are ignored. Each non-comment line is a command detection ERE regex, matched as a **substring** against the full command string via `grep -qE`. Pattern authors use `\b` for word boundaries or `^` for anchoring when needed. The config file should include a header comment documenting the matching semantics.
- **Per-line pattern matching**: The hook iterates patterns line-by-line (not `grep -f`) to isolate malformed regexes. A bad pattern on one line is silently skipped; other patterns continue to match normally.
- **Bash execution context**: Claude Code's Bash tool already runs commands in a pipe context (not a tty). The `$(cmd 2>&1)` subshell does not change tty behavior — test runner output format is the same with or without the wrapper.

## Open Decisions

None — all decisions resolved at spec time.
