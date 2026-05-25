# Specification: offer-consolidation-clusters-before-r15-gate

> **Lifecycle note**: The original backlog ticket (#247) framed this as a proactive detection-driven pre-R15 pause. Research surfaced that R15 is already a loop (`revise-piece` and `drop-piece` re-present the FULL batch in the same gate session) and that only 1 of 4 R15 invocations in the corpus has ever looped. The spec below redirects the implementation to **Alternative D** from research.md — augmenting R15 with one new response value rather than introducing a new gate. The diagnosed friction (three responses for a 3-piece consolidation) is addressed at minimum cost.

## Problem Statement

When a discovery decompose produces a piece-set that includes a cluster of tickets the user wants to merge, R15's existing options (`approve-all`, `revise-piece <N>`, `drop-piece <N>`) require the user to issue the consolidation as a sequence of responses inside one R15 loop: `revise-piece <surviving>` then `drop-piece <merged-in-1>` then `drop-piece <merged-in-2>`. This is the friction the swap-daytime-autonomous-for-worktree-interactive discovery exhibited (the one R15 in the corpus that has looped). Adding a single response value `consolidate-pieces <N,M,...>` lets the user name the cluster directly in one response. The new option's bullet at `skills/discovery/references/decompose.md` parallels the loop semantics already documented for `revise-piece` and `drop-piece` — R15 has no structural loop in code; per-bullet prose at decompose.md:107–108 carries the re-presentation contract for each option, and the new bullet must independently restate that contract for `consolidate-pieces`.

## Phases

- **Phase 1: Helper module** — extend `cortex_command/discovery.py`'s `_RESPONSE_VALUES` with `consolidate-pieces` and add test coverage.
- **Phase 2: Skill prose** — update `skills/discovery/references/decompose.md` R15 option list with `consolidate-pieces <N,M,...>` and its loop semantics; add `## Consolidation Notes` recording prose; update `skills/discovery/SKILL.md:102` enumeration to four options; update the parity test docstring/assertions in `tests/test_decompose_rules.py`.

## Requirements

1. **Add `consolidate-pieces` to `_RESPONSE_VALUES`**: The frozenset at `cortex_command/discovery.py:403–411` includes a new entry `consolidate-pieces`. Acceptance: `python3 -c "from cortex_command.discovery import _RESPONSE_VALUES; assert 'consolidate-pieces' in _RESPONSE_VALUES"` exits 0. **Phase**: Helper module.

2. **Helper validation accepts `consolidate-pieces`**: `_validate_checkpoint_payload` at `cortex_command/discovery.py:445–465` accepts `response="consolidate-pieces"` for `checkpoint="decompose-commit"` without raising. Acceptance: `python3 -c "from cortex_command.discovery import _validate_checkpoint_payload; _validate_checkpoint_payload('topic-slug', 'decompose-commit', 'consolidate-pieces', 0)"` exits 0. **Phase**: Helper module.

3. **CLI argparse exposes `consolidate-pieces`**: The argparse `--response` choices at `cortex_command/discovery.py:1323` (which derives from `sorted(_RESPONSE_VALUES)`) automatically includes `consolidate-pieces`. Acceptance: `cortex-discovery emit-checkpoint-response --help 2>&1 | grep -c "consolidate-pieces"` ≥ 1. **Phase**: Helper module.

4. **Test coverage extends to `consolidate-pieces`**: `tests/test_discovery_module.py` (or the most relevant sibling test file) adds at least one positive-path test asserting `_validate_checkpoint_payload` accepts `consolidate-pieces` and that `emit_checkpoint_response` writes an event with `"response": "consolidate-pieces"`. Acceptance: `pytest tests/test_discovery_module.py -k consolidate -q` exits 0 with ≥1 test selected. **Phase**: Helper module.

5. **R15 option list documents `consolidate-pieces` with full loop semantics**: `skills/discovery/references/decompose.md` line ~107 (the bullet list of R15 options) gains a new fourth bullet describing `consolidate-pieces <N,M,...>` semantics. The bullet must explicitly state, in this order: (a) the response opens a free-text revision prompt scoped to merging pieces N,M,…; (b) the agent drafts a merged body covering the combined `## Why`, `## Role`, `## Integration` (prose merged into one piece) and union of `## Edges`, `## Touch points` bullets; (c) the user revises the draft via free text under the same UX as `revise-piece`; (d) on approval of the merged body, the lowest-index named piece survives with the revised body and the other named pieces are removed from the batch; (e) **surviving pieces renumber contiguously from 1 in the next R15 presentation** (the agent re-numbers as it presents — this is agent-context bookkeeping, not a structural property of the helper or event); (f) the FULL (now smaller, renumbered) batch re-presents at R15 and the loop continues until `approve-all` or all pieces are dropped/consolidated to one. Acceptance: a single grep checks that the bullet contains the literal `consolidate-pieces <N,M,...>` AND the canonical phrases `lowest-index`, `renumber`, and `re-presents`. Specifically: `grep -c "consolidate-pieces <N,M,...>" skills/discovery/references/decompose.md` ≥ 1, AND `grep -E "lowest-index|renumber|re-presents" skills/discovery/references/decompose.md | wc -l` ≥ 3 (three distinct anchor phrases present). **Phase**: Skill prose.

6. **Argument format documented (no helper enforcement)**: The argument to `consolidate-pieces` is a comma-separated list of piece indices (1-indexed). The R15 bullet documents the canonical form `consolidate-pieces <N,M,...>` and notes that the agent re-prompts when only a single index is named (asking "consolidate piece N with what?"). There is no helper-layer arity enforcement — the helper accepts the bare value `consolidate-pieces` per Req 1; index-handling is agent-context. Acceptance: `grep -c "consolidate-pieces <N,M,...>" skills/discovery/references/decompose.md` ≥ 1 (the prose documents the canonical multi-index form). **Phase**: Skill prose.

7. **`## Consolidation Notes` recording shape**: Consolidations are recorded under a `## Consolidation Notes` heading in `decomposed.md` — NOT under `## Dropped Items` (which is a Title-keyed Markdown table for fully-rejected tickets, per the corpus convention at `cortex/research/archive/refine-load-epic-context/decomposed.md`). The shape matches the existing `## Consolidation Note(s)` precedent at `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md` and `cortex/research/archive/gpg-signing-claude-code-sandbox/decomposed.md`: a prose entry per consolidation describing which pieces merged, what survived, and the rationale, in the agent's natural prose voice. The R15 bullet at `decompose.md` documents that on a `consolidate-pieces` approval, the agent appends an entry to `## Consolidation Notes` in `decomposed.md` (creating the heading if absent). Acceptance: `grep -c "## Consolidation Notes" skills/discovery/references/decompose.md` ≥ 1 AND the surrounding prose explicitly distinguishes the heading from `## Dropped Items`. **Phase**: Skill prose.

8. **Event reuse — no new event row**: The existing `approval_checkpoint_responded` row in `bin/.events-registry.md:116` already covers R15 emission and (verified) does not enumerate the closed list of response values in its description, so adding a new response value is invisible to the registry row. Acceptance: `git diff --stat bin/.events-registry.md` is empty after Phase 1 + Phase 2 commits. **Phase**: Skill prose (verification at end of phase).

9. **`skills/discovery/SKILL.md:102` enumeration updated**: The SKILL.md prose at line 102 currently reads "The gate offers `approve-all`, `revise-piece <N>`, and `drop-piece <N>` options" — a closed three-option list. After this feature ships, SKILL.md must reflect the fourth option. Resolution: update the SKILL.md line to either (a) enumerate all four (`approve-all`, `revise-piece <N>`, `drop-piece <N>`, `consolidate-pieces <N,M,...>`) OR (b) replace the closed list with an authoritative pointer ("see decompose.md §5 for the full option list"). Acceptance: `grep -c "consolidate-pieces" skills/discovery/SKILL.md` ≥ 1 OR `grep -c "see decompose.md" skills/discovery/SKILL.md` ≥ 1 (whichever form is chosen). **Phase**: Skill prose.

10. **`tests/test_decompose_rules.py:254` parity test updated**: The existing test `test_r15_batch_review_gate_three_options_documented` has a docstring stating "§5 documents the R15 gate's three options" and three assertions. Rename to `test_r15_batch_review_gate_options_documented` (drop "three"), update docstring to "§5 documents the R15 gate options including approve-all, revise-piece, drop-piece, and consolidate-pieces," and add an assertion `"consolidate-pieces" in body`. Acceptance: `pytest tests/test_decompose_rules.py::test_r15_batch_review_gate_options_documented -q` exits 0; `grep -c "consolidate-pieces" tests/test_decompose_rules.py` ≥ 1. **Phase**: Skill prose.

## Non-Requirements

- No detector or signal-detection logic — `consolidate-pieces` is invoked by the user, who names the cluster directly. Spec does not commit to "skip silently when no candidates" because there are no candidates to detect.
- No new `AskUserQuestion` site — the new response value lives within the existing R15 surface.
- No new kept-pauses inventory entry — there is no new pause to inventory.
- No discovery-side parity test for kept-pauses — D does not add a pause and therefore does not exercise the parity-coverage gap (which remains a real but orthogonal follow-up).
- No new event row in `bin/.events-registry.md` — reuse `approval_checkpoint_responded`.
- No changes to the existing `## Consolidation Review` section at `skills/discovery/references/decompose.md:46–52` — that section covers a different case (reverse-detection of research-phase merger misses) and stays as-is.
- No changes to `skills/discovery/references/research.md` R3 falsification gate — Alternative E (tighten R3 upstream) remains a valid complementary follow-up but is out of scope for this ticket.
- No threshold or piece-count gating — D fires when the user invokes it, not on a count.
- No proactive surfacing of merge candidates by the agent — the user notices and names.
- No helper-layer enforcement of the index-list shape — index handling is agent-context bookkeeping, not a structural validation surface.

## Edge Cases

- **Single-index invocation** (`consolidate-pieces 3`): The agent re-prompts ("consolidate piece 3 with what?") and does not invoke `cortex-discovery emit-checkpoint-response` until a valid multi-index list is provided. Not a malformed-rejection — natural-language clarification.
- **Repeated indices** (`consolidate-pieces 3,3,4`): Agent dedupes silently, treats as `consolidate-pieces 3,4`. Agent-context bookkeeping; helper sees only the bare value.
- **Invalid index** (`consolidate-pieces 99` when there are 5 pieces): Agent flags the out-of-range index, asks the user to correct, and re-presents R15 without invoking the helper.
- **All pieces named** (`consolidate-pieces 1,2,3,4,5` on a 5-piece set): Produces a single merged piece. The other four are removed; R15 re-presents the 1-piece (renumbered as piece 1) batch.
- **Consecutive `consolidate-pieces` invocations**: Each invocation re-presents the full (now smaller) batch with pieces renumbered contiguously from 1; the user can issue another `consolidate-pieces` on the new batch using the new indices. Renumbering is agent-context bookkeeping — the agent re-numbers as it composes the next R15 presentation.
- **`consolidate-pieces` after `drop-piece`**: Drop runs first, batch re-presents with surviving pieces renumbered 1..K; then `consolidate-pieces` operates on the new 1..K indices.
- **LEX-1 scanner on merged body**: The agent's drafted merged body must pass `bin/cortex-check-prescriptive-prose` like any other ticket body. The free-text revision loop is the same as `revise-piece`'s — if the user's revision violates LEX-1, the scanner flags it and the agent re-walks the body. Existing R15 behavior, not new.
- **`## Consolidation Notes` heading absent in `decomposed.md`**: First consolidation creates the heading; subsequent consolidations append under it.

## Changes to Existing Behavior

- **MODIFIED** `cortex_command/discovery.py:403–411`: `_RESPONSE_VALUES` grows from 7 entries to 8 entries (adds `consolidate-pieces`). Validation downstream of `_RESPONSE_VALUES` automatically accepts the new value without further code changes.
- **MODIFIED** `cortex_command/discovery.py:1323`: argparse `--response` choices list grows by one entry via `sorted(_RESPONSE_VALUES)`.
- **MODIFIED** `skills/discovery/references/decompose.md:104–108`: R15 option list grows from three bullets to four; new bullet documents `consolidate-pieces <N,M,...>` per Requirement 5.
- **MODIFIED** `skills/discovery/references/decompose.md`: adds prose documenting that consolidations record under a `## Consolidation Notes` heading in `decomposed.md`, distinct from `## Dropped Items` (Requirement 7).
- **MODIFIED** `skills/discovery/SKILL.md:102`: closed-list enumeration of three options updated per Requirement 9 (either four-option enumeration or pointer to decompose.md).
- **MODIFIED** `tests/test_decompose_rules.py:254`: parity test renamed and assertions extended per Requirement 10.
- **ADDED** to `tests/test_discovery_module.py` (or sibling): at least one test exercising `consolidate-pieces` per Requirement 4.

## Technical Constraints

- The helper module's `_RESPONSE_VALUES` frozenset is the single source of truth for accepted response values — both the validation function and the argparse subcommand derive from it. Adding the new value once propagates to both surfaces.
- `bin/cortex-check-events-registry` (project.md:41 architectural constraint) does not require updates because no new event name is introduced. The registry row's description does not enumerate response values; this is the contingent reason the row is unchanged, not an architectural inevitability of event-name reuse.
- `bin/cortex-check-parity` (project.md:33 architectural constraint) verifies SKILL.md ↔ bin script parity. Requirement 9 updates SKILL.md to keep this parity intact; without Req 9, the SKILL.md ↔ decompose.md option-list would silently drift.
- `bin/cortex-check-prescriptive-prose` (LEX-1 scanner) runs on the merged body produced inside the free-text revision loop. The constraint that `## Why`, `## Role`, `## Integration`, `## Edges` are forbidden sections for path:line / section-index / multi-line-fenced patterns applies to the merged body unchanged.
- The 500-line SKILL.md size cap (project.md:34) has ample headroom: SKILL.md is 114 lines, decompose.md is 175 lines; the change adds ≤15 lines total across both.
- The R15 "loop" lives entirely in per-bullet prose at `decompose.md:104–108` — there is no helper-level loop control. The new bullet must independently restate re-presentation and loop continuation (Req 5(f)) because it is the only enforcement surface for those semantics on the new option.

## Open Decisions

None. All design questions were resolved in the research phase or by orchestrator call in this spec.

## Proposed ADR

None considered. The change is a small additive modification to an existing surface; no architectural decision rises to the three-criteria gate (hard-to-reverse + surprising + real trade-off).
