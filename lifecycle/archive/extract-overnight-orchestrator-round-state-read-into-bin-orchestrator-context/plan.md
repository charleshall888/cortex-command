# Plan: extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context

## Overview

Extract the orchestrator-round prompt's four scattered file reads into a single in-process Python aggregator (`aggregate_round_context`) under a new `cortex_command/overnight/orchestrator_context.py` module, re-exported through `orchestrator_io.py` (the sanctioned import surface). Per Distribution Option 0 chosen at refine, no CLI is added — the prompt rewrite swaps file-read pseudocode for a single library call, preserving all round-filter, escalation-cap, cycle-breaker, and conflict-recovery logic. Baseline R11 measurement is captured before the prompt rewrite lands; R12 post-merge note is informational and not a close gate.

## Tasks

### Task 1: Create `orchestrator_context.py` with `aggregate_round_context`
- **Files**:
  - `cortex_command/overnight/orchestrator_context.py` (new)
- **What**: Implement the in-process aggregator that reads round-startup state (state, strategy, escalations, session plan, merge-conflict events) and returns the nested-shape dict with `schema_version`. Includes the in-process schema-drift `RuntimeError` raise.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Public API:
    ```python
    _EXPECTED_SCHEMA_VERSION = 1

    def aggregate_round_context(session_dir: Path, round_number: int) -> dict: ...
    ```
  - **Spec deviation note**: spec R3 lists `merge_conflict_events` as a sixth top-level key. The plan drops it per CLAUDE.md "don't design for hypothetical future requirements" — Task 5's prompt rewrite has no consumer for the field, and R10's strict-set fixture would pin a key no production code reads. **Spec amendment required**: R3 and R10 must be updated in lockstep before implementation begins. Revisit `merge_conflict_events` when (and only when) a prompt amendment surfaces a real consumer.
  - Returned dict shape (deviates from spec R3 — five top-level keys, see deviation note above):
    ```
    {
      "schema_version": 1,
      "state": dict,                              # asdict(load_state(session_dir / "overnight-state.json"))
      "strategy": dict,                           # asdict(load_strategy(session_dir / "overnight-strategy.json"))
      "escalations": {"unresolved": [...], "all_entries": [...]},
      "session_plan_text": str
    }
    ```
  - Inputs read (resolved relative to `session_dir`):
    - `overnight-state.json` — call `load_state(...)` from `cortex_command.overnight.state` (line 334); re-raise `FileNotFoundError` if missing, per spec R5.
    - `overnight-strategy.json` — call `load_strategy(...)` from `cortex_command.overnight.strategy` (line 36); already returns defaults on missing/invalid (line 50).
    - `escalations.jsonl` — read line-by-line; on `json.JSONDecodeError`, skip the line and emit a stderr warning matching the inline-read style at `cortex_command/overnight/prompts/orchestrator-round.md:48-50` (`print("WARNING: Skipping malformed ...", file=sys.stderr)`); compute `unresolved` as `escalation` entries whose `escalation_id` has no matching `resolution` or `promoted` entry (mirror logic at orchestrator-round.md lines 53-61); `all_entries` is the full list including `resolution` and `promoted` types (cycle-breaker at orchestrator-round.md line 87 needs these). Missing file → `{"unresolved": [], "all_entries": []}`.
    - Session plan markdown — path is `session_dir / "session-plan.md"` (verify exact filename by inspecting `runner.sh` template path; the orchestrator prompt's `{session_plan_path}` substitution resolves to the session-local plan); missing → `""`.
    - `overnight-events.log` is **NOT read** by the aggregator — the field is dropped per spec deviation above.
  - Schema-drift enforcement: define `_EXPECTED_SCHEMA_VERSION = 1` as a module-level constant. Construct the dict with literal `"schema_version": 1`. Immediately before `return`, check `if payload["schema_version"] != _EXPECTED_SCHEMA_VERSION: raise RuntimeError(f"orchestrator_context schema_version drift: returned {payload['schema_version']}, expected {_EXPECTED_SCHEMA_VERSION}")`.
  - Lock-free reads per `requirements/pipeline.md:127,134`. No writes. No in-process caching (per spec Technical Constraints — fresh orchestrator agent each round).
  - Edge case (large `overnight-events.log`): stream line-by-line; do not `read_text()` then split — keeps memory bounded for ≥10MB logs.
- **Verification**:
  - `grep -c '^def aggregate_round_context' cortex_command/overnight/orchestrator_context.py` = 1 — pass if count = 1.
  - `grep -cE '^_EXPECTED_SCHEMA_VERSION = 1$' cortex_command/overnight/orchestrator_context.py` = 1 — pass if count = 1.
  - `grep -cE 'raise RuntimeError.*schema_version drift' cortex_command/overnight/orchestrator_context.py` ≥ 1 — pass if count ≥ 1.
  - `grep -c '"schema_version": 1' cortex_command/overnight/orchestrator_context.py` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

### Task 2: Re-export `aggregate_round_context` from `orchestrator_io.py`
- **Files**:
  - `cortex_command/overnight/orchestrator_io.py` (modify lines 9-17)
- **What**: Add the aggregator to the sanctioned import surface so orchestrator-prompt pseudocode imports it from `orchestrator_io`, not directly from `orchestrator_context`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Add `from cortex_command.overnight.orchestrator_context import aggregate_round_context` to the import block (after line 10).
  - Append `"aggregate_round_context"` to the `__all__` list (currently 4 entries on lines 12-17; the new list has 5).
  - The convention is documented in `docs/overnight-operations.md:491-498` and the module's own docstring (lines 1-7) — no new pattern is being introduced.
- **Verification**:
  - `grep -c 'aggregate_round_context' cortex_command/overnight/orchestrator_io.py` ≥ 2 — pass if count ≥ 2 (one import, one `__all__`).
  - `python -c "from cortex_command.overnight.orchestrator_io import aggregate_round_context; print(aggregate_round_context.__module__)"` prints `cortex_command.overnight.orchestrator_context` — pass if exit 0 and stdout matches.
- **Status**: [x] complete

### Task 3: Add unit tests for `aggregate_round_context`
- **Files**:
  - `tests/test_orchestrator_context.py` (new)
- **What**: Cover spec acceptance criteria for R3 (dict shape), R4 (strategy passthrough — no truncation), R5 (missing-file tolerance), R6 (malformed-line tolerance + stderr warning), R8 (schema drift raise), and R10 (contract-test fixture pinning the top-level key set).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Test naming pattern (per spec R10 acceptance — at least 5 distinct functions, one per acceptance criterion):
    - `test_dict_shape_returns_six_top_level_keys` (R3)
    - `test_strategy_passthrough_no_truncation` (R4)
    - `test_missing_files_use_per_source_defaults` (R5)
    - `test_malformed_jsonl_line_skipped_with_warning` (R6)
    - `test_schema_version_drift_raises` (R8)
    - `test_dict_top_level_keys_pinned` (R10 contract fixture)
  - Existing fixture pattern reference: `cortex_command/overnight/tests/test_strategy.py:11-19` (uses `tmp_path` for session directory construction).
  - For R8: monkeypatch the dict-construction site (or directly mutate `_EXPECTED_SCHEMA_VERSION`) so `payload["schema_version"]` differs from the constant; assert `RuntimeError` raised with substring `"schema_version drift"`. Pattern reference: `pytest.raises(RuntimeError, match="schema_version drift")`.
  - For R6: use `capsys` to capture stderr; assert (a) two valid entries in `result["escalations"]["all_entries"]`, (b) malformed entry absent, (c) `"WARNING"` substring in `capsys.readouterr().err`.
  - For R10 contract fixture: `assert set(result.keys()) == {"schema_version", "state", "strategy", "escalations", "session_plan_text"}` (5 keys — `merge_conflict_events` dropped per Task 1 spec deviation note). Adding any new top-level key without bumping the test set breaks this — surfaces version-bump decision.
  - For R5: assert `aggregate_round_context` raises `FileNotFoundError` when `overnight-state.json` is missing (spec R5); other missing files use defaults.
  - Edge-case coverage (spec Edge Cases): the 10k-line `overnight-events.log` runtime assertion is dropped along with the `merge_conflict_events` field per Task 1 spec deviation. The 10MB-log edge case is no longer reachable through the aggregator.
- **Verification**:
  - `just test tests/test_orchestrator_context.py` exits 0 — pass if exit 0.
  - `grep -cE '^def test_' tests/test_orchestrator_context.py` ≥ 6 — pass if count ≥ 6 (five named tests + contract fixture).
- **Status**: [x] complete

### Task 4: Pre-merge baseline capture (R11)
- **Files**:
  - `lifecycle/archive/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md` (new)
- **What**: Run ticket 104's pipeline skill-name aggregator against a recent or freshly-run overnight session whose orchestrator-round prompt is still the *current* (inline-read) version; record one round-startup token cost as the comparison point for R12.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - **Must run before Task 5** (the prompt rewrite). Once Task 5 lands on `main`, the inline-read prompt is gone and the baseline cannot be captured retroactively except from session data already on disk.
  - Aggregator entry-point reference: ticket 104's pipeline aggregator (consult `lifecycle/{ticket-104}/spec.md` or `cortex_command/overnight/pipeline_aggregator.py` — find via `grep -rn "pipeline.*aggregator\|skill_name.*aggregat" cortex_command/`); orchestrator-round token attribution should appear under the orchestrator skill name.
  - Output format (fenced YAML block in `verification.md`):
    ```yaml
    baseline_tokens: <int>
    session_id: <str>
    captured_at: <ISO 8601 UTC>
    ```
  - This task is independent of code changes — it can run in parallel with Tasks 1–3, but must complete before Task 5.
  - **Wall-clock cost note**: "simple" complexity reflects the act of writing the YAML block once the data is in hand. If no recent overnight session ran with the inline-read prompt, a fresh overnight cycle is required first — that wall-clock cost is not budgeted in the task's own time estimate.
- **Verification**:
  - `grep -cE '^baseline_tokens:' lifecycle/archive/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md` ≥ 1 — pass if count ≥ 1.
  - Interactive/session-dependent: the *value* of `baseline_tokens` comes from running ticket 104's aggregator against a real overnight session — no synthetic command can produce it. The grep above only confirms the field is present.
- **Status**: [x] complete

### Task 5: Rewrite `orchestrator-round.md` round-startup
- **Files**:
  - `cortex_command/overnight/prompts/orchestrator-round.md` (modify lines 32-66, 181-198, 214-216, and the cycle-breaker at line 87)
- **What**: Replace the inline file-read pseudocode in Steps 0b, 1a, and 2 with a single `aggregate_round_context(session_dir, round_number)` call; retarget the cycle-breaker (line 87) and conflict-recovery awareness (Step 1b) to the new dict keys; preserve round-filter, escalation cap, dependency gate verbatim.
- **Depends on**: [2, 4]
- **Complexity**: complex
- **Context**:
  - Replace these regions (inline file-read pseudocode only — total ~56 lines today):
    - Step 0b lines 32-66 (escalations.jsonl parser block).
    - Step 1a lines 181-198 (`load_strategy` import + call block).
    - Step 2 lines 214-216 (session-plan `Read` invocation).
  - With ~5 lines:
    ```python
    from cortex_command.overnight.orchestrator_io import aggregate_round_context
    from pathlib import Path

    ctx = aggregate_round_context(Path("{session_dir}"), {round_number})
    ```
  - Retargeting required (every reference to a now-aggregated source becomes a `ctx[...]` access):
    - Step 0c lines 75-81 — `entries` → `ctx["escalations"]["all_entries"]`; `unresolved_ids`/`unresolved_entries` computed against `ctx["escalations"]["unresolved"]` (already pre-computed by the aggregator, so the comprehension can be replaced with `unresolved_entries = sorted(ctx["escalations"]["unresolved"], key=lambda e: e.get("ts", ""))[:5]`).
    - Step 0d cycle-breaker at line 87 — count must read from `ctx["escalations"]["all_entries"]` (NOT `unresolved`, which excludes resolution/promoted entries — this is the spec R7 acceptance regression check).
    - Step 1 (lines 153-175) — references to `state` are unchanged in shape; if pseudocode uses `state.features` the orchestrator now reads `ctx["state"]["features"]` (same dict shape as `asdict(OvernightState)`).
    - Step 1a — `hot_files = ctx["strategy"]["hot_files"]`, `round_history = ctx["strategy"]["round_history_notes"]`.
    - Step 1b conflict-recovery awareness (lines 200-212) — inspected during planning: lines 200-212 are prose only, no inline `overnight-events.log` read. Retargeting is a no-op for this section; the new `ctx["merge_conflict_events"]` field is available if a future amendment surfaces it.
    - Step 2 — replace the `Read` of `{session_plan_path}` with reference to `ctx["session_plan_text"]`.
  - Must preserve verbatim modulo the dict-key retargeting:
    - Step 0c escalation cap (`unresolved_entries[:5]`).
    - Step 0d cycle-breaking check semantics.
    - Step 1 round-filter logic at lines 162-175 (paused-always-included, `round_assigned <= current_round`, null-guard).
    - Step 1b conflict-recovery awareness prose.
    - Step 2a intra-session dependency gate.
  - Caller enumeration (R7 reach): the only file that renders this prompt is `cortex_command/overnight/runner.py` via `fill_prompt()` (see `tests/test_orchestrator_prompt_render.py`); the `{session_dir}` and `{round_number}` substitutions remain available, no runner changes needed. Re-run `tests/test_orchestrator_prompt_render.py` post-edit to catch render failures.
- **Verification**:
  - `grep -c 'aggregate_round_context' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 1 — pass if count ≥ 1.
  - `grep -cE '^from cortex_command\.overnight\.strategy import load_strategy|^[[:space:]]*strategy = load_strategy\(' cortex_command/overnight/prompts/orchestrator-round.md` = 0 — pass if count = 0.
  - **Cycle-breaker region scoped grep** (anchors the load-bearing semantic check at Step 0d, line 87 — file-global presence is insufficient because Step 0c also references the dict): `awk '/^\*\*Cycle-breaking check/{f=1; next} /^\*\*Resolution attempt/{f=0} f' cortex_command/overnight/prompts/orchestrator-round.md | grep -cF 'ctx["escalations"]["all_entries"]'` ≥ 1 — pass if count ≥ 1 (the cycle-breaker block reads `all_entries`, not `unresolved`).
  - `grep -cE 'paused|round_assigned' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 4 — pass if count ≥ 4.
  - **Escalation-cap rewrite shape** (matches the prescribed `sorted(...)[:5]` form, since the literal substring `unresolved_entries[:5]` does not appear in the prescribed rewrite): `grep -cE 'sorted\(ctx\["escalations"\]\["unresolved"\].*\)\[:5\]' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 1 — pass if count ≥ 1.
  - `just test tests/test_orchestrator_prompt_render.py` exits 0 — pass if exit 0 (prompt still renders with substituted variables).
- **Status**: [x] complete

### Task 6: Update `docs/overnight-operations.md` (aggregator docs + obsolete-prose amendment)
- **Files**:
  - `docs/overnight-operations.md` (modify around line 72, line 309, plus a new section)
- **What**: Add a new section documenting `aggregate_round_context`, its dict shape, and the schema-version drift mechanism; amend the existing prose at line 72 ("orchestrator reads the whole file as session context") and line 309 (tuning-surface description) to reflect aggregator-mediated reads.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Source-of-truth rule (per `CLAUDE.md` Conventions): `docs/overnight-operations.md` owns the round loop and orchestrator behavior. The new aggregator section is the canonical spot — `docs/pipeline.md` will cross-link, not duplicate.
  - Section content (prose, not code budget): describe the function signature, the dict's five top-level keys (`schema_version`, `state`, `strategy`, `escalations`, `session_plan_text`), what each key represents, the schema-version-drift `RuntimeError` mechanism, and the in-process import surface (`from cortex_command.overnight.orchestrator_io import aggregate_round_context`).
  - Line 72 amendment: the obsolete sentence "The orchestrator reads the whole file as session context — particularly recovery_log_summary and round_history_notes for continuity between rounds" must be rewritten or removed. Spec R9 acceptance requires `grep -cE 'orchestrator reads the whole file' docs/overnight-operations.md` = 0.
  - Line 309 amendment: the tuning-surface description should reference that round-startup state assembly is now mediated by `aggregate_round_context`.
  - Locate exact wording in current file; existing convention: prose paragraphs, no code blocks except for short snippets.
- **Verification**:
  - `grep -c 'aggregate_round_context' docs/overnight-operations.md` ≥ 1 — pass if count ≥ 1.
  - `grep -cE 'orchestrator reads the whole file' docs/overnight-operations.md` = 0 — pass if count = 0.
- **Status**: [x] complete

### Task 7: Cross-link from `docs/pipeline.md`
- **Files**:
  - `docs/pipeline.md` (modify — add a one-paragraph cross-reference)
- **What**: Add a short reference linking to the aggregator section in `docs/overnight-operations.md`, with no content duplication. Per CLAUDE.md, `docs/pipeline.md` owns pipeline-module internals; the aggregator is overnight-runner orchestrator behavior, so its details live in overnight-operations.md.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - One sentence, e.g.: "Round-startup state assembly is documented in `docs/overnight-operations.md` (see `aggregate_round_context`)."
  - No duplicated dict shape or signature description.
  - Insertion point: locate the existing pipeline.md section that discusses orchestrator-round inputs (likely a "Round inputs" or "Pipeline orchestrator" subsection); add the cross-link there.
- **Verification**:
  - `grep -cE 'aggregate_round_context|orchestrator-context|orchestrator_context' docs/pipeline.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [x] complete

## Verification Strategy

End-to-end verification gates after all tasks complete:

1. **Module + tests pass**: `just test tests/test_orchestrator_context.py` exits 0 and `just test tests/test_orchestrator_prompt_render.py` exits 0.
2. **Full suite green**: `just test` exits 0.
3. **Acceptance grep matrix** (one command, all R-criteria):
   ```bash
   grep -c '^def aggregate_round_context' cortex_command/overnight/orchestrator_context.py  # = 1 (R1)
   grep -c 'aggregate_round_context' cortex_command/overnight/orchestrator_io.py             # >= 2 (R2)
   grep -cE '^_EXPECTED_SCHEMA_VERSION = 1$' cortex_command/overnight/orchestrator_context.py # = 1 (R8)
   grep -c 'aggregate_round_context' cortex_command/overnight/prompts/orchestrator-round.md  # >= 1 (R7)
   awk '/^\*\*Cycle-breaking check/{f=1; next} /^\*\*Resolution attempt/{f=0} f' cortex_command/overnight/prompts/orchestrator-round.md | grep -cF 'ctx["escalations"]["all_entries"]'  # >= 1 (R7 cycle-breaker rewire — region-scoped to Step 0d)
   grep -cE 'orchestrator reads the whole file' docs/overnight-operations.md                  # = 0 (R9 prose amendment)
   grep -c 'aggregate_round_context' docs/overnight-operations.md                              # >= 1 (R9)
   grep -cE 'aggregate_round_context|orchestrator-context|orchestrator_context' docs/pipeline.md  # >= 1 (R9 cross-link)
   grep -cE '^baseline_tokens:' lifecycle/archive/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md  # >= 1 (R11)
   ```
4. **Deletion proportional check** (R7): `wc -l` on the file-read pseudocode regions before and after — Step 0b lines 32-66, Step 1a lines 181-198, Step 2 lines 214-216 (56 lines total today) → ≤6 lines after rewrite.
5. **Importability**: `python -c "from cortex_command.overnight.orchestrator_io import aggregate_round_context; print(aggregate_round_context.__module__)"` prints `cortex_command.overnight.orchestrator_context`.
6. **Post-merge note (R12)** is informational and out-of-scope for ticket close — opportunistic measurement after the first overnight session that exercises the rewritten prompt.

## Veto Surface

- **Spec R3/R10 deviation: `merge_conflict_events` dropped.** Plan critical-review surfaced this field as dead-load contract surface (Task 5 has no consumer). The plan applies the drop per CLAUDE.md "don't design for hypothetical future requirements." **Spec amendment is required before implementation begins** — R3's dict shape and R10's contract-fixture key set both need to be updated in lockstep. If you prefer to keep the field as forward-looking infrastructure, revert this deviation by re-adding the field to Task 1's dict shape, the overnight-events.log streaming code, R10's expected key set, and the docs section.
- **Session plan filename `session-plan.md`**: derived from prompt rendering convention; if the actual filename differs, Task 1 must be revised.
- **Stream-and-filter for `overnight-events.log`** (vs. eager-read-then-filter) is chosen to handle ≥10MB logs per spec Edge Cases. Eager-read is simpler but unbounded.
- **Pattern reference for stderr warnings** uses `print(..., file=sys.stderr)` to match the existing inline-read style at orchestrator-round.md:48-50. Logging-module migration is out of scope.
- **Test placement at `tests/test_orchestrator_context.py`** (project root) follows spec R10. The alternative `cortex_command/overnight/tests/test_orchestrator_context.py` (next to `test_strategy.py`, `test_map_results.py`) is closer to the module under test but contradicts the spec.

## Scope Boundaries

Per spec § Non-Requirements:

- **No CLI subcommand.** No `cortex overnight orchestrator-context`, no `bin/orchestrator-context`, no `bin/cortex-orchestrator-context`, no `cli_handler.handle_orchestrator_context`.
- **No new persistent file format.** Aggregator only reads.
- **No locking on reads.**
- **No per-feature `spec.md` / `plan.md` aggregation** — Steps 0d and 3 reads remain inline.
- **No `load_state` rehydration changes.**
- **No JSON serialization or stdout discipline tests.** Option 0 has no CLI surface.
- **No CI-level schema-drift gate** beyond the in-process `RuntimeError` and the contract-test fixture.
- **No fallback to inline reads on aggregator failure.** Exceptions propagate; orchestrator's existing error path handles them.
- **No re-targeting of plan-gen dispatch (C9)** or other orchestrator-prompt simplifications.
- **R12 post-merge note is not a close blocker** — informational only.
- **Round-filter, escalation cap, cycle-breaker, dependency-gate logic remain markdown pseudocode** — extracting these to Python helpers (which would enable fixture-driven semantic testing of round-spawn decisions) is a separate refactor, deferred to a follow-up backlog ticket. This ticket's scope is state-read extraction only. Plan critical-review flagged the gap; the right resolution is a follow-up, not bloating this ticket.
