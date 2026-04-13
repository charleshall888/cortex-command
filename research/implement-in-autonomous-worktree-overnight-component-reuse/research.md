# Research: Implement in autonomous worktree (overnight-component reuse)

**Backlog**: [074](../../backlog/074-implement-in-autonomous-worktree-overnight-component-reuse.md)
**Date**: 2026-04-13
**Phase**: Research (discovery)

## Executive framing

This research started from backlog 074's framing — build a daytime autonomous-worktree pipeline that reuses overnight primitives. Investigation revealed that framing is secondary to a bigger question: **`batch_runner.py` (2198 LOC) mixes three distinct architectural layers** (session coordination, per-feature execution, outcome routing) in one file with no dedicated unit tests. The cleanest decomposition of that file *is* the extraction that would let a daytime pipeline exist cheaply. The modularization is the primary value driver; daytime pipeline is a follow-on consumer that may or may not be built.

This reframes the epic:
- If we only extract to serve daytime, the ROI case depends on evidence that TC4 (context exhaustion) actually occurs — evidence is currently absent.
- If we extract for overnight's own maintainability and testability, the ROI case stands on its own, and daytime becomes nearly free afterwards.

Recommendation below leans into this reframing.

## Research Questions

1. **Extractability of pipeline primitives** — Can the overnight orchestrator be reused from a daytime orchestrator?
   → At the *leaf* level, yes (dispatch_task, dispatch_review, merge_feature, retry_task are clean async functions with no session coupling). At the *pipeline orchestration* level, no — the ~700 LOC of glue inside `batch_runner.py` conflates three layers and is not reusable as-is. The right answer is not "extract a little layer for daytime" but "decompose batch_runner along its natural seams" — the byproduct is a reusable orchestration core.

2. **Entry point shape** — `python3 -m` module invoked as a subprocess, mirroring `batch_runner.py`'s argparse + `asyncio.run()` pattern.

3. **Main-session communication** — Synchronous `subprocess.run()`. Critical constraint: subprocess must write `events.log` to the *main repo's working tree*, not inside the daytime worktree — otherwise main reads stale data (the TC8 pattern).

4. **Escalation without a morning report** — Defer-and-exit. Per-feature `lifecycle/{feature}/deferred/` (not the shared `lifecycle/deferred/`) to avoid colliding with overnight's morning report.

5. **Co-exist vs. replace (single-agent worktree)** — Co-exist. Single-agent retains a property subprocess doesn't: the user can watch and interrupt in-session (live-steerability). Replacement removes this.

6. **Cost/benefit vs. "queue for overnight"** — The value case for daytime pipeline alone is thin: TC4 is theoretical (no retro/log evidence), and a <50-LOC "queue-for-overnight" skill action substitutes for most async needs. *But* the value case for the underlying batch_runner decomposition is independent and stronger (see Q7).

7. **Refactor risk / opportunity** — The file isn't just big; it's mixing levels. Map below. Extraction is justified on maintainability grounds even without daytime pipeline. Mitigation: new tests land alongside extracted modules; treat a successful overnight run + unit-test pass as acceptance.

8. **Interaction with #073 (overnight docs)** — Parallel. #073's architectural description *will* use the decomposed module names; landing #073 first lets its diagrams be drawn against the target shape rather than the legacy one. Sequencing preference: #073 first, then the decomposition, then (optionally) daytime.

## Codebase Analysis

### Leaf primitives (claude/pipeline/) — already clean

| Primitive | File | Takes | Writes |
|-----------|------|-------|--------|
| `dispatch_task` | `claude/pipeline/dispatch.py:332` | feature, task, worktree_path, complexity, system_prompt, optional log_path | Caller's log_path, worktree files |
| `dispatch_review` | `claude/pipeline/review_dispatch.py:121` | feature, worktree_path, branch, spec_path, complexity, criticality | Feature events.log, `review.md`, optionally deferral |
| `merge_feature` | `claude/pipeline/merge.py:158` | feature, base_branch, test_command, optional branch, repo_path | Caller's log_path, git state (merge/revert) |
| `retry_task` | `claude/pipeline/retry.py:160` | Same as dispatch_task + retry context | Feature events.log, `learnings/progress.txt` |
| Test-gate + auto-revert | `merge.py:292-324` (inside merge_feature) | — | `git revert -m 1 --no-ff HEAD` on test failure |

Tool allowlist hardcoded at `dispatch.py:188`:
```python
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
```

### batch_runner.py responsibility map (2198 LOC, 15 conceptual buckets)

| # | Responsibility | Lines |
|---|----------------|-------|
| 1 | Multi-repo integration-branch routing | 166–328 |
| 2 | Per-feature context loading (spec, learnings, plan, prompt render) | 335–410, 853–878 |
| 3 | Exit-report validation | 443–490 |
| 4 | Idempotency (plan hash, task tokens, completion scan) | 580–654 |
| 5 | Brain-agent triage on failed tasks | 496–576 |
| 6 | Git state inspection (`_get_changed_files`, `_classify_no_commit`) | 391–437 |
| 7 | Per-feature execution loop (`execute_feature`) | 662–1066 |
| 8 | Conflict recovery policy (trivial fast-path, repair agent, budget gate) | 679–825 |
| 9 | Backlog write-back | 1070–1193 |
| 10 | Feature result dispatch (`_apply_feature_result`) | 1203–1532 |
| 11 | Merge + test-gate + review gating | 1328–1456, 1674–1826 |
| 12 | Post-merge test-failure recovery | 1842–1983 |
| 13 | Concurrency management (semaphore, throttle, rate-limit) | 1591–2030 |
| 14 | Circuit breaker + global abort signal | 1515–1516, 1627–1650, 1965–2016 |
| 15 | Batch-level orchestration loop, heartbeat, final state write-back | 1535–2144 |

Key structural observation: **three architectural layers are interleaved**, which is what makes the file hard to test and hard to reason about:
- **Session layer** (rows 1, 13, 14, 15): rounds, concurrency, heartbeat, final persistence.
- **Feature-execution layer** (rows 2–8): per-feature task orchestration.
- **Outcome-routing layer** (rows 9–12): what happens when a feature produces a result — merge, review, recovery, backlog, circuit-break.

Every outcome path writes event logs, mutates `consecutive_pauses_ref` (shared mutable circuit-breaker counter), and calls `_write_back_to_backlog` — these are scattered across 12+ sites. Policy ("is 2 review cycles enough?", "is the conflict trivial?", "is recovery budget exhausted?") is interleaved with mechanism ("run the review cycle", "call the repair agent", "attempt merge") inside the same functions.

### Prior art in this repo

`claude/pipeline/review_dispatch.py` was successfully extracted from batch_runner along exactly one of these seams (outcome routing → review gating). The boundary has survived; batch_runner imports from it cleanly. This is a data point that the same extraction pattern applied to the remaining seams will survive.

`claude/pipeline/` generally is well-modularized (dispatch, retry, merge, conflict, merge_recovery, review_dispatch) — the primitives layer is the precedent for how decomposition looks in this codebase. batch_runner is the last remaining multi-responsibility module.

### Test coverage

- `claude/pipeline/tests/`: dedicated unit tests for each pipeline primitive. Good coverage.
- `claude/overnight/tests/`: covers deferral, state, escalation, plan parsing.
- **No dedicated unit tests for batch_runner.py** — integration runs are the only behavior-pinning mechanism. This is a liability regardless of #074.

### Retro signal

- `retros/2026-04-12-2038`: 8 failure modes of current single-agent worktree dispatch (TC8, AskUserQuestion sharp edge, cleanup hook mismatch, etc.).
- `retros/2026-04-12-2057`: "ceremony/complexity ratio" concern. Argues against both over-engineering the refactor *and* against permanent duplication.
- **No retro or events.log cites a daytime feature actually hitting TC4 (context exhaustion).** The epic's framing of TC4 as inevitable is theoretical by current evidence.

Repo history: 0 of 73 backlog titles contain "unify / consolidate / extract shared / deduplicate / promote to shared". The "ship duplicated, unify later" pattern has no precedent — reinforcing that if extraction is worth doing, it should be done once, not staged through duplication.

## Proposed decomposition (Candidate A: 3-way split)

Target layout after refactor:

```
claude/overnight/
    batch_runner.py      # ~30 LOC — thin CLI wrapper (argparse + asyncio.run)
    orchestrator.py      # ~600 LOC — session layer (run_batch, _run_one, _accumulate_result, heartbeat, final state)
    feature_executor.py  # ~600 LOC — per-feature execution (execute_feature, idempotency, context, exit-report, brain triage, conflict recovery)
    outcome_router.py    # ~700 LOC — outcome routing (apply_feature_result, merge paths, review gating, test-recovery, backlog write-back, circuit breaker)
    state.py, throttle.py, deferral.py, brain.py, strategy.py   # unchanged
```

**Public contracts:**

```python
# orchestrator.py
async def run_batch(config: BatchConfig) -> BatchResult

# feature_executor.py
async def execute_feature(
    feature: str,
    worktree_path: Path,
    config: BatchConfig,
    spec_path: Optional[str] = None,
    manager: Optional[ConcurrencyManager] = None,
    consecutive_pauses_ref: Optional[list[int]] = None,
    repo_path: Path | None = None,
    integration_branches: dict[str, str] | None = None,
) -> FeatureResult

# outcome_router.py
def apply_feature_result(
    name: str,
    result: FeatureResult,
    batch_result: BatchResult,
    consecutive_pauses_ref: list[int],
    config: BatchConfig,
    backlog_ids: dict[str, Optional[int]],
    ...
) -> None
```

### Why this split (maintainability argument)

- **One question per module.** orchestrator.py answers "how many things run in parallel and when do we stop?"; feature_executor.py answers "how do we execute one feature?"; outcome_router.py answers "what happens when a feature produces a result?". Today all three questions are answered in the same file, tangled across ~1500 LOC.
- **Testability step-change.** outcome_router becomes ~70% unit-testable (pure routing; mock merge/review). feature_executor becomes ~50% unit-testable (pure helpers + mockable agent dispatch). orchestrator stays integration-testable. Current file is ~30% unit-testable.
- **Policy/mechanism alignment.** outcome_router centralizes policy ("is review needed?", "is conflict trivial?", "budget exhausted?") that is currently buried inside execution loops. Changes to policy touch one file.
- **Extension points clarified.** New outcomes → add a case to `apply_feature_result`. New triage criteria → modify `feature_executor._handle_failed_task`. New concurrency rules → modify `orchestrator.run_batch`. Today all three blur into the same file.
- **Consistent with repo's existing modularization.** `claude/pipeline/` followed this exact pattern; `review_dispatch.py` extraction is prior-art evidence the boundary holds.

### What does NOT move

- `ConcurrencyManager`, `OvernightState`, `strategy.py`, `deferral.py`, `brain.py`: already separate modules, not in scope.
- Conflict recovery stays inside feature_executor (not split further) — current shape is cohesive; Candidate C (4-way split with separate policy modules) is over-engineering for this scope.

### Daytime pipeline after the decomposition

Once feature_executor + outcome_router exist as modules:

- **Option 1**: Daytime calls `execute_feature()` + `apply_feature_result()` directly with a minimal driver. ~100–150 LOC new code for the driver, CLI, and output surfacing — vs. 300–700 LOC of duplication or a full refactor, either of which was the cost in the first-draft framing.
- **Option 2**: Don't build daytime at all; keep the decomposition as its own win. Revisit daytime if/when TC4 evidence materializes.

Either way, the extraction pays for itself independent of the daytime decision.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Decompose batch_runner into 3 modules (orchestrator / feature_executor / outcome_router) + tests** | L (~16–20 hrs: 5 hrs extraction, 8 hrs tests, rest for integration) | Refactoring untested code; regression risk on overnight; circuit-breaker / consecutive_pauses_ref passing across module boundaries. Mitigated by tests landing alongside each extraction phase. | #073 docs first (recommended, not strictly blocking) |
| **A + daytime driver** | L + S (~4 hrs after A lands) | Subprocess lifecycle, cleanup-hook race, TC8 events.log placement — addressed as design questions not blockers. | A landed first |
| **B. Daytime-only orchestrator, duplicate ~300–700 LOC, overnight untouched** | M–L | Drift on hot surface (retry ladder, model escalation, review cycle, merge policy, error taxonomy). Follow-up unify pattern has no precedent (0/73 tickets). Batch_runner remains 2198 LOC and untested. | None |
| **C. Defer everything pending #073 + batch_runner unit tests** | XL | Blocks all daytime benefit and all modularization benefit. | Full #073 + a lot of test writing |
| **D. Status quo — do nothing** | S | batch_runner stays 2198 LOC and untested. Single-agent "Implement in worktree" stays live but hits TC4 ceiling. | None |
| **E. "Queue for overnight" skill action + nothing else** | S (<50 LOC wrapper) | Doesn't fix batch_runner's maintainability. Doesn't cover "user wants result today." | None |

**Recommendation: A (with or without the daytime follow-on).** The modularization value is real and independent. The refactor cost is L but scoped — we're not rewriting 2198 LOC, we're extracting along three existing seams, with tests landing alongside each phase. If the daytime follow-on is desirable, it becomes cheap (~S effort); if it isn't, A still stands on its own.

**What to do about the daytime question**: Treat it as optional. After A lands, either build the thin daytime driver (Option 1) or don't (Option 2); the decision can be made later with evidence from actual TC4 incidents. Do not gate A on the daytime outcome.

## Decision Records

### DR-1 (revised): Extract batch_runner along three seams; treat daytime as optional follow-on

- **Context**: The refactor question and the daytime question are separable. The refactor is justified by batch_runner's current structure (2198 LOC, three layers interleaved, no unit tests). Daytime is justified only by TC4 evidence, which is currently absent.
- **Options considered**:
  - A. Decompose batch_runner; daytime becomes a thin follow-on if wanted.
  - B. Daytime-only orchestrator, duplicate glue, overnight untouched.
  - D/E. Status quo or tiny substitute (queue-for-overnight).
- **Recommendation**: A. Pay the refactor cost once for overnight's own maintainability. Build daytime driver only if subsequent TC4 evidence justifies it.
- **Trade-offs**: L effort upfront with no shipped feature during the refactor phase. Benefits: smaller, testable modules; daytime becomes cheap later; batch_runner stops being a "change at your own risk" file.

### DR-2: Daytime (if built) co-exists with single-agent "Implement in worktree"

- **Context**: Live-steerability is a property of the single-agent path that the subprocess path cannot replicate (subprocess is opaque until exit).
- **Recommendation**: If daytime is built, offer it as a third pre-flight option alongside single-agent worktree and feature branch. Document that daytime is for many-task features; single-agent for live-steerable small work.

### DR-3: Daytime subprocess writes events.log to main repo CWD, not worktree

- **Context**: If subprocess writes events.log inside its worktree, main reads stale data — the TC8 pattern.
- **Recommendation**: Pass `--events-log-path` pointing at main repo's `lifecycle/{feature}/events.log`. Worktree code changes stay in the worktree; event stream stays in main.

### DR-4: Per-feature `lifecycle/{feature}/deferred/`, not shared `lifecycle/deferred/`

- **Context**: Shared deferred/ collides with overnight's morning report if daytime and overnight run concurrently.
- **Recommendation**: Namespace per-feature. Morning report opt-in if it ever needs to surface prior daytime deferrals.

### DR-5 (new, central): Modularization is the primary value driver

- **Context**: The extraction improves overnight's maintainability, testability, and extensibility independent of daytime pipeline. batch_runner today is the largest and least-tested file in `claude/overnight/` and sits in the hot path of every overnight session.
- **Recommendation**: Fund the refactor on its own merits. Daytime pipeline is a consumer of the cleaner surface, not a justification for it.
- **Trade-offs vs. "don't refactor"**: L effort with no new user-visible behavior in the refactor phase itself. Offset by: every future change to overnight's feature-dispatch / outcome-routing becomes safer and smaller.

## Implementation phasing (for /lifecycle plan, if epic proceeds)

1. **Phase 1 — Extract `feature_executor.py`**. Move `execute_feature` + helpers (idempotency, context loading, exit-report, brain triage, conflict recovery). batch_runner imports from it. Add unit tests for idempotency + context loading. Run full overnight as regression gate.
2. **Phase 2 — Extract `outcome_router.py`**. Move `_apply_feature_result` + merge paths + review gating + test-recovery + backlog write-back + circuit-breaker detection. batch_runner's `_accumulate_result` collapses to a one-line call. Add unit tests for `apply_feature_result` (mock merge/review); assert circuit breaker fires at threshold.
3. **Phase 3 — Rename batch_runner.py → orchestrator.py**; keep batch_runner.py as thin CLI wrapper preserving the `python3 -m claude.overnight.batch_runner` contract.
4. **Phase 4 — Integration tests for `orchestrator.run_batch`**: multi-feature batch with mocked feature_executor + outcome_router; assert concurrency, circuit breaker, budget exhaustion, heartbeat.
5. **Phase 5 (optional) — Daytime driver**: thin module (~150 LOC) + CLI entry + skill integration. Only if TC4 evidence justifies.

## Open Questions (for /lifecycle specify/plan)

- **Direction call**: Does the epic proceed as "refactor for modularization; daytime as optional Phase 5"? Or is daytime pipeline a hard requirement regardless?
- **Should #073 land before Phase 1?** Recommended yes (docs drawn against target shape); not strictly blocking.
- **Test coverage target per phase**: specific LOC targets, or a blanket "70% of extracted module" goal?
- **`consecutive_pauses_ref` plumbing**: remains a mutable list passed through call chain. Clean up opportunistically (e.g., into a small `CircuitBreakerState` dataclass) or leave as-is?
- **Naming**: `orchestrator.py` vs. keeping `batch_runner.py` for the session-layer module? (The CLI wrapper claims the `batch_runner.py` filename.) Bikeshed territory; decide in spec phase.

If daytime Phase 5 proceeds:
- Subprocess lifecycle / parent-death handling (PID file, watchdog, or accept orphans?).
- Worktree prefix — `worktree/agent-*` (inherits cleanup hook + race) or new `worktree/daytime-*` (requires hook update)?
- `.dispatching` marker replacement for double-dispatch guard.
- Concurrent daytime + overnight locking on `main`.
- Mid-merge SIGKILL recovery protocol.
- Brain-triage behavior for daytime (inherit? simplify? skip?).
- Budget caps; `_ALLOWED_TOOLS` delta (daytime may want `WebFetch`).

## Skipped sections

- **Web & Documentation Research**: Purely internal refactor; no external dependencies in scope.
- **Domain & Prior Art (external)**: The most relevant prior art is this repo's own `claude/pipeline/` decomposition and the already-successful `review_dispatch.py` extraction. Industry parallels (git plumbing/porcelain split, workflow-engine operator separation) exist but don't add specifics beyond what the internal pattern already shows.
