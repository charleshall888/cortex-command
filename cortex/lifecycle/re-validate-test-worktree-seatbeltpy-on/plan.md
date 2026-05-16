# Plan: re-validate-test-worktree-seatbeltpy-on

## Overview
Replace the env-var-gated skip in `tests/test_worktree_seatbelt.py` with a kernel-level capability probe anchored on `<repo>/.git/HEAD`, fix the latent `os` NameError in the smoke runner, register a new `seatbelt_probe` event, and add a session-start probe module wired into the overnight runner that spawns `claude -p` under sandbox-active settings, parses pytest output from `$TMPDIR/`-resident result files (bypassing model paraphrase), and emits a dual JSONL event to both the per-session log and a top-level `seatbelt-probe.log`. The probe never blocks the session; its outcome surfaces in the morning report.

## Outline

### Phase 1: Test correctness foundation (tasks: 1, 2, 3, 4)
**Goal**: Remove brittle env-var gating, close the latent smoke-runner NameError, register the new event, and update the parent lifecycle's stale acceptance command. After this phase, `tests/test_worktree_seatbelt.py` correctly runs under any real Seatbelt-active session and skips clearly elsewhere; smoke is importable in all auth branches; `bin/cortex-check-events-registry --audit` accepts the new `seatbelt_probe` row.
**Checkpoint**: `uv run pytest tests/test_worktree_seatbelt.py -v` outside an active sandbox exits 0 with `2 skipped` and the new kernel-probe reason; `uv run python3 -c "import cortex_command.overnight.smoke_test"` exits 0; `bin/cortex-check-events-registry --audit` exits 0.

### Phase 2: Recurring probe at overnight session-start (tasks: 5, 6, 7, 8, 9)
**Goal**: Introduce the `seatbelt_probe` module, unit-test its parse and failure branches, wire it into the runner's session-start sequence after the auth probe and before round 1, surface its outcome in the morning report, and document the cadence.
**Checkpoint**: `uv run pytest tests/test_seatbelt_probe.py -v` exits 0; after an overnight session starts, the `seatbelt_probe` event appears in both the per-session `overnight-events.log` and the top-level `cortex/lifecycle/seatbelt-probe.log`; the morning report renders a `Seatbelt probe:` line; `docs/overnight-operations.md` has a "Seatbelt probe" section.

## Tasks

### Task 1: Add `import os` to smoke runner

- **Files**: `cortex_command/overnight/smoke_test.py`
- **What**: Add `import os` to the top-level imports of `cortex_command/overnight/smoke_test.py`, closing the latent `NameError` at lines 173 and 253 where `os.environ.get(...)` is called in the OAuth-token / auth-fallback branches.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The file currently uses `os.environ.get(...)` at lines 173 and 253 without an `import os` at module top. Place the import alphabetically among existing stdlib imports. Spec R2; spec "Changes to Existing Behavior" item 2.
- **Verification**: `grep -c "^import os" cortex_command/overnight/smoke_test.py` returns `1` AND `uv run python3 -c "import cortex_command.overnight.smoke_test as m; assert hasattr(m, 'os')"` exits 0 — pass if both conditions hold.
- **Status**: [x] completed

### Task 2: Replace env-var skipif with kernel-probe fixture in `tests/test_worktree_seatbelt.py`

- **Files**: `tests/test_worktree_seatbelt.py`
- **What**: Remove both `@pytest.mark.skipif(os.environ.get("CLAUDE_CODE_SANDBOX") != "1", ...)` decorators on `test_python_resolver_default_passes_probe_under_seatbelt` and `test_hook_emitted_path_passes_probe_under_seatbelt`. Add a module-scoped pytest fixture named `seatbelt_active` that uses the existing `_repo_root()` helper to compute `<repo>/.git/HEAD`, attempts `fd = os.open(repo_root / ".git" / "HEAD", os.O_WRONLY)` (no `O_TRUNC`, no `O_CREAT`), and routes by exception: `PermissionError` → fixture returns `True` (sandbox enforcing); successful open → close FD and call `pytest.skip("sandbox not active (open-for-write to .git/HEAD succeeded)")`; `FileNotFoundError` → `pytest.fail("kernel probe sentinel .git/HEAD missing; run from a git checkout")`. Add `seatbelt_active` as the single parameter to both test functions. Preserve the test bodies verbatim (assertions, cleanup, etc.). Drop the now-unused `SEATBELT_REASON` constant and update the module docstring's reference to `CLAUDE_CODE_SANDBOX=1` to describe the kernel-probe gate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Fixture signature: `@pytest.fixture(scope="module")` then `def seatbelt_active() -> bool`. `_repo_root()` already exists in the file at the top level. The `<repo>/.git/HEAD` path is a member of `GIT_DENY_SUFFIXES` in `cortex_command/overnight/sandbox_settings.py:55-60` and is denied by `build_orchestrator_deny_paths`. Test bodies start at lines 48–60 and 67–95. Spec R1; spec "Edge Cases" item "Sentinel path `.git/HEAD` is missing"; spec "Technical Constraints" item "`os.O_WRONLY` open without `O_TRUNC` is safe".
- **Verification**: `uv run pytest tests/test_worktree_seatbelt.py -v` from a plain shell exits 0 with stdout containing `2 skipped` and the reason text `sandbox not active (open-for-write to .git/HEAD succeeded)` — pass if both conditions hold. (Pass-under-Seatbelt branch is verified end-to-end by Task 7's runner integration; per-test sandbox-active verification is interactive/session-dependent.)
- **Status**: [x] completed

### Task 3: Register `seatbelt_probe` row in events registry

- **Files**: `bin/.events-registry.md`
- **What**: Append one row to the events-registry table with `event = seatbelt_probe`, `targets = overnight-events-log | seatbelt-probe-log`, `scan_coverage = manual`, `producers = cortex_command/overnight/seatbelt_probe.py (run_probe)`, `consumers = cortex_command/overnight/report.py`, lifecycle status `live`, today's date, and notes describing the schema (`ts, event=seatbelt_probe, session_id, result: ok|failed, pytest_exit_code: int|null, pytest_summary: str, stdout_path: str|null, stdout_sha256: hex|null, softfail_active: bool, source: seatbelt_probe.run_probe`) and the kernel-probe gate (`.git/HEAD` write attempt under sandbox-active settings).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The existing `auth_probe` row at `bin/.events-registry.md:118` is the closest precedent (dual targets, `scan_coverage: manual`, Python-source emission). Match its column layout exactly. Spec R3; spec "Technical Constraints" item "No prompt-corpus emission".
- **Verification**: `grep -c "\bseatbelt_probe\b" bin/.events-registry.md` returns `>= 1` AND `bin/cortex-check-events-registry --audit` exits 0 — pass if both conditions hold.
- **Status**: [x] completed

### Task 4: Update parent lifecycle's R10 acceptance command

- **Files**: `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md`
- **What**: Amend `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` line 36 and any sibling references in that file (search for `CLAUDE_CODE_SANDBOX=1 pytest`) to drop the obsolete `CLAUDE_CODE_SANDBOX=1` env-var prefix from the R10 re-attestation command, replacing it with `pytest tests/test_worktree_seatbelt.py -q` (run from inside an active Claude Code session). Append a one-sentence note that the new gate is a kernel-level probe defined by this lifecycle (link the slug `re-validate-test-worktree-seatbeltpy-on`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: This is a should-have item per the spec's priority block. The parent lifecycle's plan.md may also mention the old command — a follow-up search of `cortex/lifecycle/restore-worktree-root-env-prefix/plan.md` should catch any sibling reference; if found, amend it the same way. Spec R7.
- **Verification**: `grep -c "CLAUDE_CODE_SANDBOX=1 pytest" cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` returns `0` AND `grep -c "kernel-level probe" cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` returns `>= 1` — pass if both conditions hold.
- **Status**: [x] completed

### Task 5: Implement `seatbelt_probe.py` module

- **Files**: `cortex_command/overnight/seatbelt_probe.py`
- **What**: Create the module exposing a `ProbeResult` `@dataclass` and a public `run_probe(session_dir: Path, home_repo: Path) -> ProbeResult` function. The module spawns `claude -p` under orchestrator-style sandbox settings, has the spawned agent invoke pytest via Bash, reads pytest exit code and summary from `$TMPDIR/`-resident files the agent's command writes (bypassing model paraphrase), computes `stdout_sha256`, and constructs the `ProbeResult`. On any failure mode (claude binary missing, non-zero exit, result-file missing, exit != 0, count assertion fails), populate `result="failed"` with a one-line `cause`. The module emits no events itself — the runner (Task 7) is the dual emitter.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - `ProbeResult` fields and types: `result: Literal["ok","failed"]`, `pytest_exit_code: Optional[int]`, `pytest_summary: str`, `stdout_path: Optional[Path]`, `stdout_sha256: Optional[str]`, `cause: Optional[str]`.
  - Helpers to reuse from `cortex_command/overnight/sandbox_settings.py`: `build_orchestrator_deny_paths(home_repo, integration_worktrees={})`, `build_sandbox_settings_dict(deny_paths, allow_paths=[resolved-$TMPDIR], soft_fail=read_soft_fail_env())`, `write_settings_tempfile(session_dir, settings)`, `register_atexit_cleanup(tempfile_path)`, `read_soft_fail_env()`. Note: this probe deliberately uses orchestrator-style deny set (NOT `build_dispatch_allow_paths`) with a minimal explicit `allow_paths=[resolved-$TMPDIR]` so `$TMPDIR/` is the only writable target.
  - `$TMPDIR/` resolution: `os.environ.get("TMPDIR", "/tmp")`, then `Path(...).resolve()` for the allow-list entry.
  - UUID-randomized basenames: `output_path = Path(tmpdir) / f"cortex-seatbelt-output-{uuid.uuid4()}.txt"`, `result_path = Path(tmpdir) / f"cortex-seatbelt-result-{uuid.uuid4()}.txt"`.
  - Prompt template: the verbatim three-paragraph text from spec R4 (the block beginning "Execute exactly this Bash command in a single tool call and exit immediately…"), with `<output_path>` and `<result_path>` substituted at build time. Treat the spec's text as the canonical source; do not paraphrase.
  - Subprocess invocation pattern: follow the `cortex_command/overnight/runner.py:1029` stdout-to-file pattern (avoid Popen pipe-buffer deadlock). Spawn: `claude -p <prompt> --settings <tempfile-path> --dangerously-skip-permissions --max-turns 4 --output-format=json`. Capture stdout to a file under `session_dir` (e.g., `session_dir / "seatbelt-probe-claude-stdout.json"`).
  - Result parsing: open `result_path`, regex `r"exit=(-?\d+)"`, extract exit code; open `output_path`, regex separately `r"(\d+) passed"`, `r"(\d+) failed"`, `r"(\d+) skipped"`, `r"(\d+) error"` and tally; compute `hashlib.sha256(output_path.read_bytes()).hexdigest()`.
  - `result="ok"` iff: (i) claude returned exit 0, (ii) `result_path.exists()` and parsed `exit=0`, (iii) `passed >= 2 AND failed == 0 AND skipped == 0 AND error == 0`. Otherwise `result="failed"` with a one-line `cause`.
  - `cause` strings to use: `"claude binary not found"` (FileNotFoundError); `"claude exit nonzero: <code>, stderr tail: <last 200 chars>"`; `"result file not written; agent likely paraphrased instead of executing the bash command"`; `"pytest exit nonzero: <code>"`; `"unparseable pytest summary"`; `"result file empty"`; `"skipped count > 0; sandbox not enforcing"`.
  - The module does not write events. Spec R4; spec "Edge Cases" items "claude binary missing", "claude -p returns non-zero", "agent paraphrases", "pytest summary line format change", "test count drift", "$TMPDIR resolves to a denied path", "concurrent probe invocations".
- **Verification**: `uv run python3 -c "from cortex_command.overnight.seatbelt_probe import run_probe, ProbeResult; import dataclasses; assert dataclasses.is_dataclass(ProbeResult); assert callable(run_probe)"` exits 0 — pass if exit 0. (Behavioral correctness is covered by Task 6's unit tests, which mock the subprocess boundary.)
- **Status**: [x] completed

### Task 6: Unit tests for `seatbelt_probe`

- **Files**: `tests/test_seatbelt_probe.py`
- **What**: Create a new test file covering the five failure-mode branches of `run_probe`: (i) successful parse → `result="ok"`; (ii) missing result file → `result="failed"` with cause containing "result file"; (iii) exit-code != 0 → `result="failed"`; (iv) skipped > 0 → `result="failed"`; (v) `FileNotFoundError` on `claude` binary → `result="failed"` with cause "claude binary not found". Tests mock the subprocess boundary (e.g., `monkeypatch.setattr` on `subprocess.run` or `subprocess.Popen`) and use a `tmp_path` fixture for the `session_dir` and a controlled `$TMPDIR` via `monkeypatch.setenv` so the result/output files are written to a temp location the tests pre-populate or leave unpopulated.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Test pattern: each test calls `run_probe(tmp_path, home_repo=Path.cwd())` after pre-staging the `$TMPDIR/`-resident output_path/result_path contents the mocked subprocess "would" have written, then asserts on `ProbeResult` fields. For branch (v), patch `subprocess.run` (or `Popen`) to raise `FileNotFoundError`. For branch (iii), pre-write `exit=1` to the result file. For branch (iv), pre-write a pytest summary containing `1 skipped`. Use `pytest.fixture` for shared setup if it reduces duplication. Spec R4 acceptance — the five branches.
- **Verification**: `uv run pytest tests/test_seatbelt_probe.py -v` exits 0 — pass if exit 0 and 5 tests pass.
- **Status**: [x] completed

### Task 7: Wire `run_probe` into runner session-start with dual JSONL emission

- **Files**: `cortex_command/overnight/runner.py`
- **What**: In the `run` function in `cortex_command/overnight/runner.py`, insert a call to `seatbelt_probe.run_probe(session_dir, home_repo)` immediately AFTER the existing `auth.resolve_and_probe(...)` block at line 2044 (specifically, after the `if not probe_result.ok: ... return 1` block ending at line 2054) and BEFORE the main round loop's `start_wall = time.monotonic()` at line 2057. After `run_probe` returns, build a single JSONL event matching the spec R5 schema (`{"ts", "event": "seatbelt_probe", "session_id", "result", "pytest_exit_code", "pytest_summary", "stdout_path", "stdout_sha256", "softfail_active", "source": "seatbelt_probe.run_probe"}`) and atomically append it to BOTH `events_path` (the per-session `overnight-events.log`) AND `cortex/lifecycle/seatbelt-probe.log` (top-level, tracked). Wrap the entire `run_probe` call in a `try`/`except Exception` that translates an unhandled probe exception to a `result="failed"` event with `cause=<exception text>` and continues — session startup must not abort on probe failure.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**:
  - Imports: add a module-level import of `seatbelt_probe` from the `cortex_command.overnight` package alongside the existing `auth` import in this file.
  - `home_repo` is already in scope as `repo_path` (line 2017 `os.environ["CORTEX_REPO_ROOT"] = str(repo_path)`).
  - `softfail_active` field value: call `sandbox_settings.read_soft_fail_env()` at event-construction time.
  - Atomic write: use `cortex_command.common.atomic_write` in append mode (the existing pattern in `cortex_command/pipeline/state.py:288` log_event uses single-line append; follow that).
  - Top-level log path: `Path("cortex/lifecycle/seatbelt-probe.log")` resolved against the repo root; ensure the parent dir exists (it should, since `cortex/lifecycle/` exists).
  - The runner does NOT transition state on `result=failed` — no `state.phase` mutation, no `state_module.save_state` call from this block.
  - Spec R5; spec "Edge Cases" item "`runner.py`-context probe failure".
- **Verification**: `grep -n "seatbelt_probe.run_probe\|seatbelt-probe.log" cortex_command/overnight/runner.py | wc -l` returns `>= 2` (at least one call site and one top-level log reference) — pass if count >= 2. End-to-end emission verification is interactive/session-dependent: starting an actual overnight session and inspecting both logs requires the operator's overnight cadence.
- **Status**: [x] completed

### Task 8: Extend morning-report renderer with `Seatbelt probe` line

- **Files**: `cortex_command/overnight/report.py`
- **What**: Add a new renderer function `render_seatbelt_probe_header(data: ReportData) -> str` that scans `data.events` for the most recent `seatbelt_probe` event and produces a single line: `Seatbelt probe: <result> | pytest_summary="<summary>" | softfail_active=<bool>`. When no `seatbelt_probe` event is present, return the empty string. Splice the call into `generate_report` immediately after `render_soft_fail_header` (around line 1957) so the line renders in the session-header band, before Executive Summary. Wrap the line in a blank line above and below when non-empty, mirroring the soft-fail header treatment.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Existing pattern at `cortex_command/overnight/report.py:324-343` (`render_soft_fail_header`) is the closest precedent: scan `data.events`, return a single header string or empty. `ReportData.events` is a `list[dict]` per the dataclass at line 67. The new function reads `evt.get("event") == "seatbelt_probe"` and pulls `result`, `pytest_summary`, `softfail_active` fields. If multiple `seatbelt_probe` events exist (multiple sessions reported in one window), select the last one chronologically (iterate the events list in order and overwrite the captured event each match — events are append-only and chronological per `pipeline.md:129`). Spec R6.
- **Verification**: After implementation, a synthetic test invocation `uv run python3 -c "from cortex_command.overnight.report import render_seatbelt_probe_header; from cortex_command.overnight.report import ReportData; from datetime import datetime; data = ReportData(date='2026-05-16', state=None, events=[{'event':'seatbelt_probe','result':'ok','pytest_summary':'passed=2 failed=0 skipped=0 error=0','softfail_active':False}], batch_results=[], deferred=[], paused=[], escalations=[]); out = render_seatbelt_probe_header(data); assert out.startswith('Seatbelt probe: '); print('OK')"` exits 0 with stdout `OK`. (Adjust the `ReportData` constructor kwargs to match the actual dataclass field set discovered during implementation.) — pass if exit 0 and stdout contains `OK`.
- **Status**: [x] completed

### Task 9: Document the Seatbelt probe in overnight operations

- **Files**: `docs/overnight-operations.md`
- **What**: Add a new section titled `## Seatbelt probe` (or `### Seatbelt probe` if a section above it owns the H2) describing: the kernel-probe gate (`.git/HEAD` write attempt), the session-start cadence (after auth probe, before round 1), the F-row schema (verbatim from spec R5), the dual emission targets (`cortex/lifecycle/sessions/<id>/overnight-events.log` and top-level `cortex/lifecycle/seatbelt-probe.log`), and the non-blocking failure mode (probe failure surfaces in the morning report but does not pause the session). Cross-link the parent lifecycle slug `restore-worktree-root-env-prefix` for context on what regression the probe guards against.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Place the section near the existing Sandbox/Auth-probe discussion (search for `auth_probe` or `Sandbox enforcement` to find the right neighborhood). The file currently ends at line 713; choose insertion point by topic, not file end. Spec R8; spec "Non-Requirements" item "Hard-blocking the overnight session on probe failure".
- **Verification**: `grep -cE "^#+ Seatbelt probe" docs/overnight-operations.md` returns `>= 1` AND `grep -c "cortex/lifecycle/seatbelt-probe.log" docs/overnight-operations.md` returns `>= 1` AND `grep -c "morning report" docs/overnight-operations.md` returns `>= 1` — pass if all three conditions hold.
- **Status**: [x] completed

## Risks

- **Probe spawn cost on session start (~5–15s).** Every overnight session now pays a probe latency before round 1. Tradeoff: this is the cadence the user explicitly chose ("every overnight session re-validates") and is small relative to a full overnight; alternative cadences (cron, pre-commit) are deferred per spec Non-Requirements.
- **Probe is a real failure surface (claude binary, rate limit, agent paraphrase).** A flake produces a `result=failed` event with no session-level impact, but the morning report will read "Seatbelt probe: failed" — operators must distinguish probe flake from a real regression in `resolve_worktree_root()`. Mitigation: the `cause` field carries a one-line diagnostic that should distinguish these (`"claude binary not found"` vs `"skipped count > 0"`).
- **R7's parent-lifecycle amendment touches a closed lifecycle's spec.** The amendment is documentation-only (no production-code change in the parent), but if the parent's plan.md or events.log references the old command verbatim, those references will be subtly stale. Task 4's Files list includes a search for sibling references; if `plan.md` is affected, amend it as part of Task 4.
- **R5 wire site is a single line range.** The "after `auth.resolve_and_probe` ... before main round loop" window is currently lines 2055–2057 in `runner.py`. If a parallel commit lands code in that range before this lifecycle merges, the wire site shifts. Mitigation: Task 7's Context names the surrounding symbols (`auth.resolve_and_probe`, `start_wall = time.monotonic()`) so a future rebase can re-anchor by symbol, not line number.
- **`$TMPDIR/`-resident output files are not cleaned up explicitly.** OS-level `$TMPDIR/` reaping handles them eventually; if a tighter cleanup is wanted, a follow-up could add `register_atexit_cleanup` on the output/result paths. Out of scope for this lifecycle.
