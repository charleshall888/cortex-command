# Specification: trigger-cortex-cli-reinstall-at-sessionstart

## Problem Statement

The `_ensure_cortex_installed` reinstall mechanism in `plugins/cortex-overnight/server.py:775` is MCP-tool-call-gated: it only fires when the cortex-overnight MCP server is invoked. Interactive sessions that shell out to `cortex …` via Bash, hooks under `claude/hooks/`, plugin-mirrored `bin/cortex-*` Python helpers that import `cortex_command.*`, and JSON envelopes parsed outside MCP all bypass the version check. After a marketplace fast-forward bumps `CLI_PIN[0]`, the user can hit `No such command 'X'`, `ImportError`, or silent schema-bumped JSON breakage on any of those surfaces until they happen to invoke an MCP tool that triggers Layer 2. This work adds a SessionStart hook that **detects** drift (and a related latent stale-cache bug in `_ensure_cortex_installed`) so Claude has the breadcrumb to give a correct remediation on subsequent Bash failures. The hook does not itself reinstall — execution remains MCP-tool-call-gated — but it closes the visibility gap that previously caused mystery failures.

## Phases

- **Phase 1: CLI_PIN extraction** — move `CLI_PIN` to a side-effect-free sibling so the hook can read it without paying server.py's import cost (PEP 723 venv + plugin-root enforce). Re-export from server.py preserves all existing callers.
- **Phase 2: SessionStart drift-detector hook** — bash trampoline + Python helper that probes the installed CLI, compares against `CLI_PIN`, and emits `additionalContext` on drift. Honors dev-mode skip predicates and a 30-minute freshness throttle. Defensive `exit 0` on every error path.
- **Phase 3: `--refresh` flag fix in `_ensure_cortex_installed`** — bundles the latent stale-cache bug fix so the existing Layer 2 reinstall mechanism actually picks up force-pushed release tags. Closes the loop: Phase 2 detects drift visibly, Phase 3 ensures the next MCP-call-driven reinstall fixes it.
- **Phase 4: Docs update** — rewrite the `docs/internals/auto-update.md` Bash-tool carve-out section to reflect the new visibility mechanism; add component-map row.

## Requirements

1. **`CLI_PIN` lives in a side-effect-free sibling module**: New file `plugins/cortex-overnight/cli_pin.py` declares `CLI_PIN: tuple[str, str] = (...)`. The module contains only the `CLI_PIN` declaration, optional module docstring, and the standard PEP 723-less shebang / pure-Python header — no third-party imports, no top-level function calls, no side effects on import. Acceptance: `python3 -c "from plugins.cortex_overnight.cli_pin import CLI_PIN; print(CLI_PIN)"` from a bare shell (no PEP 723 venv) exits 0 and prints the tuple. **Phase**: Phase 1: CLI_PIN extraction.

2. **`server.py` re-exports `CLI_PIN` from the sibling**: `plugins/cortex-overnight/server.py:106`'s inline `CLI_PIN = (...)` replaced by `from cli_pin import CLI_PIN`. `MCP_REQUIRED_CLI_VERSION` derivation at `server.py:113` unchanged. Acceptance: `grep -c "^CLI_PIN = " plugins/cortex-overnight/server.py` = 0, and `grep -c "^from cli_pin import CLI_PIN" plugins/cortex-overnight/server.py` = 1. **Phase**: Phase 1: CLI_PIN extraction.

3. **`bin/cortex-rewrite-cli-pin` retargets to `cli_pin.py`**: The rewriter's `DEFAULT_TARGET` (line 47) updates to `plugins/cortex-overnight/cli_pin.py`. The single-declaration regex constraints at lines 64–91 hold. Acceptance: `bin/cortex-rewrite-cli-pin v9.9.9-test` modifies only `plugins/cortex-overnight/cli_pin.py` (verify with `git status --porcelain`), and the rewriter's existing tests pass with no modification. **Phase**: Phase 1: CLI_PIN extraction.

4. **Single-declaration invariant holds across the repo**: After Phase 1, `git grep -E "^CLI_PIN[[:space:]]*[:=]"` returns exactly one match (the new `cli_pin.py`). Acceptance: the grep count equals 1. **Phase**: Phase 1: CLI_PIN extraction.

5. **SessionStart hook script exists at canonical source path**: New file `hooks/cortex-cli-version-sync.sh` (canonical source; mirrored into `plugins/cortex-overnight/hooks/` by `just build-plugin`). Bash trampoline (`set -euo pipefail`) reads JSON stdin via `jq`, applies the GUI-launched PATH bootstrap (precedent: `claude/hooks/cortex-worktree-create.sh:18`), and invokes a sibling Python helper. Acceptance: `test -x hooks/cortex-cli-version-sync.sh` (executable bit set) and `bash -n hooks/cortex-cli-version-sync.sh` exits 0 (syntactically valid). **Phase**: Phase 2: SessionStart drift-detector hook.

6. **Hook registered in `cortex-overnight` plugin's SessionStart array**: `plugins/cortex-overnight/hooks/hooks.json` appends a second SessionStart entry alongside the existing `cortex-scan-lifecycle.sh`. Acceptance: `jq '.hooks.SessionStart | length' plugins/cortex-overnight/hooks/hooks.json` = 2 and `jq -r '.hooks.SessionStart[].hooks[].command' plugins/cortex-overnight/hooks/hooks.json | grep -c cortex-cli-version-sync` = 1. **Phase**: Phase 2: SessionStart drift-detector hook.

7. **`just build-plugin` mirrors the new hook**: The `HOOKS=(...)` array for cortex-overnight in `justfile` (around line 655) includes `cortex-cli-version-sync.sh`. Acceptance: `just build-plugin cortex-overnight` succeeds and `plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh` exists and is byte-identical to the canonical source at `hooks/cortex-cli-version-sync.sh`. **Phase**: Phase 2: SessionStart drift-detector hook.

8. **Pure-stdlib Python helper performs the probe and version compare**: A Python script (either inline `python3 -c '…'` in the bash trampoline, or a sibling `.py` file invoked via `python3`) reads `CLI_PIN[0]` from `plugins/cortex-overnight/cli_pin.py` via stdlib regex or AST parse (no third-party deps), shells `cortex --print-root --format json` with a 10-second timeout, parses the JSON envelope, and compares `payload["version"]` against `CLI_PIN[0].lstrip("v")` using a simple PEP 440 prefix split (split on `.`, compare tuple of ints — no `packaging` import needed). On version mismatch (`installed < expected`), the script emits `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<message>"}}` to stdout. Acceptance: `python3 -m py_compile <helper-path>` exits 0 and `grep -E "^import (packaging|mcp|pydantic)" <helper-path>` returns nothing. **Phase**: Phase 2: SessionStart drift-detector hook.

9. **30-minute freshness throttle via sentinel file**: After each completed probe (drift or no-drift), the hook writes a zero-byte sentinel at `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-version-check`. On subsequent invocations within 1800 seconds of the sentinel's mtime, the hook skips the probe entirely and exits 0. Acceptance: hook invocation when the sentinel is newer than 1800s exits within 50ms cold (single `stat(2)` + `exit 0`), measured by `time ./hooks/cortex-cli-version-sync.sh <fixture-stdin>`. **Phase**: Phase 2: SessionStart drift-detector hook.

10. **Dev-mode skip predicates honored identically to `_evaluate_skip_predicates`**: The hook short-circuits and exits 0 silently when (a) `CORTEX_DEV_MODE=1` is set, (b) `git -C <cortex_root> status --porcelain` returns nonempty output (dirty tree), or (c) `git -C <cortex_root> rev-parse --abbrev-ref HEAD` returns anything other than `main`. Predicate (a) evaluates first (free, no shell-out); (b) and (c) only run if (a) does not fire. `cortex_root` comes from `cortex --print-root`'s `root` field. If the git subprocesses fail (`OSError`, non-zero exit), the hook treats the failure as a conservative skip (silent exit 0), mirroring `_evaluate_skip_predicates` at `plugins/cortex-overnight/server.py:1195-1249`. Acceptance: hook invocation with `CORTEX_DEV_MODE=1` set exits 0 with no stdout output and the freshness sentinel is not written. **Phase**: Phase 2: SessionStart drift-detector hook.

11. **Schema-floor parity with `_schema_floor_violated`**: When the hook detects that the installed CLI's `payload["schema_version"]` major is less than `CLI_PIN[1]` major, AND the install is a wheel install (mirror the existing gate at `plugins/cortex-overnight/server.py:1294` — check that the `cortex_root` does NOT contain a `.git/` directory), it emits the same remediation message as `_schema_floor_violated` (server.py:1860–1869): `Schema-floor violation: installed CLI schema_version={cli_version}, required={CLI_PIN[1]}; run 'uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@{CLI_PIN[0]} --refresh' to upgrade`. The message is emitted as `additionalContext` (not stderr) so Claude has the breadcrumb. Under editable install (`.git/` directory present), the hook does not emit the schema-floor message — matching the existing `_schema_floor_violated` gate. Acceptance: hook fixture with installed `schema_version=1.0` and `CLI_PIN[1]="2.0"`, no `.git/` at cortex_root, emits the literal `"Schema-floor violation"` string in `additionalContext` (verify via `jq -r '.hookSpecificOutput.additionalContext' <hook-stdout>`). **Phase**: Phase 2: SessionStart drift-detector hook.

12. **`additionalContext` message format on drift detection (non-schema-floor case)**: When the hook detects a normal version drift (`installed < expected`, schema floor OK), it emits `additionalContext`: `cortex CLI is drifted: installed v{installed}, expected v{expected}. The next MCP tool call will reinstall automatically. Bash 'cortex …' calls before then may fail with 'No such command' or import errors; if so, run 'uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@v{expected} --refresh' manually.` The message exists so Claude has the diagnostic context to route subsequent Bash failures correctly. Acceptance: hook fixture with installed v2.0.0 and `CLI_PIN[0]="v2.1.0"` produces `additionalContext` containing both literal strings `"cortex CLI is drifted"` and `"v2.0.0"` and `"v2.1.0"`. **Phase**: Phase 2: SessionStart drift-detector hook.

13. **Defensive `exit 0` on every error path**: The hook returns exit code 0 in all of: (a) probe subprocess timeout, (b) probe subprocess non-zero exit, (c) probe stdout JSON parse failure, (d) `cortex_root` cannot be resolved, (e) `cli_pin.py` cannot be read or parsed, (f) any unhandled exception in the Python helper. None of these paths emit `additionalContext` (silent skip — the hook cannot brick Claude Code launch). Acceptance: hook fixture invoked with `PATH=/nonexistent` (cortex not on PATH) exits 0 with empty stdout (verify exit code = 0 and `wc -c` on stdout = 0). **Phase**: Phase 2: SessionStart drift-detector hook.

14. **Hook stdin contract**: The hook reads JSON from stdin matching Claude Code's SessionStart payload (`hook_event_name`, `session_id`, `cwd`, `source`, etc.). The hook uses `cwd` to ground the `cortex_root` resolution. On stdin parse failure, the hook exits 0 silently (defensive). Acceptance: fixture `tests/fixtures/hooks/cli-version-sync/claude-agent.json` exists, mirrors the existing `tests/fixtures/hooks/scan-lifecycle/claude-agent.json` shape, and the hook runs to completion when fed via `cat <fixture> | ./hook`. **Phase**: Phase 2: SessionStart drift-detector hook.

15. **`_ensure_cortex_installed` adds `--refresh` to `uv tool install --reinstall` invocation**: The `_run_install_and_verify` function at `plugins/cortex-overnight/server.py:580-772` builds the `uv tool install --reinstall git+...@{CLI_PIN[0]}` command. The fix appends `--refresh` to that argv so force-pushed release tags reliably miss uv's tag→commit cache. Acceptance: `grep -E "uv.*tool.*install.*--reinstall.*--refresh" plugins/cortex-overnight/server.py` returns at least 1 match. **Phase**: Phase 3: --refresh flag fix in _ensure_cortex_installed.

16. **`docs/internals/auto-update.md` Bash-tool carve-out section updated**: The "Bash-tool subprocess carve-out" section (lines 37–39) is rewritten to reflect that the visibility gap is closed by the SessionStart hook (#235), while the execution gap remains MCP-tool-call-gated. The component map (table starting line 47) adds a row for the new hook. The Residual Risks section (lines 105–111) is amended to remove or revise the "force-pushed release tag" entry now that `--refresh` is part of the reinstall argv. Acceptance: `grep -c "wontfix per #145" docs/internals/auto-update.md` = 0 (the wontfix language is removed); `grep -c "#235" docs/internals/auto-update.md` ≥ 1 (new ticket cited). **Phase**: Phase 4: Docs update.

17. **Hook tests cover golden path and edge cases**: New test file (either `tests/test_cli_version_sync_hook.sh` modeled on `tests/test_hooks.sh`, or a Python test under `tests/`) covers: (a) no-drift case (installed == expected → no additionalContext, sentinel written), (b) drift case (installed < expected → additionalContext emitted, sentinel written), (c) schema-floor case (schema major mismatch → schema-floor message emitted), (d) dev-mode skip (CORTEX_DEV_MODE=1 → silent exit 0), (e) probe-failure case (cortex not on PATH → silent exit 0), (f) throttle hit (sentinel newer than 1800s → silent exit 0 without probe). Acceptance: `just test tests/test_cli_version_sync_hook.sh` (or the Python test equivalent) exits 0 covering all six scenarios. **Phase**: Phase 2: SessionStart drift-detector hook.

18. **`cli_pin.py` parity is enforceable**: Add a pre-commit guard (extending `.githooks/pre-commit` or `bin/cortex-check-parity`) that verifies `plugins/cortex-overnight/cli_pin.py` contains only the `CLI_PIN` declaration and an optional docstring — no third-party imports, no top-level executable statements beyond the assignment. This guards against future regressions where a contributor adds side-effecting code to `cli_pin.py` and breaks the hook's bare-Python import contract. Acceptance: adding a top-level `import packaging` to `plugins/cortex-overnight/cli_pin.py` and running the pre-commit guard exits non-zero with an actionable message. **Phase**: Phase 1: CLI_PIN extraction.

## Non-Requirements

- **The hook does not execute `uv tool install --reinstall`.** Reinstall remains MCP-tool-call-gated via the existing `_ensure_cortex_installed` path. The hook's job is visibility, not execution.
- **The hook does not consult the in-flight install guard.** Because it doesn't reinstall, it has no need for `check_in_flight_install_core`. A third byte-identical mirror of `install_guard.py` is explicitly out of scope.
- **The hook does not acquire the install flock.** No flock means no 60s wait budget, no concurrent-session contention failure mode.
- **The hook does not write NDJSON audit records.** `_NDJSON_ERROR_STAGES` allowlist additions (e.g., `session_start_sync`) are out of scope.
- **The hook does not refresh `PATH` or write `CLAUDE_ENV_FILE`.** Because it doesn't reinstall, it never relocates the binary; PATH is unchanged.
- **No env-var kill switch.** Existing dev-mode skip predicates (`CORTEX_DEV_MODE=1`, dirty tree, non-main branch) are sufficient; adding `CORTEX_SESSION_START_SYNC=0` would expand the env-var surface without solving a problem the predicates don't already address.
- **Cross-plugin coupling is not introduced.** The hook lives in `cortex-overnight` (where `CLI_PIN` already lives). `cortex-core` is not modified.
- **Downgrade prevention in `_ensure_cortex_installed` is not changed.** That existing function's `!=` comparison stays as-is; the hook's drift detection uses `installed < expected` (strict <), so it only emits `additionalContext` on stale-installed cases, not on installed-ahead cases.
- **PEP 723 frontmatter is not added to the hook helper.** The whole point of `cli_pin.py` extraction is to keep the hook on bare stdlib.

## Edge Cases

- **`cortex` not installed**: probe fails with `command not found`. Hook exits 0 silently. Rationale: the first-install path is handled by `_ensure_cortex_installed` on the next MCP call; the hook has no role here.
- **`cortex --print-root` exits 2 (not a cortex repo)**: hook exits 0 silently. Mirrors the existing skip semantics (this cwd isn't a cortex project; no version sync needed).
- **`cortex --print-root` returns invalid JSON or missing `version` field**: hook exits 0 silently. Defensive against future envelope schema changes.
- **`CLI_PIN[0]` and installed `version` are equal**: hook writes the freshness sentinel, exits 0 with no `additionalContext`. The no-op happy path.
- **Installed `version` is greater than `CLI_PIN[0]`** (user manually installed a newer tag than the plugin pins): hook does NOT emit `additionalContext`. The comparison is strict `<`. Rationale: this is a dogfooding case, not a drift case; the user knows what they're doing.
- **Sentinel exists but mtime is unreadable or in the future** (system clock skew): hook treats sentinel as expired, runs the probe, rewrites the sentinel. Conservative.
- **`${XDG_STATE_HOME}` is unset and `${HOME}` is unwritable**: sentinel write fails. Hook still emits `additionalContext` if drift is detected, but cannot throttle subsequent invocations. Exits 0.
- **`cli_pin.py` is malformed or missing**: hook exits 0 silently. The pre-commit parity guard prevents this from reaching main.
- **Multiple SessionStart hooks fire simultaneously** (e.g., tmux split + IDE re-attach): each runs its own probe; first to write the sentinel wins the throttle update. No coordination needed because the hook is read-mostly.
- **`cortex_root` resolves to a path outside the user's HOME**: hook still runs the probe; skip predicates still apply (CORTEX_DEV_MODE / dirty tree / non-main branch). No special handling.
- **Schema-floor violation on editable install** (.git/ present at `cortex_root`): hook does NOT emit the schema-floor message (mirrors `_schema_floor_violated`'s wheel-only gate). The dogfooder is managing CLI versions directly via `pip install -e .`.

## Changes to Existing Behavior

- **MODIFIED**: `plugins/cortex-overnight/server.py:106` — `CLI_PIN` declaration moves from inline tuple to `from cli_pin import CLI_PIN` re-export. All existing callers (`MCP_REQUIRED_CLI_VERSION` derivation, `_ensure_cortex_installed`, `_schema_floor_violated`) continue to work because the import yields the identical tuple object.
- **MODIFIED**: `plugins/cortex-overnight/server.py:580-772` (`_run_install_and_verify`) — `uv tool install --reinstall git+...@{CLI_PIN[0]}` argv gains a `--refresh` flag so force-pushed release tags reliably miss the uv tag→commit cache.
- **MODIFIED**: `plugins/cortex-overnight/hooks/hooks.json` — SessionStart array gains a second entry for `cortex-cli-version-sync.sh`.
- **MODIFIED**: `bin/cortex-rewrite-cli-pin` (`DEFAULT_TARGET` line 47) — retargets from `plugins/cortex-overnight/server.py` to `plugins/cortex-overnight/cli_pin.py`.
- **MODIFIED**: `justfile` `build-plugin` recipe — `HOOKS=(...)` array for cortex-overnight gains `cortex-cli-version-sync.sh`.
- **MODIFIED**: `docs/internals/auto-update.md` — Bash-tool carve-out section rewritten; component map gains a hook row; Residual Risks section amended.
- **ADDED**: `plugins/cortex-overnight/cli_pin.py` — new side-effect-free module holding `CLI_PIN`.
- **ADDED**: `hooks/cortex-cli-version-sync.sh` (top-level canonical source; mirrored into plugin via `just build-plugin`) — new SessionStart hook script.
- **ADDED**: `tests/test_cli_version_sync_hook.sh` (or Python equivalent) — new test surface.
- **ADDED**: `tests/fixtures/hooks/cli-version-sync/claude-agent.json` — new fixture.
- **ADDED**: pre-commit guard / `bin/cortex-check-parity` extension — new enforcement of `cli_pin.py`'s "constant-only" invariant.

## Technical Constraints

- **Plugin-imports-zero-cortex-modules contract** (`docs/internals/mcp-contract.md:3`): the hook lives inside the cortex-overnight plugin and is subject to the same plugin/CLI separation. It MAY NOT import from `cortex_command.*`. It MAY use `subprocess.run(["cortex", ...])` and parse the versioned JSON envelope.
- **`cortex --print-root` envelope is forever-public-API** (`docs/internals/mcp-contract.md:22-28`): the hook can rely on `version` (string, PEP 440), `schema_version` (string, M.m), and `root` (absolute path) being present and typed correctly across all cortex CLI versions.
- **SessionStart cannot block startup via exit code**: only `{"continue": false}` in JSON output halts Claude entirely; the hook does not use this. Exit 2 = non-blocking stderr-shown error.
- **Hook stdout is parsed as JSON output contract**, not streamed to user UI. No progress indicator is visible during hook execution.
- **The freshness throttle is per-user (`${XDG_STATE_HOME}/cortex-command/`)**, not per-repo. Version sync is a user-level concern; the same installed CLI serves all cortex projects on the machine.
- **The hook depends on `jq` and `python3` being on PATH**: both are project-wide dependencies (jq is used by existing hooks; python3 ships with macOS / Linux). The PATH bootstrap from `claude/hooks/cortex-worktree-create.sh:18` covers GUI-launched Claude Code (`~/.local/bin:~/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH`).
- **`_schema_floor_violated`'s wheel-only gate** (`plugins/cortex-overnight/server.py:1294`): the hook mirrors this gate by checking `(Path(cortex_root) / ".git").is_dir()` and skipping the schema-floor message under editable installs.
- **`bin/cortex-rewrite-cli-pin` single-declaration regex** (lines 64-91): only one `CLI_PIN = (...)` declaration may exist in the rewrite target. Phase 1's retarget preserves this invariant.

## Open Decisions

None — all questions resolved during the interview. Phase ordering is straightforward (Phase 1 unblocks Phase 2; Phase 3 is independent; Phase 4 references both).

## Proposed ADR

None considered.
