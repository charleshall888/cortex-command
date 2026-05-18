# Plan: resolve-cortex-interpreter-via-cli

## Overview

Refactor the 460-line bash SessionStart hook into a thin shell wrapper around a new `cortex hooks scan-lifecycle` subcommand. Python subcommand follows the existing lazy-dispatch pattern at `cortex_command/cli.py:48-66`. The wrapper uses a `--help` probe to detect subcommand presence (no exit-code guessing). New mutation discipline (`fcntl.flock` + `tempfile + os.replace`) eliminates the bash hook's latent race surface and orphan-`.session-owner` resurrection bug.

**Perf note**: the probe-then-exec wrapper spawns Python TWICE per SessionStart (`--help` short-circuits in argparse before any cortex_command imports — ~50-100ms; then the actual subcommand run pays full cold-start). Net wall-clock cost is comparable to today's three-Python-boot bash hook, NOT strictly faster as the earlier spec framing implied. The win is structural (no install-topology bug, no race surface, no orphan bug, vastly cleaner test surface) not raw latency.

## Outline

### Phase 1: Capture baseline + Python subcommand (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
**Goal**: Capture golden-file fixtures from the bash hook BEFORE replacing it, then build `cortex_command.hooks.scan_lifecycle` and wire it as a `cortex hooks scan-lifecycle` subcommand via the existing lazy-dispatch pattern. All hook logic moves from bash to Python.
**Checkpoint**: 6 fixture pairs exist on disk under `tests/fixtures/hooks/scan_lifecycle/`; `cortex hooks scan-lifecycle --help` exits 0; `python3 -c "import cortex_command.cli"` does not import `cortex_command.hooks.*`; module passes its own unit tests at the helper level.

### Phase 2: Hook replacement + version pin (tasks: 11, 12, 13)
**Goal**: Replace the bash hook with a thin wrapper that probes-then-execs the subcommand; regenerate plugin mirror; bump `CLI_PIN` to a concrete `v2.2.0` minor-bump target; update statusline docstring. Phase 1 must complete first so Task 11 has the captured goldens to reference and Task 12 has the working subcommand to exec.
**Checkpoint**: `hooks/cortex-scan-lifecycle.sh` ≤ 15 lines; `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` regenerates clean via `just build-plugin`; `CLI_PIN` set to a parse-valid version; statusline doc references new subcommand.

### Phase 3: Test coverage validation (tasks: 14, 15, 16, 17)
**Goal**: Write the pytest module that consumes Phase 1's captured fixtures and exercises all eleven spec requirements; write the uv-tool smoke test that closes the topology gap.
**Checkpoint**: `just test` exits 0 with all new tests passing.

**Phase ordering note**: Phase 1 has BOTH golden-fixture capture (Task 1) AND Python subcommand build (Tasks 2-10). Task 1 must precede the bash hook replacement (Task 11 in Phase 2) — this ordering is enforced structurally via Task 11's `Depends on: [10, 1]` edge, NOT prose. CLAUDE.md's "prefer structural separation over prose-only enforcement" principle applies.

## Tasks

### Task 1: Capture golden-file fixtures from current bash hook + write pytest module skeleton

- **Files**: `tests/fixtures/hooks/scan_lifecycle/{a..f}.in.json` (6 new fixture inputs), `tests/fixtures/hooks/scan_lifecycle/{a..f}.expected.additionalContext.txt` (6 new expected outputs captured from the existing bash hook), `tests/test_hooks_scan_lifecycle.py` (new, pytest module skeleton), `tests/conftest.py` or new helper `tests/_hook_fixture_helpers.py` (new, fixture-staging helpers)
- **What**: Build fixture-staging infrastructure that stages a temporary repo with arbitrary lifecycle state. For each of cases (a)-(f), stage the appropriate state, run the CURRENT bash hook against it under a working install topology (a venv where bare `python3 -c "import cortex_command"` succeeds — e.g., the local dev checkout's `.venv`), capture the `hookSpecificOutput.additionalContext` substring, and store as the expected output. Write the pytest module with stubs `def test_golden_<case>_additionalContext()` for each case.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Fixture cases per spec req #2: (a) no lifecycle dir, (b) single incomplete feature, (c) multiple incomplete features, (d) post-`/clear` session migration, (e) Morning Review active, (f) pipeline-state with executing/paused/failed features. Reuse the TMPDIR-based fixture pattern from `tests/test_hooks.sh:94-143` but port it to pytest fixtures using `tmp_path`. File count is high (~13) but the work is mechanical bulk fixture-staging — accepted carve-out from the 5-file target. The capture script invokes the bash hook via `bash hooks/cortex-scan-lifecycle.sh` while bare `python3` resolves `cortex_command` from the dev venv. This task must complete before Task 11 (bash hook replacement); enforced via Task 11's explicit dependency.
- **Verification**: `ls tests/fixtures/hooks/scan_lifecycle/ | grep -c '\.in\.json$'` = 6 AND `ls tests/fixtures/hooks/scan_lifecycle/ | grep -c '\.expected\.additionalContext\.txt$'` = 6 AND each `.expected.additionalContext.txt` file is non-empty (`find tests/fixtures/hooks/scan_lifecycle/ -name '*.expected.additionalContext.txt' -empty | wc -l` = 0) AND `pytest tests/test_hooks_scan_lifecycle.py --collect-only 2>&1 | grep -c 'test_golden_'` ≥ 6 (stubs collected).
- **Status**: [ ] pending

### Task 2: Create `cortex_command/hooks/` package skeleton

- **Files**: `cortex_command/hooks/__init__.py` (new, empty), `cortex_command/hooks/scan_lifecycle.py` (new, skeleton with `main()` entry point)
- **What**: Create the new sub-package and skeleton module. `main()` reads stdin JSON, parses session_id/cwd, returns 0 with no output (filled in by subsequent tasks).
- **Depends on**: none
- **Complexity**: simple
- **Context**: New package. `scan_lifecycle.main()` signature is `def main(argv: list[str] | None = None) -> int`. Module imports limited to stdlib at the top — `cortex_command.common` and other intra-package imports go inside the functions that need them (lazy-load discipline per `cortex_command/cli.py:48-66` overnight precedent).
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import main; assert callable(main)"` exits 0.
- **Status**: [ ] pending

### Task 3: Implement input parsing and `cwd/lifecycle` early-exit + CLAUDE_ENV_FILE injection

- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify)
- **What**: Parse stdin JSON; extract `session_id` and `cwd` fields; default cwd to `os.getcwd()` when missing; early-return 0 with no stdout when `{cwd}/cortex/lifecycle/` does not exist. When `CLAUDE_ENV_FILE` is set, append `export LIFECYCLE_SESSION_ID='<session_id>'` to that file using `shlex.quote()`. When `CLAUDE_ENV_FILE` is unset and `session_id` non-empty, log a stderr warning matching bash precedent.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Bash precedent at `hooks/cortex-scan-lifecycle.sh:7-21`. Python equivalent reads stdin via `sys.stdin.read()`, parses with `json.loads`, resolves cwd via `Path(payload.get("cwd") or os.getcwd())`, checks `(cwd / "cortex" / "lifecycle").is_dir()`. The wrapper at `hooks/cortex-scan-lifecycle.sh` (Task 11) does its own pre-check; the Python early-exit is defense-in-depth.
- **Verification**: `echo '{"cwd":"/tmp/no-such-dir"}' | python3 -m cortex_command.hooks.scan_lifecycle` exits 0 with no stdout AND `CLAUDE_ENV_FILE=/tmp/test-env LIFECYCLE_SESSION_ID="" echo '{"session_id":"foo'\''bar","cwd":"<a-tmp-dir-with-cortex/lifecycle/-staged>"}' | python3 -m cortex_command.hooks.scan_lifecycle; grep -c "LIFECYCLE_SESSION_ID='foo'\\\\''bar'" /tmp/test-env` ≥ 1 (shlex.quote correctly handles the embedded quote).
- **Status**: [ ] pending

### Task 4: Implement session-state mutation helpers (no scan_lifecycle.py integration yet)

- **Files**: `cortex_command/hooks/_session_state.py` (new), `.gitignore` (modify — add `cortex/lifecycle/*/.lock`)
- **What**: Implement the four session-state mutation branches per spec req #6 — P1 (Phase 1 migration), P2 (Phase 2 chain migration), SC (single-feature crash-recovery claim), OR (orphan-`.session-owner` skip). Use `fcntl.flock(LOCK_EX)` on a directory-level lockfile per feature; use `tempfile.NamedTemporaryFile + os.replace` for atomic writes. Helpers expose pure-function entry points consumable by Task 8's orchestrator. Update `.gitignore` to exclude the new `.lock` files so they don't show up in `git status` or fixture-staging cleanup.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Bash precedent: lines 38-65 (Phase 1 + Phase 2 migration), lines 343-351 (single-feature claim). Behavior departure from bash on orphan-`.session-owner` (bash line 69 leaves it unchanged when no `.session` matches — Python detects this and skips writing). Lockfile path: `{lifecycle_dir}/{feature}/.lock`. Helper signatures: `def migrate_session_p1(feature_dir: Path, new_id: str, stale_id: str) -> bool`, `def migrate_session_p2(lifecycle_dir: Path, new_id: str, stale_id: str) -> list[Path]`, `def claim_single_feature(feature_dir: Path, new_id: str) -> None`, `def skip_orphan_session_owner(feature_dir: Path) -> bool`. Atomic write helper: `def _atomic_write(path: Path, content: str) -> None`. Lockfile context manager: `@contextmanager def feature_lock(feature_dir: Path)`. **Task 4 does NOT modify scan_lifecycle.py** — integration into the orchestrator is Task 8's job, eliminating the merge collision with Task 5.
- **Verification**: `python3 -c "from cortex_command.hooks._session_state import migrate_session_p1, _atomic_write; from pathlib import Path; import tempfile, os; td = Path(tempfile.mkdtemp()); fd = td / 'feature1'; fd.mkdir(); (fd / '.session').write_text('stale-id'); migrate_session_p1(fd, 'new-id', 'stale-id'); assert (fd / '.session').read_text() == 'new-id' and (fd / '.session-owner').read_text() == 'stale-id'"` exits 0 (verifies P1 branch end-to-end with filesystem assertion) AND `grep -c 'cortex/lifecycle/\*/\.lock' .gitignore` ≥ 1.
- **Status**: [ ] pending

### Task 5: Implement pipeline-state detection helpers (no scan_lifecycle.py integration yet)

- **Files**: `cortex_command/hooks/_pipeline_state.py` (new)
- **What**: Implement pipeline-state detection: read `{lifecycle_dir}/overnight-state.json` (if present); compute `pipeline_context` string per bash precedent at lines 67-163. When phase is "complete" and not all merged features have `feature_complete` events, mark Morning Review active and collect the feature set to suppress. **Task 5 does NOT modify scan_lifecycle.py** — integration is Task 8's job.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: Bash precedent: lines 67-163. Python `json.load` replaces the bash jq/sed fallback dance. Returns a `PipelineState` dataclass with fields `context_string: str`, `morning_review_active: bool`, `morning_review_features: set[str]`. Status-counting becomes a `collections.Counter` over feature statuses. Helper signature: `@classmethod PipelineState.from_path(state_file: Path | None) -> PipelineState` — returns empty state when state_file is None or doesn't exist. **Sequenced after Task 4** to serialize edits within `cortex_command/hooks/` and keep parallel-dispatch dependency graph honest.
- **Verification**: `grep -c "class PipelineState" cortex_command/hooks/_pipeline_state.py` ≥ 1 AND `python3 -c "from cortex_command.hooks._pipeline_state import PipelineState; ps = PipelineState.from_path(None); assert ps.context_string == '' and ps.morning_review_active is False"` exits 0 (empty case) AND `python3 -c "
import json, tempfile
from pathlib import Path
from cortex_command.hooks._pipeline_state import PipelineState
state = {'phase': 'executing', 'features': {'f1': {'status': 'executing'}, 'f2': {'status': 'merged'}, 'f3': {'status': 'failed'}}}
p = Path(tempfile.mkstemp(suffix='.json')[1])
p.write_text(json.dumps(state))
ps = PipelineState.from_path(p)
assert 'executing' in ps.context_string and 'merged' in ps.context_string and 'failed' in ps.context_string and ps.morning_review_active is False
"` exits 0 (inline fixture exercises status-counting + non-complete phase).
- **Status**: [ ] pending

### Task 6: Implement phase-encoding helper

- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify)
- **What**: Add the `_encode_phase(phase, checked, total, cycle)` helper that maps the four bash branches to wire-format strings. Pure function; no side effects.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Bash precedent lines 176-193. Encoding rule: `implement` + total>0 → `"implement:<checked>/<total>"`; `implement` + total==0 → `"implement:0/0"`; `implement-rework` → `"implement-rework:<cycle>"`; otherwise bare phase string. This is intra-file with Tasks 3, 7, 8 but they're chained via depends-on so no merge collision.
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import _encode_phase; assert _encode_phase('implement', 3, 5, 1) == 'implement:3/5' and _encode_phase('research', 0, 0, 1) == 'research' and _encode_phase('implement', 0, 0, 1) == 'implement:0/0' and _encode_phase('implement-rework', 0, 0, 2) == 'implement-rework:2'"` exits 0 (covers all four enumerated branches).
- **Status**: [ ] pending

### Task 7: Implement phase-label and helper functions for context message

- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify)
- **What**: Add `_phase_label(encoded_phase)` mapping per bash precedent lines 196-209. Add small helpers for interrupted-state hint emission (one per `implement:N/M`, `implement-rework:N`, `escalated` case). Pure functions; no I/O.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Bash precedent lines 196-209 for `phase_label`. The interrupted-hint helpers take an encoded phase and return a one-line hint string (or empty when not applicable).
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import _phase_label, _interrupted_hint; assert _phase_label('implement:3/5') == 'Implement (3/5 tasks done)' and _phase_label('escalated') == 'Escalated (REJECTED — needs user direction)' and 'in progress' in _interrupted_hint('implement:3/5', 'feat-x').lower() and _interrupted_hint('implement:0/0', 'feat-x') == ''"` exits 0 (mappings + non-empty hint for in-progress + empty hint for not-started).
- **Status**: [ ] pending

### Task 8: Implement orchestrator integration in scan_lifecycle.py

- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify)
- **What**: Integrate the helpers from Tasks 4, 5, 6, 7 into the main orchestrator flow. Call `cortex_command.common.detect_lifecycle_phase` for each candidate dir; apply the session-state mutation helpers under flock per the determined branch; integrate pipeline-state; build the full additionalContext string (active-feature line, interrupted hints, metrics summary, other-incomplete-features list); regenerate metrics via direct call to `cortex_command.pipeline.metrics.main()`.
- **Depends on**: [4, 5, 7]
- **Complexity**: complex
- **Context**: Bash precedent: full hook lines 211-455 (the orchestrator body). Active feature determination order: (1) session-id match against `.session` files; (2) crash-recovery claim if exactly one incomplete; (3) no match → multi-incomplete prompt. Metrics regen at bash line 417 replaced by direct module-function call. Active-feature decision logic is the most consequential glue — verifier in Task 14 exercises end-to-end.
- **Verification**: `python3 -c "
import json, tempfile, os
from pathlib import Path
from cortex_command.hooks.scan_lifecycle import _build_additional_context
from cortex_command.hooks._pipeline_state import PipelineState
ps = PipelineState(context_string='', morning_review_active=False, morning_review_features=set())
ctx = _build_additional_context(ps, active_feature='myfeat', active_phase='implement:3/5', incomplete=[('myfeat', 'implement:3/5')], lifecycle_dir=Path('/tmp'))
assert 'Active lifecycle: myfeat' in ctx and 'Phase: Implement (3/5 tasks done)' in ctx and 'Interrupted' in ctx
"` exits 0 (asserts the active-feature line, phase label, and interrupted hint are all present in the assembled context).
- **Status**: [ ] pending

### Task 9: Implement output emission (hookSpecificOutput JSON)

- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify)
- **What**: Emit the SessionStart hook contract — JSON object `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<context>"}}` to stdout when `additionalContext` is non-empty; emit nothing when context is empty.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Bash precedent: lines 459-465. Python: `json.dump({"hookSpecificOutput": ...}, sys.stdout, ensure_ascii=False)`. Preserves emoji-bearing context strings byte-for-byte against bash output.
- **Verification**: Stage a tmp repo with one incomplete feature; `echo '{"cwd":"<tmp-repo>","session_id":"abc"}' | python3 -m cortex_command.hooks.scan_lifecycle | jq -r '.hookSpecificOutput.hookEventName'` returns `SessionStart` AND `... | jq -r '.hookSpecificOutput.additionalContext'` is non-empty.
- **Status**: [ ] pending

### Task 10: Wire `cortex hooks scan-lifecycle` subcommand in CLI

- **Files**: `cortex_command/cli.py` (modify)
- **What**: Add a `hooks` subcommand namespace and a `scan-lifecycle` member following the lazy-dispatch pattern at `cli.py:48-66`. Subparser registration at module scope; dispatcher function (e.g., `_dispatch_hooks_scan_lifecycle`) imports `cortex_command.hooks.scan_lifecycle` lazily INSIDE the function and calls `main()`.
- **Depends on**: [9]
- **Complexity**: simple
- **Context**: Existing precedent at `cli.py:48-66` for overnight dispatchers. The `hooks` subparser has its own `--help`; `scan-lifecycle` has its own `--help` argparse-generated. `--help` short-circuits in argparse BEFORE the dispatcher fires, satisfying the wrapper's probe requirement at ~50-100ms per invocation (Python boot + module-level cli.py imports; deferred imports stay deferred).
- **Verification**: `cortex hooks --help` exits 0 and stdout contains "scan-lifecycle" AND `cortex hooks scan-lifecycle --help` exits 0 AND `python3 -c "import cortex_command.cli; import sys; print([m for m in sys.modules if m.startswith('cortex_command.hooks')])"` prints `[]` (lazy-load confirmed — the hooks subtree is not imported by cli module load).
- **Status**: [ ] pending

### Task 11: Replace bash hook with probe-then-exec wrapper

- **Files**: `hooks/cortex-scan-lifecycle.sh` (rewrite — was 460 lines, becomes ≤15)
- **What**: Implement the wrapper per spec requirement #4 — `command -v cortex` + cheap predicates + `--help` probe + exec. Preserves zero cost on non-cortex repos via the cwd/lifecycle dir pre-check.
- **Depends on**: [10, 1]
- **Complexity**: simple
- **Context**: Spec requirement #4 has the wrapper shape verbatim. Preserve `#!/bin/bash` shebang, `set -euo pipefail`. The explicit `Depends on: [..., 1]` edge enforces the structural ordering — Task 1 (golden capture) must complete before this task rewrites the bash hook. Without this edge a parallel scheduler could legitimately run Task 11 before Task 1, destroying the golden-capture reference behavior.
- **Verification**: `wc -l < hooks/cortex-scan-lifecycle.sh` ≤ 15 AND `bash -n hooks/cortex-scan-lifecycle.sh` exits 0 (syntax check).
- **Status**: [ ] pending

### Task 12: Regenerate plugin mirror via `just build-plugin` and bump CLI_PIN to v2.2.0

- **Files**: `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (regenerated mirror), `plugins/cortex-overnight/server.py` (modify line 106 — `CLI_PIN` tuple)
- **What**: Run `just build-plugin` to refresh the plugin mirror at `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh`. Bump `CLI_PIN = ("v2.1.2", "2.0")` to `CLI_PIN = ("v2.2.0", "2.0")` — predicted minor-bump target. The commit MUST include the `[release-type: minor]` marker so the auto-release workflow produces exactly `v2.2.0` on merge.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: `just build-plugin` recipe handles canonical→mirror copy. `.githooks/pre-commit` phase 2-4 enforces no-drift. CLI_PIN bump from v2.1.2 → v2.2.0 requires (a) the `[release-type: minor]` marker on this commit, (b) confirmation that current head is at v2.1.2 (matches existing CLI_PIN), (c) parse-validity assertion in the verification. If a subsequent commit promotes the release to major (via a `[release-type: major]` marker or `BREAKING:` footer in any commit body since the last tag), the auto-release will assign `v3.0.0` instead of `v2.2.0` — CLI_PIN will then be wrong by one major version. Mitigation: pre-merge run `bin/cortex-auto-bump-version --dry-run` and verify the predicted tag matches CLI_PIN.
- **Verification**: `grep -c '^CLI_PIN = ("v2\.1\.2", "2\.0")$' plugins/cortex-overnight/server.py` = 0 (old pin removed) AND `grep -c '^CLI_PIN = ("v2\.2\.0", "2\.0")$' plugins/cortex-overnight/server.py` = 1 (exact new pin present) AND `python3 -c "from packaging.version import Version; from plugins.cortex_overnight.server import CLI_PIN; v = Version(CLI_PIN[0].lstrip('v')); assert str(v).startswith('2.2')"` exits 0 (parse-validity + correct major.minor) AND `bin/cortex-auto-bump-version --dry-run 2>&1 | grep -c '2\.2\.0'` ≥ 1 (auto-bump dry-run agrees on the target) AND `git diff --quiet -- plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` exits 0 after `just build-plugin` (no plugin-mirror drift).
- **Status**: [ ] pending

### Task 13: Update statusline docstring to reference new subcommand

- **Files**: `claude/statusline.sh` (modify — comment block around line 377-390)
- **What**: Update the "bash-only mirror" docstring block to reference `cortex hooks scan-lifecycle` as the canonical SessionStart hook entry point. Preserve the "bash-only mirror" framing for the statusline's local phase-detection (which remains a separate parity-tested bash mirror of `cortex_command.common.detect_lifecycle_phase`).
- **Depends on**: [11]
- **Complexity**: trivial
- **Context**: Statusline's parity-mirror is at `claude/statusline.sh:377+`. After this work, the SessionStart hook is Python (subcommand-mediated), but the statusline mirror remains bash (no Python boot tolerated on statusline render). Update prose accordingly.
- **Verification**: `grep -c "bash-only mirror" claude/statusline.sh` ≥ 1 AND `grep -c "cortex hooks scan-lifecycle" claude/statusline.sh` ≥ 1.
- **Status**: [ ] pending

### Task 14: Implement golden-file equivalence tests + session-mutation table-driven tests

- **Files**: `tests/test_hooks_scan_lifecycle.py` (modify)
- **What**: Fill out the test module: (1) `test_golden_<case>_additionalContext` for each of the 6 fixture cases — invokes `cortex_command.hooks.scan_lifecycle.main()`, captures stdout, asserts emitted `additionalContext` matches the golden text captured in Task 1; (2) `test_session_mutation_P1`, `_P2`, `_SC`, `_OR` — table-driven, each stages a known lifecycle state, invokes the module, asserts post-call filesystem state of `.session` and `.session-owner` per spec req #6.
- **Depends on**: [1, 4, 8]
- **Complexity**: complex
- **Context**: pytest fixtures use `tmp_path` for per-test repo staging. Stdout capture via `capsys`. The four session-mutation tests stage specific pre-states (e.g., OR: write `.session-owner` with stale ID, ensure no `.session`, mark feature complete; assert no new `.session` after the call).
- **Verification**: `pytest tests/test_hooks_scan_lifecycle.py -v -k "golden or session_mutation"` exits 0 with ≥10 test functions passing (6 golden + 4 session-mutation).
- **Status**: [ ] pending

### Task 15: Implement wrapper behavior tests (probe + propagate)

- **Files**: `tests/test_hooks_scan_lifecycle.py` (modify — add wrapper tests), `tests/fixtures/cortex_stubs/` (new dir for stub cortex shims)
- **What**: Two wrapper tests per spec req #9: (a) `test_wrapper_probe_failure_silent_degrade` — stub `cortex` whose `--help` returns nonzero, run wrapper, assert exit 0; (b) `test_wrapper_probe_pass_run_fail_propagates` — stub returns 0 from `--help` but 1 from actual call, assert wrapper exits 1.
- **Depends on**: [11, 14]
- **Complexity**: simple
- **Context**: Stubs are simple bash scripts; PATH manipulation via `monkeypatch.setenv("PATH", ...)`. Wrapper invocation via `subprocess.run`.
- **Verification**: `pytest tests/test_hooks_scan_lifecycle.py -v -k "wrapper_probe"` exits 0.
- **Status**: [ ] pending

### Task 16: Implement concurrent-write test for fcntl.flock serialization

- **Files**: `tests/test_hooks_scan_lifecycle.py` (modify)
- **What**: Per spec req #11: `test_session_mutation_concurrent_writes_serialized` spawns two concurrent invocations of `cortex_command.hooks.scan_lifecycle.main()` (via `multiprocessing.Process`) against the same feature directory with different session_ids; asserts the final filesystem state is consistent with ONE complete migration (not partial).
- **Depends on**: [4, 14]
- **Complexity**: simple
- **Context**: `multiprocessing.Process` + `Barrier` to synchronize start. Loop the concurrent invocation 5+ times to surface any race window.
- **Verification**: `pytest tests/test_hooks_scan_lifecycle.py::test_session_mutation_concurrent_writes_serialized -v` exits 0.
- **Status**: [ ] pending

### Task 17: Add uv-tool smoke test script + just recipe

- **Files**: `tests/smoke_uv_tool_hook.sh` (new), `justfile` (modify — add `test-smoke-hook` recipe)
- **What**: Shell script per spec req #7: confirms `cortex` resolves to a uv-tool venv (via `realpath`); stages a temp repo with all six fixture lifecycle states; invokes the bash wrapper with each fixture input; asserts emitted `additionalContext` matches the Task 1 golden fixture; exits 0 on success. When run on a non-uv-tool install, the script prints a clear skip message + a suggested command for setting up a uv-tool install for verification, then exits 0.
- **Depends on**: [1, 11, 14]
- **Complexity**: simple
- **Context**: Smoke script uses `jq` to extract `additionalContext`. Topology detection: `[[ "$(realpath "$(command -v cortex)")" == *"share/uv/tools/cortex-command"* ]]`. **Acceptance handling for dev-checkout implementers**: when the smoke test skips on a non-uv-tool topology, the implementer documents (in the PR description) that they staged a uv-tool install separately for verification, OR the merge gate runs in a CI environment that DOES have a uv-tool install.
- **Verification**: `bash -n tests/smoke_uv_tool_hook.sh` exits 0 AND `just --list 2>&1 | grep -c "test-smoke-hook"` ≥ 1 AND on a system with `cortex` resolving to uv-tool venv, `just test-smoke-hook` exits 0 with all 6 cases passing AND on a system without uv-tool, `just test-smoke-hook` exits 0 with a printed skip message + suggested-setup command.
- **Status**: [ ] pending

## Risks

- **Golden-fixture capture timing slip (mitigated structurally)**: Task 11 (bash hook replacement) must run after Task 1 (golden capture); enforced via Task 11's explicit `Depends on: [10, 1]` edge, not prose. A scheduler honoring depends-on edges cannot regress this ordering.

- **Same-file merge collision (mitigated structurally)**: Tasks 4, 5 produce helper modules only (`_session_state.py`, `_pipeline_state.py`); they do NOT modify `cortex_command/hooks/scan_lifecycle.py`. The orchestrator integration happens in Task 8, sequenced after 4, 5, 6, 7. Tasks 6 and 7 share `scan_lifecycle.py` but chain via `Depends on: [6]` on Task 7.

- **CLI_PIN auto-release coordination**: Task 12 bumps `CLI_PIN` to `v2.2.0` predicated on the commit including `[release-type: minor]`. If a concurrent commit lands a `[release-type: major]` marker or a `BREAKING:` footer before merge, the auto-release will produce `v3.0.0` not `v2.2.0` — CLI_PIN will be wrong. Mitigation: Task 12 verification includes `bin/cortex-auto-bump-version --dry-run` agreement check before commit.

- **Wrapper double-boot perf cost**: the wrapper spawns Python TWICE per SessionStart (~50-100ms probe + ~150ms actual = ~200-250ms vs ~300ms three-boot bash). Net wash, not a clear win. Documented in Overview; not a regression worth blocking.

- **Lockfile side effects**: new `cortex/lifecycle/*/.lock` files land on disk. Task 4 updates `.gitignore` to exclude. Stale lockfile risk on process crash is bounded (`fcntl.flock` releases on file-descriptor close, which Python guarantees on process exit). Persistent stale `.lock` files at most cause an empty-file noise on disk; the lock itself is per-fd, not per-file-content.

- **fcntl.flock semantics on non-local filesystems**: Cortex repos typically live on local POSIX filesystems where flock is reliable. NFS / network mounts have weaker flock semantics. Accepted limitation; documented in code comment near the flock call.

- **Migration semantics drift**: The bash hook's session-state mutation logic has subtle write-order and read-write timing semantics. Mitigation: Task 14's four table-driven mutation tests assert filesystem state post-call. Task 16's concurrency test surfaces inter-write races that timing accidents may have masked in bash.

- **Acceptance verifiability on dev-checkout topology**: Acceptance requires uv-tool smoke test passes locally — but most contributors run editable pip installs. Task 17 lets the smoke test gracefully skip with a setup suggestion; the implementer is responsible for either staging a uv-tool install for verification OR documenting in the PR description that CI will run the smoke test in a uv-tool environment.

## Acceptance

All 11 spec requirements verified: subcommand exists and lazy-loads; golden-file equivalence under working topology; session-mutation paths covered with filesystem assertions; `fcntl.flock` + atomic writes serialize concurrent operations; wrapper ≤ 15 lines using probe-then-exec pattern; `CLI_PIN` parse-valid and consistent with `bin/cortex-auto-bump-version --dry-run`; plugin mirror clean against canonical; statusline docstring updated; `just test` exits 0 with all new tests passing; uv-tool smoke test passes on a real uv-tool install (run locally OR run in CI; if locally-skipped on dev-checkout, PR description documents the alternate verification path).
