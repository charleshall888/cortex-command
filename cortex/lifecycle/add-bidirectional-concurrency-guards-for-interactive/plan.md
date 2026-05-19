# Plan: add-bidirectional-concurrency-guards-for-interactive

## Overview

Build a new `cortex_command/interactive_lock.py` module exposing five primitives (`acquire_lock`, `read_lock`, `verify_live_owner`, `release_lock`, `scan_live_locks`) and a `cortex-interactive-lock` console-script entry, then wire its consumers in two directions: (a) interactive preflight in `skills/lifecycle/references/implement.md` §1 (overnight-active rejection mirror + lock acquisition between user-selection and worktree-creation), and (b) overnight per-round inverse scan in `cortex_command/overnight/orchestrator.py:run_batch` via a newly-extracted `compute_eligible_features` helper. Env-var-primary identity (`CLAUDE_CODE_SESSION_ID`) with auxiliary PID+start_time liveness; no `state.features` mutation, no `save_state`; six new events registered in `bin/.events-registry.md`. Two-phase landing (Phase 1 interactive-path; Phase 2 overnight-path).

## Outline

### Phase 1: Interactive-path guards (tasks: 1, 2, 3, 4, 5)
**Goal**: Helper module with the five primitives + per-feature `interactive.pid` writer, sidecar bash for the overnight-active probe (single source for §1a.iii + the new §1 mirror), and skill-prose wiring of the new preflight steps between user-selection and worktree-creation. Five of the six new events registered.
**Checkpoint**: `pytest tests/test_interactive_lock.py tests/test_interactive_lock_sandbox.py` exits 0 on macOS (sandbox test skipped on Linux); `which cortex-interactive-lock` resolves; `grep -c '\.runner\.lock' skills/lifecycle/references/implement.md` = 0; `grep -c 'cortex-interactive-lock acquire' skills/lifecycle/references/implement.md` ≥ 1; `cortex-check-events-registry --audit` exits 0.

### Phase 2: Overnight-path guard (tasks: 6, 7, 8)
**Goal**: Refactor `run_batch` to call an exported `compute_eligible_features(feature_names, project_root) -> (eligible, skip_events)` helper at each round entry; emit `feature_skipped_interactive_active` per excluded feature with non-empty `rationale`. Register the sixth event. End-to-end integration test exercising all three production paths.
**Checkpoint**: `pytest tests/test_orchestrator_inverse_scan.py tests/test_bidirectional_concurrency_contract.py` exits 0; `cortex-check-events-registry --audit` exits 0; `grep -c 'save_state\|state.features =\|overnight_state\.features =' cortex_command/overnight/orchestrator.py` shows no new mutations in the diff vs. main for the new scan code path.

## Tasks

### Task 1: Add `cortex_command/interactive_lock.py` helper module, register `cortex-interactive-lock` console-script, and add four Phase-1-emitted events-registry rows

- **Files**:
  - `cortex_command/interactive_lock.py` (new)
  - `pyproject.toml` (modify `[project.scripts]` — register `cortex-interactive-lock = "cortex_command.interactive_lock:main"`)
  - `bin/.events-registry.md` (modify — four new rows: `interactive_lock_acquired`, `interactive_lock_rejected_concurrent`, `interactive_lock_stale_recovered`, `interactive_lock_released`)
- **What**: Foundation module exposing the five lock primitives plus a `main()` argparse entry implementing the `acquire`, `release`, `inspect`, and `force-release` subcommands. All path resolution flows through `_resolve_user_project_root()` from `cortex_command.common`; lock writes are atomic (tempfile + `os.replace`, mode 0o600) at `_resolve_user_project_root() / "cortex/lifecycle/{slug}/interactive.pid"`. Emits four of the six new events to `cortex/lifecycle/{slug}/events.log`.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Module structure (function signatures only — see R1 of spec):
    - `acquire_lock(feature_slug: str) -> bool`
    - `read_lock(feature_slug: str) -> dict | None`
    - `verify_live_owner(lock: dict) -> bool`
    - `release_lock(feature_slug: str) -> None`
    - `scan_live_locks(project_root: Path) -> set[str]`
    - `main(argv: list[str] | None = None) -> int` (argparse — subcommands `acquire`, `release`, `inspect`, `force-release`)
  - Lock JSON schema (R3): `{"schema_version": 1, "magic": "cortex-interactive-lock", "session_id": <str | null>, "pid": <int>, "start_time": <float | null>, "acquired_at": <ISO 8601 str>}`. `session_id` reads `os.environ.get("CLAUDE_CODE_SESSION_ID")` (may be `None` — degraded mode flag in event payload). `pid` is `os.getppid()`. `start_time` is `psutil.Process(pid).create_time()` rounded to milliseconds, catching `(psutil.AccessDenied, psutil.NoSuchProcess)` → `None` without raising.
  - Liveness predicate (R4) — strict eight-row branch table from spec; treat as a closed enum, no fall-through. Recovery reason enum `{"esrch", "start_time_mismatch", "nosuchprocess"}`.
  - Mirrors `cortex_command/overnight/ipc.py:392-437 (verify_runner_pid)` for the ±2s start_time tolerance + `read_runner_pid` for the JSON-parse-defensive read pattern. Inherit `_START_TIME_TOLERANCE_SECONDS = 2.0` semantics (do not import the runner.pid constant — locally defined to preserve module boundaries).
  - Atomic write pattern mirrors `cortex_command/overnight/state.py:421-464` (tempfile + `os.replace`). Mode 0o600.
  - Stale-recovery (R6) is NOT destructive: `(a)` emit `interactive_lock_stale_recovered` with `recovery_reason ∈ {"esrch","start_time_mismatch","nosuchprocess"}` + `prior_*` fields; `(b)` `unlink` the stale file; `(c)` write fresh lock. NO `merge --abort`, NO `worktree remove`, NO `_recover_stale` analog.
  - Event-emit helper writes JSON-per-line to `_resolve_user_project_root() / "cortex/lifecycle/{slug}/events.log"`; mkdir-parent if absent.
  - `console_scripts` registration syntax in `pyproject.toml` matches the existing `cortex-daytime-pipeline` and `cortex-worktree-resolve` entries already in `[project.scripts]:20`.
  - Events-registry row format follows `bin/.events-registry.md` header columns: `event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner`. Use spec R12 table values for the four Phase-1 rows landing here; `consumers` may be `TBD`, `producers` MUST name `cortex_command/interactive_lock.py:acquire_lock` / `:release_lock` as appropriate.
- **Verification**:
  - `python3 -c "import cortex_command.interactive_lock as il; assert all(callable(getattr(il, fn)) for fn in ['acquire_lock','read_lock','verify_live_owner','release_lock','scan_live_locks','main'])"` exits 0 — pass if exit 0.
  - `which cortex-interactive-lock` exits 0 with non-empty stdout — pass if exit 0.
  - `grep -cE 'Path\("cortex/lifecycle' cortex_command/interactive_lock.py` = 0 (R2 — no CWD-relative paths) — pass if count = 0.
  - `grep -c '_resolve_user_project_root' cortex_command/interactive_lock.py` ≥ 2 (R2 — used by acquire and scan) — pass if count ≥ 2.
  - `grep -cE 'merge --abort|worktree remove --force|_recover_stale' cortex_command/interactive_lock.py` = 0 (R6 — no destructive recovery) — pass if count = 0.
  - `grep -cE '^\| `interactive_lock_(acquired|rejected_concurrent|stale_recovered|released)`' bin/.events-registry.md` = 4 — pass if count = 4.
  - `cortex-check-events-registry --staged` exits 0 — pass if exit 0.
- **Status**: [x] completed

### Task 2: Add unit tests for `interactive_lock.py` covering all R4 branch-table rows + R3 schema + R6 stale-recovery

- **Files**: `tests/test_interactive_lock.py` (new)
- **What**: Eight `test_verify_live_owner_row_N` tests (one per row of R4's eight-row branch table) plus R3 schema-shape assertions on a fresh `acquire` and R6 stale-recovery tests asserting `merge --abort` / `worktree remove` are never invoked under any STALE-recovery code path.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Test file mirrors the layout of `tests/test_runner_sandbox.py` and `tests/conftest.py` fixtures (use `monkeypatch.chdir` + `tmp_path` for isolated project roots).
  - For each R4 row, monkeypatch `os.kill`, `psutil.Process(...).create_time`, and the `CLAUDE_CODE_SESSION_ID` env var to construct the exact branch combination, then assert `verify_live_owner` returns the expected `LIVE`/`STALE` and (for STALE rows) the expected `recovery_reason`.
  - R6 destructive-recovery negative-test: invoke a STALE-triggering scenario; assert `subprocess.run` is not invoked with any of `("git", "merge", "--abort")`, `("git", "worktree", "remove")` — use `monkeypatch.setattr` on `subprocess.run` to record calls.
  - R3 schema test: call `acquire_lock("probe")` against a `tmp_path` project root (set `CORTEX_REPO_ROOT` env var), `json.load` the resulting file, assert `set(d.keys()) >= {"schema_version","magic","session_id","pid","start_time","acquired_at"}` AND `d["magic"] == "cortex-interactive-lock"` AND `oct(os.stat(path).st_mode)[-3:] == "600"`.
- **Verification**: `pytest tests/test_interactive_lock.py -v` exits 0 with all 8 `verify_live_owner_row_N` tests + schema + stale-recovery tests passing — pass if exit 0.
- **Status**: [x] completed

### Task 3: Add sandbox-write probe test verifying worktree-CWD writes to main-repo lock path

- **Files**: `tests/test_interactive_lock_sandbox.py` (new)
- **What**: Single test `test_lock_write_from_worktree_cwd` that invokes `cortex-interactive-lock acquire probe` via an explicit `sandbox-exec -p '<inline-SBPL>'` subprocess from a synthetic worktree CWD, then asserts the lock file lands at the main-repo absolute path. Validates the load-bearing assumption that `cortex init`'s allowWrite registration covers worktree-CWD-to-main-repo writes.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Pattern mirrors `tests/test_runner_sandbox.py` — pre-existing test that uses explicit `sandbox-exec` subprocess invocation rather than relying on a pytest-level sandbox.
  - Inline SBPL profile mirrors Anthropic's default Seatbelt allow-set (per `anthropic-experimental/sandbox-runtime`): `(allow process-exec)`, `(allow process-fork)`, `(allow process-info* (target same-sandbox))`, `(allow signal (target same-sandbox))`, `(allow sysctl-read ...)`, plus `(allow file-write* (subpath "<main-repo>/cortex"))` to model the `cortex init` registration.
  - Fixture sets up: (a) synthetic main-repo at `tmp_path / "main"` with `.git/` and `cortex/`; (b) synthetic worktree at `tmp_path / "worktree" / "probe"` with `.git` file pointing at main; (c) CWD set to worktree before subprocess invocation; (d) `CORTEX_REPO_ROOT` deliberately unset so `_resolve_user_project_root()` walks the `.git` boundary.
  - Skip condition: `if sys.platform != "darwin": pytest.skip("macOS-only sandbox semantics")` — Linux CI skips with explicit reason captured in pytest output.
- **Verification**:
  - On macOS: `pytest tests/test_interactive_lock_sandbox.py::test_lock_write_from_worktree_cwd` exits 0 — pass if exit 0.
  - On Linux: `pytest tests/test_interactive_lock_sandbox.py::test_lock_write_from_worktree_cwd -v 2>&1 | grep -c 'SKIPPED.*macOS-only sandbox semantics'` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] completed

### Task 4: Extract overnight-active probe into sidecar bash + fix §1a.iii typo

- **Files**:
  - `skills/lifecycle/references/_interactive_overnight_check.sh` (new — extracted sidecar bash)
  - `skills/lifecycle/references/implement.md` (modify §1a.iii to source the sidecar AND replace `.runner.lock` → `runner.pid` AND switch from `kill -0 $runner_pid` to parsing the JSON `pid` field via `python3 -c "import json,sys; print(json.load(sys.stdin)['pid'])" < {session_dir}/runner.pid`)
- **What**: Extract the four-bash-call active-session probe sequence (currently inlined in §1a.iii) into a reusable sidecar bash script, then convert §1a.iii to reference it via `cat`-then-eval. Fix the `.runner.lock` → `runner.pid` typo in the same edit. Single source for both the existing daytime mirror (§1a.iii, R8) and the upcoming new interactive mirror (§1, R7) landing in Task 5.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - The sidecar script is invoked via `cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- <args>` where `<args>` are the rejection-wording template + the expected `repo_path` (CWD for §1a.iii, main-repo for §1 mirror).
  - Sidecar exit codes: `0` = no overnight active (proceed); `1` = overnight live (caller surfaces the rejection wording from `$1`); `2` = stale runner detected (caller surfaces a warn-and-continue diagnostic).
  - Bash discipline: each step in the sidecar is a single `cat`/`python3`/`kill -0` invocation with no compound commands (matches the existing §1a.iii four-bash-call shape).
  - The `python3 -c` JSON parser replaces the implicit-extract pattern from §1a.iii's pre-fix prose. Pattern reference: same JSON-via-stdin shape is used in `cortex_command/overnight/ipc.py:381-389 (read_runner_pid)`.
  - This task does NOT add the §1 mirror — that's Task 5. This task ONLY (a) creates the sidecar and (b) edits §1a.iii to call it.
- **Verification**:
  - `grep -c '\.runner\.lock' skills/lifecycle/references/implement.md` = 0 (R8 — typo gone) — pass if count = 0.
  - `bash -n skills/lifecycle/references/_interactive_overnight_check.sh` exits 0 (syntax-valid sidecar) — pass if exit 0.
  - `grep -c '_interactive_overnight_check.sh' skills/lifecycle/references/implement.md` ≥ 1 (sidecar referenced from §1a.iii) — pass if count ≥ 1.
- **Status**: [x] completed

### Task 5: Wire interactive preflight guards into `implement.md` §1 — overnight-active mirror + lock acquisition + fifth events-registry row

- **Files**:
  - `skills/lifecycle/references/implement.md` (modify §1 — add two new steps between the user-selection `AskUserQuestion` block and the worktree-creation step landing via #239: (a) overnight-active rejection mirror sourcing the sidecar from Task 4 with interactive-tailored wording; (b) `cortex-interactive-lock acquire {slug}` single-Bash-call invocation with R5's rejection wording surfaced on non-zero exit)
  - `bin/.events-registry.md` (modify — one new row: `interactive_overnight_active_rejected`)
- **What**: Add the two preflight steps to §1 that sit between the user-selection prompt and worktree creation. The overnight-active mirror runs first; on success, the lock-acquisition step runs second. Both reject with interactive-tailored wording (different from daytime's "wait for it to complete"). Inline bash is forbidden for the lock-acquisition step per R13 — the single `cortex-interactive-lock acquire` invocation does the JSON parse / `kill -0` / start-time check internally.
- **Depends on**: [1] (console-script must exist), [4] (sidecar bash must exist for the mirror)
- **Complexity**: simple
- **Context**:
  - Insert location: after the §1 `AskUserQuestion` for branch selection resolves to a path that proceeds with worktree creation (Variant A under #238/#239 — the new "Implement on feature branch with worktree" path #238 introduces). Anchor: the new steps land before the worktree-creation step #239 inserts (which uses `cortex-worktree-resolve` and/or `create_worktree`). Anchor regex: between `/AskUserQuestion.*Implement on feature branch/` and `/create_worktree|cortex-worktree-resolve/`.
  - Step A (overnight-active mirror) sources `_interactive_overnight_check.sh` via `cat ... | bash -s -- "<interactive-wording>" "$(_resolve_user_project_root)"`. R7 wording: `"Overnight runner is active (session {session_id}, PID {pid}, phase: executing) — wait for the run to complete (\`cortex overnight status\`), or open a different feature."`. R15 sub-test C grep target is `"the run to complete"` (natural substring of R7's wording — spec.md R15 says `"work to complete"` but that's a spec drift; plan resolves it by anchoring the grep target on the natural R7 substring).
  - Step B (lock acquisition) is a single Bash invocation of `cortex-interactive-lock acquire {slug}`. On exit 0 → proceed. On non-zero exit → the console-script has already written stderr containing R5's exact wording: `"Interactive session already active on this feature (session {session_id}, acquired {acquired_at}). Wait for it to exit, or work on a different feature, or run \`cortex-interactive-lock inspect {slug}\` for details."` — skill prose surfaces stderr verbatim and exits §1.
  - Events-registry row for `interactive_overnight_active_rejected` follows R12 producer: `skills/lifecycle/references/implement.md §1 (interactive mirror)`. Scan-coverage: `gated` (skill-prose-emitted).
  - R13 file-wide-anchor verification target: `git diff main -- skills/lifecycle/references/implement.md | grep -E '^\+' | grep -cE 'kill -0|psutil|create_time'` must return 0. This task's additions to §1 use the console-script and the Task-4 sidecar; the sidecar is in a separate file so it doesn't count against the implement.md file-wide grep.
- **Verification**:
  - `grep -c 'cortex-interactive-lock acquire' skills/lifecycle/references/implement.md` ≥ 1 — pass if count ≥ 1.
  - `grep -c 'work on a different feature' skills/lifecycle/references/implement.md` ≥ 1 (R5 wording substring) — pass if count ≥ 1.
  - `grep -c 'cortex-interactive-lock inspect' skills/lifecycle/references/implement.md` ≥ 1 (R5 wording substring) — pass if count ≥ 1.
  - `awk '/AskUserQuestion.*Implement on feature branch/{a=NR} /_interactive_overnight_check\.sh/{b=NR} /cortex-interactive-lock acquire/{c=NR} END{exit (a<b && b<c) ? 0 : 1}' skills/lifecycle/references/implement.md` exits 0 (interactive mirror sits between user-selection and lock-acquisition) — pass if exit 0.
  - `git diff main -- skills/lifecycle/references/implement.md | grep -E '^\+' | grep -cE 'kill -0|psutil|create_time'` = 0 (R13 — no new inline-liveness primitives) — pass if count = 0.
  - `grep -cE '^\| `interactive_overnight_active_rejected`' bin/.events-registry.md` = 1 — pass if count = 1.
  - `cortex-check-events-registry --staged` exits 0 — pass if exit 0.
- **Status**: [x] completed

### Task 6: Refactor `run_batch` to call exported `compute_eligible_features` + add sixth events-registry row

- **Files**:
  - `cortex_command/overnight/orchestrator.py` (modify — extract `compute_eligible_features(feature_names: list[str], project_root: Path) -> tuple[list[str], list[dict]]`; call at each round entry after `load_state` at line 182, before the per-feature dispatch loop; emit `feature_skipped_interactive_active` to `cortex/lifecycle/overnight-events.log` per excluded feature)
  - `bin/.events-registry.md` (modify — one new row: `feature_skipped_interactive_active`)
- **What**: Extract a new exported helper that takes the master-plan-derived feature list and the project root, calls `cortex_command.interactive_lock.scan_live_locks`, and returns the eligible subset plus the list of skip-event payloads to emit. `run_batch` uses the returned `eligible` (NOT the original `feature_names`) in the subsequent per-feature dispatch. No `state.features` mutation; no `save_state` call from this code path.
- **Depends on**: [1] (consumes `scan_live_locks`)
- **Complexity**: complex
- **Context**:
  - New exported function signature: `def compute_eligible_features(feature_names: list[str], project_root: Path) -> tuple[list[str], list[dict]]` — returns `(eligible, skip_events)` where each skip-event dict has the schema `{ts, event: "feature_skipped_interactive_active", feature, session_id (from overnight state.session_id), round_number, interactive_session_id (from the lock JSON), interactive_acquired_at, rationale}`. `interactive_pid` is intentionally omitted per R11.
  - Insertion point in `cortex_command/overnight/orchestrator.py:run_batch`: after `overnight_state = load_state(...)` at line 182, before the per-feature dispatch loop near line 188. The eligible-features result replaces the bare `feature_names` everywhere the subsequent dispatch loop currently references it (lines 188, 229, 302, 331, 355, 376, 385, 422). Carefully review each call site — some references are to the bare-list-as-name-source (those need to use `eligible`); others are to per-feature-status dicts (those continue to key off the original `feature_names` for spec_paths/backlog_ids/etc.). The simplest invariant: only the iteration-driver references swap to `eligible`; the per-name-keyed dicts remain keyed off the full set.
  - The skip-event `rationale` field is REQUIRED per `cortex/requirements/pipeline.md:130`. Template: `f"Skipped at round {round_number}: feature has a live interactive owner (session {interactive_session_id}, acquired {interactive_acquired_at})."`.
  - Path resolution: `compute_eligible_features` receives the project root explicitly; do NOT call `_resolve_user_project_root()` inside the function (so tests can pass a synthetic root via `tmp_path`). `run_batch`'s call site supplies `_resolve_user_project_root()` as the argument.
  - Events-registry row for `feature_skipped_interactive_active` follows R12: target = `overnight-events-log`, scan-coverage = `manual` (Python emission site, no skill-prose scan), producers = `cortex_command/overnight/orchestrator.py:run_batch (per-round scan)`.
  - Round-loop reload caveat (R10 convergence): `run_batch` is invoked once per overnight-run; the per-round scan happens inside `run_batch`'s loop. The reload at `runner.py:2151` is the cross-`run_batch`-invocation channel. R9's per-round re-derivation is INSIDE this single `run_batch` call — verify that `run_batch`'s round-loop structure actually exists (line 156-479) and that the new scan call falls inside it, NOT before it.
- **Verification**:
  - `python3 -c "from cortex_command.overnight.orchestrator import compute_eligible_features; assert callable(compute_eligible_features)"` exits 0 — pass if exit 0.
  - `awk '/load_state\(/{a=NR} /interactive_lock\.scan_live_locks|compute_eligible_features/{b=NR} END{exit (a>0 && b>a) ? 0 : 1}' cortex_command/overnight/orchestrator.py` exits 0 (scan reference follows load_state) — pass if exit 0.
  - `git diff main -- cortex_command/overnight/orchestrator.py | grep -E '^\+.*save_state\(|^\+.*state\.features\s*=|^\+.*overnight_state\.features\s*=' | wc -l` = 0 (R9 — no new state mutations in the diff) — pass if count = 0.
  - `grep -cE '^\| `feature_skipped_interactive_active`' bin/.events-registry.md` = 1 — pass if count = 1.
  - `cortex-check-events-registry --staged` exits 0 — pass if exit 0.
- **Status**: [x] completed

### Task 7: Add orchestrator inverse-scan unit tests

- **Files**: `tests/test_orchestrator_inverse_scan.py` (new)
- **What**: Two unit tests directly exercising `compute_eligible_features` with a mocked `scan_live_locks` to simulate (a) owner-acquires-mid-overnight (round N includes X; round N+1 excludes X); (b) owner-exits-mid-overnight (round N excludes X; round N+1 re-includes X). Validates R10 convergence semantics.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Mock target: `cortex_command.interactive_lock.scan_live_locks` — `monkeypatch.setattr` to return different sets on successive calls (`set()` then `{"X"}` for test A; reversed for test B).
  - Test A asserts: round-1 call returns `(eligible=["X", ...], skip_events=[])`; round-2 call returns `(eligible=[other features without "X"], skip_events=[{event: "feature_skipped_interactive_active", feature: "X", ...rationale containing "live interactive owner"}])`.
  - Test B is the mirror: round-1 returns the skip-event for X, round-2 returns X in eligible with no skip-events.
  - Synthetic lock-data fixture: write a real lock file under `tmp_path / "cortex/lifecycle/X/interactive.pid"` matching R3's schema so that any code path that reads the lock for `interactive_session_id` / `interactive_acquired_at` (per R11) finds expected values. The mocked `scan_live_locks` returns `{"X"}` to indicate the lock is "live", but `compute_eligible_features` still does a `read_lock("X")` to populate the skip-event payload fields.
- **Verification**: `pytest tests/test_orchestrator_inverse_scan.py -v` exits 0 with both tests passing — pass if exit 0.
- **Status**: [ ] pending

### Task 8: Add bidirectional concurrency contract integration test (4 sub-tests, production paths only)

- **Files**: `tests/test_bidirectional_concurrency_contract.py` (new)
- **What**: Four sub-tests invoking PRODUCTION CODE PATHS (no Python stubs of the helper):
  - **A (interactive→interactive)**: two `cortex-interactive-lock acquire X` subprocesses with different `CLAUDE_CODE_SESSION_ID` env values; first exits 0, second exits non-zero with stderr containing `"work on a different feature"`.
  - **B (interactive→overnight via per-round scan)**: synthetic live `interactive.pid` written for feature Y; `scan_live_locks(<test-project-root>)` returns `{"Y"}`; `compute_eligible_features(["Y", "Z"], <test-project-root>)` returns `(["Z"], [<one skip-event containing rationale with test-session-B>])`.
  - **C (overnight→interactive rejection mirror — actual sidecar bash)**: synthetic `active-session.json` + `runner.pid` written; invoke the Task-4 sidecar via `subprocess.run(["bash", "-c", "cat skills/lifecycle/references/_interactive_overnight_check.sh | bash -s -- '<wording>' '<repo>'"])`; assert non-zero exit AND stderr contains `"the run to complete"`.
  - **D (lock release)**: `acquire X` → file exists → `release X` → file does not exist → `cortex/lifecycle/X/events.log` contains an `interactive_lock_released` JSON row.
- **Depends on**: [1], [5], [6]
- **Complexity**: complex
- **Context**:
  - Test discipline: NO Python stubs for `cortex-interactive-lock`. Each sub-test uses `subprocess.run([sys.executable, "-m", ...])` or direct `cortex-interactive-lock` console-script invocation. For sub-test B, the production code path is `cortex_command.overnight.orchestrator.compute_eligible_features` (real function, called directly with `tmp_path` project root).
  - Sub-test A's stderr-grep target `"work on a different feature"` is the explicit coupling point with R5's wording; documented in spec R15 as expected coupling — if R5 changes, this test must update in lockstep.
  - Sub-test C's stderr-grep target `"the run to complete"` is the explicit coupling point with R7's wording. The actual bash invocation goes through the Task-4 sidecar at `skills/lifecycle/references/_interactive_overnight_check.sh`; the test does NOT re-implement the four-bash-call logic.
  - Sub-test B writes a real `interactive.pid` JSON file at `<tmp_path>/cortex/lifecycle/Y/interactive.pid` matching R3's schema with `CLAUDE_CODE_SESSION_ID=test-session-B` and a live PID (test process's own PID) so `scan_live_locks` and `read_lock` both succeed.
  - Fixtures use `tmp_path` + `monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))` to redirect path resolution.
  - Out-of-scope per R15: the principal TOCTOU window (owner acquires AFTER scan but BEFORE round-N dispatch) is NOT exercised. Per Non-Requirements, that surfaces via `git worktree add` failure path in the orchestrator's existing error handling.
- **Verification**: `pytest tests/test_bidirectional_concurrency_contract.py -v` exits 0 with all four sub-tests (`test_*_A`, `test_*_B`, `test_*_C`, `test_*_D`) passing — pass if exit 0.
- **Status**: [ ] pending

## Risks

- **R4 row 3, 4, 8 default to LIVE (conservative)**: under EPERM, null start_time, or unusual psutil exceptions, the predicate keeps the lock LIVE — a false-LIVE permanently blocks the user until they run `cortex-interactive-lock force-release`. The alternative is to flip these rows to STALE with `force-acquire` instead; that biases toward false-STALE (silent take-over of a live session, possibly corrupting the worktree). The current bias matches R6's "preserve worktree state" intent but the user may want to revisit whether `force-release` is discoverable enough — Task 1's `inspect` subcommand output is the only diagnostic surface today.

- **Sidecar bash extraction is a new pattern**: no precedent in the codebase for `cat-then-eval` skill prose pattern. The alternative is to keep the four-bash-call sequence inlined in both §1 (new mirror) and §1a.iii (existing daytime probe) — that's literal duplication but keeps skill prose self-contained and parseable by static scanners. Sidecar wins on single-source-of-truth and test-via-bash; loses on "skill prose now requires reading two files to understand the probe." Worth surfacing for a sanity check before Task 4 lands.

- **`compute_eligible_features` refactor touches the most call sites of any change here (Task 6)**: `feature_names` is referenced at orchestrator.py lines 164, 188, 211, 212, 213, 229, 302, 331, 355, 376, 385, 422. Each site must be classified as either "iteration-driver-swap-to-eligible" or "per-name-keyed-dict-keep-full-set". A regression from misclassification corrupts the per-feature status dicts. Mitigation: the unit tests in Task 7 cover the function-level contract; Task 8 sub-test B covers the integration; but inspecting each line by hand at implementation time is unavoidable.

- **`os.getppid()` semantics under uv-run vs. direct invocation diverge**: per research.md, `uv run cortex-interactive-lock` yields `os.getppid() = uv's PID` (born-stale within milliseconds); direct invocation (post-`uv tool install`) yields a more stable parent. R4 row 4 (null start_time) and row 8 (unusual exception) catch most of the cases the born-stale problem creates, but the integration test (Task 8 sub-test A) uses direct console-script invocation, so the uv-run-specific born-stale path is not exercised. The env-var primary key (R4 row 1) carries the load; the auxiliary PID is best-effort. Documented and accepted, but worth re-flagging during implementation.

## Changes to Existing Behavior (recap from spec)

- **MODIFIED** `skills/lifecycle/references/implement.md` §1 — two new preflight steps (overnight-active mirror, interactive-lock acquisition) inserted between user-selection and #239's worktree-creation step.
- **MODIFIED** `skills/lifecycle/references/implement.md` §1a.iii — `.runner.lock` → `runner.pid` typo fix + sidecar extraction.
- **MODIFIED** `cortex_command/overnight/orchestrator.py:run_batch` — new exported `compute_eligible_features` helper + per-round scan-and-filter at each round entry.
- **MODIFIED** `pyproject.toml::[project.scripts]` — register `cortex-interactive-lock`.
- **MODIFIED** `bin/.events-registry.md` — six new event rows (four in Task 1, one in Task 5, one in Task 6).
- **ADDED** `cortex_command/interactive_lock.py`, `skills/lifecycle/references/_interactive_overnight_check.sh`, and four test files.
