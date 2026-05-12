# Review: add-parent-epic-alignment-check-to-refine-clarify-critic

## Stage 1: Spec Compliance

### Requirement 1: Conditional alignment sub-rubric in clarify-critic prompt
- **Expected**: A conditional `## Parent Epic Alignment` section appended after `## Source Material` containing the five-step ordering (untrusted-data instruction → framing-shift → body-in-markers → post-body reminder → (a)/(b)/(c) sub-rubric), with verbatim wordings from §Technical Constraints.
- **Actual**: `skills/refine/references/clarify-critic.md` lines 54–68 contain the conditional section in the documented order. Pre-body untrusted instruction (line 58), framing-shift (line 60), `<parent_epic_body source="backlog/{parent_filename}" trust="untrusted">…</parent_epic_body>` markers (lines 62–64), post-body reminder (line 66), (a)/(b)/(c) sub-rubric (line 68) — all verbatim from §Technical Constraints. `grep -c "## Parent Epic Alignment"` returns 7 (appears in heading, prose references, and constraints table); section heading present. Pre-body and post-body "untrusted data" references both present (2 occurrences of the phrase).
- **Verdict**: PASS
- **Notes**: The spec acceptance text uses `grep -c "untrusted_data"` (with underscore) which evaluates to 0; the verbatim wording in §Technical Constraints uses the space form ("untrusted data"), and that wording is present twice as required. The acceptance criterion in the spec body has a token typo, but the substantive intent — pre-body discipline + post-body reminder both quoting "untrusted data" — is satisfied.

### Requirement 2: Silent skip on no parent / non-epic / missing
- **Expected**: For no-parent, missing, non-epic, or normalize-rejected (`null`/UUID-shape) parents, the alignment sub-rubric is omitted from the prompt; `parent_epic_loaded: false`.
- **Actual**: `skills/refine/references/clarify-critic.md` §"Parent Epic Loading" lines 14–24 document each branch and the `parent_epic_loaded = false` set + section omission for all three. Helper `_run_helper` integration tests confirm `## Parent Epic Alignment` does not appear in the constructed prompt for `no_parent`, `non_epic`, and `unreadable` branches (`tests/test_clarify_critic_alignment_integration.py:282–326,329–376`). Direct helper invocations on `161-add-parent-epic-alignment-check-to-refine-clarify-critic` returns `no_parent`; on `043-wire-review-phase-into-overnight-runner` returns `non_epic`.
- **Verdict**: PASS

### Requirement 3: Warning string for malformed/unreadable parent
- **Expected**: Helper exits 1 with `status: "unreadable"` on malformed parent frontmatter; orchestrator emits a fixed-template user-facing warning; never echoes raw filesystem error text; `parent_epic_loaded: false`.
- **Actual**: `bin/cortex-load-parent-epic` lines 367–377 catch `yaml.YAMLError` from parent frontmatter parsing and emit `{"status": "unreadable", "parent_id": <id>, "reason": "frontmatter_parse_error"}` then return exit code 1. `tests/test_load_parent_epic.py::test_unreadable_malformed_yaml` confirms the behaviour. `clarify-critic.md` §"Parent Epic Loading" lines 24, 26 document the unreadable branch's warning template (`"Parent epic <id> referenced but file is unreadable — alignment evaluation skipped."`) and an explicit warning-template allowlist sentence prohibiting raw filesystem error text.
- **Verdict**: PASS

### Requirement 4: bin/cortex-load-parent-epic helper
- **Expected**: New executable Python script with argparse, `cortex-log-invocation` shim within first 50 lines, importing `normalize_parent`, glob `f"{int(parent_id):03d}-*.md"`, body extraction with named-section priority + token cap + sanitization, five exit branches; existence/parity/import/shim/classification/sanitization acceptance criteria.
- **Actual**:
  - `bin/cortex-load-parent-epic` is executable (`test -x` passes), `--help` exits 0 with usage on stdout.
  - Shim at line 36, within first 50 lines: `head -50 ... | grep -c cortex-log-invocation` returns 1.
  - `from cortex_command.backlog.build_epic_map import normalize_parent` import at line 55: grep returns 1.
  - Five status branches all implemented: `no_parent` (line 359), `missing` (line 364), `non_epic` (line 393), `loaded` (line 421), `unreadable` (line 370). Glob uses `f"{int(parent_id):03d}-*.md"` (line 279). Section priority: `## Context from discovery` → `## Context` → `## Framing (post-discovery)` (lines 68–72) → first paragraph after H1 → `(no body content)` placeholder. Token cap: tries tiktoken cl100k_base, falls back to 2000-char cap; `… (truncated)` marker appended (lines 219–238). Sanitization replaces `</parent_epic_body>` (case-sensitive) and `<parent_epic_body` (case-insensitive) with `_INVALID` variants (lines 245–258).
  - Real-data classification acceptance criteria all pass: `085-...` returns `loaded` with parent_id 82 and a non-empty body of 288 chars; `161-...` returns `no_parent`; `043-wire-review-phase-into-overnight-runner` returns `non_epic` with parent_id 21 and `type: "spike"`.
  - `bin/cortex-check-parity` exits 0 (no E002 / W003).
  - `tests/test_load_parent_epic.py` includes 14 fixture tests (one more than the 13 listed in the plan inventory — bonus `test_parent_uuid_shape` coverage already in plan); all pass via `pytest tests/test_load_parent_epic.py -v`.
- **Verdict**: PASS

### Requirement 5: events.log schema extension — `parent_epic_loaded` field
- **Expected**: `parent_epic_loaded: <bool>` REQUIRED with documented `false` default for legacy reads; YAML example includes the field; cross-field invariant documented.
- **Actual**: §"Event Logging" line 138 lists `parent_epic_loaded: <bool>  # REQUIRED; default false on read for legacy events without this field`. Line 155 elaborates the required + legacy-read semantics. Line 159 documents the cross-field invariant ("any post-feature event whose `findings[]` contains at least one item with `origin: \"alignment\"` MUST have `parent_epic_loaded: true`") in parallel with the existing `len(dismissals) == dispositions.dismiss` invariant. YAML example block (lines 165–193) shows `parent_epic_loaded: true` on line 169.
- **Verdict**: PASS

### Requirement 6: events.log schema extension — `findings[]` per-item origin field
- **Expected**: `findings[]` shape changes from flat strings to `{text, origin: "primary"|"alignment"}` objects; legacy bare-string read-fallback documented; YAML example shows both origins.
- **Actual**: §"Event Logging" line 139 documents the new shape; line 157 documents the legacy read-fallback (`{text: <string>, origin: "primary"}`). YAML example shows both `origin: primary` (line 172, 174, 176, 178) and `origin: alignment` (line 180) findings.
- **Verdict**: PASS

### Requirement 7: Apply / Dismiss / Ask self-resolution applies uniformly
- **Expected**: Statement that alignment findings flow through the same disposition framework as primary findings.
- **Actual**: Line 120: "Note: alignment findings flow through the same Apply/Dismiss/Ask framework as primary findings — same self-resolution check, same Apply/Dismiss/Ask classification, same `dismissals[]` and `applied_fixes` routing." Placed in §"Disposition Framework" immediately after the Dispositioning Output Contract sub-section.
- **Verdict**: PASS

### Requirement 8: research-considerations dispatch argument on /cortex-interactive:research
- **Expected**: New optional `research-considerations` argument; per-agent applicability (1, 2, 3 only); h3 heading; placement after job-description before output format; mode-agnostic; defaults documented.
- **Actual**: `skills/research/SKILL.md` Step 1 (line 29) lists `research-considerations` in supported keys; lines 43–45 document defaults and format. Step 3 lines 65–69 document the h3 heading, per-agent applicability (agents 1, 2, 3; 4 and 5 excluded with rationale), and placement-after-job-description rule. Each of agents 1, 2, 3 has the `### Considerations to investigate alongside the primary scope` placeholder block injected with `{research_considerations_bullets}` token (lines 87–88, 111–112, 131–132). Agents 4 and 5 do not contain the section.
- **Verdict**: PASS

### Requirement 9: Refine populates research-considerations from alignment findings
- **Expected**: §4 of `skills/refine/SKILL.md` documents the `research-considerations` populating logic; bullet-list format; Apply/Ask-resolved-Apply only; Dismiss not propagated; `=`/`"` paraphrased.
- **Actual**: `skills/refine/SKILL.md` lines 117–136 ("Alignment-Considerations Propagation" sub-section): Apply / Ask→Apply only; Dismiss not propagated (line 119); newline-delimited bullet list format (lines 121–124); strip/paraphrase `=` and `"` (line 126); pass via `research-considerations="..."` (lines 128–134); fires only when at least one Apply'd alignment finding exists (line 136).
- **Verdict**: PASS

### Requirement 10: research.md output flow-through — `## Considerations Addressed` section
- **Expected**: Lifecycle-mode + non-empty considerations triggers a `## Considerations Addressed` section in synthesized research.md after `## Open Questions`; one bullet per consideration with a note describing how it was addressed; standalone mode does not emit.
- **Actual**: `skills/research/SKILL.md` Step 4 output structure lines 238–239 documents the conditional section after `## Open Questions`. Step 5 lines 247 (lifecycle-mode emission rule) and 254 (standalone-mode non-emission) confirm the route. Section content matches the spec wording ("deferred — no relevant evidence found" fallback).
- **Verdict**: PASS

### Requirement 11: Rubric-dimension cap principle
- **Expected**: A short paragraph documenting the soft ≤5 cap with current dimension count.
- **Actual**: `skills/refine/references/clarify-critic.md` line 205 (start of §"Constraints"): "Soft rubric-dimension cap: the clarify-critic carries a soft cap of ≤5 rubric dimensions to preserve per-angle attention quality. Current dimensions: (1) intent clarity, (2) scope boundedness, (3) requirements alignment, (4) optional complexity/criticality calibration, (5) optional parent-epic alignment (when `parent:` is set and resolves to `type: epic`). Adding a 6th rubric dimension requires either replacing an existing dimension or extracting the new one to a separate critic; do not exceed the cap by simple addition." `grep -cE "≤5|<= 5|five rubric dimensions|five dimension|soft cap of 5"` returns 1.
- **Verdict**: PASS

### Requirement 12: Rollback signal documented
- **Expected**: Spec contains the 70% threshold, 10-run window, legacy exclusion, invariant-violation handling.
- **Actual**: Spec line 76 documents all four: 70% threshold, 10 consecutive runs, legacy-event exclusion, invariant-violation reported separately. `grep -c "70%" lifecycle/archive/add-parent-epic-alignment-check-to-refine-clarify-critic/spec.md` returns 2.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Helper script name (`cortex-load-parent-epic`) matches the established `cortex-<verb>-<noun>` convention used in `bin/cortex-resolve-backlog-item`, `bin/cortex-update-item`, etc. JSON status enum (`no_parent | missing | non_epic | loaded | unreadable`) is consistent and documented in both the script docstring and `--help` epilog. Test files follow `tests/test_<module>.py` pattern.
- **Error handling**: Five status branches with explicit exit codes (0 for the four read-success branches, 1 for unreadable). Frontmatter parse errors caught with narrow `yaml.YAMLError` (parent file) versus broad `OSError` (file-access). Child-file resolution errors print to stderr and exit 1 (not part of the documented JSON status set, since the script presumes the orchestrator passes a valid child slug). Sanitization applies before truncation to avoid escaping the envelope. Backlog directory resolution honours `CORTEX_BACKLOG_DIR` for tests with a walk-up fallback for production use.
- **Test coverage**: Plan's verification commands all pass — 14 helper tests + 6 integration tests = 20 tests, all green. Plan called for 13 helper tests; the implementation includes one more (`test_parent_uuid_shape`) covering the spec's UUID-shape edge case explicitly. `bin/cortex-check-parity` passes. Real-data classification acceptance criteria all confirmed against tickets 085, 161, 043. Cross-field invariant codified as a regression fixture in `test_cross_field_invariant_violation_detector` for future programmatic-validator regression.
- **Pattern consistency**: Frontmatter parsing mirrors `bin/cortex-resolve-backlog-item:53-69` precedent; backlog-directory resolution mirrors `bin/cortex-resolve-backlog-item:210-226`; shim invocation matches `bin/cortex-resolve-backlog-item:16` line-pattern. Imports `normalize_parent` from `cortex_command.backlog.build_epic_map` rather than re-implementing — matches the spec's reuse constraint. The conditional-section template in `clarify-critic.md` uses an `{IF parent_epic_loaded: ...}` orchestrator-meta-instruction comment line followed by the literal section, matching the existing pattern in the same doc for orchestrator-side branching. Plugin mirrors not inspected (auto-regenerated by `just build-plugin` per CLAUDE.md).

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
