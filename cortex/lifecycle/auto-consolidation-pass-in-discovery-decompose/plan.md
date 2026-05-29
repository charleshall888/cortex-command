# Plan: auto-consolidation-pass-in-discovery-decompose

## Overview

Make `/discovery` decompose §4 group tightly-coupled research pieces into single backlog tickets (M pieces → 1 ticket) using the emitted Architecture content, before bodies are drafted, and add a `split-piece <N>` re-derivation at the R15 gate. The change is concentrated in `skills/discovery/references/decompose.md` (prose), one frozenset line in `cortex_command/discovery.py`, the `SKILL.md` gate inventory, an ADR, and the discovery test suite. No new event type and no new `bin/` script (so the events-registry row and the `cortex-check-parity` gate need no edits). **Gate note:** editing `skills/discovery/*` triggers the pre-commit dual-source drift hook, which runs `just build-plugin` to regenerate the byte-identical `plugins/cortex-core/skills/discovery/*` mirrors — those regenerated mirrors must be staged in the same commit (the `/cortex-core:commit` flow + hook handle regeneration; the implementer stages them). Phase 1 delivers grouping; Phase 2 delivers the split undo — the feature is not shippable until both land.

## Outline

### Phase 1: §4 grouping (tasks: 1, 2, 3, 4)
**Goal**: decompose §4 groups coupled pieces into single tickets before drafting; the §1/§2/§3/Constraints input-contract and invariant are reconciled to the emitted Architecture content; grouped-body authoring + intra-group ordering are preserved and recorded in `decomposed.md`; ADR 0007 written.
**Checkpoint**: `decompose.md` is internally consistent (§1/§2/§4 all describe reading the emitted Architecture content; §4 groups; §3 distinguishes wrong-set from over-split; `## Grouping Notes` in §6); ADR 0007 exists; `tests/test_decompose_rules.py` substantively asserts the grouping prose; `just test` exits 0.

### Phase 2: R15 split re-derivation (tasks: 5, 6, 7)
**Goal**: `split-piece` is a valid R15 response value, documented in decompose.md R15 + SKILL.md as re-derivation from the retained Architecture source, with tests in the established suite.
**Checkpoint**: `grep -c '"split-piece"' cortex_command/discovery.py` = 1; R15 prose + SKILL.md inventory name `split-piece` and describe re-derivation from the Architecture source; `tests/test_discovery_module.py` + `tests/test_decompose_rules.py` cover the new option + validation; `just test` exits 0.

## Tasks

### Task 1: Write ADR 0007 (decompose groups pieces into tickets)
- **Files**: `cortex/adr/0007-decompose-groups-pieces-into-tickets.md`
- **What**: Create ADR 0007 capturing the decision to auto-group pieces at decompose §4 (reversing the implicit 1:1 contract and #247's user-driven posture), transcribing the spec's `## Proposed ADR` section into the repo's ADR format.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Follow the format of existing ADRs (e.g. `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md`) and the three-criteria gate + consumer rules in `cortex/adr/README.md` (enforcement is prose-only/PR-review — no automated link gate, and project.md does not register every ADR, so no index edit is required). Source content is the `## Proposed ADR: 0007-decompose-groups-pieces-into-tickets` block in `…/spec.md` (context, decision, trade-off, alternatives A/B rejected, residual anchoring risk). Status: Accepted. Cross-reference #268 and #247.
- **Verification**: `test -f cortex/adr/0007-decompose-groups-pieces-into-tickets.md && grep -c "decompose" cortex/adr/0007-decompose-groups-pieces-into-tickets.md` ≥ 1 — pass if file exists and matches; AND `just test` exits 0 (pass if exit code = 0).
- **Status**: [x] complete

### Task 2: Rewrite decompose.md §1/§2/§3/§4 + Constraints for grouping (incl. input-contract reconciliation)
- **Files**: `skills/discovery/references/decompose.md` (canonical; the `plugins/cortex-core/skills/discovery/references/decompose.md` mirror regenerates via the pre-commit `just build-plugin` hook and is staged at commit time)
- **What**: Rewrite §4 "Determine Grouping" to group tightly-coupled pieces into single tickets for `piece_count ≥ 2`; AND make decompose.md internally consistent about its input contract — §1 "Load Context" (line ~9) and the §2 Dependencies bullet (line ~44) currently name `### Integration shape`/`### Seam-level edges` as the source-of-truth input and dependency source, headings the research template does NOT emit. Reconcile §1, §2 (both the "each bullet is a piece" sentence ~line 13 AND the Dependencies bullet ~line 44), §3 (distinguish a *wrong* piece-set → return to research from a *right-but-over-split* set → §4 grouping), §4, and the Constraints "Architecture-section-driven" bullet so they all describe reading the *emitted* Architecture content (`### Pieces` + `### How they connect`) and derive dependencies from it. Add a back-pointer to ADR 0007.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Edit sites in `decompose.md`: §1 (line ~9, "source-of-truth input"), §2 (line ~13 "each bullet … becomes one ticket candidate" AND line ~44 "Dependencies: From the Integration shape and Seam-level edges sub-sections"), §3 "Consolidation Review" (lines ~46–52), §4 "Determine Grouping" (lines ~54–74), Constraints bullet (line ~173). This makes decompose.md *internally* consistent; it does NOT fix the upstream `research.md` template (the deferred drift per spec Non-Requirements). Express grouping as decision-criteria + output-shape per spec R1 — name the inferred coupling indicators (shared connection seam, one integration cluster, near-identical role, value-only-when-shipped-together) drawn from the emitted sub-sections. Soft positive-routing phrasing (MUST-escalation policy). The epic+children branch keeps "one ticket per *group*".
- **Verification**: differential + test — `grep -c "becomes one ticket candidate" skills/discovery/references/decompose.md` = 0 (old 1:1 wording removed) AND `grep -c "From the Integration shape and Seam-level edges" skills/discovery/references/decompose.md` = 0 (the §2 dependency-source line reconciled) AND `grep -nE "How they connect" skills/discovery/references/decompose.md` returns a hit in the §1/§4 input-contract region; AND `just test` exits 0 (Task 4's test asserts the semantic content).
- **Status**: [x] complete

### Task 3: decompose.md §5/§6 grouped-body authoring + Grouping Notes + edge cases
- **Files**: `skills/discovery/references/decompose.md` (mirror regenerates via build-plugin hook, staged at commit)
- **What**: Update §5 to author one merged body per grouped ticket (prose-merge Why/Role/Integration; union/dedup Edges/Touch points — mirroring the R15 `consolidate-pieces` convention) and state the Architecture `### Pieces` source is retained unchanged; add `## Grouping Notes` to §6 recording group membership + one-sentence rationale + surviving intra-group ordering; add the edge cases (all-pieces-group-to-one, no-coupling fallback, intra-group ordering preserved-not-dissolved).
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Edit `decompose.md` §5 "Create Backlog Tickets" (lines ~75–98; the R15 sub-section is Task 6's), §6 "Write Decomposition Record" (lines ~129–153). `## Grouping Notes` parallels the existing `## Consolidation Notes` / `## Dropped Items` headings. Intra-group ordering: when grouped pieces had `blocked-by` among themselves, record it as an explicit intra-ticket sequence note (mirror the "internal phase boundary" precedent at `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md`), per spec R5.
- **Verification**: differential + test — `grep -c "Grouping Notes" skills/discovery/references/decompose.md` ≥ 1 (new §6 heading) AND `grep -nE "retain|unchanged" skills/discovery/references/decompose.md` shows the §5 retained-Architecture-source note AND `grep -nE "prose-merge|union" skills/discovery/references/decompose.md` shows the merge-convention reference in §5; AND `just test` exits 0 (Task 4's test asserts §5/§6 content).
- **Status**: [x] complete

### Task 4: Add substantive §1–§6 grouping tests
- **Files**: `tests/test_decompose_rules.py`
- **What**: Add tests asserting the *semantic* content of Tasks 2–3, not just keyword presence: (a) §4 "Determine Grouping" names grouping criteria; (b) §2 NO LONGER contains "becomes one ticket candidate" (negative assertion proving the 1:1 rewrite landed); (c) decompose.md does not name `### Integration shape`/`### Seam-level edges` as the source-of-truth input (input-contract reconciled — assert those tokens are absent from the §1 input-contract sentence); (d) §3 distinguishes the wrong-set (return-to-research) case from the over-split (§4 grouping) case; (e) §6 contains `## Grouping Notes` and §5 references the merge convention.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Follow the existing section-aware patterns in `tests/test_decompose_rules.py` — the `_parse_sections` helper splits on `##`/`### N.` headings; existing tests use `assert "<literal>" in section_body` and negative `assert "<literal>" not in body`. Use the negative-assertion idiom for (b)/(c) so the tests catch a *missing* edit, not just a present keyword. Section-scope assertions to the relevant section body (not the whole file) so pre-existing occurrences elsewhere don't mask a missing edit.
- **Verification**: `grep -cE "def test_.*grou(p|ping)" tests/test_decompose_rules.py` ≥ 1 AND `grep -c "not in" tests/test_decompose_rules.py` increased over baseline (the negative assertions exist) AND `just test` exits 0 — pass if the new substantive tests exist and the suite is green.
- **Status**: [x] complete

### Task 5: Add `split-piece` to discovery.py `_RESPONSE_VALUES`
- **Files**: `cortex_command/discovery.py`
- **What**: Add the string `"split-piece"` to the `_RESPONSE_VALUES` frozenset so it is an accepted R15 response value; `--response` argparse choices and validation auto-derive.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `cortex_command/discovery.py:403–412` defines `_RESPONSE_VALUES = frozenset({...})`; add one entry. Confirmed sole consumers: the frozenset def (403), validation (`if response not in _RESPONSE_VALUES`, 458–460), and argparse `choices=sorted(_RESPONSE_VALUES)` (1324) — all in this file; no other reader and no test hard-codes the full set, so the auto-derivation holds. No new event type or checkpoint value (spec R8).
- **Verification**: `grep -c '"split-piece"' cortex_command/discovery.py` = 1 — pass if exactly one occurrence in the frozenset; AND `just test` exits 0.
- **Status**: [x] complete

### Task 6: Document `split-piece <N>` in decompose.md R15 + SKILL.md inventory
- **Files**: `skills/discovery/references/decompose.md`, `skills/discovery/SKILL.md` (both mirrors regenerate via the build-plugin hook, staged at commit)
- **What**: Add `split-piece <N>` to the R15 gate option list in decompose.md and the gate-option inventory in SKILL.md: it re-derives a previously-grouped ticket back into its constituent pieces by re-authoring each piece's body from the retained Architecture `### Pieces` source (per Task 3's retained-source note), restores recorded intra-group ordering, re-presents the FULL renumbered batch, is non-destructive (nothing committed until `approve-all`), and re-prompts naturally on a non-grouped target.
- **Depends on**: [3, 5]
- **Complexity**: simple
- **Context**: `decompose.md` R15 sub-section under §5 (lines ~100–115) lists `approve-all`/`revise-piece`/`drop-piece`/`consolidate-pieces`; add `split-piece <N>` mirroring their format. `SKILL.md` R15 gate option inventory (line ~102). Emphasize re-derivation FROM the Architecture source (NOT reconstruction from the lossy merged body). Reuses `approval_checkpoint_responded` with `checkpoint: decompose-commit` and `response: split-piece` (Task 5 added the value).
- **Verification**: `grep -c "split-piece" skills/discovery/references/decompose.md` ≥ 1 AND `grep -c "split-piece" skills/discovery/SKILL.md` ≥ 1 AND `grep -nE "from the .*Architecture|retained Architecture|not .*merged body" skills/discovery/references/decompose.md` shows the re-derivation-source semantics in the R15 prose; AND `just test` exits 0 (Task 7 asserts the R15 option + semantics).
- **Status**: [x] complete

### Task 7: Tests for `split-piece` (R15 option + helper validation) in the established suites
- **Files**: `tests/test_decompose_rules.py`, `tests/test_discovery_module.py`
- **What**: Extend the R15-options test in `test_decompose_rules.py` to include `split-piece` AND assert the R15 prose describes re-derivation from the Architecture source; and in `tests/test_discovery_module.py` add a positive-path test (mirroring `test_emit_checkpoint_response_accepts_consolidate_pieces_at_decompose_commit`) asserting the validator accepts `response="split-piece"`, `checkpoint="decompose-commit"` and emits `approval_checkpoint_responded` with no new event literal.
- **Depends on**: [4, 5, 6]
- **Complexity**: simple
- **Context**: NOTE — the real `emit_checkpoint_response` tests live in `tests/test_discovery_module.py` (NOT `tests/test_discovery_events.py`, which does not exist — the events-registry consumer column lists a stale path). Mirror `test_emit_checkpoint_response_accepts_consolidate_pieces_at_decompose_commit` (tests/test_discovery_module.py:216) and `test_emit_checkpoint_response_writes_jsonl_and_validates_response` (:176). `emit_checkpoint_response` is at `cortex_command/discovery.py` ~538–560. Update `test_r15_batch_review_gate_options_documented` (test_decompose_rules.py ~254–261) to include `split-piece`.
- **Verification**: `grep -c "split-piece" tests/test_decompose_rules.py` ≥ 1 AND `grep -c "split-piece" tests/test_discovery_module.py` ≥ 1 AND `just test` exits 0 — pass if both established suites reference split-piece and the suite is green.
- **Status**: [x] complete

## Risks

- **§4-yield is intentionally bounded**: §4 groups only gross, architecture-visible over-splitting (pre-draft content only); subtle body-level couplings stay with the manual `consolidate-pieces` fallback. If §4 rarely fires, the feature's value is thinner than hoped (critical review flagged this). Accepted per the operator's reported recurring pain.
- **Anchoring residual**: a pre-filled grouping the operator rubber-stamps at R15 is a wrong merge expensive to fully reverse; mitigated (not eliminated) by per-group rationale + `split-piece` re-derivation. Documented in ADR 0007.
- **Upstream heading drift left unfixed (research.md template only)**: Task 2 makes *decompose.md* internally consistent (its §1/§2/§4 read the emitted `### How they connect`), but the `research.md` template still emits `### How they connect` while `SKILL.md`'s "Why N pieces" gate vocabulary names `### Integration shape`/`### Seam-level edges`. Reconciling the research-template/SKILL.md vocabulary repo-wide is the deferred follow-up (candidate ticket); this plan scopes the fix to decompose.md's own consistency.

## Acceptance

`/discovery` decompose, given a research Architecture with ≥2 tightly-coupled pieces, groups them into fewer tickets at §4 (M pieces → 1 ticket) before bodies are drafted, records the grouping + intra-group ordering in `decomposed.md`'s `## Grouping Notes`, and offers `split-piece <N>` at R15 to re-derive a wrongly-grouped ticket from the retained Architecture source. decompose.md is internally consistent about its input contract (§1/§2/§4 read the emitted Architecture content), `grep -c '"split-piece"' cortex_command/discovery.py` = 1, decompose.md/SKILL.md document the affordance, ADR 0007 exists, the substantive tests in `tests/test_decompose_rules.py` + `tests/test_discovery_module.py` pass, and `just test` exits 0.
