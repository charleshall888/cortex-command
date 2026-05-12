# Review: tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction

## Stage 1: Spec Compliance

### Requirement 1: §1b prompt template tightened — closed-taxonomy category, no ordering-only differentiation, lowercase "must" only
- **Expected**: `grep -c 'or ordering than the obvious default' skills/lifecycle/references/plan.md` returns 0; `grep -c 'event-driven, pipeline, layered, shared-state, plug-in' skills/lifecycle/references/plan.md` returns 1; uppercase MUST/CRITICAL/REQUIRED count does not exceed pre-edit baseline (0).
- **Actual**: Old substring count = 0, closed-taxonomy occurrences = 1, uppercase marker count = 0. The replacement at `skills/lifecycle/references/plan.md:47` reads "Your approach must be architecturally distinct, not merely a different ordering or decomposition of the same strategy. Name your architectural category from this closed list — exactly one: event-driven, pipeline, layered, shared-state, plug-in." (lowercase "must" only, no escape clause).
- **Verdict**: PASS
- **Notes**: All three sub-checks satisfied.

### Requirement 2: Self-check field — "how this variant differs from the others"
- **Expected**: `grep -cE 'how this (approach|variant|plan) differs from (the )?other' skills/lifecycle/references/plan.md` returns ≥ 1.
- **Actual**: Count = 1. Line 48 reads "Populate the Plan Format's `**Architectural Pattern**` field with the named category and a one-sentence statement of how this variant differs from the other variants in this `plan_comparison`."
- **Verdict**: PASS

### Requirement 3: §1b template's Plan Format gains an `**Architectural Pattern**` field; §3 standalone format unchanged
- **Expected**: `awk '/^### 1b\./,/^### 2\./' ... | grep -c '^\*\*Architectural Pattern\*\*'` = 1; same awk against `### 3.` to `### 4.` = 0.
- **Actual**: §1b region count = 1 (line 75 of `plan.md`: `**Architectural Pattern**: {category} — {1-sentence differentiation}`, positioned between `## Overview` and `## Tasks` of the §1b embedded format). §3 region count = 0.
- **Verdict**: PASS

### Requirement 4: Post-selection graft path acknowledged in §1b's user-presentation region
- **Expected**: Within §1b, after the second template fence, ≥ 1 occurrence of `graft|cross-graft|combine variants|combined plan`.
- **Actual**: Count = 1. The §1b.f comparison-table prose at line 128 of `plan.md` includes "may also be resolved by **combining variants** — selecting one variant as the base and grafting a named task or module from another variant into it (a cross-graft producing a combined plan). … Record the graft in the §1b.g event log via `selection_rationale` (e.g. `\"operator graft: Plan A base + Plan B Task 3\"`) and write the combined plan content to `lifecycle/{feature}/plan.md`." Located outside the verbatim plan-agent prompt template fence.
- **Verdict**: PASS

### Requirement 5: Orchestrator-review Post-Plan Checklist row P8 — structural field-presence check
- **Expected**: One `| P8 |` row referencing both "Architectural Pattern" and the criticality-critical gate AND the five-category list.
- **Actual**: The single P8 row at line 165 of `orchestrator-review.md` reads `| P8 | Architectural Pattern field present and in taxonomy | Structural check only (field presence + closed-set membership): the plan contains a \`**Architectural Pattern**\` field whose value is one of the five categories: event-driven, pipeline, layered, shared-state, plug-in. Gated on \`criticality = critical\` (when §1b ran); explicitly N/A for non-critical plans. Semantic fit is not checked here — that domain belongs to the synthesizer. |`. Row contains "Architectural Pattern", the literal five-category list, and the criticality-critical gate. Sits immediately after P7.
- **Verdict**: PASS

### Requirement 6: Plugin tree regenerated and staged via `just build-plugin`
- **Expected**: `diff` between canonical and mirror produces no output for both `plan.md` and `orchestrator-review.md`.
- **Actual**: Both diffs returned exit 0 with empty output, indicating byte-identical mirrors at `plugins/cortex-interactive/skills/lifecycle/references/{plan.md,orchestrator-review.md}`.
- **Verdict**: PASS

### Requirement 7: Pytest enforces byte-equality across all canonical→mirror reference pairs (with sentinel-mutation gate)
- **Expected**: (a) `pytest tests/test_dual_source_reference_parity.py -v` exits 0; (b) collection lists ≥ 20 items; (c) sentinel test catches mutation.
- **Actual**: Test exits 0 with 40 passed in 0.05s. Collection reports 40 items (39 parametrized file-pair tests + 1 sentinel `test_assert_pytest_fails_on_mutation`), well above the 20 floor. The sentinel uses an in-memory mutation (`mirror_bytes + b'\x00'`) and asserts `assert_byte_parity` raises `AssertionError`, satisfying R7c via the in-test helper form (one of the two admitted forms). Coverage extends to both BUILD_OUTPUT_PLUGINS (`cortex-interactive` and `cortex-overnight-integration`) — strengthens spec R7's literal scope per Veto Surface decision.
- **Verdict**: PASS

### Requirement 8: Backlog item #159 deferral — verified via plan-rewritten "deferral not re-applied" form
- **Expected** (per plan rewrite, since #160 shipped and lifecycle resumed): `status` ≠ `open` AND `blocked-by` does not contain `"160"`.
- **Actual**: `backlog/159-...md` frontmatter shows `status: in_progress` and `blocked-by: []`. Both conditions satisfied — the deferral is not re-applied. Spec's literal R8 acceptance (`status: open` AND `blocked-by` contains `"160"`) was correctly identified as stale post-resumption per the plan's Veto Surface rationale.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `tests/test_dual_source_reference_parity.py` follows the existing `tests/test_*.py` pattern (sibling: `tests/test_check_parity.py`). The `PLUGINS` constant and `assert_byte_parity` helper use clear, conventional Python naming. Markdown edits use the existing `**Bold-label**` field convention from prior Plan Format fields (Files, What, Depends on, Complexity, Context, Verification, Status).
- **Error handling**: The pure parity helper raises `AssertionError` with a length summary for fast diagnosis; the test asserts file existence before reading bytes (`assert canonical.is_file()` / `assert mirror.is_file()`). The sentinel test guards against an empty pairs list with an explicit assertion. Discovery is defensive — orphan skills not in any `PLUGINS` tuple are silently skipped, with a docstring note that no orphans currently exist.
- **Test coverage**: Plan's Verification Strategy items 1–9 are all executable; spot-checked R1, R2, R3, R4, R5, R6, R7 directly via the spec's grep/diff/pytest commands and confirmed pass. The sentinel-mutation gate satisfies R7c via the in-test helper form (per Veto Surface). The dual-source parity test deliberately covers both BUILD_OUTPUT_PLUGINS, strengthening M5 defense-in-depth coverage symmetrically with pre-commit Phase 4.
- **Pattern consistency**: Edit lands inside the §1b verbatim template block (preserving the verbatim-copy semantics constraint). Orchestrator-review row P8 follows the existing P1–P7 table-row format and the `Item | Criteria` column convention. The dual-source parity test matches the existing `tests/conftest.py` registration pattern and parametrizes via `pytest.mark.parametrize` over a sorted, deterministic pair list. Soft-positive routing ("Name your category from this list") is honored — no MUST/CRITICAL/REQUIRED added (count remains 0). The standalone Plan Format under §3 was correctly left untouched per Non-Requirements.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
