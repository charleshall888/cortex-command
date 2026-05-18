# Specification: resolve-cortex-interpreter-via-cli

## Problem Statement

The SessionStart hook at `hooks/cortex-scan-lifecycle.sh` invokes bare `python3` at three sites (preflight import-check, batch phase-detection, metrics regen). Under the documented `uv tool install` distribution path, bare `python3` cannot import `cortex_command` because the package lives in an isolated tool venv — so the hook fails loudly in cortex-aware repos with a remediation message that itself is wrong (`uv tool install -e .` also produces an isolated venv). The fix is to refactor the hook into a thin bash wrapper around a new `cortex hooks scan-lifecycle` subcommand: the cortex shim already executes in the right interpreter, so one Python boot replaces today's three, the install-topology bug disappears by construction, and SessionStart cost drops (~150-200ms vs ~300ms current). Lifecycle context injection works in every install topology the CLI itself works in.

## Phases

- **Phase 1: Python subcommand** — port the bash hook's logic to `cortex_command.hooks.scan_lifecycle` and wire it as a `cortex hooks scan-lifecycle` subcommand following the existing lazy-dispatch pattern at `cli.py:48-66`.
- **Phase 2: Hook replacement + version pin** — replace the 460-line bash hook with a ~10-line wrapper that pre-checks cheap predicates and execs the subcommand; bump `CLI_PIN` in `plugins/cortex-overnight/server.py` to require the cortex version that ships the subcommand.
- **Phase 3: Test coverage** — golden-file equivalence tests against captured bash output, table-driven session-migration tests independent of the existing fragile bash scaffolding, and a uv-tool-topology smoke-test acceptance criterion.

## Requirements

1. **`cortex hooks scan-lifecycle` subcommand exists and reads stdin JSON**: invoking `echo '{"session_id":"abc","cwd":"/tmp"}' | cortex hooks scan-lifecycle` exits 0 (no lifecycle dir → silent exit) and emits no stdout. Acceptance: `cortex hooks scan-lifecycle --help` exits 0 and lists the subcommand under `cortex hooks --help`. **Phase**: Python subcommand

2. **Subcommand produces equivalent `hookSpecificOutput.additionalContext` to today's bash hook for the lifecycle-state matrix, captured under a topology where the bash hook actually runs**. Fixture inputs: (a) no lifecycle dir, (b) single incomplete feature, (c) multiple incomplete features, (d) post-`/clear` session migration, (e) Morning Review active, (f) pipeline-state present with executing/paused/failed features. **Capture topology**: fixtures are captured by running the current bash hook under a working install topology (e.g., `pip install -e .` into the active venv, or any topology where bare `python3 -c "import cortex_command.common"` succeeds) — NOT under uv-tool topology, where the bash hook's preflight aborts before cases (b)–(f) produce output. The captured fixtures represent the "no-preflight-error path" — the additionalContext substring of the JSON envelope. Acceptance: a pytest fixture replays each captured stdin/expected-additionalContext pair against the Python subcommand and asserts the emitted `hookSpecificOutput.additionalContext` matches. `just test` exits 0 with the new test module included. **Phase**: Python subcommand

3. **Subcommand lazy-loads — no `cortex_command.*` imports beyond `cli`-level entry until the subcommand dispatcher fires**: mirrors the existing pattern at `cli.py:48-66` for the overnight dispatchers. Acceptance: `python3 -c "import cortex_command.cli; import sys; print([m for m in sys.modules if m.startswith('cortex_command.hooks')])"` prints `[]` — the hooks subtree is not imported by `cli` module load. **Phase**: Python subcommand

4. **Bash hook becomes a thin wrapper that probes for subcommand presence directly rather than guessing exit codes**. The wrapper checks subcommand presence via `cortex hooks scan-lifecycle --help` and falls through silently when the subcommand is absent in any older CLI version (regardless of which exit code that older CLI happens to emit on unknown command). The wrapper shape:
   ```bash
   #!/bin/bash
   set -euo pipefail
   command -v cortex >/dev/null || exit 0
   input=$(cat)
   cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
   [[ -d "$cwd/cortex/lifecycle" ]] || exit 0
   # Probe subcommand presence; absent on older CLIs → silent skip (no version-skew assumption).
   cortex hooks scan-lifecycle --help >/dev/null 2>&1 || exit 0
   printf '%s' "$input" | exec cortex hooks scan-lifecycle
   ```
   Once the probe succeeds, the wrapper exec's the real call — any nonzero from the actual subcommand run propagates as a genuine internal error (not a skew artifact). The probe doubles the CLI invocation count vs the original sketch, but `--help` short-circuits in argparse before any cortex_command imports, so the probe's cost is ~Python-boot only (~50-100ms), and SessionStart still spawns Python only twice (probe + actual run) — half of today's three. Acceptance: `wc -l < hooks/cortex-scan-lifecycle.sh` ≤ 15. **Phase**: Hook replacement + version pin

5. **`CLI_PIN` bumped to require the cortex version that ships `hooks scan-lifecycle`**: `plugins/cortex-overnight/server.py:106`'s tuple updated from `("v2.1.2", "2.0")` to the new tag/schema pair. Acceptance: `grep -c '^CLI_PIN = ("v2\.1\.2", "2\.0")$' plugins/cortex-overnight/server.py` = 0 (the old pin is gone). **Phase**: Hook replacement + version pin

6. **Session-state mutation paths are table-driven testable in Python, enumerated from the bash hook's actual filesystem-mutation code paths, with filesystem-state assertions on each**. Branches:
   - **(P1) Phase 1 migration**: stale `.session` matching `LIFECYCLE_SESSION_ID` → overwrite `.session` with new SESSION_ID AND write `.session-owner` with old LIFECYCLE_SESSION_ID. Assert both files after the call.
   - **(P2) Phase 2 chain migration**: `.session-owner` matching stale `LIFECYCLE_SESSION_ID` AND no `.session` matched in Phase 1 → write `.session` with new SESSION_ID (leave `.session-owner` unchanged). Assert both files after the call.
   - **(SC) Single-feature crash-recovery claim**: exactly one incomplete feature, no session match → write SESSION_ID to that feature's `.session` (the bash hook's lines 343-351 path, OUTSIDE the migration block). Assert the post-call `.session`.
   - **(OR) Orphan-`.session-owner` resurrection — DEPARTURE from bash**: if `.session-owner` survives but `.session` is absent AND the feature directory has no incomplete-phase indicator (i.e., the feature is complete), the Python port does NOT write a new `.session` (the bash hook's orphan-resurrection is treated as a latent bug, intentionally not reproduced). Assert no `.session` is created.
   Acceptance: `grep -c "def test_session_mutation_" tests/test_hooks_scan_lifecycle.py` ≥ 4 (one per branch) AND each test asserts post-call filesystem state of `.session` and `.session-owner` (not just stdout). **Phase**: Test coverage

7. **uv-tool-topology smoke-test acceptance covers both liveness AND output equivalence to the golden fixtures**: a script `tests/smoke_uv_tool_hook.sh` exercises the full hook against a real `uv tool install`-installed cortex. Two assertions: (a) the full hook runs without traceback against all newly-reachable code paths (session-migration, pipeline-state, metrics regen); (b) for the lifecycle-state fixtures from requirement #2, the emitted `hookSpecificOutput.additionalContext` under uv-tool topology matches the golden fixture captured under working topology byte-for-byte. This closes the topology gap left by requirement #2 (which captures under working topology only). Acceptance: `just test-smoke-hook` exits 0 (where the recipe runs the smoke script). May be marked `skip` in CI if a uv-tool install cannot be staged, but the recipe and assertion must exist and the script must run cleanly on the developer's local machine. **Phase**: Test coverage

8. **Plugin mirror is refreshed automatically by `just build-plugin`**: editing `hooks/cortex-scan-lifecycle.sh` and running `just build-plugin` produces the corresponding mirror at `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` with byte-equivalent content. Acceptance: `git diff --quiet -- plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` after `just build-plugin` returns exit 0 with no diff post-implementation. **Phase**: Hook replacement + version pin

9. **The existing fail-loud discipline is preserved via the probe-then-exec pattern**: the wrapper's `--help` probe distinguishes "subcommand absent (old CLI)" from "subcommand present but failing." When the probe succeeds and the subsequent `exec` returns nonzero (segfault, PYTHONHOME pollution, internal error), the exit code propagates and the operator sees the actual failure. Acceptance: two tests — (a) stub `cortex` that returns nonzero from `--help` → wrapper exits 0 silently (skew window), (b) stub `cortex` that returns 0 from `--help` AND returns exit 1 from the actual call → wrapper exits 1 (real internal error). **Phase**: Test coverage

10. **`statusline.sh` parity comment is updated** to reflect that the canonical phase-detection lives in `cortex_command.common.detect_lifecycle_phase` (unchanged) but the SessionStart hook is a Python subcommand, not bash. The DR-6 parity test at `tests/test_lifecycle_phase_parity.py` continues to pass without modification. Acceptance: `grep -c "bash-only mirror" claude/statusline.sh` ≥ 1 (the existing parity-mirror docstring is preserved) AND `grep -c "cortex hooks scan-lifecycle" claude/statusline.sh` ≥ 1 (the docstring references the new subcommand entry point) AND `just test` exits 0 with `tests/test_lifecycle_phase_parity.py` passing. **Phase**: Hook replacement + version pin

11. **Session-state writes are serialized via `fcntl.flock` on the feature directory**: the Python subcommand acquires an exclusive flock on the active feature's lifecycle directory before writing `.session`, `.session-owner`, or both, releases on completion or error. Eliminates the bash hook's latent inter-write race surface (concurrent SessionStart from two terminals would otherwise observe partial filesystem state). Acceptance: `grep -c "fcntl.flock" cortex_command/hooks/scan_lifecycle.py` ≥ 1 AND a pytest test verifies that two concurrent invocations against the same feature directory produce a final filesystem state consistent with one full migration (not partial). **Phase**: Python subcommand

## Non-Requirements

- **No `cortex --print-python` flag.** Retired in favor of the subcommand refactor. Discovery is unnecessary because the cortex shim runs in the right interpreter by construction.
- **No conversion of `bin/cortex-backlog-ready`, `bin/cortex-morning-review-complete-session`, or embedded `python3 -c` snippets in skill references.** Deferred to backlog #248 (`248-convert-bin-cortex-and-skill-embedded-python3-callsites-to-cli-subcommands`), filed as the explicit successor track. Investigation during critical review verified that these four callsites are not mechanical substitutions — the bin/* scripts have a three-branch fallback architecture and the skill-embedded snippets need per-site design decisions (different mechanisms may suit different sites). Bundling them into this lifecycle would conflate two distinct design problems with the hook refactor. Backlog #248 owns the design work.
- **No fix for backlog #170's known-fragile bash test scaffolding.** The Python port has its own test surface (pytest); the bash tests for `cortex-scan-lifecycle.sh` become obsolete and can be removed or skipped. Backlog #170 remains open against the broader bash-test fragility, which this work does not touch.
- **No refactor of `cortex_command/cli.py`'s top-level imports beyond adding the `hooks` subcommand dispatcher.** The `cli.py:17` `from cortex_command.init.handler import init_main` stays as-is; it does not block the subcommand path (which has its own lazy dispatcher).
- **No new ADR.** The decision to ship hook logic as a CLI subcommand is consistent with existing ADR-0002 (CLI-first non-editable wheel) and the project.md convention of console-script entries; no new architectural surface is created.

## Edge Cases

- **Old CLI, new plugin (version-skew window)**: wrapper's `--help` probe (requirement #4) returns nonzero because the subcommand is absent. Wrapper exits 0 silently regardless of which exit code the older CLI emits (no exit-2 hard-code). Hook produces no output; session starts without lifecycle context. Mitigation: CLI_PIN bump (requirement #5) gates the MCP server path so MCP-using users see a clear upgrade prompt; non-MCP users see no upgrade prompt and the skew window persists until the user upgrades CLI or invokes any MCP-mediated flow — accepted trade-off (non-MCP users self-select into a workflow that doesn't depend on lifecycle context injection).
- **New CLI, old plugin (converse skew)**: the old plugin's 460-line bash hook with bare `python3` is still installed. The install-topology bug persists until the user re-runs `/plugin install` to pull the new plugin. CLI upgrade alone does NOT fix the hook; plugin update is a separate user-driven action. Spec acknowledges this surface; mitigation is documentation in CHANGELOG (which the plugin install path surfaces to the user as a release note).
- **CLI missing entirely**: `command -v cortex` fails → wrapper exits 0 silently. Same behavior as a non-cortex repo. No error noise.
- **CLI present but install is corrupt**: `--help` probe returns nonzero from a real failure (segfault, PYTHONHOME pollution, broken venv). Wrapper exits 0 silently (cannot distinguish corrupt-install from missing-subcommand at the wrapper layer). Operator sees no error from the hook. Detection of corrupt-install belongs in `cortex` itself (e.g., `cortex --print-root` would surface the failure), not in the hook. Accepted trade-off.
- **CLI present, subcommand present, run fails (real internal error)**: wrapper's probe succeeds but the actual `cortex hooks scan-lifecycle` invocation returns nonzero. Exit code propagates (requirement #9). Operator sees the failure directly.
- **Cross-checkout dev-loop staleness (non-regression)**: if a developer edits `cortex_command.common.detect_lifecycle_phase` in a local checkout but hasn't reinstalled, the subcommand imports the installed (stale) version. Same as the current bash hook's behavior with `python3` against an installed `cortex_command`. Not introduced by this change; not fixed by it either.
- **macOS Xcode-CLT stub `python3`**: today the hook calls bare `python3` which on a fresh macOS may resolve to a stub that opens an "Install Developer Tools" GUI prompt. After this change, the wrapper never invokes `python3` — only `cortex`. The Xcode-CLT trap is structurally eliminated.
- **`/clear` mid-session**: the Python subcommand's session-state mutation logic covers the four enumerated branches (P1, P2, SC, OR) per requirement #6, with filesystem-state assertions.
- **Concurrent SessionStart in two terminals**: requirement #11 uses `fcntl.flock` on the feature directory to serialize writes. Eliminates the latent race surface the bash hook had relied on timing accidents to mask.
- **Orphaned `.session-owner` files (cleanup divergence from bash)**: the bash hook's chain-migration would resurrect a `.session` inside a complete feature if its `.session-owner` happened to match the stale session-id (a latent bug). The Python port intentionally diverges from bash here — requirement #6's branch (OR) tests verify the port skips orphaned `.session-owner` files when the feature is complete. The golden-file equivalence test (requirement #2) does NOT include this case; it's named in the Non-Requirements as an explicit behavior departure.
- **Partial-write half-states**: the Python port's flock guard (requirement #11) covers in-process serialization but does not protect against process-death between truncate and write (a zero-byte `.session` file). Mitigation: writes use `tempfile.NamedTemporaryFile + os.replace` for atomic single-file rename, eliminating the zero-byte window. Captured under requirement #11's "consistent with one full migration" assertion.

## Changes to Existing Behavior

- **MODIFIED**: `hooks/cortex-scan-lifecycle.sh` shrinks from 460 lines to ~10 lines. Logic moves to `cortex_command/hooks/scan_lifecycle.py`. The `hookSpecificOutput.additionalContext` shape is preserved for all happy-path inputs; the migration-edge-case behavior diverges from bash in one named place (orphan `.session-owner` resurrection — see Edge Cases).
- **MODIFIED**: SessionStart performance — the wrapper spawns Python twice (`--help` probe + actual run) instead of today's three Python boots (preflight + batch + metrics). Net wall-clock cost in the success case is ~150-250ms vs ~300ms today.
- **MODIFIED**: install-hint behavior — today the bash preflight emits a remediation message that itself is wrong (`uv tool install -e .`). After this change, the wrapper has no preflight; the bash-emitted error message is removed entirely. If cortex is missing or the subcommand isn't installed, the wrapper exits 0 silently. Loud errors come from cortex itself or from genuine subcommand failures.
- **MODIFIED**: session-state mutation safety — concurrent SessionStart fires that today rely on timing accidents to not collide are now serialized via `fcntl.flock` (requirement #11). The Python port intentionally diverges from bash on the orphan-`.session-owner` resurrection edge case (which the bash hook handles incorrectly; see Edge Cases).
- **ADDED**: `cortex hooks` subcommand namespace, with `scan-lifecycle` as the first member. The `hooks` namespace is reserved for future hook-implementation subcommands; introducing it now does not preclude later additions.
- **ADDED**: `CLI_PIN` floor enforcement against the version that ships `hooks scan-lifecycle`. MCP-using consumers see a clear upgrade prompt at MCP server startup if the floor is violated. Non-MCP users may experience silent skew until they invoke any MCP-mediated flow.
- **REMOVED**: the bash hook's bare-`python3 -c "import cortex_command.common"` preflight check (along with its remediation message). The cortex shim's existence is the new gate.
- **REMOVED**: the bash hook's orphan-`.session-owner`-to-`.session` resurrection path. The Python port detects orphans and skips them when the feature is complete; the bash behavior is treated as a latent bug not preserved.

## Technical Constraints

- **CLI-first distribution (project.md:7)**: this work reinforces the CLI as the canonical entry point. The cortex shim runs in the right venv regardless of install topology (uv tool, pipx, brew, system pip — verified by research).
- **Lazy-dispatch pattern (cli.py:48-66)**: the new `hooks` subcommand dispatcher must follow this precedent — no eager imports of `cortex_command.hooks.*` at `cli.py` module load.
- **Plugin mirror enforcement (.githooks/pre-commit phase 2-4)**: edits to `hooks/cortex-scan-lifecycle.sh` trigger `just build-plugin` which regenerates the mirror at `plugins/cortex-overnight/hooks/`. The PR must include both files; pre-commit blocks on drift.
- **Parity test (tests/test_lifecycle_phase_parity.py:540-541)**: structurally consumes `hookSpecificOutput.additionalContext`. Golden-file tests (requirement #2) ensure parity is preserved post-refactor.
- **ADR-0002 schema-version envelope**: this work does not modify `--print-root`'s envelope. The new subcommand has its own JSON output shape (the existing `hookSpecificOutput` contract); no envelope versioning needed.
- **CLAUDE.md MUST-escalation policy**: the bash wrapper uses soft positive-routing phrasing. The existing fail-loud semantics in the original hook (preflight exit-1 with remediation) are REMOVED, not softened — the new shape achieves loud-failure via wrapper exit-code propagation when the subcommand returns non-zero-non-2.

## Open Decisions

None remaining at spec time. Q-B (bin/cortex-* and skill-snippet scope) resolved during critical review and Q-B approval — see Non-Requirements entry referencing backlog #248.

## Proposed ADR

None considered.
