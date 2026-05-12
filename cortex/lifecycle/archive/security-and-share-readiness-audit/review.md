# Review: Security & Share-Readiness Audit

## Stage 1: Spec Compliance

### Requirement 1: Fix shell variable injection in scan-lifecycle.sh
**PASS**

Line 10 of `hooks/scan-lifecycle.sh` now reads:
```bash
echo "export LIFECYCLE_SESSION_ID='$SESSION_ID'" >> "$CLAUDE_ENV_FILE"
```
SESSION_ID is single-quote wrapped, preventing shell metacharacter expansion when the env file is sourced. Matches the acceptance criteria exactly.

### Requirement 2: Harden test command execution in runner.sh and merge.py
**PASS**

- `eval "$TEST_COMMAND"` is gone from runner.sh. Grep for `eval.*TEST_COMMAND` returns zero matches.
- The integration gate block at line 859 uses `bash -c "$TEST_COMMAND"` inside a subshell.
- The command is logged before execution (`echo "Running integration gate: $TEST_COMMAND"` at line 857).
- `merge.py` `run_tests()` now uses `subprocess.run(["sh", "-c", test_command], ...)` with no `shell=True`. Grep for `shell=True` in merge.py returns zero matches.
- The empty/none guard is preserved at lines 65-66 of merge.py.

### Requirement 3: Fix shell variable interpolation in python3 -c calls
**PASS**

All ~44 `python3 -c` calls in runner.sh now pass shell variables via environment variable prefix assignments (e.g., `STATE_PATH="$STATE_PATH" python3 -c "...os.environ['STATE_PATH']..."`). No call embeds shell variables directly in Python string literals.

Verification:
- `grep 'python3 -c ".*\$' runner.sh` returns zero matches (spec acceptance criterion).
- The `fill_prompt` function (line 357) uses Python-based template substitution via `os.environ`, replacing the previous `sed` approach. No `sed` substitutions with path variables remain.
- `ast.literal_eval` is eliminated; `log_event` and all callers use `json.loads` for detail parsing.
- All `LOG_DETAILS` values are passed as JSON strings via env vars.

### Requirement 4: Auto-detect clone path in just setup
**PASS**

The `deploy-config` recipe (justfile line 105-116) writes `~/.claude/settings.local.json` with the correct `allowWrite` path derived from `$(pwd)/lifecycle/sessions/`. Behavior:
- If `settings.local.json` exists and `jq` is available, it merges via `jq --arg path ... '.sandbox.filesystem.allowWrite = [$path]'`.
- If not, creates a new file with the sandbox override.
- Does not modify the tracked `claude/settings.json` (git status stays clean).
- Re-running is idempotent (same `jq` transform produces same output).

Minor note: the merge replaces `allowWrite` rather than appending, but since this is the entry that `setup` owns, this is acceptable.

### Requirement 5: Print CORTEX_COMMAND_ROOT export line
**PASS**

The `setup` recipe (justfile lines 17-22) prints:
```
Setup complete. Add the following to your shell profile (.zshrc, .bashrc, etc.):

  export CORTEX_COMMAND_ROOT="<actual path>"

Then restart your shell and run: just verify-setup
```

The path is correct via `$(pwd)`. No auto-append to shell config.

### Requirement 6: Add just verify-setup recipe
**PARTIAL**

The `verify-setup` recipe (justfile lines 480-522) checks:
- (a) Symlinks via `just check-symlinks` -- present
- (b) Python 3.12+ -- present, with actionable error
- (c) uv available -- present, with `brew install uv` hint
- (d) claude CLI available -- present, with docs link
- (e) CORTEX_COMMAND_ROOT set and points to repo -- present, with path comparison

Missing from `verify-setup`: **(f) `just test` passes**. This is in a separate `verify-setup-full` recipe instead (line 525-527). The spec explicitly lists all six checks under `just verify-setup`. The plan made a conscious design decision to split tests into a separate recipe (documented as "heavyweight"), which is reasonable but deviates from the spec letter.

Acceptance criteria partially met: exits 0 on healthy install, failing checks print actionable messages, passing checks show minimal output. The test check exists but under a different recipe name.

### Requirement 7: README stays macOS-primary
**PASS**

Line 10 of README.md:
```
> These instructions target macOS. For Linux or Windows setup, see [`docs/setup.md`](docs/setup.md).
```

Appears immediately after Prerequisites, within the first few paragraphs. `docs/setup.md` exists. No README restructuring for multi-platform.

### Requirements Compliance (Project-Level)

No violations of project requirements detected:
- **Complexity**: Changes are minimal and targeted. No unnecessary abstraction layers introduced. The env-var passing pattern is consistent across all conversions.
- **File-based state**: No changes to state architecture.
- **Maintainability**: The codebase is simpler after removing `eval`, `ast.literal_eval`, and `sed` template substitution.
- **Graceful partial failure**: Error handling patterns preserved (`|| true`, `set +e`/`set -e` blocks).

One stale documentation concern: README lines 29-30 still tell users to "edit `claude/settings.json` to update the `allowWrite` path" even though `deploy-config` now auto-writes this to `settings.local.json`. This is not incorrect (manual editing still works) but is now unnecessary guidance that could confuse users.

## Stage 2: Code Quality

### Naming Conventions
Consistent with project patterns. Environment variable names follow the existing `UPPER_SNAKE_CASE` convention. The `LOG_EVENT_NAME`, `LOG_ROUND`, `LOG_DETAILS`, `LOG_EVENTS_PATH` prefix pattern is consistent across all log_event callers.

### Error Handling
Appropriate. All Python blocks that are non-critical use `|| true` or `2>/dev/null || true`. The `verify-setup` recipe counts errors and exits non-zero if any check fails. The `deploy-config` recipe handles the jq-unavailable case gracefully by creating fresh JSON.

### Test Coverage
The plan's verification strategy items are all satisfiable:
1. `just test` -- plan marks this as verified.
2. `just verify-setup` -- plan marks this as verified.
3. Grep for shell interpolation in Python blocks -- confirmed zero matches.
4. Grep for `eval.*TEST_COMMAND` -- confirmed zero matches.
5. Grep for `shell=True` in merge.py -- confirmed zero matches.
6. Grep for `ast.literal_eval` -- confirmed zero matches.
7. scan-lifecycle.sh line 10 quoting -- confirmed.

### Pattern Consistency
The env-var passing pattern (`VAR="$val" python3 -c "...os.environ['VAR']..."`) is applied uniformly across all 44 `python3 -c` calls. No mixed styles. The `fill_prompt` function conversion to Python-based template substitution is clean and consistent with the rest of the env-var approach.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [
    "verify-setup does not include 'just test' (spec requirement 6f); tests are in verify-setup-full instead",
    "README lines 29-30 still reference manual settings.json editing for allowWrite, which is now handled automatically by deploy-config"
  ]
}
```
