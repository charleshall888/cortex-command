# Plan: overnight-dispatch-sends-opus-only-xhigh (#313)

## Overview
Introduce one leaf module that resolves the best-available `claude` CLI (newer of system-vs-bundled, `CORTEX_CLAUDE_CLI_PATH`-overridable, memoized) and pin its result as `cli_path` at every SDK dispatch site plus the orchestrator spawn, so the SDK stops preferring its stale bundled binary; then make effort handling resilient and loud — classify an `--effort` hard-reject as its own non-blind-retryable type that triggers exactly one clamp-to-`max` retry, detect a warn-ignored effort on the success path, surface captured CLI stderr into `learnings/progress.txt`, and correct the stale "silently downgraded"/`AssertionError` premises.
**Architectural Pattern**: shared-state
<!-- A single cached resolver is the shared source of truth all dispatch sites read; not a pipeline or event-driven reshape. -->

## Outline

### Phase 1: Use the best available CLI (tasks: 1, 2, 3)
**Goal**: Every SDK dispatch and the orchestrator spawn run the newer of system-vs-bundled `claude`, with an operator/test override, instead of the SDK's bundled-first selection.
**Checkpoint**: `cli_path` is pinned in `dispatch.py`, `discovery.py`, and the orchestrator spawn; the resolver and stub-field unit tests pass; existing `dispatch_task`/`_stubs` tests are green (`just test` exits 0).

### Phase 2: Resilient, loud effort handling (tasks: 4a, 4b, 5, 6, 7, 8, 9)
**Goal**: An unsupported `--effort` never burns the retry budget and never degrades silently — a hard-reject clamps once to `max` (surfaced and rendered in the morning report), a warn-ignore is detected and noted while the run still succeeds, real CLI stderr reaches the learnings file, the stale code/doc premises are corrected, and ADR-0014 records the decision.
**Checkpoint**: An `--effort … invalid` rejection produces exactly one clamped `max` retry (regardless of which attempt it lands on, not preempted by the circuit breaker) with a clamp event that **renders** in the morning report; a warn-ignore on a successful dispatch records and renders a degraded-effort note without failing; `learnings/progress.txt` shows captured `child_stderr`; `grep -c "silently downgraded" cortex_command/pipeline/dispatch.py` = 0; `just test` exits 0.

## Tasks

### Task 1: Best-CLI resolver module + unit tests (R1)
- **Files**: `cortex_command/cli_resolver.py` (new), `cortex_command/pipeline/tests/test_cli_resolver.py` (new)
- **What**: Add a leaf module exposing a memoized `resolve_claude_cli() -> Optional[str]` that returns the absolute path of the best `claude` to dispatch — the newer of system-vs-bundled, never older than the bundled floor — with a `CORTEX_CLAUDE_CLI_PATH` short-circuit; cover its branches with deterministic monkeypatched tests.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Module imports stdlib only (`os`, `shutil`, `subprocess`, `pathlib`, `functools`, `typing`) plus an optional SDK-bundled lookup — it must NOT import `cortex_command.pipeline.dispatch`/`overnight`/`discovery` (it is the shared leaf those depend on; keep it import-cycle-free per the deferred-import note at `dispatch.py:41-47`).
  - Public contract: `resolve_claude_cli() -> Optional[str]`. Resolution order: (1) if env `CORTEX_CLAUDE_CLI_PATH` is set and non-empty, return it verbatim and do NOT memoize (so per-test env changes are honored); (2) else return the memoized value if present; (3) else compute prefer-newer, memoize, and return. Returning `None` means "let the caller fall back to today's behavior" (SDK bundled-first / bare `"claude"`), so the pin is safe in degraded environments.
  - Prefer-newer computation: `_find_system_cli_path()` tries `shutil.which("claude")` then the known fallbacks `~/.local/bin/claude`, `/usr/local/bin/claude`, `~/.claude/local/claude` (first existing wins); `_find_bundled_cli_path()` locates the SDK's bundled binary via the **package-relative path** `<claude_agent_sdk package dir>/_bundled/claude` — resolve the package dir with `importlib.util.find_spec("claude_agent_sdk")`. Do **not** call `claude_agent_sdk._internal.transport.subprocess_cli._find_bundled_cli`: verified it is an *instance method* of `SubprocessCLITransport` (`subprocess_cli.py:97`), not a module-level function, so a module-level reference is unreachable dead code. The package-relative path is exactly what the SDK's own bundled-first selection computes. Parse each binary's `--version` first token into a comparable tuple via `_parse_cli_version(output: str) -> Optional[tuple[int, ...]]` (e.g. `"2.1.186 (Claude Code)"` → `(2,1,186)`). Run `--version` with `CLAUDECODE` cleared from the child env (the nested-session guard, per `dispatch.py:644`) and a bounded timeout.
  - Selection rule (**probe-failure must never silently pick the stale bundle** — that would reproduce #313): if both versions parse and system ≥ bundled → system; if the system CLI is **present but its `--version` is unparseable** (timeout/parse flake) → return the **system path anyway** (a present system `claude` is the operator's intended, almost-always-newer binary) and log a loud resolver-level warning — do NOT downgrade to bundled on a probe flake; if the system CLI is genuinely **absent** → bundled; if neither found → `None`. The result is never older than the bundled floor, and an indeterminate result forced by a probe failure is **not memoized** (so a transient flake cannot pin a degraded choice for the process lifetime).
  - Test seam: `_reset_cli_cache() -> None` clears the memo; tests call it in setup/teardown.
  - Cite ADR-0014 (Task 8) in the module docstring so `cortex-adr-citation-audit` sees a reference.
- **Verification**: `.venv/bin/pytest cortex_command/pipeline/tests/test_cli_resolver.py -q` — pass if exit 0 (pytest errors non-zero if the file is absent, so this also enforces the test file was created; `just test` runs the whole suite and ignores a path argument, so it is NOT a per-file gate). Tests must cover, via monkeypatching `_find_system_cli_path`/`_find_bundled_cli_path`/`_parse_cli_version` (no real `claude` required): (a) fake system newer than bundled → system path; (b) system absent → bundled path; (c) `CORTEX_CLAUDE_CLI_PATH` set → that path verbatim; (d) neither found → `None`; (e) memoization (second call returns the cached value without recomputing); (f) **system present but version unparseable → system path returned (not bundled), result not memoized** (the #313-regression guard from the Selection rule).
- **Status**: [x] done

### Task 2: Pin `cli_path` at the SDK sites + extend the test stub (R2)
- **Files**: `cortex_command/pipeline/dispatch.py`, `cortex_command/discovery.py`, `cortex_command/tests/_stubs.py`
- **What**: Set `cli_path=resolve_claude_cli()` on the worker-dispatch and gate-brief `ClaudeAgentOptions` constructions, and add a `cli_path` field to the stub dataclass so the pin does not raise `TypeError` in tests.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - In `dispatch.py`, import `resolve_claude_cli` from `cortex_command.cli_resolver` and pass `cli_path=resolve_claude_cli()` into the `ClaudeAgentOptions(...)` at `dispatch.py:768-780`. `cli_path=None` is equivalent to today's SDK selection, so existing async dispatch tests (which don't set the override) keep working.
  - In `discovery.py`, pass `cli_path=resolve_claude_cli()` into the `_ClaudeAgentOptions(...)` at `discovery.py:724-730` (alias imported at `:656`).
  - In `cortex_command/tests/_stubs.py`, add `cli_path: str | None = None` to the `ClaudeAgentOptions` dataclass (`:76-87`), placed so existing positional constructions stay valid (append after `stderr`). The stub field is required because the dispatch/discovery production sites construct the **stub** `ClaudeAgentOptions` (which today lacks `cli_path`) under conftest, so the new kwarg would raise `TypeError` without it. (Note: the real-SDK `test_effort_value_passthrough` is NOT at risk — verified the real `claude_agent_sdk.ClaudeAgentOptions` already declares `cli_path` at `types.py:995` and that test already passes `cli_path="/usr/bin/true"`.)
  - `cli_path` overriding `_find_cli()` is confirmed for the pinned SDK (`subprocess_cli.py:46-47` → `self._find_cli()` only when `cli_path is None`, so `cli_path=None` ≡ field-absent ≡ today's bundled-first selection); no SDK bump is in scope.
- **Verification**: `grep -c "cli_path" cortex_command/pipeline/dispatch.py` ≥ 1 AND `grep -c "cli_path" cortex_command/discovery.py` ≥ 1 AND `grep -c "cli_path" cortex_command/tests/_stubs.py` ≥ 1 — pass if all three ≥ 1; AND `.venv/bin/pytest cortex_command/pipeline/tests/test_dispatch.py -q` exits 0 (existing `dispatch_task` tests still pass).
- **Status**: [ ] pending

### Task 3: Orchestrator spawn uses the resolved CLI (R3)
- **Files**: `cortex_command/overnight/runner.py`, `cortex_command/overnight/tests/test_spawn_resolved_cli.py` (new)
- **What**: Replace the bare `claude_path = "claude"` in `_spawn_orchestrator` with `claude_path = resolve_claude_cli() or "claude"` so orchestrator and workers run an identical CLI; add a test asserting the spawned `argv[0]`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - The spawn is in `_spawn_orchestrator` (`runner.py:1410`); the bare literal is at `runner.py:1482`, consumed by `subprocess.Popen([claude_path, "-p", …])` at `:1484-1505`. Import `resolve_claude_cli` from `cortex_command.cli_resolver` (module-level or local) and assign `claude_path = resolve_claude_cli() or "claude"`. The `or "claude"` preserves today's behavior when resolution returns `None`.
  - Test pattern: follow `cortex_command/overnight/tests/test_spawn_handshake.py` / `test_spawn_session_leader.py`. Monkeypatch `resolve_claude_cli` to return a sentinel absolute path and patch `subprocess.Popen` to capture args; invoke the `_spawn_orchestrator` path and assert `Popen.call_args.args[0][0] == <sentinel>`. Also assert the `None` fallback yields `"claude"`.
- **Verification**: `grep -c "resolve_claude_cli" cortex_command/overnight/runner.py` ≥ 1 (positive: the resolver is wired on the spawn path — a bare re-quoted literal would not satisfy this) AND `grep -cE 'claude_path *= *["'"'"']claude["'"'"']' cortex_command/overnight/runner.py` = 0 (no bare-literal assignment, single- or double-quoted) — pass if both hold; AND `.venv/bin/pytest cortex_command/overnight/tests/test_spawn_resolved_cli.py -q` exits 0 with the `argv[0]`-equals-resolver assertion (and the `None`→`"claude"` fallback assertion) passing.
- **Status**: [ ] pending

### Task 4a: Classify `--effort` hard-reject as its own non-blind-retryable type (R4, part 1)
- **Files**: `cortex_command/pipeline/dispatch.py`, `cortex_command/pipeline/tests/test_dispatch.py`
- **What**: Add detection of a captured `--effort` hard-rejection in `classify_error` returning a new error type (e.g. `effort_unsupported`), and add that type to `ERROR_RECOVERY` with a new recovery path (e.g. `clamp_effort`) so the loop stops re-sending the permanently-invalid flag.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - `classify_error` (`dispatch.py:469-523`) builds its corpus from `f"{error}".lower()` + lowercased `output`, where the call site (`:914`) passes `output = output_parts + _stderr_lines` — so the bundled CLI's rejection text reaches the corpus. Add a check BEFORE the final `return "task_failure"` (`:521`): if the corpus contains both `option '--effort` and `is invalid`, return `"effort_unsupported"`. Match the firsthand text `option '--effort <level>' argument 'xhigh' is invalid` (Technical Constraints / research §Root Cause).
  - Add `"effort_unsupported": "clamp_effort"` to `ERROR_RECOVERY` (`:348-358`). Define the new recovery as one-shot clamp (consumed by Task 4b), distinct from `retry`/`escalate`/`pause_*`.
  - New tests in `test_dispatch.py` (near the effort suite at `:1042-1265`): a `ProcessError` whose stderr corpus carries the `--effort … is invalid` text classifies as `effort_unsupported`; a `max`-accepted dispatch does not; the existing `classify_error` cases are unchanged.
- **Verification**: `.venv/bin/pytest cortex_command/pipeline/tests/test_dispatch.py -q` — pass if exit 0, including a new assertion that `classify_error(ProcessError(<--effort invalid text>), output=<stderr>)` returns `"effort_unsupported"` and `ERROR_RECOVERY["effort_unsupported"] == "clamp_effort"`.
- **Status**: [ ] pending

### Task 4b: One clamped `max` retry in the retry loop, no blind re-send (R4, part 2)
- **Files**: `cortex_command/pipeline/retry.py`, `cortex_command/pipeline/tests/test_retry.py`
- **What**: When a dispatch returns the `effort_unsupported` recovery, retry exactly once with `effort_override="max"`, record the clamp, and never re-clamp — replacing today's budget-burning blind retry of the invalid flag.
- **Depends on**: [4a]
- **Complexity**: complex
- **Context**:
  - In `retry_task` (`retry.py:174-473`), thread a single new attempt-scoped variable `current_effort_override: Optional[str] = None` and pass `effort_override=current_effort_override` into the `dispatch_task(...)` call (`:264-280`) — `dispatch_task` already accepts `effort_override` (`dispatch.py:556`) but no caller sets it today; `None` preserves matrix resolution.
  - **Circuit-breaker ordering (load-bearing):** the `effort_unsupported` → clamp handling must be evaluated so that neither the circuit breaker (`retry.py:333-358`) nor the last-attempt break (`:330`) can preempt it. An `--effort` hard-reject produces an **empty worktree diff** (the agent never ran), and `_check_circuit_breaker("", "")` returns `True` (`:157-167`) — so a no-diff `effort_unsupported` arriving on attempt ≥2 after any prior no-diff failure would otherwise return `paused=True` at `:350` **before** the recovery arm at `:365` ever runs, and the clamp would never fire. Fix: short-circuit the breaker when `result.error_type == "effort_unsupported"` (an empty diff from a CLI-rejected flag is not agent "no progress"), i.e. evaluate the clamp decision ahead of the breaker/last-attempt gates for this error type. This makes the clamp fire regardless of which attempt the rejection lands on (not only attempt 1, where `previous_diff is None` happens to skip the breaker).
  - Clamp handling: on the first `effort_unsupported`, set `current_effort_override = "max"`, log a `retry_effort_clamped` event (`{from_effort, to_effort: "max", model: current_model}`) via `log_event`, and continue the loop for one more attempt (do NOT escalate the model, do NOT pause). The clamp is **one-shot by construction**: `max` is universally accepted (Technical Constraints), so a re-failure at `max` cannot re-classify as `effort_unsupported` — it routes through the normal recovery arms. No separate "already-clamped" pause branch is needed (it would be unreachable); a simple `clamped_once`-style guard is optional belt-and-suspenders, not a live control path.
  - This bounds the invalid-flag dispatch to exactly one clamped retry: the first `effort_unsupported` clamps to `max`; subsequent attempts run at `max` and never re-send the rejected value.
  - New `test_retry.py` tests (pin `_get_worktree_diff` as the existing tests do, e.g. via the `diff_value=` harness): **(1)** `effort_unsupported` on attempt 1 then success ⇒ exactly two `dispatch_task` calls, the second with `effort_override="max"`, a `retry_effort_clamped` event recorded, NOT N blind retries; **(2) the circuit-breaker regression** — a prior no-diff failure on attempt 1, then `effort_unsupported` (also empty diff) on attempt 2, must STILL clamp and retry at `max` rather than tripping the breaker into `paused=True`.
- **Verification**: `.venv/bin/pytest cortex_command/pipeline/tests/test_retry.py -q` — pass if exit 0, with the new tests asserting (a) the post-clamp `dispatch_task` call received `effort_override="max"`, (b) the clamped retry fires (not the blind ladder), (c) a `retry_effort_clamped` event was logged, AND (d) the empty-diff-on-attempt-2 case clamps rather than circuit-breaker-pausing.
- **Status**: [ ] pending

### Task 5: Detect and surface a warn-ignored effort on the success path (R5)
- **Files**: `cortex_command/pipeline/dispatch.py`, `cortex_command/pipeline/tests/test_dispatch.py`
- **What**: When a dispatch succeeds but captured stderr carries the modern CLI's warn-ignore signal, record a visible degraded-effort note and keep the result `success=True`.
- **Depends on**: [4a]
- **Complexity**: simple
- **Context**:
  - In `dispatch_task`'s success branch (before `return DispatchResult(success=True, …)` at `dispatch.py:907-911`), scan the already-captured `_stderr_lines` (populated by `_on_stderr`, `:753-766`) for the warn-ignore signal — lowercased contains `unknown --effort value` and `ignoring` (firsthand text: `Warning: Unknown --effort value '…' — ignoring it and using the default effort`).
  - On a hit, `log_event(log_path, {...})` a `dispatch_effort_ignored` event carrying `model`, requested `effort`, and the matched stderr line; the dispatch RAN, so do not fail it. Optionally set a `degraded_note` on `DispatchResult` for downstream surfacing — but the event is the recorded, test-asserted note.
  - New `test_dispatch.py` test: a successful dispatch whose `_on_stderr` received the warn-ignore line ⇒ a `dispatch_effort_ignored` event is logged AND the `DispatchResult.success` is `True`.
- **Verification**: `.venv/bin/pytest cortex_command/pipeline/tests/test_dispatch.py -q` — pass if exit 0, with a new test asserting the `dispatch_effort_ignored` event is recorded and `result.success is True` on the warn-ignore stderr corpus.
- **Status**: [ ] pending

### Task 6: Surface captured CLI stderr into learnings/progress.txt (R6)
- **Files**: `cortex_command/pipeline/retry.py`, `cortex_command/pipeline/tests/test_retry.py`
- **What**: Include the dispatch's captured `child_stderr` in the `progress.txt` learnings entry on the failure path, replacing the opaque `ProcessError: exit code 1` with the real CLI error/warning text.
- **Depends on**: [4b]
- **Complexity**: simple
- **Context**:
  - On the failure path (`retry.py:309-317`), `result.diagnostics` (a `DispatchDiagnostics`, `dispatch.py:299-315`) carries `child_stderr`. Add a `child_stderr: Optional[str] = None` parameter to `_append_learnings` (`retry.py:82-128`) and include it in the written entry (a `CLI stderr:` section). Pass `child_stderr=result.diagnostics.child_stderr if result.diagnostics else None` from the failure-path call.
  - Keep the existing `error`/`output` fields; this is additive so retries still see the prior text.
- **Verification**: `.venv/bin/pytest cortex_command/pipeline/tests/test_retry.py -q` — pass if exit 0, with a new/extended test asserting that after a failure whose `result.diagnostics.child_stderr` is set, the written `progress.txt` content contains that `child_stderr` text.
- **Status**: [ ] pending

### Task 7: Correct the stale "silently downgraded"/`AssertionError` premises (R7)
- **Files**: `cortex_command/pipeline/dispatch.py`, `docs/internals/sdk.md`
- **What**: Correct the `effort_override` docstring and the SDK doc to state the verified truth — old `claude` (≤2.1.69) hard-rejects an unsupported `--effort` (exit ≠ 0); modern `claude` (≥2.1.186) warn-ignores it (exit 0, default effort); neither "silently downgrades"; and the guard raises `ValueError`, not `AssertionError`.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - In `dispatch.py`, rewrite the `effort_override` docstring claim at `:590-593` ("`xhigh` is Opus 4.7-only and is silently downgraded by non-Opus models") to describe the CLI-level hard-reject-vs-warn-ignore split. The phrase "silently downgraded" must not remain.
  - In `docs/internals/sdk.md`: fix line ~107 (`sonnet | … (xhigh NOT supported — silently downgrades)`) and line ~110 (`asserts this invariant and raises AssertionError`) — the guard at `dispatch.py:282-287` raises `ValueError`. State that the dispatched CLI binary (not the model) is what rejects/ignores an unsupported effort, and document the bundled-CLI-vs-system-CLI distinction the resolver addresses.
- **Verification**: `grep -c "silently downgraded" cortex_command/pipeline/dispatch.py` = 0 (pass if 0); AND `grep -c "AssertionError" docs/internals/sdk.md` = 0 for the `resolve_effort` claim and `grep -c "hard-reject\|warn-ignore\|warn-and" docs/internals/sdk.md` ≥ 1 (pass if the split is documented).
- **Status**: [ ] pending

### Task 8: Surface the effort-degradation notes in the morning report (R4/R5 visibility)
- **Files**: `cortex_command/overnight/report.py`, `cortex_command/overnight/tests/test_report.py`
- **What**: Render the `retry_effort_clamped` and `dispatch_effort_ignored` events as an operator-visible morning-report section so the "loud / always-surfaced" guarantee (spec R4/R5) is actually met — without this, the events are logged to JSONL but never rendered (the report assembles from a closed renderer set, no generic event dump).
- **Depends on**: [4b, 5]
- **Complexity**: simple
- **Context**:
  - Follow the `render_complexity_normalized` pattern (`report.py:2469-2518`): a new `render_effort_degradation(data: ReportData) -> str` that scans `data.events` for `event in {"retry_effort_clamped", "dispatch_effort_ignored"}`, de-dupes by a natural key (feature + event + model/effort), emits a `## Effort Degradations (N)` section listing each feature that ran clamped-to-`max` or warn-ignored-at-default, and returns `""` when none (so the section is omitted).
  - Wire it into `generate_report` (`report.py:2525-2574`) with the same conditional-append idiom the other optional sections use (`section = render_effort_degradation(data); if section: sections.append(section)`).
  - This closes the gap the critical review surfaced: the morning report renders only named sections, so a producer with no renderer is invisible. The `retry_effort_clamped` (Task 4b) and `dispatch_effort_ignored` (Task 5) events are the producers; this task is their consumer. Register both new event names in `bin/.events-registry.md` if the registry gate requires producer/consumer documentation.
- **Verification**: `.venv/bin/pytest cortex_command/overnight/tests/test_report.py -q` — pass if exit 0, with a new test asserting that a `ReportData` whose `events` include a `retry_effort_clamped` and a `dispatch_effort_ignored` entry produces a non-empty `render_effort_degradation` section naming the affected feature(s), AND that `generate_report` output contains the `Effort Degradations` heading; and that zero such events yields an empty section (omitted).
- **Status**: [ ] pending

### Task 9: ADR-0014 + whole-feature verification (ADR + gates)
- **Files**: `cortex/adr/0014-resolve-best-claude-cli-and-resilient-effort-handling.md` (new)
- **What**: Write ADR-0014 recording the prefer-newer-CLI + resilient-effort decision and trade-off (from spec §Proposed ADR), then run the full gate suite to confirm the whole feature is green.
- **Depends on**: [3, 6, 7, 8]
- **Complexity**: simple
- **Context**:
  - Author `cortex/adr/0014-…md` following the existing ADR format (`cortex/adr/0013-overnight-cli-repo-root-resolution-precedence.md` as the structural pattern: Context / Decision / Trade-off / Status). Content is given in spec §Proposed ADR. The resolver module docstring (Task 1) already cites ADR-0014, satisfying the citation-audit reference.
  - This task is the whole-feature gate: run the complete suite, not a single file.
- **Verification**: `just test` — pass if exit 0 (full suite incl. `test_dispatch.py`, `test_retry.py`, `test_cli_resolver.py`, the orchestrator-spawn test, and `cortex_command/dashboard/tests/test_routes_smoke.py`); AND `cortex/adr/0014-resolve-best-claude-cli-and-resilient-effort-handling.md` exists with Context/Decision/Trade-off sections (`grep -c "## Decision" cortex/adr/0014-*.md` ≥ 1).
- **Status**: [ ] pending

## Risks

- **Memoized resolver instead of the spec's literal "thread the path down."** The Technical Constraints say "resolve once at runner startup and thread the path down rather than resolving per-dispatch." This plan uses a memoized module-level `resolve_claude_cli()` (resolve-once via cache, env/monkeypatch-injectable) to avoid threading a new parameter through `dispatch_task` → `retry_task` → `feature_executor`. The two designs differ on one real axis — a threaded-once path resolves at one defined startup moment, while a memo's first-touch can occur at the first dispatch and freeze whatever environment that call sees. The Selection-rule hardening (Task 1: probe-flake prefers the present system CLI and is **not** memoized) closes the practical hazard of that difference. This is a deliberate smaller-surface choice satisfying the "resolve-once + injectable" intent; **flag for objection at approval if explicit startup threading is required**.
- **Morning-report visibility is now in scope (Task 8).** The report assembles from a closed renderer set, so a logged event with no renderer is invisible — Task 8 adds `render_effort_degradation` so the clamp/warn-ignore notes actually reach the operator, meeting R4/R5's "always surfaced" intent rather than deferring it.
- **`effort_unsupported` corpus match depends on the SDK passing stderr as `output`.** The classifier only sees the rejection text because the call site appends `_stderr_lines` to `output` (`dispatch.py:914`); the match keys off that corpus, not `ProcessError.stderr` (a hardcoded SDK placeholder). If a future SDK stops surfacing the child stderr there, the clamp would not trigger — acceptable given the SDK is hard-pinned and out of scope to bump.
- **Bundled-CLI lookup uses a package-relative path, not the SDK internal.** Task 1 locates `<claude_agent_sdk>/_bundled/claude` directly (the instance-method `_find_bundled_cli` is uncallable at module scope); if a future SDK relocates the bundled binary, `_find_bundled_cli_path()` returns `None` and the resolver degrades to "system or None" (today's behavior). Safe under the current hard pin.
- **Circuit-breaker preemption is explicitly handled (Task 4b).** A CLI-rejected effort produces an empty diff that the circuit breaker would otherwise read as "no progress" and pause before the clamp fires; Task 4b short-circuits the breaker for `effort_unsupported` and covers the attempt-≥2 empty-diff case in tests.
- **Serialized Phase 2.** Tasks 4a/5/7 all edit `dispatch.py` and 4b/6 both edit `retry.py`, so they are chained by `Depends on` to avoid same-file worktree-batch races rather than parallelized. Inherent to the two-file blast radius; accepted.

## Acceptance
A `(complex, high|critical)` overnight implement/review dispatch resolved to `opus + xhigh` runs to completion on a host whose system `claude` honors `xhigh` (the normal operator case) because the SDK now spawns the resolved system CLI via `cli_path`, not the stale bundled 2.1.69 — and a transient `--version` probe flake does not silently fall back to that stale bundle. On a host where only the older bundled CLI is present, the same dispatch runs at `max` after exactly one clamped retry (no blind budget burn, and the clamp fires regardless of which attempt the rejection lands on); a modern CLI that merely warn-ignores an unsupported effort still succeeds. Both the clamp and the warn-ignore render as an operator-visible **Effort Degradations** section in the morning report (not merely a buried JSONL line). Captured CLI stderr appears in `learnings/progress.txt`, the stale "silently downgraded"/`AssertionError` premises are gone, ADR-0014 records the decision, and `just test` exits 0.
