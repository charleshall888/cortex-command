# Review: standalone-refine-seeds-lifecycle-tier-criticality

## Stage 1: Spec Compliance

### Requirement R1: Reconciliation subcommand
- **Expected**: Add `cortex-refine reconcile-clarify --lifecycle-slug <slug> [--backlog-slug <slug>] [--complexity ...] [--criticality ...]` to `cortex_command/refine.py`; resolve desired tier/criticality from explicit flags else backlog frontmatter; append override rows to bring reduced state into agreement. Acceptance: seed simple/medium, reconcile complex/high → `state_cli._reduce_events(...) == {"tier":"complex","criticality":"high"}`; `pytest tests/test_refine_module.py -q` exits 0.
- **Actual**: `_build_parser` (refine.py:362-401) adds the `reconcile-clarify` sub-parser with all four flags and wires `_cmd_reconcile_clarify` (refine.py:163-243). Desired-value resolution at refine.py:190-194 reads backlog frontmatter via the existing `_read_backlog_frontmatter`, then lets explicit flags win per-field. `test_reconcile_clarify_reduce_agreement` asserts the exact reduce dict; `test_reconcile_clarify_sources_values_from_backlog` exercises the Context-A backlog branch. All 21 tests in `tests/test_refine_module.py` pass.
- **Verdict**: PASS
- **Notes**: Live spot-check confirmed the reduce agrees after a Context-B reconcile.

### Requirement R2: `to`-keyed emission; both readers agree
- **Expected**: Each override sets `to` (and `from`); after reconcile, `common.py` readers (read `.to` only) and `state_cli._reduce_events` (read `.to or .<field>`) both return complex/high. Values lowercase.
- **Actual**: Rows emit `from`/`to` (refine.py:201-223) with lowercase values from the validated allow-sets. `test_reconcile_clarify_both_readers_agree` clears the `__wrapped__.cache_clear()` lru_caches then asserts `read_tier`/`read_criticality` equal the `_reduce_events` result, all == complex/high. Verified independently: `state_cli._reduce_events` reads `record.get("to") or record.get("tier")`/`.criticality` (state_cli.py:116,120) and `common.py:_read_tier_inner`/`_read_criticality_inner` read `.to` only (common.py:535,608) — a `to`-keyed row satisfies both.
- **Verdict**: PASS

### Requirement R3: State-based no-op-when-matches, tolerant read
- **Expected**: Append a field's override only when desired ≠ current; read current via a tolerant reduce that skips malformed lines (not caller identity). Acceptance: two identical invocations leave override count and file size unchanged.
- **Actual**: `_reduce_current_state` (refine.py:113-160) is the tolerant local reduce — skips `JSONDecodeError` and non-dict lines, replays `lifecycle_start` then override `.to`. The no-op guard is the rank comparison at refine.py:200,211 plus the empty-`rows` early return at refine.py:226-227. `test_reconcile_clarify_idempotent` asserts identical size and override counts (== 1 each) after a second run. Live spot-check confirmed 2 override rows total after a double-run.
- **Verdict**: PASS

### Requirement R4: Monotonic no-downgrade guard
- **Expected**: Never lower an already-higher reduced value (tier simple<complex; criticality low<medium<high<critical). Acceptance: pre-populate complex/high, reconcile simple/medium → state stays complex/high, no override appended.
- **Actual**: `_TIER_RANK`/`_CRITICALITY_RANK` (refine.py:30-31) drive a strict `>` comparison (refine.py:200,211): an override is appended only when desired ranks strictly above current. Unknown values rank -1 (reconcile up toward canonical, never KeyError). `test_reconcile_clarify_no_downgrade` asserts the file is byte-unchanged and reduce stays complex/high.
- **Verdict**: PASS

### Requirement R5: Graceful behavior on unreadable state; no hard-stop
- **Expected**: Do not hard-stop on a pre-existing malformed line; read tolerantly, treat absent log as seed-absent baseline, append a well-formed override, never rewrite, never repair/fail-loud on a torn log. Acceptance: malformed line + valid seed → reconcile complex/high exits 0 and appends overrides without raising.
- **Actual**: `_reduce_current_state` skips malformed lines (refine.py:138-143) and defaults to ("simple","medium") on an absent file (refine.py:132-133), distinct from a present-but-malformed log. `test_reconcile_clarify_tolerates_malformed_line` asserts exit 0 with both overrides appended. The divergence from `state_cli._reduce_events` (which nulls on any malformed line) is intentional and documented in the docstring (refine.py:121-125) — the local reduce is the R5 mechanism. This matches the project.md "keep working unless blocked" / "graceful partial failure" attributes.
- **Verdict**: PASS

### Requirement R6: Append-only; never re-seed
- **Expected**: Only append; never rewrite/remove the `lifecycle_start` seed. Acceptance: original `lifecycle_start` line byte-identical present after reconciliation.
- **Actual**: The handler only ever opens `events.log` in append mode (refine.py:230) and never touches earlier rows. `test_reconcile_clarify_append_only` asserts `lines[0] == seed_line` byte-for-byte. Live spot-check confirmed the seed row is unchanged.
- **Verdict**: PASS

### Requirement R7: Distinguishable provenance (`gate: "clarify_reconcile"`)
- **Expected**: Overrides carry `gate: "clarify_reconcile"`. Acceptance: `grep -c '"gate": "clarify_reconcile"'` equals the number of fields reconciled.
- **Actual**: Both row dicts set `"gate": "clarify_reconcile"` (refine.py:208,221). `test_reconcile_clarify_provenance_marker` asserts gate_count == 2 (both fields reconciled). Verified the escalator's `read_effective_tier` and the dashboard parser never inspect `gate`, so the marker breaks no consumer.
- **Verdict**: PASS

### Requirement R8: Skill wiring before the FIRST spec-phase tier/criticality read
- **Expected**: `skills/refine/SKILL.md` invokes `reconcile-clarify` at Spec-phase entry, before both §3a and §3b reads (i.e., before the §5 `specify.md` delegation). Covers fresh-Clarify and `resume=spec` paths; Context A from backlog, Context B explicit. Acceptance: literal present (`grep -c >= 1`); precedes the §3a/§3b reads.
- **Actual**: SKILL.md:161-166 (under the `## Step 5: Spec Phase` heading at line 159) describes the reconcile step with both Context A (line 163) and Context B (line 164) invocation forms, the idempotent/monotonic/no-op note (line 166), positioned before the `Read … specify.md and follow it` delegation at line 168. The literal `cortex-refine reconcile-clarify` appears at lines 163-164.
- **Verdict**: PASS

### Requirement R9: Events-registry producers updated (documentation)
- **Expected**: No new registry rows; add `cortex_command/refine.py` to the producer columns of `complexity_override` and `criticality_override`. Acceptance: `pytest tests/test_check_events_registry.py -q` exits 0; both rows name refine.py.
- **Actual**: `bin/.events-registry.md:17` (`criticality_override`) and `:101` (`complexity_override`) both list `cortex_command/refine.py` as a producer; the `lifecycle_start` row (:13) already lists it. `grep -c 'cortex_command/refine.py' bin/.events-registry.md` == 3. `tests/test_check_events_registry.py` passes (no new scanned literal introduced).
- **Verdict**: PASS

### Requirement R10: Kept-pauses parity preserved
- **Expected**: Re-verify the refine §4 pick-menu anchor in `skills/lifecycle/SKILL.md`; update inventory + parity test only if drift exceeds ±35-line tolerance. Acceptance: `pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0.
- **Actual**: Inventory anchor records `skills/refine/SKILL.md:166`; the actual §4 complexity-value gate pick-menu is now at line 173 (7-line drift), comfortably inside the ±35-line tolerance, so no inventory/test edit was needed (correctly left untouched per the plan's conditional clause). `tests/test_lifecycle_kept_pauses_parity.py` passes (11 tests).
- **Verdict**: PASS

### Requirement R11: Dual-source mirror regenerated
- **Expected**: `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` is empty; `cortex_command/` is not mirrored. Drift hook passes.
- **Actual**: Both mirrors are byte-identical: `diff skills/refine/SKILL.md plugins/cortex-core/skills/refine/SKILL.md` empty, and `diff skills/lifecycle/references/criticality-matrix.md plugins/cortex-core/skills/lifecycle/references/criticality-matrix.md` empty (the criticality-matrix doc touched in Task 5 is also mirrored). `cortex_command/refine.py` is not mirrored, as specified.
- **Verdict**: PASS

### Requirement R12: End-to-end regression + delegated-path no-op test
- **Expected**: (a) Standalone headline scenario: fresh ticket → seed simple/medium → reconcile to complex/high (Context A, no flags) → `cortex-lifecycle-state --field tier` → `{"tier":"complex"}`. (b) Delegated path: `[seed(simple/medium), lifecycle_start(complex/high)]` → reconcile no-ops (no new override row) and final reduce is complex/high. Acceptance: new test file exits 0.
- **Actual**: `tests/test_refine_reconcile_clarify.py` has both. `test_reconcile_clarify_standalone_headline_scenario` writes a backlog with complex/high, seeds simple/medium, reconciles via Context A (no flags), and reads through the real `state_cli.main` CLI surface asserting `{"tier":"complex"}`/`{"criticality":"high"}`. `test_reconcile_clarify_delegated_path_noops` pre-populates the two `lifecycle_start` rows, asserts the override count stays 0 after reconcile, and final reduce is complex/high — correctly framing reconcile as the would-be most-recent write the no-op guard suppresses (not supersession). Both pass.
- **Verdict**: PASS

### Requirement R13: Criticality-matrix doc updated
- **Expected**: Document the optional `gate` field the fix emits; reconcile the "user's criticality is always final" invariant with the new automated emitter. Acceptance: `grep -c 'gate' criticality-matrix.md >= 1` in the override-shape context.
- **Actual**: `skills/lifecycle/references/criticality-matrix.md:11` documents the optional `gate: "clarify_reconcile"` field and notes `from`/`to`-only consumers are unaffected. Line 13 adds the user-final carve-out: the Clarify reconciliation is not a user-override (it transcribes the Clarify-determined criticality, is monotonic-up-only, gate-marked), and an explicit user request still wins via a later ungated `criticality_override`. `grep -c 'clarify_reconcile'` == 2; `grep -c 'gate'` == 2.
- **Verdict**: PASS

### Acceptance criterion (well-formed events.log)
- **Expected**: On a well-formed `events.log`, standalone `/refine` Clarify-assessed complex/high ends Spec entry with `cortex-lifecycle-state --field tier` → complex and `--field criticality` → high (so §3b fires), while a `/lifecycle`-delegated run no-ops (no duplicate override). All touched pytest files, events-registry gate, kept-pauses parity, and mirror diff green. Torn-log case explicitly out of scope (#287).
- **Actual**: The R12 standalone test verifies the headline through the actual `state_cli` CLI surface; the R12 delegated test verifies the no-op. `pytest tests/test_refine_module.py tests/test_refine_reconcile_wiring.py tests/test_refine_reconcile_clarify.py -q` → 21 passed; `tests/test_check_events_registry.py tests/test_lifecycle_kept_pauses_parity.py` → 11 passed; both mirror diffs empty. The torn-log read-path divergence is correctly scoped out (tracked as #287) and the tolerant local reduce avoids regressing it — not marked a FAIL.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the module's existing patterns. `_cmd_reconcile_clarify` mirrors `_cmd_emit_lifecycle_start`; `_reduce_current_state` parallels `_lifecycle_start_present`; `_TIER_RANK`/`_CRITICALITY_RANK` reuse the established `_ALLOWED_*` private-constant style. Test helpers (`_seed_events`, `_count_event`, `_state_field`) follow the file's existing in-process `main([...])` + `monkeypatch.chdir` convention.
- **Error handling**: Appropriate. The append uses the same `PermissionError/OSError → exit 70` idiom (with the cortex-init sandbox hint) as `_cmd_emit_lifecycle_start` (refine.py:233-241). The tolerant reduce never raises on a torn log (R5). Invalid frontmatter values still route through `_read_backlog_frontmatter`'s exit-64 path. The row shape correctly omits `schema_version` to match the canonical escalator producer `complexity_escalator._emit_event` (verified keys: `ts, event, feature, from, to, gate`) rather than inventing a third convention.
- **Test coverage**: Each plan per-task Verification step was executed and passes. `pytest tests/test_refine_module.py tests/test_refine_reconcile_wiring.py tests/test_refine_reconcile_clarify.py -q` → 21 passed; gate + parity tests → 11 passed. The Context-A backlog-sourcing branch (the real production trigger) and the explicit-flag precedence case are both covered, closing the gap a pure explicit-flag suite would miss. The wiring test correctly anchors on the unique §5 delegation phrase `specify.md\` and follow it` rather than the bare first `specify.md` occurrence (which appears earlier in the §2a Research-bypass note at line 104), satisfying the position assertion against the correct §3a/§3b-triggering delegation.
- **Pattern consistency**: Follows project conventions — mirrors `_cmd_emit_lifecycle_start` for the append idiom, the required-flag argparse convention, the dual-source mirror parity (both touched canonical docs regenerated byte-identical), and the events-registry producer-documentation precedent set by the `lifecycle_start` row. The structural CLI subcommand (no bare-Python import in SKILL.md, no new MUST escalation) honors the prefer-structural-over-prose-enforcement and MUST-escalation policies.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
