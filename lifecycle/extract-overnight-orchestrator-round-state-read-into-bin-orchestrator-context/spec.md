# Specification: Extract overnight orchestrator-round state read into an in-process aggregator (ticket 111)

## Problem Statement

The overnight orchestrator-round prompt (`cortex_command/overnight/prompts/orchestrator-round.md`) currently contains scattered state reads spread across Steps 0b, 1, 1a, and 2: a raw `Path.read_text` of `escalations.jsonl`, a raw load of `overnight-state.json`, a `load_strategy` call, and a `Read`-tool invocation on the session-plan markdown. This means the orchestrator agent re-implements the read-and-rehydrate ceremony every round, with the per-round procedure documented inline as Python pseudocode the agent must reproduce. The aim is to consolidate these reads into one in-process Python function (`aggregate_round_context`) re-exported through `cortex_command/overnight/orchestrator_io.py`, so the orchestrator prompt's round-startup section becomes a single import + call. The expected wins are (a) reduced inline Python pseudocode in the prompt, (b) a single audit-point for round-startup state assembly, and (c) a single failure surface to test against.

> **Value-case caveat (load-bearing for §4 approval surface).** Direct API-cost savings are negligible (~$0.05–$4/year per the Adversarial review in `lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/research.md`). The bet is on agent-attention quality (one library call rather than four scattered reads), which is not directly measurable by ticket 104's instrumentation. Ticket 111's original ROI quantification (300–500 tokens × 50–100 rounds/year) overstates the savings because most "inline reads" are already structured Python calls, not raw `Read`-tool invocations.

## Requirements

**MoSCoW classification**: All 12 requirements below are **must-have** for shipping the feature as specified. R1–R7 are the implementation surface (function, re-export, dict shape, file tolerance, malformed-line tolerance, prompt rewrite). R8 is the schema-version contract enforced as in-process Python raise. R9 is the docs convention (CLAUDE.md mandates the source-of-truth split) plus amendment of the existing `docs/overnight-operations.md:72,309` "whole file" wording that the new aggregator-mediated read pattern invalidates. R10 is test coverage including a contract-test fixture pinning the dict's top-level key set. R11 is the pre-merge baseline-capture step. R12 is a post-merge observability note (informational; not a close gate). There are no should-haves; won't-do items are in `## Non-Requirements`.

1. **New module `cortex_command/overnight/orchestrator_context.py`** exporting `aggregate_round_context(session_dir: Path, round_number: int) -> dict`. The function reads the round-startup snapshot (state + strategy + unresolved escalations + session plan markdown) and returns a single dict with a `schema_version` key.
   - **Acceptance**: `python -c "from cortex_command.overnight.orchestrator_context import aggregate_round_context; help(aggregate_round_context)"` exits 0 and prints a help string referencing `session_dir`, `round_number`, and `dict`.
   - **Acceptance**: `grep -c '^def aggregate_round_context' cortex_command/overnight/orchestrator_context.py` = 1.

2. **Re-export through `orchestrator_io.py`**. Add `from cortex_command.overnight.orchestrator_context import aggregate_round_context` to `cortex_command/overnight/orchestrator_io.py` and append `"aggregate_round_context"` to `__all__`.
   - **Acceptance**: `grep -c 'aggregate_round_context' cortex_command/overnight/orchestrator_io.py` ≥ 2 (one import, one `__all__` entry).
   - **Acceptance**: `python -c "from cortex_command.overnight.orchestrator_io import aggregate_round_context; print(aggregate_round_context.__module__)"` prints `cortex_command.overnight.orchestrator_context`.

3. **Returned dict shape — nested per-source sub-objects with `schema_version`**:
   ```python
   {
       "schema_version": 1,
       "state": <dict — asdict(OvernightState)>,
       "strategy": <dict — asdict(OvernightStrategy)>,
       "escalations": {
           "unresolved": [<list of unresolved escalation entry dicts>],
           "all_entries": [<list of all entries from escalations.jsonl, including resolution and promoted entries needed for cycle-breaking>]
       },
       "session_plan_text": <str — raw markdown text of the session plan, or "" if missing>,
       "merge_conflict_events": [<list of merge_conflict_classified event dicts from overnight-events.log>]
   }
   ```
   - **Acceptance**: A pytest in `tests/test_orchestrator_context.py` constructs a fixture session directory with all four input files, calls `aggregate_round_context`, and asserts each top-level key exists with the expected type. `just test` exits 0.
   - **Acceptance**: `grep -c '"schema_version": 1' cortex_command/overnight/orchestrator_context.py` ≥ 1.

4. **Strategy passes through unchanged**: the aggregator returns `asdict(load_strategy(strategy_path))` as the `strategy` sub-object. No truncation, no field filtering. Preserves the existing documented contract (`docs/overnight-operations.md:72,309` — "the orchestrator reads the whole file as session context"). Rationale: per the spec's value-case caveat, direct token savings from truncation are negligible (~$0.05/year for ~400 bytes/round); silent truncation creates a hidden invariant at the call site and assumes a writer contract (one-entry-per-round) that the `list[str]` schema does not enforce.
   - **Acceptance**: A pytest seeds `overnight-strategy.json` with 10 `round_history_notes` entries, calls the aggregator, and asserts `len(result["strategy"]["round_history_notes"]) == 10` (no truncation).

5. **Tolerate missing input files using existing per-source defaults** (no new error-handling layers):
   - Missing `overnight-state.json`: re-raise `FileNotFoundError` (matches `load_state`'s current contract at `cortex_command/overnight/state.py:343-345`).
   - Missing `overnight-strategy.json`: include the default `OvernightStrategy()` payload (matches `load_strategy`'s current behavior at `cortex_command/overnight/strategy.py:36-50`).
   - Missing `escalations.jsonl`: return `{"unresolved": [], "all_entries": []}` for the `escalations` sub-object.
   - Missing session plan markdown: `session_plan_text` is `""`.
   - Missing or unreadable `overnight-events.log`: `merge_conflict_events` is `[]`.
   - **Acceptance**: A pytest with only `overnight-state.json` present (other files absent) calls the aggregator and asserts no exception, default values for absent sources, and rehydrated state for the present source.

6. **Malformed `escalations.jsonl` line tolerance**: skip the malformed line and log a warning to stderr. Match the existing inline-read behavior at `cortex_command/overnight/prompts/orchestrator-round.md:48-50`.
   - **Acceptance**: A pytest seeds `escalations.jsonl` with two valid lines and one malformed line, captures stderr via `capsys`, and asserts (a) the two valid entries appear in `escalations.all_entries`, (b) the malformed line is absent, (c) stderr contains a warning string.

7. **Rewrite `cortex_command/overnight/prompts/orchestrator-round.md` round-startup**. Replace the *file-read pseudocode only* — Step 0b's inline `escalations.jsonl` parser (lines 32–66), Step 1a's `load_strategy` import + call block (lines 181–198), and Step 2's session-plan `Read` (lines 214–216) — with a single in-process call: `ctx = aggregate_round_context(session_dir, round_number)`. Step 1's *round-filter logic* (lines 162–175, including `paused` always included and the `(f.get('round_assigned') or 0)` null-guard), Step 0c's *escalation cap* (`unresolved_entries[:5]`), Step 0d's *cycle-breaking check* (counting `resolution`-typed entries with matching `feature`), Step 1b's *conflict-recovery awareness*, and Step 2a's *intra-session dependency gate* are NOT in scope for replacement and must be preserved verbatim modulo retargeting onto the new dict keys.
   - **Acceptance**: `grep -c 'aggregate_round_context' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 1.
   - **Acceptance (load_strategy code removed)**: `grep -cE '^from cortex_command\.overnight\.strategy import load_strategy|^[[:space:]]*strategy = load_strategy\(' cortex_command/overnight/prompts/orchestrator-round.md` = 0 (the import line and call line in the fenced code block are removed; prose mentions of `load_strategy` outside fenced code may remain).
   - **Acceptance (cycle-breaker rewired)**: `grep -cF 'ctx["escalations"]["all_entries"]' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 1 — the cycle-breaking check at the current line 87 now reads from the aggregated dict's `all_entries` (NOT `unresolved`, which excludes resolution/promoted entries and would silently break the check).
   - **Acceptance (round-filter survives)**: `grep -cE 'paused|round_assigned' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 4 — `paused` and `round_assigned` keywords appear at least twice each, confirming the round-filter logic at the current lines 162–175 was preserved (not deleted).
   - **Acceptance (escalation cap survives)**: `grep -cF 'unresolved_entries[:5]' cortex_command/overnight/prompts/orchestrator-round.md` ≥ 1 OR an equivalent slice expression — the "process only the oldest 5 by ts" cap from current Step 0c is preserved.
   - **Acceptance (deletion proportional)**: The rewritten prompt deletes ≥ 50 lines from the file-read pseudocode regions (Step 0b lines 32–66, Step 1a lines 181–198, Step 2 lines 214–216 — total 56 lines today, replaced by ~5 lines). Measured via `wc -l` before/after on the affected step blocks. Lines outside those file-read regions (Step 1's round-filter, Step 1b's conflict-recovery awareness, Step 2a's dependency gate) are NOT counted toward the deletion budget — a deletion that hits ≥50 by trimming non-file-read pseudocode is a regression, not a pass.

8. **Schema-version check enforced in-process**: `aggregate_round_context` defines a module-level `_EXPECTED_SCHEMA_VERSION = 1` constant and, immediately before returning, raises `RuntimeError(f"orchestrator_context schema_version drift: returned {payload['schema_version']}, expected {_EXPECTED_SCHEMA_VERSION}")` if the assembled dict's `schema_version` does not match the constant. The check is in-process Python — the interpreter enforces it; it does not depend on the orchestrator agent reading and executing a markdown assert. Bumping the literal `"schema_version": 1` in the dict-construction code without bumping `_EXPECTED_SCHEMA_VERSION` raises immediately, surfacing the missed update at first call. The orchestrator-round.md prompt does NOT need to assert version; the function refuses to return on mismatch.
   - **Acceptance (constant exists)**: `grep -cE '^_EXPECTED_SCHEMA_VERSION = 1$' cortex_command/overnight/orchestrator_context.py` = 1.
   - **Acceptance (raise exists)**: `grep -cE 'raise RuntimeError.*schema_version drift' cortex_command/overnight/orchestrator_context.py` ≥ 1.
   - **Acceptance (test fires)**: A pytest in `tests/test_orchestrator_context.py` monkeypatches the dict-construction site to emit `"schema_version": 99`, calls `aggregate_round_context`, and asserts `RuntimeError` is raised with substring `"schema_version drift"`. `just test tests/test_orchestrator_context.py::test_schema_version_drift_raises` exits 0.

9. **Documentation**: update `docs/overnight-operations.md` to (a) document `aggregate_round_context`, its returned dict shape, and the schema-version drift mechanism; AND (b) amend the existing prose at `docs/overnight-operations.md:72` ("The orchestrator reads the whole file as session context — particularly recovery_log_summary and round_history_notes for continuity between rounds") and the tuning-surface description at line 309 to reflect that round-startup state is now assembled by `aggregate_round_context` rather than by inline reads. Cross-link from `docs/pipeline.md` (do not duplicate content; CLAUDE.md owns the source-of-truth rule).
   - **Acceptance**: `grep -c 'aggregate_round_context' docs/overnight-operations.md` ≥ 1.
   - **Acceptance (existing prose amended)**: `grep -cE 'orchestrator reads the whole file' docs/overnight-operations.md` = 0 — the obsolete wording is removed or rewritten to reflect the aggregator-mediated read.
   - **Acceptance**: `grep -c 'aggregate_round_context\|orchestrator-context\|orchestrator_context' docs/pipeline.md` ≥ 1.

10. **Tests**: `tests/test_orchestrator_context.py` covers the aggregator function against the acceptance criteria in Requirements 3, 4, 5, 6, and 8. Includes a *contract-test fixture* that pins the dict's top-level key set so additive changes (a new top-level key added to the returned dict) break the test until intentionally bumped. No subprocess testing is required (Option 0 means no CLI surface).
    - **Acceptance**: `just test tests/test_orchestrator_context.py` exits 0 with at least 5 distinct test functions named to reflect each acceptance criterion (R3 dict shape, R4 strategy passthrough, R5 missing-file tolerance, R6 malformed-line tolerance, R8 schema-version drift raise).
    - **Acceptance (contract fixture)**: A test `test_dict_top_level_keys_pinned` asserts that `set(result.keys()) == {"schema_version", "state", "strategy", "escalations", "session_plan_text", "merge_conflict_events"}`. Adding a new top-level key (additive drift) without updating the test set breaks the test, signaling the version-bump decision needs to be made.

11. **Pre-merge baseline capture**: before R7's prompt rewrite lands on `main`, the implementer captures one round-startup token-cost measurement against the *current* (inline-read) `orchestrator-round.md` using ticket 104's pipeline skill-name aggregator on a recent or freshly-run overnight session. The number is written to `lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md` as a fenced YAML block with fields `baseline_tokens: <int>`, `session_id: <str>`, `captured_at: <ISO8601>`. This is the comparison point for R12 below.
    - **Acceptance**: `grep -cE '^baseline_tokens:' lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md` ≥ 1 in the PR diff before merge.

12. **Post-merge observability note** (informational, NOT a close gate): after the first overnight session that exercises the rewritten orchestrator-round prompt, the implementer documents the round-startup token cost in the existing `lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md` file as a fenced YAML block with fields `post_merge_tokens: <int>`, `session_id: <str>`, `captured_at: <ISO8601>`, `ratio: <float — post_merge_tokens / baseline_tokens>`, `notes: <str — qualitative observations, including any agent-attention-quality observations>`. There is no threshold, no pass/fail, and no close blocker. The note is informational so a future regression investigation has a comparison point. Per the spec's value-case caveat, the actual bet (agent-attention quality) is not directly measurable by 104's instrumentation; the token-cost number is opportunistic data, not a verdict.
    - **Acceptance criterion (interactive/session-dependent)**: After at least one overnight session post-merge, `verification.md` is appended with `post_merge_tokens`, `ratio`, and `notes` fields. Ticket close does not depend on the ratio's value or on the existence of the post-merge entry — only on R1–R11 acceptance. Rationale for interactive: post-merge measurement requires a real overnight session and is opportunistic by design.

## Non-Requirements

- **No CLI subcommand.** Distribution Option 0 was selected during research (see `lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/research.md`'s Open Questions Q1). The aggregator is in-process Python only. `cortex overnight orchestrator-context`, `bin/orchestrator-context`, `bin/cortex-orchestrator-context`, and any `cli_handler.handle_orchestrator_context` are explicitly out of scope.
- **No new persistent file format.** The aggregator only reads existing files; it writes nothing.
- **No locking on reads.** Per `requirements/pipeline.md:127,134`, state reads are not lock-protected; this aggregator follows that constraint.
- **No per-feature spec.md / plan.md aggregation.** Those reads in Steps 0d and 3 remain inline because they are conditional and per-feature; folding them in would require either eager-read-all or per-call filters and is rejected per the research Tradeoffs section.
- **No `load_state` rehydration changes.** The aggregator returns `asdict(load_state(...))` as the `state` sub-object — it does not introduce a new state schema. Any orchestrator pseudocode that today operates on raw-JSON state dicts is migrated to operate on `ctx["state"]` (which is the same shape as `asdict(OvernightState)`).
- **No JSON serialization or stdout discipline tests.** Option 0 has no CLI surface. The aggregator returns a Python `dict`; testing is in-process import + assertion.
- **No CI-level schema-drift gate across releases.** Per R8, the in-process `RuntimeError` raise inside `aggregate_round_context` enforces version match at every call. The contract-test fixture in R10 catches additive drift at test time (new top-level key requires updating the fixture, which forces the version-bump conversation). No additional CI tooling beyond `just test`.
- **No fallback to inline reads on aggregator failure.** Exceptions propagate; the orchestrator's existing in-process error-handling pattern (`orchestrator-round.md:48-50` for parse errors and the per-step try/except discipline) handles them. Centralizing the failure surface is an explicit accepted risk — see Edge Cases.
- **No re-targeting of plan-gen dispatch (C9)** or other orchestrator-prompt simplifications beyond the round-startup state-read extraction. Per `backlog/111-...md:42-43`.

## Edge Cases

- **Aggregator raises in the middle of a round-spawn**: the orchestrator agent's containing process exits non-zero, the runner observes the failure, and the round is paused via the existing pipeline failure-handling path (`requirements/pipeline.md:32-42`). No new failure mode beyond what already exists for any orchestrator pseudocode crash. **Accepted risk per research Adversarial Review**: this is a centralized chokepoint — a bug in the aggregator can fail every round until fixed.
- **`escalations.jsonl` mutated between read and use within a round**: The aggregator captures a snapshot at call time. New escalation entries written by workers later in the round are not visible to the orchestrator until the next round's aggregator call. This matches the inline-read behavior today (the inline read also runs once at Step 0).
- **`overnight-events.log` is large**: filter to `merge_conflict_classified` events at read time, not after; do not load the full log into memory if it's > 10MB. Streaming line-by-line and yielding only matching events keeps the memory footprint bounded. **Acceptance**: A pytest with a 10k-entry events log measures aggregator runtime under 200ms.
- **`round_history_notes` arbitrarily long**: passed through unchanged (no truncation). Per R4 rationale, the savings do not justify the silent-regression risk; existing docs (`docs/overnight-operations.md:72,309`) already document the "whole file" contract, which the aggregator preserves.
- **Missing `escalations.jsonl` AND missing `overnight-strategy.json` AND missing session plan markdown** (first round, fresh session): aggregator returns the dict with empty escalations, default strategy, and `session_plan_text == ""`. `state` is the only required input; if `overnight-state.json` is missing the aggregator raises `FileNotFoundError`.
- **Schema drift between the aggregator's returned dict and what the orchestrator prompt expects**: R8's in-process `RuntimeError` raise fires at every call, catching coordinated bumps that omit one side. R10's contract-test fixture pins the top-level key set; an additive change (new top-level key) breaks the test until the fixture is updated, surfacing the version-bump decision. Field-level drift inside `state` or `strategy` (e.g., a new `OvernightFeatureStatus` field that the prompt now reads) is still caught at prompt runtime via missing-key access — the spec accepts that internal-field additive drift is not version-gated.

## Changes to Existing Behavior

- **MODIFIED**: `cortex_command/overnight/prompts/orchestrator-round.md` *file-read pseudocode only* is replaced by a single `aggregate_round_context(session_dir, round_number)` call. Specifically: Step 0b's JSONL parser block (current lines 32–66), Step 1a's `load_strategy` import + call block (current lines 181–198), and Step 2's session-plan `Read` (current lines 214–216) — total ~56 lines today, replaced by ~5 lines. Step 1's round-filter logic (current lines 162–175), Step 0c's escalation cap, Step 0d's cycle-breaking check, Step 1b's conflict-recovery awareness, and Step 2a's intra-session dependency gate are NOT modified except to retarget their dict access onto the new `ctx[...]` keys.
- **MODIFIED**: `docs/overnight-operations.md:72` and `docs/overnight-operations.md:309` are amended to reflect the aggregator-mediated read pattern (the obsolete "the orchestrator reads the whole file" wording is removed or rewritten — see R9 acceptance).
- **MODIFIED**: `cortex_command/overnight/orchestrator_io.py` (lines 9–17) gains one new import and one `__all__` entry, raising the audit-point surface from 4 functions to 5.
- **ADDED**: `cortex_command/overnight/orchestrator_context.py` is a new module exporting `aggregate_round_context`.
- **ADDED**: `tests/test_orchestrator_context.py` is a new test file covering the aggregator's contract.
- **ADDED**: a new section in `docs/overnight-operations.md` documenting `aggregate_round_context` and its returned dict shape.
- **NO CHANGE**: `cortex_command/overnight/map_results.py` (the ticket's original suggestion to extend it is rejected per research's Module-organization recommendation B).
- **NO CHANGE**: `cortex_command/cli.py`, `cortex_command/overnight/cli_handler.py`, `cortex_command/overnight/cli_handler.py:_emit_json` (no CLI shape under Option 0).
- **NO CHANGE**: state-write paths, atomic-write helpers, or the lock-free-read architectural constraint.

## Technical Constraints

- **Sanctioned import surface**: per `docs/overnight-operations.md:491-498`, "any new orchestrator-callable I/O primitive is added [to `orchestrator_io.py`] rather than imported directly." Requirement 2 enforces this.
- **Lock-free reads**: per `requirements/pipeline.md:127,134`, state reads are unprotected by design; the aggregator follows the same convention.
- **Stdout cleanliness**: not directly applicable under Option 0 (no CLI). The aggregator runs in-process; stderr is the standard channel for warnings (Requirement 6).
- **Atomic-write convention** (`requirements/pipeline.md:126`): the aggregator does not write any files. If a future requirement adds writes, they must use `cortex_command.common.atomic_write`.
- **Read-only with respect to state files** (`requirements/observability.md:93`): the aggregator does not mutate any input file.
- **Each round spawns a fresh orchestrator agent** (`docs/overnight-operations.md:32-33`): no in-process caching is required and none should be introduced. The aggregator is called once per round-spawn; rejected research Alternative D (lazy-eval/memoization) stays rejected.

## Open Decisions

- **None.** R11's "blocking for ticket close" framing was reframed to an observability-note pair (R11 pre-merge baseline + R12 post-merge note, neither blocking close) per user decision during critical-review §4. All other research-deferred questions resolved: module name → `orchestrator_context.py`; dict shape → nested with `schema_version` key; truncation policy → no truncation (R4 dropped per critical-review); schema-version enforcement → in-process `RuntimeError` raise (R8 inverted from prompt-side assert); fallback path → exceptions propagate; the `--help` visibility question (research Q7) is moot under Option 0; the aggregated-dict size budget (research Q3) is replaced by R11/R12's opportunistic measurement (no enforced threshold).
