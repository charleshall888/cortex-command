# Plan: reconcile-discovery-skillmd-architecture-vocabulary-with

## Overview

Conform `skills/discovery/SKILL.md`'s two operator-facing surfaces (GATE-2 fallback line 82, `revise` re-walk line 85) and the one residual dangling gate reference in `skills/discovery/references/decompose.md` (line 50) to the emitted Architecture vocabulary (`### Pieces` + `### How they connect`), drop the orphaned `### Why N pieces` gate and the superseded `spec R4 GATE-2` pointer, regenerate both plugin mirrors, and pin regression tests (revise-bullet-scoped) so the vocabulary cannot silently re-drift. Pure prose-vocabulary reconciliation; no code/behavioral logic changes.

## Outline

### Phase 1: Reconcile discovery instruction vocabulary (tasks: 1, 2, 3)
**Goal**: SKILL.md (lines 82, 85) and decompose.md (line 50) describe only the emitted Architecture vocabulary; both plugin mirrors regenerated and byte-identical.
**Checkpoint**: `grep -c "Integration shape" skills/discovery/SKILL.md` = 0, `grep -c "Seam-level edges" skills/discovery/SKILL.md` = 0, `grep -c "Why N pieces" skills/discovery/SKILL.md` = 0, `grep -c "spec R4 GATE-2" skills/discovery/SKILL.md` = 0, `grep -c "research-phase R3" skills/discovery/references/decompose.md` = 0, and `diff -q` of each canonical/mirror pair exits 0.

### Phase 2: Regression test (tasks: 4, 5)
**Goal**: revise-bullet-scoped assertions lock the reconciliation in place so the drifted vocabulary cannot return and the `revise` bullet's live-template pointer + emitted headings stay present.
**Checkpoint**: `just test` exits 0 with the new/extended assertions. (Note: `just test` includes `tests/test_dual_source_reference_parity.py`, which covers the discovery mirrors — it passes only after Task 3 regenerates them, which is why the Phase 2 test tasks depend on Task 3.)

## Tasks

### Task 1: Reconcile both SKILL.md surfaces (lines 82 and 85)
- **Files**: `skills/discovery/SKILL.md`
- **What**: Rewrite the GATE-2 fallback sub-section list (line 82) and the `revise` re-walk clause (line 85) to name only the emitted Architecture sub-sections, dropping the non-emitted headings, the `### Why N pieces` gate, and the superseded spec pointer.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Line 82 currently reads: `... falls back to displaying the dense \`## Architecture\` section (sub-sections \`### Pieces\`, \`### Integration shape\`, \`### Seam-level edges\`, and optionally \`### Why N pieces\`) and surfaces a warning ...`. Replace the parenthetical so it names only `### Pieces` and `### How they connect` (the headings the research template at `skills/discovery/references/research.md` §6 actually emits, lines 120/123).
  - Line 85 (a single physical line, the `revise` bullet beginning `- **\`revise\`**`) currently reads: `... The agent re-walks the Architecture write protocol per spec R4 GATE-2 (iii) (re-emit \`### Pieces\`, re-run \`### Integration shape\` and \`### Seam-level edges\`, re-run the \`### Why N pieces\` falsification gate if piece_count > 5), re-presents the gate ...`. Replace this clause so it (a) points the agent at the live template in `references/research.md` §6, (b) names re-emitting `### Pieces` (per the role-naming convention) then `### How they connect`, and (c) carries the piece-count concern as the template's soft "consider merging" guidance — with NO `### Why N pieces` gate and NO `spec R4 GATE-2` pointer. Use soft positive-routing phrasing (MUST-escalation policy); describe the output shape and intent, not step-by-step method. Preserve the rest of the bullet (the `approval_checkpoint_responded` event emission, `revision_round` increment, loop semantics) unchanged.
  - **Interface contract for Task 4 (corrected)**: `references/research.md` is NOT a file-unique token — it already appears at SKILL.md line 67 (the Step 3 phase-reference table). Therefore the rewritten `revise` bullet (the single physical line containing `` `revise` ``) MUST itself contain, on that one line: the `references/research.md` §6 pointer, `### Pieces`, and `### How they connect`. Task 4 asserts these scoped to the `revise` line (not a file-wide check).
- **Verification**: `grep -c "Integration shape" skills/discovery/SKILL.md` = 0 AND `grep -c "Seam-level edges" skills/discovery/SKILL.md` = 0 AND `grep -c "Why N pieces" skills/discovery/SKILL.md` = 0 AND `grep -c "spec R4 GATE-2" skills/discovery/SKILL.md` = 0 AND the `revise` bullet line itself carries the pointer: `grep -cE '`revise`.*references/research\.md' skills/discovery/SKILL.md` = 1 — pass if all hold.
- **Status**: [x] completed (commit 5fffbfb1)

### Task 2: Reconcile the dangling gate reference in decompose.md (line 50)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Reword the §3 Consolidation Review sentence that names the now-removed gate, while preserving its behavioral instruction (do not re-derive/re-merge the research-delivered piece-set at decompose).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Line 50 currently reads: `The Architecture section's falsification gate (research-phase R3) has already run the structural-coherence merge test. Do not re-run it here. The analytical piece-set at decompose entry is the merged set.` After Task 1, the "(research-phase R3)" gate no longer exists in any active skill prose, so this becomes a dangling reference.
  - Reword to drop the `falsification gate (research-phase R3)` naming while keeping the instruction that the analytical piece-set delivered by research is final and must not be re-derived or re-merged at decompose. Match the existing register (the surrounding §3 prose describes the piece-set as research-owned and final). Do NOT re-open decompose.md §1/§2/§4 (already reconciled by #268) — line 50 is the only edit.
  - Note: line 122's "the prior R3 per-item-ack flow" is a DIFFERENT, historical R3 (a superseded per-item-ack flow) — leave it untouched. The negative assertion in Task 5 targets the literal `research-phase R3`, which appears only on line 50.
- **Verification**: `grep -c "research-phase R3" skills/discovery/references/decompose.md` = 0 AND the §3 Consolidation Review section still instructs against re-deriving/re-merging the piece-set (observable: the "Do not re-run it here" / "piece-set ... is the merged set" intent survives in §3) — pass if both hold.
- **Status**: [x] completed (commit afcbf8ca)

### Task 3: Regenerate and stage both plugin mirrors
- **Files**: `plugins/cortex-core/skills/discovery/SKILL.md`, `plugins/cortex-core/skills/discovery/references/decompose.md`
- **What**: Run `just build-plugin` to regenerate the byte-identical plugin mirrors of the two edited canonical files, then stage only those two mirror paths.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - The pre-commit dual-source drift hook (`.githooks/pre-commit`) runs `just build-plugin` and blocks the commit on mirror drift; `tests/test_dual_source_reference_parity.py` (covers `discovery` per its PLUGINS dict) independently fails `just test` on canonical/mirror byte-parity mismatch. Regenerate before the phase commit and before any `just test`-based verification.
  - `just build-plugin` is a whole-skill-directory rsync, not a two-file operation. After running it, confirm via `git status --porcelain plugins/cortex-core/skills/discovery/` that ONLY the two intended mirror files (`SKILL.md`, `references/decompose.md`) show changes. If any other discovery mirror file (`references/clarify.md`, `references/orchestrator-review.md`, `references/research.md`) shows unexpected drift, stop and surface it (pre-existing drift, out of scope) rather than staging it. Stage ONLY the two intended mirror paths explicitly (not `git add plugins/`).
- **Verification**: `diff -q skills/discovery/SKILL.md plugins/cortex-core/skills/discovery/SKILL.md` exits 0 AND `diff -q skills/discovery/references/decompose.md plugins/cortex-core/skills/discovery/references/decompose.md` exits 0 — pass if both identical.
- **Status**: [x] completed (mirrors regenerated + staged within commits 5fffbfb1 and afcbf8ca; both pairs byte-identical, no residual drift)

### Task 4: Pin SKILL.md vocabulary with a revise-bullet-scoped regression test
- **Files**: `tests/test_discovery_gate_presentation.py`
- **What**: Add a test asserting the four drifted tokens are absent from SKILL.md (file-wide) AND — scoped to the `revise` bullet line specifically — that it carries the live-template pointer and the emitted headings, so a degenerate edit that fixes line 82 but stubs/deletes the `revise` bullet fails.
- **Depends on**: [1, 3]
- **Complexity**: simple
- **Context**:
  - The file already reads the `DISCOVERY_SKILL` path constant and demonstrates the **scoped-assertion idiom** in `test_r3_drop_description_has_dual_use_marker` (lines ~108–116): iterate `text.splitlines()`, find the line containing the marker, assert a second token (`` `drop` ``) is on that SAME line. Follow this idiom.
  - Negative assertions (file-wide): `"Integration shape" not in text`, `"Seam-level edges" not in text`, `"Why N pieces" not in text`, `"spec R4 GATE-2" not in text`.
  - Positive assertion (revise-bullet-SCOPED — NOT a file-wide `in text` check): a file-wide `"references/research.md" in text` is hollow because that token already appears at SKILL.md line 67 (the Step 3 phase-reference table). Instead, iterate `text.splitlines()`, locate the line containing `` `revise` `` (the bullet), and assert that SAME line contains `references/research.md` AND `### Pieces` AND `### How they connect`. This enforces the Task 1 interface contract and closes the spec's Edge Case 2 (degenerate `revise`-bullet edit).
  - Add the new function alongside the existing tests; edit nothing existing.
- **Verification**: `just test` exits 0 with the new scoped test present and passing — pass if exit code = 0. (Requires Task 3: `test_dual_source_reference_parity.py` fails on stale discovery mirrors until then.)
- **Status**: [x] completed (commit 06413ae1)

### Task 5: Pin the decompose.md reconciliation with a regression assertion
- **Files**: `tests/test_decompose_rules.py`
- **What**: Add an assertion that the decompose.md body no longer contains the `research-phase R3` gate naming, leaving existing intentional non-emitted-heading failure-message strings untouched.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**:
  - `tests/test_decompose_rules.py` is where decompose.md heading/vocabulary assertions already live (e.g. `test_grouping_section_1_input_contract_omits_non_emitted_headings`, ~lines 371–395) — it reads the decompose.md body and runs negative assertions. Add a negative assertion `"research-phase R3" not in body` using that file's existing read pattern.
  - Do NOT modify the existing failure-message strings that intentionally name `### Integration shape`/`### Seam-level edges` (those are test scaffolding explaining what is guarded, per the spec Non-Requirements).
- **Verification**: `just test` exits 0 with the new assertion present and passing — pass if exit code = 0. (Requires Task 3: the discovery-mirror parity test must pass for the full suite to be green.)
- **Status**: [x] completed (commit d58cfd0e)

## Risks

- **Conform-down direction**: drops the `### Why N pieces` falsification gate from SKILL.md rather than restoring it to the template. If the gate is later judged a valuable structural mechanic, that is a separate change (rejected Approach B: restore to template + wire decompose to consume it) — out of scope here. Approved at spec §4.
- **decompose.md:50 scope expansion**: editing decompose.md goes beyond the ticket's original "decompose read-only" framing, but #269's own gate-removal orphans line 50, so fixing it in the same change is the dead-reference principle. Approved at spec §4.
- **Mirror-parity ordering**: `tests/test_dual_source_reference_parity.py` covers the discovery mirrors, so any `just test`-based verification fails until Task 3 regenerates the mirrors — the Phase 2 test tasks therefore depend on Task 3, not only on their respective canonical-edit tasks.
- **Deferred follow-up**: the `has_why_n_justification` event field + CLI flag + events-registry row (incl. stale `producers` column and dangling `tests/test_discovery_events.py` reference) + the real test consumer `tests/test_discovery_module.py` + the stale `tests/fixtures/discovery-brief/*` fixtures are intentionally NOT touched — a follow-up ticket to be filed at Complete.

## Acceptance

The feature is complete when: all four drifted tokens (`Integration shape`, `Seam-level edges`, `Why N pieces`, `spec R4 GATE-2`) are absent from `skills/discovery/SKILL.md`; `research-phase R3` is absent from `skills/discovery/references/decompose.md` while §3's don't-re-derive instruction survives; the `revise` bullet line itself carries the `references/research.md` §6 pointer plus `### Pieces` and `### How they connect`; both plugin mirrors are byte-identical to their canonical sources; and `just test` exits 0 with the new regression assertions (one revise-bullet-scoped test pinning SKILL.md vocabulary + the pointer + headings, one pinning decompose.md's absence of the gate naming).
