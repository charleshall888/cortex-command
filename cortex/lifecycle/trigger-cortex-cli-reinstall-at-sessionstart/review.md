# Review: trigger-cortex-cli-reinstall-at-sessionstart

## Stage 1: Spec Compliance

### Requirement 1: `CLI_PIN` lives in a side-effect-free sibling module
- **Expected**: New `plugins/cortex-overnight/cli_pin.py` declaring the tuple in isolation.
- **Actual**: Extraction deliberately dropped per plan Overview — the hook regex-parses `CLI_PIN` from `server.py` directly to avoid breaking 4+ existing regex-based callers (`release.yml` cli-pin-lint, `auto-release.yml:138`, `test_release_artifact_invariants.py`, `bin/cortex-rewrite-cli-pin`).
- **Verdict**: N/A
- **Notes**: Plan Overview supersedes Req 1.

### Requirement 2: `server.py` re-exports `CLI_PIN` from the sibling
- **Verdict**: N/A
- **Notes**: Same supersession; `server.py:106` retains inline declaration `CLI_PIN = ("v2.7.0", "2.0")`.

### Requirement 3: `bin/cortex-rewrite-cli-pin` retargets to `cli_pin.py`
- **Verdict**: N/A
- **Notes**: Same supersession; rewriter unchanged.

### Requirement 4: Single-declaration invariant
- **Verdict**: N/A
- **Notes**: Same supersession; invariant already held against `server.py`.

### Requirement 5: SessionStart hook script exists at canonical source path
- **Expected**: `hooks/cortex-cli-version-sync.sh` executable, syntactically valid bash.
- **Actual**: File exists at `/Users/charlie.hall/Workspaces/cortex-command/hooks/cortex-cli-version-sync.sh`, mode `0755`, `set -euo pipefail` at line 15, applies PATH bootstrap at line 20.
- **Verdict**: PASS

### Requirement 6: Hook registered in cortex-overnight plugin SessionStart array
- **Expected**: 2 SessionStart entries, one referencing `cortex-cli-version-sync`.
- **Actual**: `plugins/cortex-overnight/hooks/hooks.json` shows 2 SessionStart entries (scan-lifecycle + cli-version-sync) at lines 3–19.
- **Verdict**: PASS

### Requirement 7: `just build-plugin` mirrors the new hook
- **Expected**: HOOKS array includes the new script; byte-identical mirror at plugin path.
- **Actual**: `justfile:559` includes `hooks/cortex-cli-version-sync.sh` in the cortex-overnight HOOKS array. `cmp hooks/cortex-cli-version-sync.sh plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh` reports byte-identical (both 8983 bytes, mtime matched).
- **Verdict**: PASS

### Requirement 8: Pure-stdlib Python helper performs probe + version compare
- **Expected**: Heredoc or sibling Python script, stdlib-only, no `packaging`/`mcp`/`pydantic` imports; uses regex/AST for CLI_PIN parse; PEP 440 prefix split.
- **Actual**: Heredoc at lines 57–260 imports only `json`, `os`, `pathlib`, `re`, `subprocess`, `sys`. `parse_cli_pin` at lines 87–102 uses `re.search` with the same anchor shape as `bin/cortex-rewrite-cli-pin`. `version_tuple` at lines 155–165 implements prefix-split int-tuple compare with no third-party imports. Heredoc compiles via `python3 -c "exec(compile(...))"`.
- **Verdict**: PASS
- **Notes**: Regex `^CLI_PIN\s*=\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,?\s*\)` correctly matches the actual literal `CLI_PIN = ("v2.7.0", "2.0")` at `server.py:106`. (The spec's type-annotated form `CLI_PIN:` does not exist in the code; the regex's `\s*=` handles the actual unannotated assignment.)

### Requirement 9: 30-minute freshness throttle via sentinel file
- **Expected**: Zero-byte sentinel at `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-version-check`; within-window invocations exit fast.
- **Actual**: Lines 22–35 implement the throttle as the FIRST action after PATH bootstrap (before `cat`/jq/python startup). Cross-platform mtime via BSD `stat -f %m` with GNU `stat -c %Y` fallback. Test (f) `throttle-hit` records elapsed=37ms — well under the 50ms cold target and 200ms warm budget.
- **Verdict**: PASS

### Requirement 10: Dev-mode skip predicates honored
- **Expected**: `CORTEX_DEV_MODE=1` (first, free), dirty-tree, non-main branch; git-subprocess failures are conservative skips; mirrors `_evaluate_skip_predicates`.
- **Actual**: `skip_predicate_fires` at lines 105–132 checks env var first, then `git status --porcelain` with `subprocess.TimeoutExpired`/`OSError` → True (conservative skip), then `git rev-parse --abbrev-ref HEAD` with same fallback. Test (d) `dev-mode-skip` confirms silent exit + no sentinel write.
- **Verdict**: PASS

### Requirement 11: Schema-floor parity with `_schema_floor_violated`
- **Expected**: Wheel-only gate (no `.git/` at cortex_root); literal "Schema-floor violation" string; emit as additionalContext (not stderr); message references `--refresh-package cortex-command` per plan substitution.
- **Actual**: Lines 216–234 of the hook gate on `is_wheel = bool(cortex_root) and not (pathlib.Path(cortex_root) / ".git").is_dir()` matching the same `(Path / ".git").is_dir()` check at `server.py:1866`. Byte-comparison of the emitted message vs `server.py:1867–1873`'s stderr literal (with identical substitutions) is identical — both produce `"Schema-floor violation: installed CLI schema_version=1.5, required=2.0; run 'uv tool install --reinstall --refresh-package cortex-command git+https://github.com/charleshall888/cortex-command.git@v9.9.9' to upgrade"`. Hook emits via `additionalContext`; server emits to stderr (different surfaces per spec). Test (c) confirms.
- **Verdict**: PASS

### Requirement 12: `additionalContext` message format on drift detection
- **Expected**: Literal template containing both "cortex CLI is drifted" plus installed/expected version strings; spec's `--refresh` substituted with `--refresh-package cortex-command` per plan.
- **Actual**: Lines 243–254 of the hook produce the message; byte-compared against the plan-revised template — identical. The drift-message string matches the checked-in golden fixture `tests/fixtures/hooks/cli-version-sync/expected-additional-context.txt` (test (b) asserts byte-equality with `{installed}`/`{expected}` substitution applied to the fixture).
- **Verdict**: PASS

### Requirement 13: Defensive `exit 0` on every error path
- **Expected**: All probe/parse/missing-pin/unhandled-exception paths exit 0 with no additionalContext.
- **Actual**: Bash trampoline wraps the Python heredoc with `set +e` (line 56) so any non-zero exit cannot crash the hook; final `exit 0` at line 263 is unconditional. Python body wraps the main logic in a `try: ... except Exception: sys.exit(0)` at lines 175/258–259. `probe_installed` returns None on `TimeoutExpired`/`OSError` and on `json.JSONDecodeError`. `parse_cli_pin` returns None on `OSError` or no-match. Test (e) `probe-failure` (no cortex on PATH) confirms exit 0 + empty stdout.
- **Verdict**: PASS

### Requirement 14: Hook stdin contract
- **Expected**: Reads JSON via stdin, parses `cwd`; defensive on stdin parse failure; fixture exists.
- **Actual**: Lines 39–41 read stdin via `cat`, parse `cwd` via `jq -r '.cwd // empty'` with `2>/dev/null || true` (defensive). Falls back to `pwd` if cwd absent. Fixture exists at `tests/fixtures/hooks/cli-version-sync/claude-agent.json` mirroring the SessionStart payload shape.
- **Verdict**: PASS

### Requirement 15: `_ensure_cortex_installed` adds `--refresh-package cortex-command` (plan substitution for spec's `--refresh`)
- **Expected**: Install argv carries the flag between `--reinstall` and the git URL (plan task 5).
- **Actual**: `server.py:626–635` argv shape: `["uv", "tool", "install", "--reinstall", "--refresh-package", "cortex-command", f"git+...@{CLI_PIN[0]}"]`. Flag is adjacent to `--reinstall` and precedes the URL. `tests/test_no_clone_install.py:427–434` asserts the adjacency invariant positionally (`argv[reinstall_idx+1:reinstall_idx+3] == ["--refresh-package", "cortex-command"]`), and a parallel phase-3 assertion at lines 528–533 covers the version-mismatch reinstall path.
- **Verdict**: PASS

### Requirement 16: `docs/internals/auto-update.md` updated
- **Expected**: Bash-tool carve-out rewritten; component map row added; Residual Risks revised; `wontfix per #145` removed; `#235` cited.
- **Actual**: `grep -c "wontfix per #145"` = 0; `grep -c "#235"` = 4; new component-map row at line 60 (`cortex-cli-version-sync.sh (#235)`); Bash-tool carve-out at lines 37–41 explicitly distinguishes execution-gap (still MCP-tool-call-gated) from visibility-gap (closed by hook); Residual Risks at lines 110–115 drops the force-pushed release tag entry and adds a paragraph documenting `--refresh-package cortex-command` closure.
- **Verdict**: PASS

### Requirement 17: Hook tests cover golden path + 5 edge cases
- **Expected**: 6 scenarios: no-drift, drift, schema-floor, dev-mode-skip, probe-failure, throttle-hit.
- **Actual**: `tests/test_cli_version_sync_hook.sh` covers all 6 with isolated tmpdir-per-scenario scaffolding. Re-run confirms `6 passed, 0 failed`. The drift case (b) uses the golden text fixture `expected-additional-context.txt` for byte-equality (not substring containment) — breaking the same-author tautology risk.
- **Verdict**: PASS

### Requirement 18: `cli_pin.py` parity guard
- **Verdict**: N/A
- **Notes**: Plan Overview supersedes — no `cli_pin.py` exists, so no parity guard needed.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Bash trampoline names (`HOOK_CWD`, `HOOK_STATE_DIR`, `HOOK_SENTINEL`, `HOOK_PLUGIN_ROOT`) follow the exported-env convention used by sibling hooks. Python helper functions (`parse_cli_pin`, `skip_predicate_fires`, `probe_installed`, `version_tuple`, `schema_major`, `emit_context`, `touch_sentinel`) use clear verb-prefixed names matching `_evaluate_skip_predicates` / `_ensure_cortex_installed` server-side conventions.

- **Error handling**: Strong. Three layers of defense: (1) bash `set +e` around the heredoc so python crashes can't propagate; (2) Python-level `try/except Exception → sys.exit(0)` wraps the entire main block; (3) per-operation `except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError)` for granular paths. Sentinel write is itself wrapped in `except OSError: pass` so a read-only `$HOME` can't break the hook. Throttle-fast-path uses `2>/dev/null` plus arithmetic fallback (`|| echo 0`) so missing/corrupt mtimes degrade gracefully.

- **Test coverage**: Excellent. All 6 spec-required scenarios covered, plus the throttle case includes a latency budget assertion (≤2000ms ceiling, observed 37ms). Argv adjacency invariant covered by two test sites in `test_no_clone_install.py` (lines 411–434 first-install + 524–534 phase-3 version-mismatch). Golden text fixture breaks the same-author tautology risk by providing an independent oracle. Heredoc compile-check via `python3 -c "exec(compile(...))"` catches syntax errors that `bash -n` can't see.

- **Pattern consistency**: Hook structure matches existing precedents — PATH bootstrap shape mirrors `claude/hooks/cortex-session-start-path-bootstrap.sh:29`; `INPUT=$(cat)` + `jq -r '.cwd // empty'` mirrors `cortex-scan-lifecycle.sh:5–13`; skip-predicate order mirrors `_evaluate_skip_predicates` at `server.py:1195–1249`. The throttle-fast-path-before-stdin ordering is a deliberate optimization documented in-file (lines 11–13) and verified by test (f).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
