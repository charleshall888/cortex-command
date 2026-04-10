# Research: Add hook-based preprocessing for test/build output

## Epic Reference

Part of the Agent Output Efficiency epic (`research/agent-output-efficiency/research.md`). This ticket focuses specifically on approach G (hook-based preprocessing / DR-5) — deterministic filtering of high-volume tool output before tokens enter the context window.

## Codebase Analysis

### Existing Hook Architecture

The project has two categories of hooks deployed via symlinks to `~/.claude/hooks/`:

**PreToolUse hooks** (fire before tool execution):
- `hooks/cortex-validate-commit.sh` — matches `Bash`, validates git commit messages, returns `permissionDecision: allow|deny`

**PostToolUse hooks** (fire after tool execution):
- `claude/hooks/cortex-tool-failure-tracker.sh` — matches `Bash`, tracks failure counts, returns `additionalContext` at threshold
- `claude/hooks/cortex-skill-edit-advisor.sh` — matches `Write|Edit`, runs `just test-skills` after SKILL.md edits, returns `additionalContext`

**Other hooks**: SessionStart (permissions sync, lifecycle scan, GPG setup), SessionEnd (cleanup), Notification (desktop/push alerts, permission audit), WorktreeCreate/Remove (worktree lifecycle).

### Hook Registration Pattern

Hooks are registered in `claude/settings.json` under the `hooks` key, organized by event type. Each entry specifies a `matcher` (tool name regex), `type: "command"`, `command` (path to script), and optional `timeout`. Example structure:

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "~/.claude/hooks/cortex-validate-commit.sh",
          "timeout": 5
        }
      ]
    }
  ]
}
```

Multiple hooks per event type are supported; they run in registration order. PreToolUse hooks that return `deny` stop the chain.

### Hook Input/Output Contract

**Stdin**: JSON object with `tool_name`, `tool_input`, and (for PostToolUse) `tool_response`. For Bash tools: `tool_input.command` contains the shell command string.

**Stdout**: JSON with `hookSpecificOutput` containing event-specific fields. All hooks exit 0; non-zero is treated as unexpected error.

### Files That Will Change

| File | Change |
|------|--------|
| `claude/hooks/cortex-output-filter.sh` (new) | PreToolUse hook script — detects test/lint/build commands, returns `updatedInput` with filter pipe |
| `claude/settings.json` | Register new PreToolUse hook under `Bash` matcher |
| `justfile` | Add deployment recipe for the new hook (symlink to `~/.claude/hooks/`) |

### Integration Points

- **Existing PreToolUse chain**: The new hook must coexist with `cortex-validate-commit.sh` (also matches `Bash`). Order matters — validate-commit should run first (it may deny), then the output filter applies to allowed commands.
- **PostToolUse failure tracker**: `cortex-tool-failure-tracker.sh` reads `tool_response.exit_code`. If the PreToolUse hook wraps commands with filter pipes, `PIPESTATUS` handling must preserve the original command's exit code.
- **Symlink deployment**: Follows existing pattern — script lives in `claude/hooks/`, deployed to `~/.claude/hooks/` via `just setup`.

## Web Research

### Claude Code Hook API: Definitive Capabilities

Official documentation at [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks) confirms:

**PreToolUse `updatedInput`** — Replaces the tool's input parameters before execution. The `updatedInput` object replaces the entire input, so unchanged fields must be included alongside modified ones. Can be combined with `permissionDecision: "allow"` for auto-approval.

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "updatedInput": {
      "command": "modified command here"
    }
  }
}
```

**PostToolUse `additionalContext`** — Appends a string to Claude's context after tool execution. Does NOT replace or filter the tool's output. For standard tools (Bash, Edit, Read, etc.), this is the only output-related capability.

**PostToolUse `updatedMCPToolOutput`** — Replaces MCP tool output only. Not applicable to standard tools.

**Critical finding**: PreToolUse `updatedInput` is the only mechanism that can reduce standard tool output before it enters context. By rewriting the bash command to pipe through a filter, the filtered output is what Claude sees — the unfiltered output never enters the context window.

### Anthropic's Recommended Pattern

From Anthropic's cost documentation (referenced in the backlog item): a PreToolUse hook intercepts test runner commands and appends a filter pipe:

```bash
# Original: npm test
# Modified: npm test 2>&1 | grep -A 5 -E '(FAIL|ERROR|error:)' | head -100
```

This is deterministic, requires no model judgment, and provides guaranteed token reduction.

### Project Documentation Gap

The project's `docs/agentic-layer.md` documents PreToolUse hooks with `permissionDecision: allow|deny` only — it does not mention `updatedInput`. This documentation predates the `updatedInput` capability (added in Claude Code v2.0.10). The documentation should be updated as part of this feature.

## Requirements & Constraints

### From requirements/project.md

- **"Complexity must earn its place by solving a real problem that exists now"** — Hook-based preprocessing solves a concrete problem: test/build output can be thousands of lines, all of which enter context untruncated. The filtering is deterministic and minimal.
- **"File-based state"** — Hooks are stateless shell scripts; no state files needed.
- **"Graceful partial failure"** — If the filter hook fails (non-zero exit), Claude Code treats it as an unexpected error and proceeds without filtering. The original command runs unmodified.

### From requirements/pipeline.md

- **Overnight sessions**: Long-running overnight sessions are most likely to trigger compaction (~95% capacity, retains ~12%). Filtering high-volume output before context entry extends the useful life of the context window.
- **Feature execution**: Each overnight feature runs test suites after implementation. Test output volume multiplied by N features per session makes filtering high-value for overnight.

### From requirements/observability.md

- **Hook timeout**: Existing hooks use 5-10s timeouts. The output filter hook should be fast (command rewriting only, no execution) — 5s timeout is generous.
- **No writes**: The hook only modifies the command string; it does not write to any state files.

### Scope Boundaries

- **In scope**: Bash tool commands that match known test/lint/build patterns
- **Out of scope**: Non-Bash tool output (Read, Grep, etc.), model-based output compression, prompt-level brevity instructions (those are separate epic tickets)

## Tradeoffs & Alternatives

### Approach A: PreToolUse `updatedInput` Command Wrapping

**Description**: A PreToolUse hook on Bash detects test/lint/build commands via pattern matching, then returns `updatedInput` with the command piped through a filter.

**Pros**:
- Only filtered output enters context — maximum token reduction
- Deterministic, no model judgment
- Single hook, no prompt changes needed
- Follows the pattern Anthropic recommends in their cost documentation
- Graceful degradation: if hook exits non-zero, original command runs unmodified

**Cons**:
- Exit code preservation: piping through `grep | head` changes the exit code (grep returns 1 when no matches). Must use `set -o pipefail` or `PIPESTATUS` handling in the wrapped command, or use a subshell wrapper
- Command detection: regex-based pattern matching may miss unusual invocations or false-positive on non-test commands
- Compound commands: `npm test && npm run lint` — the pipe attaches to the whole compound expression via subshell wrapping, which may have unintended effects
- Debug visibility: when a test fails, the developer sees filtered output but may need the full output for diagnosis

### Approach B: PostToolUse `additionalContext` Summary

**Description**: A PostToolUse hook on Bash detects test/lint/build output in `tool_response`, extracts a summary, and returns it as `additionalContext`.

**Pros**:
- No risk of breaking command execution
- Original output preserved for debugging

**Cons**:
- **Does not reduce context** — the original unfiltered output PLUS the summary both enter context
- Doubles token cost rather than reducing it
- Not viable for the stated goal

**Verdict**: Rejected. Does not achieve the goal of reducing context consumption.

### Approach C: Bash Wrapper Scripts via CLAUDE.md

**Description**: Create wrapper scripts (`run-tests`, `run-lint`, etc.) and instruct Claude via CLAUDE.md to use them instead of raw commands.

**Pros**:
- No hook API dependency
- Full control over output formatting

**Cons**:
- Fragile — depends on Claude following CLAUDE.md instructions consistently
- Adds to CLAUDE.md token load (loaded every turn)
- Doesn't help when Claude generates ad-hoc test commands
- Doesn't work for overnight sessions where command choice is model-driven

**Verdict**: Rejected. Unreliable and doesn't cover ad-hoc command generation.

### Approach D: Per-Command Separate Hooks vs. Single Generic Hook

**Per-command**: Register separate PreToolUse hooks for each tool type (test-filter, lint-filter, build-filter), each with different matchers.

**Single generic**: One PreToolUse hook on `Bash` that pattern-matches the command internally and applies the appropriate filter.

**Analysis**: The `matcher` field for PreToolUse only matches on tool name (e.g., `Bash`), not on command content. All test/lint/build commands go through the `Bash` tool. Therefore, per-command separation would require a single matcher anyway, with internal routing. A single generic hook with internal pattern matching is the natural design.

**Verdict**: Single generic hook. Per-command hooks provide no architectural benefit when the matcher granularity is tool-level.

### Recommended Approach

**Approach A: PreToolUse `updatedInput` command wrapping** with a single generic hook.

Rationale: It is the only approach that actually reduces context consumption. The exit code and compound command concerns are solvable engineering problems (subshell wrappers, `PIPESTATUS` preservation). The command detection concern is mitigated by conservative matching — better to miss a command and let it through unfiltered than to break a non-test command.

## Adversarial Review

### Failure Modes

- **False negatives in filter**: `grep -E '(FAIL|ERROR|error:)'` misses test frameworks that use different failure markers (e.g., Python's `FAILED`, Rust's `failures:`, Go's `--- FAIL:`). The filter pattern must be comprehensive across the project's actual test runners.
- **False positives in command detection**: A command like `echo "running test suite"` could match a test pattern. Conservative matching (requiring the command to start with or contain specific binary names) mitigates this.
- **Exit code corruption**: `cmd | grep | head` returns grep's exit code (1 if no match = all tests pass). A naive pipe breaks the contract that Claude reads exit codes to determine success/failure. The wrapped command must preserve the original exit code.
- **Truncation of critical context**: `head -100` may cut off a critical error message at line 101. The line limit should be configurable or generous enough for diagnostic purposes.

### Edge Cases

- **All tests pass**: When all tests pass, `grep '(FAIL|ERROR)'` returns empty output and exit code 1. The hook must handle the "no failures" case — either pass through a success summary or detect the all-pass condition.
- **Interactive commands**: `npx vitest --watch` produces interactive output. The hook should NOT wrap interactive or long-running commands.
- **Already-piped commands**: `npm test | grep something` — adding another pipe is safe but may interact unexpectedly.
- **Sandbox**: The hook script must be accessible from the sandbox. Since it's deployed to `~/.claude/hooks/`, which is on the sandbox read-allow list, this is fine. The hook itself doesn't write to any restricted paths.
- **Subagent contexts**: Hooks run in all contexts including subagents. This is desirable — subagent test runs should also be filtered.

### Assumptions That May Not Hold

- **`updatedInput` field stability**: This is a relatively new API feature (v2.0.10). If the API changes, the hook would silently stop filtering. Mitigated by: the hook always returns `permissionDecision: "allow"`, so worst case the original command runs unmodified.
- **Pattern completeness**: The initial pattern set will not cover every possible test/lint/build command. This is acceptable — the hook can be iteratively expanded as new patterns are encountered.

### Recommended Mitigations

1. **Exit code preservation**: Use a subshell wrapper pattern:
   ```bash
   OUTPUT=$($ORIGINAL_CMD 2>&1); EXIT=$?; echo "$OUTPUT" | grep -A 5 -E '(FAIL|ERROR|error:)' | head -100; exit $EXIT
   ```
   Or use a temporary file to capture output while preserving the exit code.

2. **All-pass detection**: If the filter produces empty output, emit a summary line like "All tests passed (output filtered — N lines suppressed)".

3. **Configurable patterns**: Store command patterns and filter rules in a configuration file (e.g., `claude/hooks/output-filter-rules.conf`) rather than hardcoding in the script, for easy iteration.

4. **Bypass flag**: Support a mechanism (e.g., command prefix or environment variable) to bypass filtering when full output is needed for debugging.

## Open Questions

- **Exit code preservation strategy**: Should the hook use the subshell-capture pattern (`OUTPUT=$(cmd); EXIT=$?; echo "$OUTPUT" | filter; exit $EXIT`) or the temporary-file pattern (`cmd > tmpfile; EXIT=$?; filter < tmpfile; exit $EXIT`)? The subshell pattern buffers in memory (problematic for very large output); the temporary file pattern requires write access to `$TMPDIR`.
- **All-pass summary format**: When all tests pass and the filter produces empty output, what should the summary line contain? Options: pass count from the runner's summary line, or a generic "all passed" message.
- **Command pattern scope for v1**: Which specific commands should the initial implementation match? Candidates: `npm test`, `jest`, `pytest`, `python -m pytest`, `cargo test`, `go test`, `just test`, `make test`, plus linter equivalents (`eslint`, `ruff`, `pylint`, `cargo clippy`). Build tools are lower priority (build output is typically shorter).
