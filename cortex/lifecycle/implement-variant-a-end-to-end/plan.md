# Plan: implement-variant-a-end-to-end

## Overview
Wire the orchestrator session's mid-lifecycle `cd` into the interactive worktree, deploy a new `cortex-lifecycle-event log` CLI helper that uses the new `_resolve_user_project_root_from_cwd()` resolver to emit `interactive_worktree_entered`, extend `cortex init` to register the worktree base in both `sandbox.filesystem.allowWrite` and `additionalDirectories`, add a pre-flight check that gates §1a `cd` on the user's settings being migrated, and add cd-in-then-out around `/cortex-core:pr` in the Complete phase. The work lands as four PRs (Slice 7): Phase 1 (inventory + characterization + inventory-size gate), Phase 2 (`cortex init` extension), Phase 3 (new helper + new CLI), Phase 4 (lifecycle prose).

**Spec R3 divergence (operator-approved at plan critical-review):** Spec R3 prescribes a per-callsite `worktree_root: Path | None = None` parameter on the four CWD-pinned writer sites (`refine.py:117`, `critical_review.py`, `cortex-complexity-escalator`, `discovery.py:189-197`). This plan **does not** add that parameter to those sites — they already follow CWD via process inheritance after the §1a `cd`, so adding a parameter exercised only by tests would be dead surface area. Instead, the new `cortex-lifecycle-event` CLI helper internally calls `_resolve_user_project_root_from_cwd()` and is the load-bearing production-caller of Phase 3's helper. R3's acceptance ("each refactored writer site has at least one test passing a non-None `worktree_root` that lands the write in that path") is met by the new CLI helper's tests in Task 9. The operator may reject this divergence at §4 plan approval; if rejected, restore the four-site parameter refactor as a follow-up.

## Outline

### Phase 1: Writer-site inventory & characterization + size gate (tasks: 1, 2, 3)
**Goal**: Lock in the call-graph-derived writer-site inventory with a quantitative size signal so Phase 3 task decomposition can adapt; pin current behavior with characterization tests.
**Checkpoint**: `writer-sites.md` committed with a machine-readable `site_count` line; baseline tests green on `main`; Task 3 gate has surfaced size to operator (or auto-passed below threshold).

### Phase 2: Sandbox infrastructure (tasks: 4, 5)
**Goal**: Extend `cortex init` to additively register the worktree base path in `allowWrite` and `additionalDirectories`.
**Checkpoint**: A fresh `cortex init` populates both arrays idempotently in an isolated test fixture; re-running does not duplicate.

### Phase 3: Path-resolution helper + CLI emission helper (tasks: 6, 7, 8, 9)
**Goal**: Add `_resolve_user_project_root_from_cwd()` and a new `cortex-lifecycle-event log` CLI helper that uses it. The CLI is the load-bearing production caller of the helper.
**Checkpoint**: `just test` exits 0; new helper + CLI emission behavior covered; existing env-first contract in `_resolve_user_project_root()` unchanged.

### Phase 4: Lifecycle integration (tasks: 10, 11, 12, 13, 14)
**Goal**: Wire the cd handoff (with pre-flight migration check) and event emission via the new CLI into `implement.md` §1a; wire cd-in-then-out around `/cortex-core:pr` in `complete.md` Step 3 with advisory two-signal detection.
**Checkpoint**: `just test` exits 0 (including kept-pauses parity); four detection-outcome cases verified; manual end-to-end exercise of a Variant-A lifecycle observably writes the `interactive_worktree_entered` event into the worktree's events.log.

## Tasks

### Task 1: Phase 1 writer-site inventory artifact
- **Files**: `cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` (new)
- **What**: Enumerate orchestrator-session-reachable writer sites by tracing call graphs from `skills/lifecycle/references/implement.md` §1a–§4 and `skills/lifecycle/references/complete.md`. Each entry: `file:line` + reachability rationale + classification (`cwd-pinned` vs `env-pinned` per `research.md`'s "The eight named writer sites" section). Exclude sites in `cortex_command/overnight/daytime_pipeline.py` (slated for #246 removal). End the artifact with a machine-readable trailing line of the form `site_count: N` (exact case, single integer) for Task 3 to parse.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R4. Start from the eight ticket-named sites in `research.md` § "The eight named writer sites — verified state" and add any additional sites surfaced by call-graph audit. The classification informs reviewers that no parameter refactor is planned (Phase 3 routes via the new CLI helper instead); the size signal informs the Task 3 gate.
- **Verification**: `test -f cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` — pass if exit 0; `grep -c "^site_count: " cortex/lifecycle/implement-variant-a-end-to-end/writer-sites.md` = 1 — pass if count = 1.
- **Status**: [ ] pending

### Task 2: Characterization tests pinning current writer-site behavior
- **Files**: `tests/test_variant_a_writer_sites_baseline.py` (new), or per-module additions to existing test files where suitable.
- **What**: For each inventoried site, add a test that pins current pre-refactor behavior (resolved write target with default args). These tests pass on `main` and remain green after Phases 3–4 land — the plan does not modify the four CWD-pinned sites, so the assertion is regression detection only.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Spec R5. Pattern reference: env-var assertion structure in `cortex_command/tests/test_common.py:55-56`. Use `tmp_path` + `monkeypatch.chdir`/`monkeypatch.setenv` per case.
- **Verification**: `just test` — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Inventory-size operator gate
- **Files**: `cortex/lifecycle/implement-variant-a-end-to-end/phase-1-gate.md` (new) — a short structured note that records the inventory size and the gate decision (auto-passed vs surfaced-to-operator).
- **What**: Read `site_count` from `writer-sites.md`. If `site_count ≤ 12`, write `decision: auto-passed` to `phase-1-gate.md` and proceed. If `site_count > 12`, write `decision: surface-to-operator` plus the count to `phase-1-gate.md` and halt with an operator-visible message: "Phase 1 inventory surfaced {N} writer sites (threshold: 12). Phase 3 scope expansion may be needed before proceeding to Phase 4 — review `writer-sites.md` and request plan revision if the scope is no longer suitable for a single-CLI-helper Phase 3." The threshold 12 is the heuristic: under 12 sites, the existing CLI-helper-only Phase 3 strategy is sound; above 12, the unmodeled inventory growth is large enough that the operator should re-scope.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Resolves the critical-review A-class objection that the Risks-bullet mitigation "surface back at end of Task 1" had no executor. This task is the executor. The threshold is heuristic, not specced — chosen because the plan as written assumes ≲10 sites; a doubling justifies operator attention.
- **Verification**: `test -f cortex/lifecycle/implement-variant-a-end-to-end/phase-1-gate.md` — pass if exit 0; `grep -E "^decision: (auto-passed|surface-to-operator)$" cortex/lifecycle/implement-variant-a-end-to-end/phase-1-gate.md` returns 1 line — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Extend `cortex init` to register worktree base in `allowWrite` and `additionalDirectories`
- **Files**: `cortex_command/init/handler.py`
- **What**: Additively register the worktree base path (`$TMPDIR/cortex-worktrees/` by default, or `CORTEX_WORKTREE_ROOT` if set) in both `sandbox.filesystem.allowWrite` and `additionalDirectories` of `~/.claude/settings.local.json`. Idempotent under the existing `fcntl.flock`-guarded merge (per ADR-0003).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R6. Pattern reference: existing umbrella registration at `cortex_command/init/handler.py:194-198` (Step 7). Reuse the existing merge helpers — additive only.
- **Verification**: `grep -c "additionalDirectories" cortex_command/init/handler.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 5: Tests for `cortex init` worktree-base registration
- **Files**: `cortex_command/init/tests/test_settings_merge.py` (additions) or new sibling test file under `cortex_command/init/tests/`.
- **What**: Verify that after `cortex init` runs in an isolated test fixture, `settings.local.json` contains the worktree base path in both `allowWrite` and `additionalDirectories`. Re-running `cortex init` does not duplicate either entry.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Spec R6 acceptance. Pattern reference: fixtures in `cortex_command/init/tests/test_settings_merge.py:954`. Use `tmp_path` + `monkeypatch.setenv("HOME", ...)` to isolate the user settings path.
- **Verification**: `uv run python -m pytest cortex_command/init/tests/ -k "worktree_base"` — pass if exit 0 and at least one test in the selection passes.
- **Status**: [ ] pending

### Task 6: Add `_resolve_user_project_root_from_cwd()` helper
- **Files**: `cortex_command/common.py`
- **What**: New module-level function performing walk-up from `Path.cwd().resolve()` ignoring `CORTEX_REPO_ROOT`. Same stop conditions as the existing function: `.git` (file or directory) or `cortex/` directory presence. Raises `CortexProjectRootError` when no ancestor matches. Signature: `def _resolve_user_project_root_from_cwd() -> Path:`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R1, R2. Existing function at `cortex_command/common.py:55-103` retains its env-first contract — do not modify. Reuse the existing walk-up loop body (extract into a shared private helper if natural, otherwise duplicate the loop).
- **Verification**: `grep -c "def _resolve_user_project_root_from_cwd" cortex_command/common.py` = 1 — pass if count = 1.
- **Status**: [ ] pending

### Task 7: Tests for `_resolve_user_project_root_from_cwd()`
- **Files**: `cortex_command/tests/test_common.py`
- **What**: Add tests verifying (a) the helper returns the worktree root when CWD is inside a worktree even with `CORTEX_REPO_ROOT` set to the main repo; (b) the helper raises `CortexProjectRootError` from a non-cortex directory. Existing tests at lines 55-56 unchanged.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Spec R2 acceptance. Pattern reference: `cortex_command/tests/test_common.py:55-56`. Use `tmp_path` + a fake `.git` file (worktree-shaped) + `monkeypatch.setenv("CORTEX_REPO_ROOT", ...)`.
- **Verification**: `uv run python -m pytest cortex_command/tests/test_common.py -k "from_cwd"` — pass if exit 0 and at least one test in the selection passes.
- **Status**: [ ] pending

### Task 8: Build `cortex-lifecycle-event log` CLI helper
- **Files**: `cortex_command/lifecycle_event.py` (new), `pyproject.toml` (add `cortex-lifecycle-event` to `[project.scripts]`), plus one in-scope wiring reference (a `justfile` recipe `emit-event` is the lightest option, but the implementer may instead add a `docs/internals/events.md` mention — either satisfies the SKILL.md-to-bin parity rule). Eventual consumer wiring lands in Task 11.
- **What**: New module exposing a `log` subcommand. Signature (argparse): `cortex-lifecycle-event log --event {name} --feature {slug} [--worktree-path {path}]`. Internally calls `_resolve_user_project_root_from_cwd()` (Task 6) to resolve the lifecycle base, constructs `{base}/cortex/lifecycle/{feature}/events.log`, and appends a JSONL line `{schema_version, ts, event, feature, worktree_path}`. Use `tempfile + os.replace` for atomic append-with-flock per `cortex/requirements/pipeline.md:126`.
- **Depends on**: [6]
- **Complexity**: complex
- **Context**: This is the load-bearing production caller of Task 6's helper — the resolver is exercised in production, not test-only. Pattern reference: `cortex_command/interactive_lock.py:92-102` (`_emit_event` helper). The console-script entry-point pattern is documented in `cortex/requirements/project.md:35` ("Skill-helper modules"). Same task adds one in-scope wiring reference to satisfy the parity check (`bin/cortex-check-parity`); the recommended choice is a `justfile` recipe (`emit-event` that proxies to the CLI) because the justfile is already in-scope per the parity rule.
- **Verification**: `grep -c "cortex-lifecycle-event" pyproject.toml` ≥ 1 — pass if count ≥ 1; `grep -c "cortex-lifecycle-event\|emit-event" justfile` ≥ 1 OR `grep -c "cortex-lifecycle-event" docs/internals/events.md` ≥ 1 — pass if either count ≥ 1 (one in-scope reference suffices).
- **Status**: [ ] pending

### Task 9: Tests for `cortex-lifecycle-event log`
- **Files**: `cortex_command/tests/test_lifecycle_event.py` (new)
- **What**: Verify that (a) `cortex-lifecycle-event log --event interactive_worktree_entered --feature foo --worktree-path /tmp/xyz` appends a JSONL line to `{cwd-resolved}/cortex/lifecycle/foo/events.log` with the expected schema fields; (b) when CWD is inside a worktree (fake `.git` file), the events.log path resolves to the worktree base, not the env-pinned `CORTEX_REPO_ROOT`; (c) concurrent invocations do not interleave JSONL records (basic flock contract). This test also satisfies spec R3's acceptance criterion (the CLI is the "refactored writer site" with the non-None `worktree_root`-equivalent test).
- **Depends on**: [8]
- **Complexity**: complex
- **Context**: Use `tmp_path` + `monkeypatch.chdir` for CWD control + `monkeypatch.setenv("CORTEX_REPO_ROOT", ...)` to verify CWD-override behavior. Pattern reference: existing test fixtures in `cortex_command/tests/`.
- **Verification**: `uv run python -m pytest cortex_command/tests/test_lifecycle_event.py` — pass if exit 0 and at least one test in the file passes.
- **Status**: [ ] pending

### Task 10: Register `interactive_worktree_entered` event in events registry
- **Files**: `bin/.events-registry.md`
- **What**: Add a registry entry for `interactive_worktree_entered` with producer `cortex_command/lifecycle_event.py` (executable, not prose) and consumer `skills/lifecycle/references/implement.md` §1a. JSON schema: `{schema_version: 1, ts, event, feature, worktree_path}`.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: Spec R7 acceptance gates on `grep -c "interactive_worktree_entered" bin/.events-registry.md` = 1. Producer is the new module from Task 8 — making this entry consistent with adjacent entries (`interactive_lock_acquired`, `pr_opened`, `feature_complete`) which point at executable producers.
- **Verification**: `grep -c "interactive_worktree_entered" bin/.events-registry.md` = 1 — pass if count = 1; `grep -c "cortex_command/lifecycle_event" bin/.events-registry.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 11: Wire cd handoff + migration pre-flight + CLI emission into `implement.md` §1a
- **Files**: `skills/lifecycle/references/implement.md`. Plugin mirror at `plugins/cortex-core/skills/lifecycle/references/implement.md` regenerates via the pre-commit hook — edit canonical source only.
- **What**: After worktree creation and lock acquisition in §1a, add prose directing the orchestrator to:
  1. **Pre-flight check**: Verify `~/.claude/settings.local.json` contains the worktree base path (default `$TMPDIR/cortex-worktrees/` or `$CORTEX_WORKTREE_ROOT`) in BOTH `sandbox.filesystem.allowWrite` AND `additionalDirectories`. Implementer chooses the form — either a one-shot Bash check inlined in the §1a prose, or a new `cortex-lifecycle-event preflight` subcommand on the Task 8 CLI (preferred if implementer's judgment is that pre-flight is reusable). On a missing or mismatched registration, halt with the message "Variant A requires the worktree base to be registered in your settings. Re-run `cortex init` and retry. See cortex/lifecycle/implement-variant-a-end-to-end/spec.md Edge Cases for context." Exit-code contract: implementer's chosen mechanism uses exit 0 for pass, exit 2 for missing-registration, exit 3 for malformed-settings (operator can re-run `cortex init`).
  2. **Capture origin pwd**: `_origin_pwd=$(pwd)` (held for the lifecycle, not just §1a).
  3. **Cd into worktree**: `cd $(cortex-worktree-resolve interactive/{slug})`.
  4. **Emit event via CLI**: `cortex-lifecycle-event log --event interactive_worktree_entered --feature {slug} --worktree-path "$(pwd)"`.
  5. **Scope cross-reference paragraph**: Include a paragraph beginning "Variant A's cd affects only orchestrator-session Bash" whose final sentence cross-references §2(e) Worktree Integration (`implement.md:151-161`).
- **Depends on**: [8, 10]
- **Complexity**: simple
- **Context**: Spec R7. The pre-flight check resolves the critical-review B-class objection that the Risks-bullet migration gap was unmitigated. The CLI emission resolves the A-class objection that the emission mechanism was unspecified. Kept-pauses parity: if line shifts cause the inventory anchor at `skills/lifecycle/SKILL.md:60` or `implement.md:22` to move >35 lines, update `skills/lifecycle/SKILL.md` "Kept user pauses" inventory in this task.
- **Verification**: `grep -c "cortex-lifecycle-event log" skills/lifecycle/references/implement.md` ≥ 1 — pass if count ≥ 1; `grep -c "Variant A's cd affects only orchestrator-session Bash" skills/lifecycle/references/implement.md` = 1 — pass if count = 1; `grep -c "settings.local.json" skills/lifecycle/references/implement.md` ≥ 1 — pass if count ≥ 1; `just test` — pass if exit 0 (kept-pauses parity included).
- **Status**: [ ] pending

### Task 12: Add advisory worktree-detection prose to `complete.md` Step 3
- **Files**: `skills/lifecycle/references/complete.md`. Plugin mirror regenerates via pre-commit hook.
- **What**: In Step 3, add prose for two-signal advisory detection: read `interactive.pid` via `cortex_command/interactive_lock.py:read_lock(feature_slug)` AND corroborate by comparing `git rev-parse --show-toplevel` against `pwd`. If either signal is absent or contradictory, treat as NOT in Variant A and skip the cd-in-then-out branch (proceed with `/cortex-core:pr` from current cwd).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Spec R9. Public API reference: `cortex_command/interactive_lock.py` `read_lock`. Pattern reference: existing cd-out-or-bail guard at `complete.md:159-163` (Step 8).
- **Verification**: `grep -c "git rev-parse --show-toplevel" skills/lifecycle/references/complete.md` ≥ 1 — pass if count ≥ 1; `grep -c "interactive.pid" skills/lifecycle/references/complete.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 13: Wire cd-in-then-out around `/cortex-core:pr` in `complete.md` Step 3
- **Files**: `skills/lifecycle/references/complete.md`. Plugin mirror regenerates via pre-commit hook.
- **What**: Update Step 3 so that when the Task 12 detection reports positive, the lifecycle (a) saves `_origin_pwd=$(pwd)`, (b) `cd`s into the worktree if not already there, (c) invokes `/cortex-core:pr`, (d) restores `cd "$_origin_pwd"` after the PR skill returns. The Step 8 cd-out hard guard at `complete.md:159-163` composes correctly because of (d).
- **Depends on**: [12]
- **Complexity**: simple
- **Context**: Spec R8. Pattern reference: existing Step 3 prose. Kept-pauses parity: if line shifts cause `complete.md` inventory anchors to move >35 lines, update `skills/lifecycle/SKILL.md` "Kept user pauses" inventory in this task.
- **Verification**: `grep -c "_origin_pwd" skills/lifecycle/references/complete.md` ≥ 2 — pass if count ≥ 2; `just test` — pass if exit 0 (kept-pauses parity included).
- **Status**: [ ] pending

### Task 14: Add detection-case tests in `test_complete_pr_routing.py`
- **Files**: `tests/test_complete_pr_routing.py` (new)
- **What**: Verify the four detection-outcome cases for advisory worktree detection: (a) both signals positive → cd-in-then-out path is selected; (b) PID stale + pwd in worktree → cd-in-then-out path; (c) PID present + pwd NOT in worktree → non-worktree path; (d) both absent → non-worktree path.
- **Depends on**: [12, 13]
- **Complexity**: complex
- **Context**: Spec R9 acceptance. Mock `cortex_command.interactive_lock.read_lock` and `subprocess.run` for `git rev-parse --show-toplevel`. Use `tmp_path` + `monkeypatch.chdir` to control `pwd`.
- **Verification**: `uv run python -m pytest tests/test_complete_pr_routing.py` — pass if exit 0 and at least one test in the file passes.
- **Status**: [ ] pending

## Risks

- **Spec R3 divergence (operator-approved at plan critical-review):** spec R3 prescribes per-callsite `worktree_root` parameter additions to four CWD-pinned sites; this plan replaces that with a CLI-helper-as-production-caller approach. If the operator rejects the divergence at §4 approval, restore the parameter refactor as a follow-up — Task 8/9 stay; Task 7's helper stays; only the four-site param add is reinstated.
- **Task 3 gate threshold (12) is heuristic.** If Phase 1 surfaces between 8 and 12 sites, the gate auto-passes and the plan as written executes. Between 12 and 20, the gate halts but the resolution path (split Task 8 / add follow-up tasks / re-scope) is unspecified — operator judgment fills the gap. The threshold can be tuned in this task as inventory results surface.
- **Migration pre-flight halt may surprise an early user.** Task 11's pre-flight check halts §1a on unmigrated `settings.local.json`. Users on a recent install who have not re-run `cortex init` will hit the halt. The message names the recovery path explicitly — re-run `cortex init` — so the surprise is recoverable. Release notes should call out the re-init step.
- **Slice 7 four-PR commit shape (R10, should-have)** is preferred for reviewability and bisect-ability. If reviewer load on four sequential PRs proves heavy, fall back to a single bundled PR; the four-phase task structure remains intact.
- **Kept-pauses parity drift**: Tasks 11 and 13 modify `implement.md` and `complete.md` near existing parity anchors. If line-shift exceeds the 35-line tolerance in `tests/test_lifecycle_kept_pauses_parity.py`, the SKILL.md inventory must update in the same task (called out per-task).
- **Open Decision — `interactive.pid` session_id migration on `/clear`** (spec § Open Decisions): surface to user during plan approval; either fold into Task 12 scope or carve out as a follow-up ticket.

## Acceptance

After all four phases land: a Variant-A session that selects implement-phase preflight option 2 creates an `interactive/{slug}` worktree; §1a's pre-flight check confirms the user's `~/.claude/settings.local.json` has the worktree base registered (halting with re-run guidance if not); the orchestrator `cd`s into the worktree and emits an `interactive_worktree_entered` event via `cortex-lifecycle-event log` (which uses `_resolve_user_project_root_from_cwd()` to land the event in the worktree's events.log, observable in the eventual PR); and `/cortex-core:lifecycle complete <slug>` opens a worktree-aware PR via cd-in-then-out around `/cortex-core:pr`. `just test` exits 0; kept-pauses parity passes; existing env-first contract in `_resolve_user_project_root()` unchanged.
