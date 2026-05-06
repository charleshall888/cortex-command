# Review: build-shared-synthesizer-for-critical-tier-dual-plan-flow-interactive-overnight

## Stage 1: Spec Compliance

### Requirement 1 — Shared synthesizer prompt fragment

- File `cortex_command/overnight/prompts/plan-synthesizer.md` exists and contains `plan_synthesizer_v1` identity tag (line 1).
- Verbatim MT-Bench-derived "Avoid any position biases" instruction present (line 30, 32).
- Untrusted-data instruction present (lines 20-24, framed against `/cortex-interactive:research` convention).
- JSON envelope schema is in positional order: `schema_version` → `per_criterion` → `verdict` → `confidence` → `rationale` (lines 81-101). Field-by-field documentation (lines 104-112) explicitly calls the order "load-bearing".
- `<!--findings-json-->` delimiter present (line 78).

**Rating: PASS**

### Requirement 2 — Synthesizer dispatch shape (shared)

- `grep -q "Task sub-agent" cortex_command/overnight/prompts/orchestrator-round.md` → exit 0.
- `grep -q "Task tool" plugins/cortex-interactive/skills/lifecycle/references/plan.md` → exit 0.
- `grep -q "<!--findings-json-->" cortex_command/overnight/prompts/plan-synthesizer.md` → exit 0.
- `LAST.occurrence|last.occurrence` references count = 4 across the two dispatching contexts (≥ 1 required).

**Rating: PASS**

### Requirement 3 — Interactive §1b wiring

- `grep -c "synthesizer" plugins/cortex-interactive/skills/lifecycle/references/plan.md` → 14 (≥ 5 required).
- "rubber-stamp" present (line 112).
- "synthesizer's preliminary rationale is hidden" verbatim present (line 114).
- Synthesizer dispatch + envelope extraction + verdict/confidence routing + v2 logging all wired in §1b.d–g (lines 96-139).
- Fallback table preserved on low-confidence/malformed envelope (lines 114-123).

**Rating: PASS**

### Requirement 4 — Overnight Step 3b wiring (criticality branch)

- `grep -A 3 "criticality.*critical" cortex_command/overnight/prompts/orchestrator-round.md | grep -q "plan-variant"` → exit 0.
- `grep -q "synthesizer Task sub-agent" cortex_command/overnight/prompts/orchestrator-round.md` → exit 0.
- Step 3b.1 (lines 227-396) implements gate check → criticality check → variant dispatch → edge cases → synthesizer dispatch → LAST-occurrence extraction → verdict/confidence routing → SDK error handling → fall-through, with deferred features marked via worker-style exit-report wrapper.
- `uv run pytest cortex_command/overnight/tests/test_orchestrator_round.py -k synthesizer -v` → 4 passed.

**Rating: PASS**

### Requirement 5 — Extended `plan_comparison` event schema (v2, additive)

- `grep -E '"schema_version":\s*2' ...` across the three target files → 3 matches (≥ 3 required).
- All five new fields (`selection_rationale`, `selector_confidence`, `position_swap_check_result`, `disposition`, `operator_choice`) present in the v2 example JSON in canonical plan.md (line 128).
- `uv run pytest cortex_command/pipeline/tests/test_metrics.py -k 'plan_comparison or v2_tolerance'` → 2 passed (round-trip + downstream-filter-unaffected).

**Rating: PASS**

### Requirement 6 — Unit-test coverage (3 calibration probes)

- `uv run pytest cortex_command/pipeline/tests/test_plan_synthesizer.py -v` → 4 passed.
- Test file covers: identical-variants tie, position-swap consistency (verbatim "Run the comparison twice with variant order swapped" assertion), and planted-flaw probe with synthetic fallback fixture (no `pytest.mark.skipif` — runs unconditionally).

**Rating: PASS**

### Requirement 7 — Validation gate (runtime-enforced)

- `grep -q "synthesizer_overnight_enabled" cortex_command/overnight/prompts/orchestrator-round.md` → exit 0.
- `grep -q "synthesizer_overnight_enabled" cortex_command/overnight/cli_handler.py` → exit 0.
- `read_synthesizer_gate(config_path)` at `cli_handler.py:57-97` is fail-closed: returns `False` on `FileNotFoundError`, `OSError`, missing field, malformed frontmatter, or non-`true` value (case-insensitive).
- `lifecycle.config.md` has `synthesizer_overnight_enabled: false` at line 9 (default-false posture preserved; no premature flag-flip in this lifecycle's commits).
- Canonical asset and plugin mirror at `skills/lifecycle/assets/lifecycle.config.md` and `plugins/cortex-interactive/skills/lifecycle/assets/lifecycle.config.md` both carry the flag.

**Rating: PASS**

### Requirement 8 — Defer-count session circuit breaker

- `_count_synthesizer_deferred(events_path, session_id)` extracted at `runner.py:317-340`.
- Threshold reuses shared `CIRCUIT_BREAKER_THRESHOLD = 3` from `constants.py:7` (no separate threshold introduced).
- On reaching threshold (`runner.py:2310-2357`): emits `SYNTHESIZER_CIRCUIT_BREAKER_FIRED`, calls `_transition_paused` with `reason="synthesizer_circuit_breaker"`, marks remaining critical-tier features `paused`, breaks the round loop.
- `uv run pytest cortex_command/overnight/tests/test_synthesizer_circuit_breaker.py -v` → 4 passed.

**Rating: PASS**

### Requirement 9 — Anti-sway protections at prompt-fragment layer

- 7-instruction grep loop passes for all of: `Variant 1`, `did not produce any variant`, `per-criterion`, `ignore.*order`, `uncertain.*low confidence`, `untrusted`, `swap`.
- Fragment includes blinded labels, fresh-agent role separation, per-criterion scoring before prose rationale, MT-Bench position-bias instruction, "When uncertain, assign low confidence", untrusted-variant-data instruction (analogous to `/cortex-interactive:research`), and verbatim swap-and-require-agreement instruction.

**Rating: PASS**

### Requirement 10 — Lifecycle index.md artifact registration

- `grep -E '^artifacts:' lifecycle/archive/build-shared-synthesizer-for-critical-tier-dual-plan-flow-interactive-overnight/index.md` → `artifacts: [research, spec, plan]`. Spec and plan both registered.

**Rating: PASS**

## Stage 2: Code Quality

### Naming conventions

Consistent with existing project patterns. Event constants follow lowercase-string-equals-uppercase-name convention from `events.py:32-83`. `read_synthesizer_gate` mirrors `_read_test_command` in `daytime_pipeline.py`. Helper `_count_synthesizer_deferred` is module-private (leading underscore) matching `_count_pending`/`_count_merged` neighbors at `runner.py:303-314`. `synthesizer_overnight_enabled` is snake_case matching the existing `lifecycle.config.md` field style.

### Error handling

- Gate read is fail-closed per Requirement 7 (file absent, malformed frontmatter, missing field → `False`); catches `FileNotFoundError` and `OSError`. Appropriate.
- Circuit breaker uses the existing `_transition_paused` helper rather than reimplementing pause semantics; reuses `CIRCUIT_BREAKER_THRESHOLD` constant rather than introducing a parallel threshold. Appropriate.
- Synthesizer SDK error path in `orchestrator-round.md` step (6) emits `SYNTHESIZER_ERROR` before `PLAN_SYNTHESIS_DEFERRED` for postmortem visibility — both signals captured.

### Test coverage

All targeted pytest commands from plan.md Verification Strategy pass:
- `cortex_command/pipeline/tests/test_plan_synthesizer.py` → 4 passed.
- `cortex_command/pipeline/tests/test_metrics.py -k 'plan_comparison or v2_tolerance'` → 2 passed.
- `cortex_command/overnight/tests/test_orchestrator_round.py -k synthesizer` → 4 passed.
- `cortex_command/overnight/tests/test_synthesizer_circuit_breaker.py` → 4 passed.
- `just test` → 6/6 passed (no regression in pre-existing tests).

### Pattern consistency (dual-source mirrors)

- `git diff --quiet -- plugins/cortex-interactive/skills/` → exit 0 (mirror in sync with canonical).

### LLM prompt-following coverage boundary

Documented explicitly in plan.md §83 (Task 9 What-field) and §122 (Verification Strategy item 6): the orchestrator agent's interpretation of `orchestrator-round.md`'s Step 3b prose is verified by acceptance greps + manual operator validation gate (Requirement 7's `synthesizer_validated_overnight` from a `cortex overnight start --dry-run`), not by Python unit tests. The boundary is named, justified, and links to the operator validation event that closes it. Appropriate.

### Out-of-scope commit observation

Commit `e1e7fff` ("Capture scheduler drift in pipeline.md") is unambiguously orthogonal to this lifecycle. It modifies `requirements/pipeline.md` (LaunchAgent scheduler CLI verbs, transient `phase: "starting"`, `scheduled-launches.json` sidecar) and appends a `requirements_updated` event to the `migrate-overnight-schedule-to-a-launchagent-based-scheduler` lifecycle's events.log — both belong to ticket #112's lifecycle, not this one. The work itself appears legitimate and well-scoped to that other ticket. Bundling it here violates "one task, one commit, one concern" and complicates future revert/cherry-pick of either lifecycle. Recommendation: either accept the bundling with a follow-up note in this lifecycle's events.log explaining the cross-lifecycle drift capture, or revert the commit from this branch and re-apply it under the LaunchAgent ticket. The work itself does not need to be reverted from the repo — it just shouldn't be in this lifecycle's commit range. Non-blocking for approval given the changes are correct in isolation.

The prereq commit `3ae1663` ("Reserve cortex-overnight-launch in parity linter") is similarly out of plan scope but is justified by the user's task description as a linter prereq blocking the synthesizer commits from landing; it is acknowledged as out-of-scope-but-justified.

## Requirements Drift
**State**: none
**Findings**:
- Spec Non-Requirements explicitly excludes `requirements/pipeline.md` §87-95 amendment because the synthesizer's deferral wraps as a worker-style exit report (existing channel). Verified: pipeline.md §87-95 lists three deferral sources (`Worker exit report declaring action: "question"`, CI gate block, repair agent) and the synthesizer routes through the first one — no fourth source needed.
- multi-agent.md:74 (orchestrator dispatches sub-agents) honored: synthesizer is dispatched by the orchestrator role (skill in interactive, orchestrator agent in overnight) per the permissive O1 reading documented in spec Technical Constraints.
- multi-agent.md:46 (3-pause batch circuit breaker) honored: synthesizer defer-count breaker reuses the same `CIRCUIT_BREAKER_THRESHOLD = 3` constant and `_transition_paused` helper.
- The unexpected pipeline.md edit in `e1e7fff` is LaunchAgent scheduler drift (ticket #112), not synthesizer drift; it does not represent a missed requirement of this lifecycle.
- `synthesizer_overnight_enabled` flag default-false posture preserved across `lifecycle.config.md` (project root), the canonical asset template, and the plugin mirror — no premature flag-flip.

**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
