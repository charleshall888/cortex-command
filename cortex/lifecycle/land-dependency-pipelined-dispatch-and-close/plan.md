# Plan: land-dependency-pipelined-dispatch-and-close

## Overview

A prose-only change across five reference/doc files plus one new ADR: give plan authors an
ordering-only write-serialization annotation (over deletion), widen the hub-file threshold to two
writers, add a graph-width authoring rule and checklist row, fix plan.md §4's picker protocol to the
composed guard-bearing verb, surface trunk's serialization cost at both picker surfaces, and land the
dispatch-mechanics half as ADR-0031 (re-affirming ADR-0030's barrier) rather than as pipelining
prose. No wheel/code changes; the parser already tolerates the annotation dialect.

The Outline phases below are the logical decomposition; execution batches fall out of `Depends on`,
so the ADR/doc riders (Phase 3) run in the first wave alongside the Phase-1/2 leaf tasks. plan.md is
the one shared hub: Tasks 1 and 3 both edit it, so Task 3 carries an ordering-only
write-serialization edge to Task 1 (the exact tool this feature adds) rather than a fake logical
dependency — a registration seam does not apply to prose rules in a reference file.

## Outline

### Phase 1: Plan-authoring rules (tasks: 1, 2)
**Goal**: Authors gain the ordering-only annotation vocabulary, the 2-writer hub threshold, and the
graph-width rule, with the matching orchestrator checklist rows.
**Checkpoint**: `plan.md` and `orchestrator-checklist-plan.md` carry every Phase-1 anchor grep from
spec R1–R4; `just test` green.

### Phase 2: Picker surfaces (tasks: 3, 4)
**Goal**: plan.md §4 renders from the composed `cortex-lifecycle-branch-decision` payload (not the
raw verb pair), and the trunk serialization cost is visible at both §4 and implement §1 / worktree-entry.
**Checkpoint**: §4's on-main block cites the composed verb and no bare `picker-decision`; `serialize`
copy present in all three picker/entry files; `just test` green (incl.
`test_lifecycle_picker_label_pins_worktree.py`, `test_skill_section_citations.py`).

### Phase 3: Decision record and doc riders (tasks: 5, 6)
**Goal**: ADR-0031 re-affirms the batch barrier, adopts the annotation, and names the pipelining
preconditions; ADR-0030 flips to `accepted` via an in-file amendment; the stale sdk.md line is corrected.
**Checkpoint**: `cortex/adr/0031-*.md` exists, ADR-0030 is `accepted` and references ADR-0031,
sdk.md no longer says "synchronously coupled"; `just test` green (incl. `test_adr_citation_audit.py`).

## Tasks

### Task 1: plan.md authoring rules — annotation, 2-writer hub, graph-width (R1, R2, R3)
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: In the `### Authoring rules` section (:66–94), add the ordering-only write-serialization
  annotation rule (R1), restate the Hub-file seam bullet from ≥3 to any 2-writer file with the
  seam-resistant caveat (R2), and add a graph-width rule beside Straggler isolation (R3). Prose only;
  net-line target ≤ ~7 (leanification floor, #401 precedent).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Anchors — Straggler isolation :82, Hub-file seam :84 (`≥3 tasks` → any 2-writer file
  + caveat: when a registration seam can't apply — structural rework, deletions, re-pointing — the
  honest remedy is an annotated write-serialization edge), Sub-task headings :86 (its sibling remedy
  sentence "disjoint `Files`, or serialize with an explicit edge" MUST survive **in effect** —
  siblings still directed there). R1 rule states: canonical form is the parenthetical
  `**Depends on**: [12] (write-serialization: night_rig.gd)` (parser strips it via
  `cortex_command/pipeline/parser.py::_parse_field_depends_on`; a single-hyphen suffix `[12] - note`
  is NOT stripped and fails overnight conformance R4 — warn this); semantics = ordering-only
  (per-task isolation may **relax** to not-before; **no executor deletes** it; the overnight pipeline
  treats it as a **real edge**). R3 width rule names both restructure signals (a single-task level
  between multi-task levels; a level count approaching half the task count — calibrated to #358's 11
  levels / 24 tasks), the no-merge caveat (never merge tasks to shrink depth — P1 oversized-task
  tension), and the face-value/dissolve-first rule (every edge counts at face value when judging
  depth; annotated write-serialization segments are named as dissolve-first candidates). Authoring
  policy: soft positive-routing phrasing, no new MUST/CRITICAL (MUST-escalation, docs/policies.md);
  What/Why-not-How. Edit the canonical file only — `plugins/cortex-core/` mirror regenerates via the
  pre-commit hook (`tests/test_plugin_mirror_parity.py`); run `just test` **after** committing (a
  pre-commit run shows expected mirror drift, not a real failure).
- **Verification**: (b) `grep -c 'write-serialization' skills/lifecycle/references/plan.md` ≥ 1 AND
  `grep -ci 'relax' skills/lifecycle/references/plan.md` ≥ 1 AND
  `grep -cE 'no executor deletes|never delet' skills/lifecycle/references/plan.md` ≥ 1 AND
  `grep -c 'real edge' skills/lifecycle/references/plan.md` ≥ 1 AND
  `grep -c '≥3 tasks' skills/lifecycle/references/plan.md` = 0 AND
  `grep -cEi 'dissolve-first|face value|face-value' skills/lifecycle/references/plan.md` ≥ 1; then
  `just test` (green). Assembled-prose correctness (2-writer caveat reads right, width signals named)
  is a Review-phase check — no test pins reference prose.
- **Status**: [ ] pending

### Task 2: orchestrator-checklist-plan.md — P13 width row + P11 2-writer update (R4)
- **Files**: `skills/lifecycle/references/orchestrator-checklist-plan.md`
- **What**: Add row P13 (flag single-task levels between multi-task levels, or a level count
  approaching half the task count — counting every edge at face value; the flag rationale lists any
  write-serialization-annotated segments as dissolve-first candidates, never as a depth discount).
  Update P11 from the ≥3 threshold to the 2-writer threshold, its remedy wording accepting either an
  early seam task or a serializing `Depends on` chain (annotated edges qualify).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Table rows P11 :17 (`≥3 tasks' Files lists` → any file two tasks would both edit;
  remedy keeps "no early seam task and no serializing `Depends on` chain"), P12 :18 (append P13 after
  it, matching the `| # | Item | Criteria |` idiom). P13 is flag-only like P1/P11 (orchestrator may
  pass with rationale) — no computed width verb (Non-Requirement; named future upgrade). Independent
  of Task 1: this file's wording derives from spec R4, not from Task 1's output. Canonical file only
  (mirror regenerates via pre-commit hook); run `just test` after committing.
- **Verification**: (b) `grep -c 'P13' skills/lifecycle/references/orchestrator-checklist-plan.md` ≥ 1
  AND `grep -c '≥3' skills/lifecycle/references/orchestrator-checklist-plan.md` = 0; then `just test`
  (green).
- **Status**: [ ] pending

### Task 3: plan.md §4 picker protocol fix + trunk-cost copy (R5, R6a)
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: In §4 (:102–144), replace the on-main raw verb pair with the composed
  `cortex-lifecycle-branch-decision --feature {slug}` and render from its payload; drop §4's
  attribution of guard ownership to Implement §1; document the §4-self-dirtying acknowledgment and the
  two `resolved` sources with the stale-carryover rule; add the plan-conditional trunk-cost note (R6a)
  to the current-branch/trunk approval option.
- **Depends on**: [1] (write-serialization: plan.md)
- **Complexity**: simple
- **Context**: Same-file conflict with Task 1 (both edit plan.md, disjoint regions) — the annotated
  edge is ordering-only, so this task starts after Task 1's commit; it is not a logical dependency.
  Anchors — §4 attribution "Implement §1's branch-mode preflight — it owns the picker guards" :106
  (remove/re-own), on-main command block :108–111 (`cortex-lifecycle-branch-mode .` :109 +
  `cortex-lifecycle-picker-decision . {feature} {branch_mode}` :110 — both removed, replaced by the
  composed verb; these are the pair's ONLY occurrences in the file), off-main collapse :113 (unchanged
  — the composed verb does not replace it; `skip`/`source: skip` routes here), AskUserQuestion options
  :116/:120–127 (fold a config-pinned `source: branch_mode` mode into the options per ADR-0012).
  Render guards exactly as implement §1 does (:24): `uncommitted_changes` demotes only current-branch,
  `worktree_option_available=false` drops worktree only when the CLI is absent. §4-specific `resolved`
  handling by `source`: (a) `branch_mode` (config-pinned) → fold fixed mode into options; (b)
  `dispatch_choice` (stale carryover from a prior `plan_approved` row) → still render the full option
  surface with the carried mode as pre-selected default only, and authorize NO worktree auto-entry
  (ADR-0008: only a live selection at §4 authorizes `EnterWorktree`; a `dispatch_choice`-sourced
  `entry_mode: selected` is not live). Document that `dirty_tree` at §4 is expected for the
  just-written lifecycle artifacts (plan.md uncommitted until §5) and is not a worktree blocker, while
  the current-branch demotion warning still renders on any dirty tree and foreign dirt (other
  sessions') is the strongest case for isolation, not against it. R6a note: one line —
  no isolation ⇒ same-file tasks serialize and the plan must carry write-serialization edges — added
  to the current-branch/trunk option; where cheap, cite the count of write-serialization annotations
  in the just-written plan.md (orchestrator has it in hand). Pinned: `test_skill_section_citations.py`
  requires headings `### 1b. Competing Plans (Critical Only)` and `### 5. Transition` unchanged;
  zero-sweep (`test_lifecycle_event_roundtrip.py` `ZERO_SWEEP_FILES`) forbids any raw event-emission
  surface in plan.md — the composed `branch-decision`/`picker-decision` verbs are read-only picker
  reads, not emitters, so they are permitted. Canonical file only (mirror regenerates via pre-commit
  hook); run `just test` after committing. Net-line target ≤ ~7.
- **Verification**: (b) `grep -c 'cortex-lifecycle-branch-decision' skills/lifecycle/references/plan.md`
  ≥ 1 AND `grep -c 'cortex-lifecycle-picker-decision' skills/lifecycle/references/plan.md` = 0 AND
  `grep -c 'cortex-lifecycle-branch-mode' skills/lifecycle/references/plan.md` = 0 AND
  `grep -c 'serialize' skills/lifecycle/references/plan.md` ≥ 1; then `just test` (green, incl.
  `test_skill_section_citations.py`). The two-`resolved`-source distinction and stale-carryover
  wording are Review-phase prose checks.
- **Status**: [ ] pending

### Task 4: trunk-cost copy at implement §1 and worktree-entry (R6b, R6c)
- **Files**: `skills/lifecycle/references/implement.md`, `skills/lifecycle/references/worktree-entry.md`
- **What**: Add the one-line trunk-cost note (no isolation ⇒ same-file tasks serialize; plan must
  carry write-serialization edges) to implement §1's picker options block and to worktree-entry.md's
  framing.
- **Depends on**: none
- **Complexity**: simple
- **Context**: implement.md §1 picker options block is `**Picker options**:` :26 through the next
  line-start `**` boundary `**Dependency graph**:` :32; current-branch option :28. `test_lifecycle_picker_label_pins_worktree.py`
  extracts the block with `^\*\*Picker options\*\*.*?(?=^\*\*)` and requires ≥1 `- **<label>**` list
  item whose label contains `worktree` — so add the cost note as **trailing text on the current-branch
  bullet** (:28) or a non-`**`-line-start line INSIDE the block; do NOT introduce a new line-start
  `**`-prefixed line before the options (it would truncate the block regex) and do NOT alter the
  worktree option label. worktree-entry.md — ADR-0008 authorization prose lives here (:1–3 intro,
  route-on-entry-mode); add the framing where the isolation benefit is described. Kept-pause markers
  in implement.md (`implement-branch-pick` :23, `implement-batch-failure` :81) must stay
  byte-identical (`test_lifecycle_kept_pauses_parity.py`); this task adds no pause. Canonical files
  only (mirrors regenerate via pre-commit hook); run `just test` after committing. Net-line target
  ≤ ~2 per file.
- **Verification**: (b) `grep -c 'serialize' skills/lifecycle/references/implement.md` ≥ 1 AND
  `grep -c 'serialize' skills/lifecycle/references/worktree-entry.md` ≥ 1; then `just test` (green,
  incl. `test_lifecycle_picker_label_pins_worktree.py` and `test_lifecycle_kept_pauses_parity.py`).
- **Status**: [ ] pending

### Task 5: ADR-0031 + ADR-0030 amendment/promotion (R7)
- **Files**: `cortex/adr/0031-reaffirm-batch-barrier-and-ordering-only-serialization-annotation.md`,
  `cortex/adr/0030-mode-agnostic-interactive-dispatch.md`
- **What**: Create ADR-0031 that (a) re-affirms ADR-0030's batch barrier against the #358 evidence,
  graded honestly; (b) adopts the ordering-only annotation as the plan-authoring complement; (c) names
  the preconditions any future pipelining must clear; (d) promotes ADR-0030 to `accepted` via an
  in-file amendment section written into ADR-0030 itself (ADR-0004 precedent), co-promoting its Status
  field in the same commit and cross-referencing ADR-0031.
- **Depends on**: none
- **Complexity**: simple
- **Context**: ADR-0030 :1–3 frontmatter (`status: proposed` → `accepted`); append an amendment
  section after :24 that references ADR-0031 and states it co-promotes Status in the same commit —
  precedent: ADR-0004's "## Approach A resolved decisions" :43–45 ("Per the ADR-README promotion gate,
  this amendment co-promotes the ADR's Status field from `proposed` to `accepted` in the same
  commit."). Do NOT do a bare cross-file frontmatter flip. ADR-0031 body (spec §Proposed ADR is the
  source): honest evidence grading (single mid-run simulation, real durations for 12 of 24 tasks with
  placeholders concentrated in exactly the moved tasks, run 54% complete, citing artifact off-disk;
  the surviving fact is structural — one false edge cut DAG depth 11→8); mustRunAfter annotation
  semantics; preconditions list (durable per-task dispatch/completion events, metrics batch-semantics
  decision, fused per-task checkpoint+merge-back closing the stale-base window, admission policy during
  the `implement-batch-failure` pause, commit-serialization story, substrate pinnability, #39886
  mitigation, and the `plan_approved` `dispatch_choice` freshness/re-record gap — its emitter is
  name-only idempotent, so a plan-redo cannot re-record a changed choice). Frontmatter shape per
  `cortex/adr/README.md` (`status:` scalar; new ADRs land `proposed` but this one lands `accepted` on
  merge — land it `accepted` per the promotion gate since it is decided). `test_adr_citation_audit.py`
  hygiene: no `unresolved`/`slug_mismatch`/`duplicate_number`/`gap` — every `ADR-NNNN` citation must
  resolve to a filed file (0031 references 0030/0012/0008 — all exist; 0030's amendment references
  0031 — will exist), 0031 follows 0030 with no gap/duplicate.
- **Verification**: (b) `test -f cortex/adr/0031-reaffirm-batch-barrier-and-ordering-only-serialization-annotation.md`
  (exit 0) AND `grep -c '^status: accepted' cortex/adr/0030-mode-agnostic-interactive-dispatch.md` = 1
  AND `grep -c 'status: proposed' cortex/adr/0030-mode-agnostic-interactive-dispatch.md` = 0 AND
  `grep -c 'ADR-0031' cortex/adr/0030-mode-agnostic-interactive-dispatch.md` ≥ 1; then `just test`
  (green, incl. `test_adr_citation_audit.py`).
- **Status**: [ ] pending

### Task 6: correct stale sdk.md run_in_background line (R8)
- **Files**: `docs/internals/sdk.md`
- **What**: Replace the `run_in_background` row's rationale ("Interactive skill dispatch is
  synchronously coupled to the batch verify-and-merge loop") with the mode-agnostic rationale, citing
  ADR-0030.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Row at :241 in the "SDK Primitives Not Used" table (`| `run_in_background` | ... |`).
  The mode-agnostic rationale is ADR-0030's decision (dispatch mode is runtime-owned, not harness-owned;
  completion derived from the git checkpoint). Nice-to-have rider — independent of Phases 1–2. Must
  commit ⇒ simple (not trivial).
- **Verification**: (b) `grep -c 'synchronously coupled' docs/internals/sdk.md` = 0 AND
  `grep -c 'ADR-0030' docs/internals/sdk.md` ≥ 1; then `just test` (green).
- **Status**: [ ] pending

## Risks

- **Item-1 descope (dispatch mechanics does NOT land)**: the ticket's headline ask — land #401 item 2
  (pipelined dispatch) — is deliberately NOT built; it lands as ADR-0031 re-affirming the barrier. This
  was resolved at spec approval (research Open Questions; spec Non-Requirements). Surfaced again here so
  it is not a silent omission at implementation.
- **Dogfooded write-serialization edge (Task 3 ← Task 1)**: this plan uses the very annotation it
  introduces to serialize its two plan.md writers. It is safe on the current runtime (the parser strips
  the parenthetical today; every executor treats it as a real edge), and it demonstrates the intended
  pattern — but if the operator prefers, the two plan.md tasks could instead be merged into one
  (cheaper by one dispatch, at the cost of one task spanning the authoring-rules and §4-protocol
  concerns, which P1 task-sizing would flag).
- **Reference-prose growth is invisible to tests**: R1/R3/R5 acceptance is partly semantic (assembled
  sentences reading correctly); anchor greps bound it lexically but the Review phase is the real check.
  Net-line targets (≤ ~7 plan.md, ≤ ~2 per rider file) keep it inside the leanification floor.

## Acceptance

Plan authors can express same-file conflict-without-dependency via the ordering-only
write-serialization annotation (documented in plan.md with relax/never-delete/real-edge semantics and
the 2-writer hub + graph-width rules, mirrored by checklist P11/P13); plan.md §4 renders the branch
picker from the composed guard-bearing `cortex-lifecycle-branch-decision` and both picker surfaces
name trunk's serialization cost; the pipelining question is settled by an `accepted` ADR-0030 +
new ADR-0031 (barrier re-affirmed, preconditions named) and the stale sdk.md line is corrected — with
`just test` green and no wheel/code/PROTOCOL_VERSION change.
