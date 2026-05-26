# Review: offer-consolidation-clusters-before-r15-gate (cycle 1)

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```

## Stage 1: Spec Compliance

| # | Requirement | Rating | Evidence |
|---|---|---|---|
| 1 | `_RESPONSE_VALUES` gains `consolidate-pieces` | PASS | `cortex_command/discovery.py:411`; `python3 -c "from cortex_command.discovery import _RESPONSE_VALUES; assert 'consolidate-pieces' in _RESPONSE_VALUES"` exits 0 |
| 2 | `_validate_checkpoint_payload` accepts the new response | PASS | `cortex_command/discovery.py:458–462` (set-membership check unchanged); standalone validation call exits 0 |
| 3 | CLI argparse `--response` exposes new value | PASS | `cortex_command/discovery.py:1322–1325` derives choices from `sorted(_RESPONSE_VALUES)`; `python -m cortex_command.discovery emit-checkpoint-response --help` shows `consolidate-pieces` in choices (the installed `cortex-discovery` binary is a stale uv-tool install, not a source defect) |
| 4 | Positive-path test exists | PASS | `tests/test_discovery_module.py:216–256` (`test_emit_checkpoint_response_accepts_consolidate_pieces_at_decompose_commit`) asserts both `_validate_checkpoint_payload` and the JSONL emission; `pytest tests/test_discovery_module.py -k consolidate -q` → 1 passed |
| 5 | R15 bullet documents `consolidate-pieces <N,M,...>` with full loop semantics | PASS | `skills/discovery/references/decompose.md:109` covers all six sub-clauses (a)–(f); `grep -c "consolidate-pieces <N,M,...>" decompose.md` = 1; `grep -E "lowest-index\|renumber\|re-presents" decompose.md \| wc -l` = 3 |
| 6 | Argument format documented; no helper enforcement | PASS | Canonical form documented at decompose.md:109; single-index re-prompt behavior named explicitly; helper layer unchanged beyond bare-value acceptance |
| 7 | `## Consolidation Notes` recording shape documented and distinguished from `## Dropped Items` | PASS | `decompose.md:113` introduces the heading and states "This heading is distinct from `## Dropped Items` (the Title-keyed Markdown table for fully-rejected tickets used by `drop-piece`)"; corpus precedents named |
| 8 | No new event row in `bin/.events-registry.md` | PASS | `git diff --stat bin/.events-registry.md` empty |
| 9 | `skills/discovery/SKILL.md:102` enumeration updated | PASS | Line 102 enumerates all four options including `consolidate-pieces <N,M,...>` and points to decompose.md §5 for semantics; mirror regenerated at `plugins/cortex-core/skills/discovery/SKILL.md` |
| 10 | Parity test renamed and assertion added | PASS | `tests/test_decompose_rules.py:254–269` renamed to `test_r15_batch_review_gate_options_documented`, docstring updated, `"consolidate-pieces" in body` assertion added at line 261; test passes |

All 10 requirements PASS. No FAIL or PARTIAL ratings.

## Stage 2: Code Quality

- **Naming conventions**: `consolidate-pieces` follows the same hyphenated-lowercase verb-noun pattern as the sibling R15 responses (`revise-piece`, `drop-piece`, `approve-all`). The frozenset entry slots in cleanly; argparse sorts alphabetically so help-output ordering remains predictable. The new test name `test_emit_checkpoint_response_accepts_consolidate_pieces_at_decompose_commit` mirrors the structural template named in its docstring (the R4-path counterpart `test_emit_checkpoint_response_writes_jsonl_and_validates_response`). The parity test rename drops "three" verbatim per Req 10.
- **Error handling**: Helper layer correctly does not validate the index-list shape — index handling is documented as agent-context bookkeeping (per Non-Requirements and Req 6). The bare value `consolidate-pieces` is the only thing the helper sees, and validation reuses the existing `_RESPONSE_VALUES` membership check without bespoke branching. No new error paths introduced.
- **Test coverage**: The new positive-path test exercises both validation (clause a) and JSONL emission (clause b) with assertions on `event`, `response`, `checkpoint`, and `revision_round` fields. Full `tests/test_discovery_module.py` + `tests/test_decompose_rules.py` runs green (29 passed). The parity test's new assertion at line 261 fails closed if the bullet is removed from decompose.md.
- **Pattern consistency**: The new R15 bullet at `decompose.md:109` follows the existing bullet shape (boldface literal token + em-dash + prose paragraph). The Consolidation Notes paragraph is placed after the bullet list and before the event-emission paragraph, mirroring how `## Dropped Items` recording is described for `drop-piece`. The auto-regenerated mirrors in `plugins/cortex-core/skills/discovery/` are byte-identical to the canonical sources (verified via `diff`). The dual-source pre-commit hook will keep them in sync going forward. The 500-line SKILL.md cap is well under (SKILL.md grew by ~0 lines structural; only the single line 102 changed).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None
