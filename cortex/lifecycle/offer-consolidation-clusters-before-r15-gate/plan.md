# Plan: offer-consolidation-clusters-before-r15-gate

## Overview

Add a fourth response value `consolidate-pieces` to R15's option set with no detector, no new event, and no new gate. Phase 1 extends the helper module's `_RESPONSE_VALUES` frozenset and adds positive-path test coverage. Phase 2 updates three prose surfaces in lockstep: the canonical R15 option list at `decompose.md`, the closed-list summary at `SKILL.md:102`, and the parity test docstring/assertions at `test_decompose_rules.py:254`. The new bullet at `decompose.md` is the sole carrier of `consolidate-pieces`'s loop semantics (R15 has no structural loop in code); the spec mandates explicit prose for renumbering, lowest-index survival, and re-presentation.

## Outline

### Phase 1: Helper module (tasks: 1, 2)
**Goal**: `consolidate-pieces` is a valid response value in `cortex_command/discovery.py` with positive-path test coverage.
**Checkpoint**: `python3 -c "from cortex_command.discovery import _RESPONSE_VALUES; assert 'consolidate-pieces' in _RESPONSE_VALUES"` exits 0 AND `pytest tests/test_discovery_module.py -k consolidate -q` exits 0 with ≥1 test selected.

### Phase 2: Skill prose (tasks: 3, 4, 5)
**Goal**: All three prose surfaces (decompose.md R15 list, SKILL.md:102 enumeration, test_decompose_rules.py:254 parity test) document the four-option set; `decomposed.md` recording shape is documented under `## Consolidation Notes`.
**Checkpoint**: All spec Req 5–10 grep/pytest acceptances pass AND `git diff --stat bin/.events-registry.md` is empty (Req 8).

## Tasks

### Task 1: Add `consolidate-pieces` to `_RESPONSE_VALUES`
- **Files**: `cortex_command/discovery.py`
- **What**: Add the string `"consolidate-pieces"` as the eighth entry in the `_RESPONSE_VALUES` frozenset at lines 403–411. No other code changes — argparse `--response` choices at line 1323 (which derives from `sorted(_RESPONSE_VALUES)`) and `_validate_checkpoint_payload` at lines 445–465 (which checks `response in _RESPONSE_VALUES`) both pick up the new value automatically.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_RESPONSE_VALUES` is defined as `frozenset({...})` containing seven entries: `approve`, `revise`, `drop`, `promote-sub-topic`, `approve-all`, `revise-piece`, `drop-piece`. Insert `consolidate-pieces` among the R15-group entries (`approve-all`, `revise-piece`, `drop-piece`) — the existing set is gate-grouped, not alphabetic. The frozenset is the single source of truth for both validation and CLI choices.
- **Verification**: `python3 -c "from cortex_command.discovery import _RESPONSE_VALUES; assert 'consolidate-pieces' in _RESPONSE_VALUES"` — pass if exit 0.
- **Status**: [x] completed

### Task 2: Add helper-module test coverage for `consolidate-pieces`
- **Files**: `tests/test_discovery_module.py`
- **What**: Add a positive-path test asserting (a) `_validate_checkpoint_payload('topic-slug', 'decompose-commit', 'consolidate-pieces', 0)` does not raise, and (b) `emit_checkpoint_response('topic-slug', 'decompose-commit', 'consolidate-pieces', 0, repo_root)` writes a JSONL line with `"response": "consolidate-pieces"` and `"checkpoint": "decompose-commit"` to the resolved events log path. Test name should include the literal substring `consolidate` so `pytest -k consolidate` selects it.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: This is the FIRST R15-path test for `emit_checkpoint_response` in this file — the existing `test_emit_checkpoint_response_writes_jsonl_and_validates_response` at line ~176 exercises only the R4 path (`response="approve"`, `checkpoint="research-decompose"`). Use that test's structure as the structural template (fixture wiring, JSONL parse, assertion shape) but with R15 payload values. Shape: build a `tmp_path`-based `repo_root` (mirror the existing fixture); call `emit_checkpoint_response(topic, 'decompose-commit', 'consolidate-pieces', 0, repo_root)`; assert the returned path exists, read the last JSONL line, assert `event == 'approval_checkpoint_responded'`, `response == 'consolidate-pieces'`, `checkpoint == 'decompose-commit'`, `revision_round == 0`. `emit_checkpoint_response` signature: `(topic: str, checkpoint: str, response: str, revision_round: int, repo_root: Path) -> Path` from `cortex_command/discovery.py:537–559`. pytest's `pythonpath = ["."]` in `pyproject.toml:82` resolves `cortex_command` imports to the working tree — no wheel reinstall needed between Task 1 and Task 2.
- **Verification**: `pytest tests/test_discovery_module.py -k consolidate -q` — pass if exit 0 AND ≥1 test selected (pass count = collected count).
- **Status**: [x] completed

### Task 3: Update R15 option list in `decompose.md` with `consolidate-pieces` bullet and `## Consolidation Notes` recording prose
- **Files**: `skills/discovery/references/decompose.md`
- **What**: (a) Add a fourth bullet to the R15 option list at lines 104–108 documenting `consolidate-pieces <N,M,...>` with the full loop semantics per spec Req 5(a)–(f): free-text revision prompt scoped to the named subset, agent drafts merged body with prose-merged `## Why`/`## Role`/`## Integration` and unioned `## Edges`/`## Touch points`, user revises under `revise-piece` UX, lowest-index named piece survives with revised body and lands at the lowest-named slot, other named pieces are removed, surviving pieces renumber contiguously from 1, FULL renumbered batch re-presents at R15, loop continues until `approve-all` or all pieces dropped/consolidated to one. (b) Add a 2–3 sentence note at the foot of the option list documenting that `consolidate-pieces` approvals append an entry to a `## Consolidation Notes` heading in `decomposed.md` (creating the heading on first use, appending on subsequent), distinct from `## Dropped Items` (Title-keyed Markdown table for fully-rejected tickets). The note must specify the entry shape: a prose entry naming (i) which pieces merged into which surviving piece by current index, (ii) the surviving piece's revised role summary, (iii) a one-sentence rationale — matching the corpus precedent at `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md` and `cortex/research/archive/gpg-signing-claude-code-sandbox/decomposed.md`. (c) Note that the agent re-prompts on single-index invocations rather than rejecting them (per spec Edge Case). (d) Clarify the renumbering edge-case behaviors in the bullet (or in an adjacent paragraph): piece-index references in OTHER ticket bodies' `## Edges`/`## Touch points` sections are not assumed to exist by index (bodies reference contracts and files by name, not by piece-index); the merged body should re-read its own sections for literal piece-index references and rewrite if found. After a `drop-piece` on a consolidation survivor, batch renumbering proceeds as normal (no slot reclamation needed; renumbering re-runs contiguously from 1 on each round).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The R15 option list is at `skills/discovery/references/decompose.md:104–108` under the `#### Post-decompose batch-review gate (R15)` heading. Existing bullets follow the pattern `- **\`<option-name> <args>\`** — <one-paragraph semantics>`. Match this format. Do NOT modify `decompose.md:46–52` (the existing `## Consolidation Review` section); that section covers a different case (reverse-detection of research-phase merger misses) per spec Non-Requirements. The two headings (`## Consolidation Review` at line 46, the new `## Consolidation Notes` reference at line ~108) live in different surfaces (one in decompose protocol, one in the R15 bullet) but share a name-prefix — the verification grep distinguishes via the `Notes` vs `Review` suffix.
- **Verification**: `grep -c "consolidate-pieces <N,M,...>" skills/discovery/references/decompose.md` ≥ 1 AND `grep -Eo "lowest-index|renumber|re-presents" skills/discovery/references/decompose.md | sort -u | wc -l` ≥ 3 (all three anchor phrases present) AND `grep -c "## Consolidation Notes" skills/discovery/references/decompose.md` ≥ 1.
- **Status**: [x] completed

### Task 4: Update `SKILL.md:102` enumeration to include `consolidate-pieces`
- **Files**: `skills/discovery/SKILL.md`
- **What**: Update line 102's closed-list enumeration ("The gate offers `approve-all`, `revise-piece <N>`, and `drop-piece <N>` options") to include `consolidate-pieces <N,M,...>` as the fourth option. Preferred form: enumerate all four explicitly. Alternative if the line grows awkwardly long: replace the closed list with the pointer "See decompose.md §5 for the gate's full option list." Either form satisfies the acceptance.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `skills/discovery/SKILL.md:102` currently reads: "The gate offers `approve-all`, `revise-piece <N>`, and `drop-piece <N>` options and emits an `approval_checkpoint_responded` event per response. See decompose.md §5 for the gate semantics." The change preserves the "emits…event" clause and the "See decompose.md §5" clause — only the option list changes.
- **Verification**: `grep -c "consolidate-pieces" skills/discovery/SKILL.md` ≥ 1 OR `grep -c "See decompose.md" skills/discovery/SKILL.md` ≥ 1 (whichever form was chosen — both satisfy Req 9).
- **Status**: [x] completed

### Task 5: Update parity test in `test_decompose_rules.py` to cover four options
- **Files**: `tests/test_decompose_rules.py`
- **What**: Rename the existing test `test_r15_batch_review_gate_three_options_documented` (at line 254) to `test_r15_batch_review_gate_options_documented` (drop "three"). Update the docstring from "§5 documents the R15 gate's three options (approve-all/revise-piece/drop-piece)." to "§5 documents the R15 gate options including approve-all, revise-piece, drop-piece, and consolidate-pieces." Add the assertion `assert "consolidate-pieces" in body, "R15 gate must document the consolidate-pieces <N,M,...> option"` alongside the existing three assertions.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `tests/test_decompose_rules.py:254` is the existing parity test for the R15 option enumeration in `decompose.md`. It locates the relevant section via `_find_section(sections, "Create Backlog Tickets")` and asserts presence of each option's literal name in the body. The new assertion follows the existing pattern verbatim. Keep the existing assertions (`approve-all`, `revise-piece`, `drop-piece`, `user-blocking`, `FULL`) unchanged.
- **Verification**: `pytest tests/test_decompose_rules.py::test_r15_batch_review_gate_options_documented -q` — pass if exit 0; `grep -c "consolidate-pieces" tests/test_decompose_rules.py` ≥ 1.
- **Status**: [x] completed

## Risks

- **Renumbering prose ambiguity**: Task 3 introduces the renumbering contract for the first time in the R15 bullet list. The clarifications in Task 3(d) (piece-index references in OTHER bodies not assumed; no slot reclamation; standard contiguous renumbering each round) close the most common edge cases, but a multi-round consolidate-then-drop-then-consolidate scenario may still surface ambiguity at implement time. Mitigation: if the implementer notices ambiguity while writing Task 3, surface it before proceeding to Task 5.
- **`## Consolidation Notes` heading-creation prose**: First consolidation creates the heading; subsequent appends. Task 3(b) requires explicit prose covering both. The note's entry-shape spec (i/ii/iii sub-clauses) is the only enforcement surface — the agent will not have a parity test for entry shape in this lifecycle. If shape drift surfaces in practice, a follow-up backlog item should add structural test coverage.
- **Task 4 form choice**: Two acceptance forms ("enumerate four" vs "pointer to decompose.md §5") have different durability properties. The pointer form ages better if a fifth option is ever added; the enumeration form is more discoverable in isolation. Default to enumeration; switch to pointer only if the line grows awkwardly.
- **Auto-mirror plugins/cortex-core/ regeneration**: `plugins/cortex-core/skills/discovery/SKILL.md` and `plugins/cortex-core/skills/discovery/references/decompose.md` are auto-regenerated from the canonical sources by the `.githooks/pre-commit` hook (per CLAUDE.md "Auto-generated mirrors at plugins/cortex-core/{skills,hooks,bin}/ regenerate via pre-commit hook"). No manual edit of mirror files is needed; the commit hook will regenerate them. Plan correctly omits mirror files from Files lists.

## Acceptance

The whole feature is complete when a user can issue `consolidate-pieces 3,4,5` as an R15 response, the agent drafts a merged body covering pieces 3+4+5, the user approves via the existing `revise-piece`-style free-text revision loop, the merged body becomes piece 3 in a renumbered batch (with originally-4 and originally-5 removed), the FULL renumbered batch re-presents at R15, and a `## Consolidation Notes` entry appears in `decomposed.md` describing the merge. All four R15 options are documented consistently across `decompose.md`, `SKILL.md:102`, and `tests/test_decompose_rules.py:254`. No new event row, no new kept-pause, no `bin/.events-registry.md` diff.
