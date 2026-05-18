# Review: propagate-backlog-criticality-to-lifecycle-start

## Stage 1: Spec Compliance

- **R1 — Helper module produces lifecycle_start row from backlog frontmatter**: PASS. `cortex_command/refine.py:105-180` reads frontmatter via `_read_backlog_frontmatter`, appends a JSONL row with schema_version/ts/event/feature/tier/criticality/entry_point keys. `tests/test_refine_module.py::test_emit_lifecycle_start_writes_backlog_values` passes (asserts `tier=complex`, `criticality=high`, `entry_point=refine`, `schema_version=1`).
- **R2 — Defaults applied when frontmatter absent**: PASS. `_read_backlog_frontmatter` returns `("simple", "medium")` when `backlog_slug is None` (cortex_command/refine.py:43-44) or file missing (line 47-48). Per-key absence falls back at lines 54-55 and 65-66. All three parametrized sub-cases pass.
- **R3 — Idempotent on existing lifecycle_start**: PASS. `_lifecycle_start_present` scan at refine.py:120-121 short-circuits before append. `test_emit_lifecycle_start_idempotent` asserts size_after == size_before and rows unchanged after re-run on pre-seeded log.
- **R4 — Atomic append with read-after-write verify**: PASS. `grep -c "read_after_write" cortex_command/refine.py` = 2 (`read_after_write_io_error` at line 154, `read_after_write_mismatch` at line 177). Bare `open(events_log, "a")` append at line 136, re-read at 150, mismatch check at 159-178. Pattern mirrors `bin/cortex-complexity-escalator:192-235`.
- **R5 — Invalid frontmatter values rejected with diagnostic**: PASS. `_read_backlog_frontmatter` calls `sys.exit(64)` with stderr diagnostic naming invalid value, file path, and allowed set (refine.py:56-63 for criticality; 67-74 for complexity). `test_emit_lifecycle_start_rejects_invalid_value` parametrized over `criticality: extreme` and `complexity: medium` passes.
- **R6 — Console-script entry registered**: PASS. `grep -c '^cortex-refine = "cortex_command.refine:main"$' pyproject.toml` = 1 (line 40).
- **R7 — Refine SKILL.md invokes the helper at the canonical site**: PASS. `grep -c "cortex-refine emit-lifecycle-start" skills/refine/SKILL.md` = 1 (line 66, end of Step 2 after the resume-point decision tree, before Step 3 Clarify). Prose uses soft-positive routing ("invoke...") per the MUST-escalation policy and explicitly handles Context B ("omit `--backlog-slug` for Context B").
- **R8 — Static wiring test catches regressions**: PASS. `tests/test_refine_lifecycle_start_wiring.py::test_refine_skill_wires_emit_lifecycle_start` passes; asserts literal `cortex-refine emit-lifecycle-start` present in skills/refine/SKILL.md.
- **R9 — Producers column updated in events-registry**: PASS. `bin/.events-registry.md` `lifecycle_start` row producers cell includes `cortex_command/refine.py:128` (the `event: "lifecycle_start"` line inside the row dict). `grep -E "^\| .lifecycle_start.*cortex_command/refine" bin/.events-registry.md` matches.
- **R10 — Refine §5 transition prose updated for the carve-out**: PASS. `grep -c "phase_transition" skills/refine/SKILL.md` = 1 (line 167) and `grep -c "lifecycle_start" skills/refine/SKILL.md` = 3. Line 167 reads: "Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; ... The `lifecycle_start` session-start sentinel emitted at Step 2 is a deliberate carve-out from this rule and is owned by refine."
- **R11 — Backlog 227 regression scenario covered**: PASS. `test_emit_lifecycle_start_matches_227_repro_scenario` uses `criticality: high` + `complexity: simple` and asserts `read_criticality(...)` returns `"high"` and `read_tier(...)` returns `"simple"`. Test correctly clears `__wrapped__.cache_clear()` for both readers per plan.md Risks note.

Full test run: `uv run pytest tests/test_refine_module.py tests/test_refine_lifecycle_start_wiring.py -v` — 9 passed in 0.04s.

## Stage 2: Code Quality

- **Naming conventions**: Consistent with `cortex_command/discovery.py` canonical pattern. Private helpers (`_read_backlog_frontmatter`, `_now_iso`, `_lifecycle_start_present`, `_cmd_emit_lifecycle_start`, `_build_parser`) prefix-leaded; module-level constants (`_ALLOWED_CRITICALITY`, `_ALLOWED_COMPLEXITY`) frozenset for O(1) membership. The `main(argv: list[str] | None = None) -> int` signature matches the spec's Technical Constraint pointing at discovery.py.
- **Error handling**: Exit codes align with spec. R5 invalid-value path uses `sys.exit(64)` (EX_USAGE) with named-value/path/allowed-set diagnostic on stderr. IO failures on append (refine.py:138-146) and on re-read (152-157) return 70 with the sandbox-registration hint (`cortex init` mention) per the spec's "Permission denied" edge case. Mismatch path (line 177) emits the canonical `read_after_write_mismatch` token consumed by event-registry observability.
- **Test coverage**: All 11 spec acceptance criteria have matching coverage. R1, R2 (×3 sub-cases), R3, R5 (×2 sub-cases), R11 are pytest tests; R4 is grep-verified (`read_after_write` x2); R6 is grep-verified; R7 is grep-verified + wired through tests/test_refine_lifecycle_start_wiring.py; R8 is the wiring test itself; R9 is grep-verified; R10 is dual-grep-verified. The test scaffolding mirrors `tests/test_discovery_module.py` (`monkeypatch.chdir(tmp_path)`, direct-import of `main`, JSON re-read helpers).
- **Pattern consistency**: Module structure matches `cortex_command/discovery.py` (argparse builder, `set_defaults(func=...)`, `if __name__ == "__main__":` → `raise SystemExit(main(sys.argv[1:]))`). Emit + verify pattern faithfully reproduces `bin/cortex-complexity-escalator:192-235` including the `read_after_write_mismatch` literal. SKILL.md mirror at `plugins/cortex-core/skills/refine/SKILL.md` was auto-regenerated by the dual-source pre-commit hook (canonical and mirror are identical).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
