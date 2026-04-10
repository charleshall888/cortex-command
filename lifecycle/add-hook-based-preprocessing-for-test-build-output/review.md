# Review: Hook-based preprocessing for test/build output

**Cycle**: 1
**Reviewer**: Claude (automated spec compliance review)

---

## Stage 1: Spec Compliance

### R1: PreToolUse hook intercepts test commands
**Rating**: PASS

- `grep -c 'cortex-output-filter' claude/settings.json` returns 1
- `grep -c 'PreToolUse' claude/settings.json` returns 1
- Hook is registered in the Bash matcher chain under PreToolUse
- Non-matching commands (e.g., `ls -la`) produce no output and exit 0
- Matching commands (e.g., `npm test`) produce JSON with `updatedInput`

### R2: Exit-code-conditional filtering
**Rating**: PASS

- Wrapped command captures output via `$(eval ... 2>&1)` subshell-capture pattern
- Success path (exit 0): filters to summary line + suppression note
- Failure path (exit != 0): extracts failure blocks with `grep -B 2 -A 20` context, capped at `head -200`
- Failure-path fallback: when exit != 0 and no failure markers match, falls back to `tail -20` of output + suppression note
- Runtime tests (g, h, i, j) all pass, confirming behavioral correctness

### R3: Exit code preservation
**Rating**: PASS

- Hook itself always exits 0 (confirmed: `echo '{"tool_name":"Bash","tool_input":{"command":"exit 1"}}' | bash cortex-output-filter.sh; echo $?` returns 0)
- Wrapped command preserves original exit code via `EXIT_CODE=$?` capture and `exit $EXIT_CODE` on failure path
- Success path does not explicitly exit, relying on shell default exit 0 (correct since exit code was 0)
- Runtime test (g) confirms a command exiting 1 produces exit code 1 from the wrapped command
- Runtime test (j) confirms exit code 139 is preserved through the wrapped command

### R4: Global default pattern file
**Rating**: PASS

- `output-filters.conf` exists at `claude/hooks/output-filters.conf`
- Contains 12 non-comment lines (spec requires >= 10)
- Covers all required runners: `npm test`, `npx jest`, `jest`, `pytest`, `python -m pytest` (via `python3?`), `uv run pytest`, `cargo test`, `go test`, `just test`, `make test`
- Path-prefixed variants covered: `.venv/bin/pytest`, `./node_modules/.bin/jest`
- Header comment documents substring matching semantics and `\b` convention

### R5: Per-project override (merge mode)
**Rating**: PASS

- Project config at `$CWD/.claude/output-filters.conf` is loaded when present
- Default behavior merges project + global patterns (test e confirms project-only pattern matches after merge)
- `# disable-globals` as first non-blank line suppresses global patterns (test f confirms `npm test` does not match when globals disabled)
- Local patterns still work with `# disable-globals` active (test f2 confirms)

### R6: Hook coexistence
**Rating**: PASS

- In `claude/settings.json`, the PreToolUse Bash matcher has two hooks in order: `cortex-validate-commit.sh` (index 0), `cortex-output-filter.sh` (index 1)
- Validated programmatically: the assertion `hooks.index('cortex-validate-commit') < hooks.index('cortex-output-filter')` holds (using substring matching on full paths)

### R7: Graceful degradation
**Rating**: PASS

- Missing config: `OUTPUT_FILTERS_CONF=/nonexistent` produces exit 0 with empty stdout (confirmed)
- Missing jq: script checks `command -v jq` and exits 0 if missing (line 23-25)
- Malformed regex: line-by-line iteration with `2>/dev/null` on `grep -qE` silently skips bad patterns; test (d) confirms a malformed regex `[invalid(regex` is skipped while valid patterns still match
- Malformed JSON input: jq parsing failures trigger `|| exit 0` fallbacks (lines 28, 33)

### R8: All-pass summary extraction
**Rating**: PASS

- Summary markers grep: `grep -E 'passed|failed|test result:|Tests:|ok'` matches spec-required patterns
- Takes last matching line via `tail -1`
- Falls back to `tail -5` when no summary markers found (verified: 7-line output with no markers shows last 5 lines)
- Always appends `(output filtered -- N lines suppressed)` with actual line count

---

## Stage 2: Code Quality

### Naming conventions
- Hook script: `cortex-output-filter.sh` -- follows `cortex-{purpose}.sh` pattern used by all other hooks in `claude/hooks/`
- Config file: `output-filters.conf` -- no `cortex-` prefix, but this is a data file not a script; reasonable distinction
- JSON field names match Claude Code hook contract exactly (`hookSpecificOutput`, `permissionDecision`, `updatedInput`)
- Test file: `test_output_filter.sh` -- follows existing `tests/test_*.sh` pattern

### Error handling
- `set -euo pipefail` at top, consistent with other hooks
- Every jq call has `|| exit 0` fallback for graceful degradation
- `INPUT=$(cat)` reads stdin once, avoids re-reads
- Pattern matching loop uses `2>/dev/null` on grep to suppress bad-regex errors
- `|| true` on optional reads (project patterns, global patterns) prevents pipeline failures

### Test coverage
- 11 tests covering all 6 config-level behaviors and all 4 runtime behaviors from the plan
- Tests use crafted JSON payloads, not mocks -- they exercise the actual hook script
- Runtime tests extract the wrapped command and execute it, verifying end-to-end filtering behavior
- Temp directory with cleanup trap prevents test artifacts from persisting

### Pattern consistency
- Hook follows the same stdin/stdout JSON contract as `cortex-validate-commit.sh`
- Uses `jq` for JSON parsing/generation, consistent with all other hooks
- `exit 0` always, consistent with project convention (hooks never exit non-zero)
- Config file uses simple line-based format with `#` comments, similar to gitignore patterns
- `updatedInput` preserves all original `tool_input` fields (not just `command`), satisfying the technical constraint
- The `@sh` quoting via jq for shell-safe command embedding is a sound approach for handling special characters

### Minor observations (non-blocking)
- The `ok` summary marker in R8 is broad and could match non-summary lines (e.g., "Looking for tokens"), but the spec explicitly requires it and `tail -1` mitigates noise by selecting only the last match
- The wrapped command is a single long line; readability could improve with line breaks, but this is cosmetic and the single-line format avoids shell quoting issues in JSON

---

## Requirements Drift
**State**: detected
**Findings**:
- The output filter hook introduces a new global behavior (PreToolUse command rewriting for test runners) and a new per-project convention (`.claude/output-filters.conf`) that are not reflected in `requirements/project.md`. The project requirements mention "defense-in-depth for permissions" and hooks generally but do not describe output/context efficiency optimization as a stated goal or architectural pattern.
**Update needed**: requirements/project.md

## Suggested Requirements Update
Add to the "Quality Attributes" section of `requirements/project.md`:

```
- **Context efficiency**: Deterministic preprocessing hooks filter verbose tool output (test runners, build tools) before it enters the context window. Configured via pattern files (`output-filters.conf`) at global and per-project levels. Filtering is substring-based grep, not model judgment — no token cost for the filtering itself.
```

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
