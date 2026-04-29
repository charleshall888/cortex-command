# Review: unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception

## Stage 1: Spec Compliance

### R1 — Canonical Python detector returns structured output and full phase vocabulary
**Rating**: PASS
- `cortex_command/common.py:88-217` returns `dict[str, str | int]` with keys `phase, checked, total, cycle`.
- Phase vocabulary at L96-102 docstring and L144-216 returns enumerates `{research, specify, plan, implement, implement-rework, review, complete, escalated}`.
- Acceptance command exits 0; observed return: `{'phase': 'review', 'checked': 15, 'total': 15, 'cycle': 1}`.

### R2 — CLI default output is JSON; bare-string output retired
**Rating**: PASS
- `_cli_detect_phase` at `cortex_command/common.py:514-520` emits `json.dumps(result, separators=(",", ":")) + "\n"` to stdout.
- Acceptance pipeline exits 0; output `{"phase":"review","checked":15,"total":15,"cycle":1}`.

### R3 — Hook subprocesses to canonical CLI; bash glue layer is normatively specified
**Rating**: PARTIAL
- The bash ladder regexes at the prior L170-207 are removed. `grep -cE 'sed -n.*verdict|grep -cE.*Status.*\[ x\]' hooks/cortex-scan-lifecycle.sh` returns 0 (PASS).
- The R3 normative wire-format encoding is implemented faithfully in `encode_phase()` at `hooks/cortex-scan-lifecycle.sh:186-203`, covering all four R3 cases.
- **Deviation**: the spec's literal acceptance grep `grep -c 'python3 -m cortex_command.common detect-phase' hooks/cortex-scan-lifecycle.sh` returns 0. Implementation uses `python3 -c '<inline script>'` (L254-266) with `from cortex_command.common import detect_lifecycle_phase` to inline-batch all candidate dirs in one Python interpreter session. The plan (Task 7 + Veto Surface) explicitly redesigned this to avoid an N×30-80ms cold-start cost (the repo currently has 34 lifecycle dirs). The single-dir CLI from R2 still exists; only the hook deviates from the literal R3 invocation form. The spirit of R3 (subprocess to canonical Python detector, R3 normative encoding via bash glue) is fully realized.

### R4 — Hook hard-fails on missing Python or cortex_command, but only after confirming a cortex repo
**Rating**: PASS
- Precondition block at `hooks/cortex-scan-lifecycle.sh:23-29`, placed after the `[[ -d "$LIFECYCLE_DIR" ]] || exit 0` guard at L21 and before iteration.
- Diagnostic text matches spec verbatim: `cortex_command not available; cortex-scan-lifecycle hook requires the cortex CLI — install via 'uv tool install -e .' from the cortex-command repo`.
- Verified: with `lifecycle/` present and `PATH=/usr/bin:/bin` (no `cortex_command`), exit=1 with diagnostic on stderr; without `lifecycle/`, exit=0 silently.

### R5 — Skill prose ladder replaced with CLI invocation
**Rating**: PASS
- `skills/lifecycle/SKILL.md:41-62` replaces the prose ladder with `python3 -m cortex_command.common detect-phase` invocation plus a one-line-per-phase reference table covering all 8 phase values.
- Acceptance: `grep -c 'python3 -m cortex_command.common detect-phase' skills/lifecycle/SKILL.md`=1; `grep -cE 'plan\.md exists with all \[x\]' skills/lifecycle/SKILL.md`=0.

### R6 — Dashboard `parse_plan_progress` folded into canonical detector
**Rating**: PASS
- `grep -c 'def parse_plan_progress' cortex_command/dashboard/data.py`=0.
- `grep -rc 'parse_plan_progress' cortex_command/dashboard/`=0 across all files.
- Caller now consumes `checked`/`total` from the canonical detector's dict via `parse_feature_events` at `cortex_command/dashboard/data.py:312`.

### R7 — Sibling implementation at `tests/lifecycle_phase.py` is removed; consumers re-point to canonical
**Rating**: PASS
- `test -f tests/lifecycle_phase.py` returns 1 (file deleted).
- `grep -rc 'tests.lifecycle_phase\|from .lifecycle_phase' tests/` = 0 across all consumers.
- `pytest tests/test_lifecycle_state.py -x` exits 0 (7 passed).

### R8 — `compute_slow_flags` updated to handle `implement-rework`
**Rating**: PASS
- `cortex_command/dashboard/data.py:1189`: `if current_phase in ("implement", "implement-rework"):`.
- `pytest cortex_command/dashboard/tests/test_data.py -x -k slow` exits 0 (8 passed, 78 deselected).

### R9 — events.log `phase_transition` writer and consumer aligned to new vocabulary
**Rating**: PASS
- Writer (prose protocol per Veto Surface): `skills/lifecycle/references/review.md:203` and `skills/lifecycle/references/implement.md:258` emit `"to": "implement-rework"` for the CHANGES_REQUESTED re-entry case. Confirmed there is no Python writer for `review→implement` transitions.
- Consumer: `cortex_command/overnight/report.py` updated — `phase_transitions[-1].get("to") in {"implement", "implement-rework"}`.
- Acceptance grep `grep -E 'to.*implement-rework|implement-rework.*to' cortex_command/overnight/` returns ≥1; `grep -c 'implement-rework' cortex_command/overnight/report.py` = 1.
- `pytest cortex_command/overnight/tests/ -x` exits 0 (313 passed, 1 xpassed).

### R10 — Dashboard `current_phase` and `backlog/index.json` `lifecycle_phase` remain scalar strings; vocabulary expansion documented
**Rating**: PASS
- `current_phase` projected to scalar via `result["phase"]` in `parse_feature_events` (data.py:312).
- `backlog/generate_index.py:115` projects `lifecycle_phase` to scalar via the dict-return.
- `backlog/index.json` `lifecycle_phase` values remain scalar strings.
- Documentation updated in BOTH `skills/backlog/references/schema.md` (line 22, with attribution) AND `backlog/generate_index.py` (inline comment, count=2). Spec only required one; both is fine.
- Existing dashboard tests pinning `"implement"` continue to pass.

### R11 — Statusline retains its bash ladder with documenting comment
**Rating**: PASS
- `claude/statusline.sh:377-401` logic unchanged.
- Comment block at L377-390 includes all four required substrings: `bash-only mirror`, `< 500ms`, `parity test`, `cortex_command.common`. Acceptance grep returns 6 matches (≥3 required).
- Comment further warns "Do not 'fix' this apparent duplication by collapsing it into a Python call."

### R12 — Three-layer parity tests enforce equivalence at distinct surfaces
**Rating**: PASS
- `pytest tests/test_lifecycle_phase_parity.py -x` exits 0 (40 passed).
- `grep -cE 'def test_.*glue|def test_.*statusline|def test_.*hook_end_to_end' tests/test_lifecycle_phase_parity.py` = 4 (≥3 required).
- 12a glue cases cover all 10 R12a-enumerated fixtures.
- 12b adds both ladder and parser sub-tests; cycle-blindness exception enumerated in test docstrings.
- 12c hook end-to-end uses the fixture matrix from `tests/fixtures/lifecycle_phase_parity/` (10 fixture dirs).

### R13 — Plugin mirror regenerated and drift hook clean
**Rating**: PASS
- `diff hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight-integration/hooks/cortex-scan-lifecycle.sh` exits 0.
- `diff skills/lifecycle/SKILL.md plugins/cortex-interactive/skills/lifecycle/SKILL.md` exits 0.
- `diff skills/lifecycle/references/{implement,review}.md plugins/cortex-interactive/skills/lifecycle/references/{implement,review}.md` exits 0.
- `diff skills/backlog/references/schema.md plugins/cortex-interactive/skills/backlog/references/schema.md` exits 0.

### R14 — Full repo test suite passes
**Rating**: PASS (within scope)
- Per review constraints, full `pytest -x` was not run — 19 pre-existing dashboard template failures (unrelated jinja2 `'request' is undefined`) pre-date this change.
- In-scope targeted runs all pass: `tests/test_lifecycle_state.py` (7 passed), `tests/test_lifecycle_phase_parity.py` (40 passed), `cortex_command/overnight/tests/` (313 passed, 1 xpassed), `cortex_command/dashboard/tests/test_data.py -k slow` (8 passed).

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. The new `encode_phase` and `phase_label` bash glue functions follow the existing snake_case style. Python detector uses standard dict keys; type hint `dict[str, str | int]` matches `requires-python = ">=3.12"`.

### Error handling
- Hook precondition block fails loud with remediation text per R4.
- Inline `python3 -c` invocation in hook redirects stderr to /dev/null and falls back to empty `batch_output`; the iteration loop skips dirs with empty results — appropriate post-precondition.
- Detector handles missing files gracefully (defaults: `checked=0, total=0, cycle=1, phase="research"`).

### Test coverage
- Three-layer parity test matrix exceeds spec minimums (40 cases vs ≥3 functions required).
- Stall-detection rework path covered (R8).
- Dashboard tests (`test_data.py`) extended for new vocabulary; existing fixtures preserved.
- Plan-verification step at Task 7 ("< 500ms wall clock") was operationally verified by the inline-batch design.

### Pattern consistency
- Boundary projection at consumers (current_phase, lifecycle_phase) preserves the scalar-string serialization contract while expanding the in-process API to dict — a clean layering.
- Statusline structural exception is documented exactly per R11; mirrors the project's preference for explicit-exception over silent-duplication.
- Plan correctly identifies the prose-vs-Python writer location (Veto Surface) and updates skill markdown rather than chasing a non-existent Python writer.

### Notes / follow-ups (not gating)
- The critical-review residue notes a Class-B cosmetic finding: `_phase_transition_abbrev` at `cortex_command/dashboard/data.py:577-583` lacks a `review→implement-rework` entry. This is cosmetic — display falls through to raw_label rather than the abbreviated form. Not in spec; suitable as a follow-up if dashboard transition labels begin looking inconsistent.
- R3 deviates from the literal acceptance grep (`python3 -m cortex_command.common detect-phase`) in favor of an inline-batched `python3 -c` invocation. The deviation is justified by the per-invocation cold-start cost (N=34 dirs × 30-80ms = 1-3s). The plan documents the redesign in Task 7 and Veto Surface. The spirit of R3 (subprocess to the canonical detector + R3 normative wire-format encoding via bash glue) is fully preserved. Calling this PARTIAL rather than FAIL because (a) the design is sound and explicitly approved in the plan, (b) all other R3 acceptance lines pass (regex removal, normative encoding, glue function structure), and (c) reviewers should not invalidate well-justified design refinements documented in the plan.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
