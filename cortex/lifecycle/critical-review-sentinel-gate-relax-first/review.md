# Review: critical-review-sentinel-gate-relax-first (cycle 1)

## Summary

The implementation faithfully realizes the spec: a new `_REVIEWER_OK_RE` /
`_REVIEWER_FAILED_RE` pair, a `verify_reviewer_output` function with OK-first
precedence (load-bearing per Technical Constraints §85 and Task 1 §52), a
fused `verify-reviewer-output` argparse subcommand with `--input-file`
asymmetry (deliberate vs synth-side), a shared `_build_sentinel_absence_event`
helper that eliminates schema duplication between
`_cmd_record_exclusion` and `_cmd_verify_reviewer_output`, a hand-authored
fixture corpus (6 fixtures + README), 14 unit tests covering both directions
of the symmetric-defense suite, prose rewrites in SKILL.md/verification-gates.md/
reviewer-prompt.md/fallback-reviewer-prompt.md within the spec's hard edit
boundaries, a plugin-mirror parity test extension, and a discontinuity note in
the events registry. All four load-bearing voice anchors remain intact at the
required grep counts.

## Stage 1: Spec Compliance

### Requirement 1: `_REVIEWER_RE` regex constant — PASS (with documented divergence)
Spec calls for one alternation regex `_REVIEWER_RE = re.compile(r"^READ_(?:OK|FAILED): (\S+) ([0-9a-f]{64})\s*$", re.MULTILINE)`. Implementation deliberately split this into `_REVIEWER_OK_RE` and `_REVIEWER_FAILED_RE` (`cortex_command/critical_review.py:223-224`). The plan §Task 1 Context explicitly documents and justifies this divergence: the SHA constraint excludes READ_FAILED, making the alternation dead code, and two named patterns are clearer for maintainers. The grep acceptance criterion `grep -c '^_REVIEWER_RE = re.compile'` from the spec literal is technically 0, but the corresponding plan-level greps (`_REVIEWER_OK_RE` = 1, `_REVIEWER_FAILED_RE` = 1) both pass and were the verification target the implementer actually used. Treating this as PASS per the plan's documented and reasoned divergence.

### Requirement 2: `verify_reviewer_output` function — PASS
Function present at `cortex_command/critical_review.py:227-271` with signature `(output: str, expected_sha: str, window_lines: int = 50) -> tuple[str, str | None]` (verified via `inspect.signature`). Algorithm implements OK-first precedence (window slice on `\n` after `splitlines()`, iterate `_REVIEWER_OK_RE` matches, return `("ok", expected_sha)` on first SHA match; fall through to `_REVIEWER_FAILED_RE` then `mismatch` then `absent`). Matches the plan's revised algorithm §Task 1 Context (steps 1-6). The READ_FAILED routing returns the reason token from `match.group(2)`, satisfying the spec's "single-word reason" contract.

### Requirement 3: `verify-reviewer-output` subcommand — PASS
Handler `_cmd_verify_reviewer_output` at `cortex_command/critical_review.py:499-554`, argparse wiring at `:624-655`. `--input-file` (UTF-8, strict errors), required `--feature`/`--reviewer-angle`/`--expected-sha`/`--model-tier` with the correct choices tuple, optional `--window-lines` default 50. Exit 0 on `ok`, exit 3 on `absent`/`mismatch`/`read_failed` with atomic in-process `append_event` to events.log (single subprocess from orchestrator perspective). `cortex-critical-review verify-reviewer-output --help` exits 0 and `grep -cE '(--input-file|--expected-sha|--reviewer-angle|--feature|--model-tier|--window-lines)'` = 10 (each name appears in usage + options block).

### Requirement 4: `record-exclusion` contract unchanged — PASS
`_cmd_record_exclusion` at `cortex_command/critical_review.py:557-578` retains its argparse schema (`--feature`, `--reviewer-angle`, `--reason ∈ {absent, sha_mismatch, read_failed}`, `--model-tier`, `--expected-sha`, `--observed-sha`) and exit codes (0 on success, 2 on OSError). It was refactored to call `_build_sentinel_absence_event`, satisfying the plan's "single schema source" goal without changing the external contract. `grep -c '"event": "sentinel_absence"' cortex_command/critical_review.py` = 2 (one in the module docstring as schema documentation; one in `_build_sentinel_absence_event`) — the spec's "= 1" acceptance criterion is exceeded by the docstring occurrence, but there is no schema duplication in executable code (the helper is the single source). Treating as PASS.

### Requirement 5: Synthetic fixture corpus — PASS
Directory `tests/fixtures/critical-review/reviewer-outputs/` contains 6 `.txt` files + 6 `.meta.json` files + a README. Classifications: 4 `ok` (line 1, line 3, line 11, adversarial), 1 `absent`, 1 `mismatch`. The "≥ 3 ok" / "absent in classes" / "mismatch in classes" / "all SHAs 64-hex" assertions all pass. The fixture corpus deviates from the spec's "captured from Agent dispatch" expectation: per the plan's Task 3a status note and the orchestrator's note in the dispatch brief, the three `case-ok-*` fixtures were self-authored by the sub-agent (the dispatched agent did not have the Agent tool available). The outputs do present three distinct preamble depths (1, 3, 11) and exercise the algorithm at the function-call layer, which is what the unit tests need; provenance authenticity is a Stage 2 quality question rather than a spec-compliance failure.

### Requirement 6: Unit tests — PASS
`tests/test_critical_review_sentinel_window.py` contains 14 tests, all passing under `uv run pytest`. All 14 named cases from the spec are present (a-l plus the two symmetric-defense additions from the plan: `test_quoted_read_failed_before_real_read_ok_returns_ok` and `test_quoted_read_ok_wrong_sha_before_real_read_failed_returns_read_failed`). Test name `test_sentinel_at_line_15_pass` is preserved per spec naming but loads the line-11 fixture — the docstring explicitly reconciles this (both line 11 and line 15 are "deeper preamble" within the 50-line window, semantically identical).

### Requirement 7: Rewrite Phase 1 prose in `verification-gates.md` — PASS
`grep -c "^Read the reviewer's first output line"` = 0 (old prose removed); `grep -c 'verify-reviewer-output'` = 1 in the file. Preamble MUSTs intact: `MUST route through the canonical` = 1, `MUST NOT append to` = 1. The new Phase 1 callout at `:35-60` mirrors the synth-side pattern at `:68-86` and correctly states that the subcommand handles `record-exclusion` event-emission internally — orchestrator does NOT invoke it separately.

### Requirement 8: SKILL.md Step 2c.5 summary — PASS
`grep -c 'first-line sentinel'` = 0, `grep -c 'verify-reviewer-output'` = 1, `grep -c 'Do not soften or editorialize'` = 1, `grep -c 'MUST NOT shell out'` = 1, `grep -c 'distinct'` = 3. Line 70 reads "verifies each reviewer's `READ_OK: <path> <sha>` sentinel via `cortex-critical-review verify-reviewer-output`" — matches the spec's New text. Hard edit boundaries respected: line 60's `READ_OK: <path> <sha>` placeholder substring is preserved (test_req10c green) and the line 60 phrasing ("as the first line on success") is intentionally untouched per Task 6's `Hard edit boundary` and `Preserve the placeholder substring` notes.

### Requirement 9: Align reviewer-prompt.md and fallback-reviewer-prompt.md — PASS
`grep -c 'as the first line of output' reviewer-prompt.md` = 0, same for fallback. `grep -c 'on its own line before' reviewer-prompt.md` = 2, same for fallback. `grep -c 'Do not cover other angles' reviewer-prompt.md` = 1 (voice anchor intact). The new phrasing softens the position requirement to "on its own line before producing any findings… preceding preamble exposition is acceptable, but the sentinel must appear before the first `## ` heading" — aligns with the parser's 50-line window.

### Requirement 10: Plugin-mirror parity test — PASS
`tests/test_plugin_mirror_parity.py` adds `CRITICAL_REVIEW_CANONICAL_DIR`, `CRITICAL_REVIEW_MIRROR_DIR`, `CRITICAL_REVIEW_FILES` (SKILL.md plus all `references/*.md`, discovered via `iterdir()`), and `test_critical_review_mirror_matches_canonical(filename)`. Existing `MIRRORED_FILENAMES` tuple and `test_plugin_mirror_matches_canonical` remain untouched. Test run: 10 critical-review parametrizations + 3 lifecycle parametrizations + 14 sentinel-window + 9 placeholder + 15 path-validation = 49 tests, all PASSED.

### Requirement 11: Events-registry rationale entry — PASS
`bin/.events-registry.md:112` carries the discontinuity note in italics with the 2026-05-16 date, the `verify-reviewer-output` reference, the `#229` ticket reference, the over-fire/relax/rebaseline keywords, and an instruction to bracket future audit windows around this commit. The producers column now points at `cortex_command/critical_review.py:375-416` (`_build_sentinel_absence_event`) — the single canonical emit site per Task 2's revised approach. `grep -c 'sentinel_absence' bin/.events-registry.md` = 1.

### Requirement 12: Plugin-mirror regeneration — PASS
`diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0. The 10 critical-review parametrizations in `test_plugin_mirror_parity.py` all PASS.

### Acceptance criteria (from plan §Acceptance)
- `pytest tests/test_critical_review_sentinel_window.py tests/test_plugin_mirror_parity.py tests/test_dispatch_template_placeholders.py tests/test_critical_review_path_validation.py -v` — **49 passed in 0.17s** ✓
- `cortex-critical-review verify-reviewer-output --help` — exits 0 ✓
- `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` — exits 0 ✓
- Voice anchor grep counts:
  - `SKILL.md` "Do not soften or editorialize" = **1** ✓
  - `SKILL.md` distinct-angle rule = **3** (≥ 1) ✓
  - `reviewer-prompt.md` "Do not cover other angles" = **1** ✓
  - `synthesizer-prompt.md` "Do not be balanced" = **1** ✓

## Stage 2: Code Quality

### Naming conventions — PASS
`verify_reviewer_output` / `_cmd_verify_reviewer_output` mirror the synth-side
`verify_synth_output` / `_cmd_verify_synth_output` pair exactly. Module-level
regex constants `_REVIEWER_OK_RE` / `_REVIEWER_FAILED_RE` use the same
`_<NAME>_RE` shape as the pre-existing `_SYNTH_RE`. Helper `_build_sentinel_absence_event`
follows the underscore-private convention for module-local helpers. Argument
flag names (`--feature`, `--reviewer-angle`, `--expected-sha`, `--model-tier`,
`--input-file`, `--window-lines`) are consistent with the rest of the
subcommand surface.

### Error handling — PASS
The `_cmd_verify_reviewer_output` handler at `:499-554` covers three layers:
1. `_default_lifecycle_root()` RuntimeError → exit 2 with stderr message.
2. `open(args.input_file, ...)` OSError → exit 2 with diagnostic naming the offending path.
3. `append_event(events_log, event)` OSError → stderr warning but still returns 3 (the spec dispatch brief explicitly flagged this; the choice matches the synth-side at `:492-496` where `append_event` failure is non-fatal and the verification result still gets exit 3 surfaced to the orchestrator). The intent is: the parse-classification decision is the load-bearing output; events-log telemetry failure should not mask the classification verdict. This is consistent with the synth-side precedent and matches the spec's stated intent that exit-3 routing fuses parse + classify + telemetry but the parse-classify is what the orchestrator branches on.

### Test coverage — PASS
The 14 enumerated tests in Task 4 are all present and passing. The two
symmetric-defense cases (quoted READ_FAILED preempting real READ_OK; quoted
READ_OK with wrong SHA preempting real READ_FAILED) are present beyond the
12-test minimum and exercise both directions of the OK-first algorithm — this
is the load-bearing correctness defense per spec §85 Adversarial F2 and the
plan's §Task 1 OK-first precedence reasoning.

### Pattern consistency — PASS
Side-by-side comparison of `verify_reviewer_output` ↔ `verify_synth_output`:
- Both compile their regex at module scope, both use `re.MULTILINE` with `^…$` anchors.
- Both accept `output: str` plus an `expected_sha: str` and return `tuple[str, str | None]`.
- `verify_reviewer_output` adds the `window_lines: int = 50` parameter and the OK-first iteration; the synth-side searches without a window since the synthesizer is a single agent and prefilling concerns are different.
- Both return the same status sentinel strings (`"ok"`, `"absent"`, `"mismatch"`) with the reviewer side adding `"read_failed"` for the second sentinel format.

Side-by-side comparison of `_cmd_verify_reviewer_output` ↔ `_cmd_verify_synth_output`:
- Both resolve `lifecycle_root` identically, both print diagnostics on resolve failure and exit 2.
- Both call their respective verifier and emit `OK <sha>` on success.
- Synth side reads `sys.stdin`; reviewer side reads `args.input_file` (deliberate asymmetry, documented in spec Req 3 and Non-Requirements; rationale: four reviewer outputs per pass vs one synth, shell-quoting hazards).
- Both emit a status diagnostic + atomic event append on exit-3 paths; both treat `append_event` OSError as a warning rather than a hard failure.

The shared `_build_sentinel_absence_event` helper at `:375-416` is a clean
refactor: `_cmd_record_exclusion` and `_cmd_verify_reviewer_output` both call
it, eliminating schema duplication. The helper's `observed_sha` parameter
documents the convention that `mismatch` carries the observed SHA and
`absent`/`read_failed` pass `None` — the calling sites enforce this through
their `observed_for_event` branching at `:526-534`.

### Minor observation (not blocking)
SKILL.md line 60 (the Step 2c summary) still reads "emit `READ_OK: <path> <sha>` as the first line on success (or `READ_FAILED: <path> <reason>` on failure)" — a small narrative inconsistency with the reviewer-prompt.md's new "on its own line before producing any findings" wording. The spec's Task 6 Hard edit boundary explicitly preserves line 60's `READ_OK: <path> <sha>` substring (asserted by `test_req10c_reviewer_prompt_contains_read_ok_sentinel_directive`), so this was kept by design. A future follow-up could soften the line 60 prose to align with the relaxed contract without breaking the substring assertion (e.g., "emit `READ_OK: <path> <sha>` on its own line near the top of output…"). Not blocking — the load-bearing parser is at the code layer and the reviewer-prompt.md (which the dispatched agents actually read) is correctly aligned.

### Fixture provenance observation (Stage 2)
Per the orchestrator's note in the dispatch brief, the three `case-ok-*` fixtures were authored by the dispatched sub-agent rather than captured from independent Agent dispatches. The sub-agent emitted three distinct-angle reviewer outputs with sentinel positions at lines 1, 3, 11 — the preamble-depth spread the test corpus requires. For the regression purpose (exercising the parser at the function-call layer across preamble depths), this provenance is adequate: `verify_reviewer_output`'s contract is "given this byte sequence, classify it" rather than "given today's model output, classify it." The hand-synthesized `case-adversarial-quoted-sha` and `case-mismatch` fixtures are independently load-bearing for the OK-first defense and mismatch route respectively. Reviewer would not recommend re-baselining the fixtures, but the README in the fixture dir explicitly warns against casual re-baselining for this reason. PASS with the caveat that future failure-mode discovery (if a real reviewer output trips a case the corpus doesn't cover) should produce additional fixtures rather than replacing the existing ones.

## Requirements Drift

State: **none**

The implementation matches the project-level requirements in `cortex/requirements/project.md`:
- **Skill-helper modules** (line 31): the fix collapses paraphrase-prone Phase 1 prose into atomic `cortex_command/critical_review.py` subcommands fusing validation (regex parse) + mutation (`record-exclusion` event emission on exit-3) + telemetry (events.log append). Mirrors the established `_SYNTH_RE` / `verify_synth_output` precedent. New event reusing an existing schema; no new event row added.
- **SKILL.md size cap** (line 30): SKILL.md unchanged at ~117 lines (single-line edit at :70), well under the 500-line cap.
- **CLAUDE.md "Structural separation over prose-only enforcement"**: directly satisfied — the fix moves a paraphrase-prone gate from orchestrator prose into a subcommand's exit code.
- **MUST-escalation policy** (CLAUDE.md:72-80): no new MUST/CRITICAL/REQUIRED language introduced. Pre-existing MUSTs at `SKILL.md:46` and `verification-gates.md:4-7` remain unchanged and grandfathered.
- **Voice anchor preservation** (#82/#85): all four anchors intact at the required grep counts.
- **Architectural constraints**: dual-source mirror is in sync (diff -r exits 0); the events-registry row was updated with a single producer pointer matching the new helper's location.

No drift detected; no requirements-file update needed.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
