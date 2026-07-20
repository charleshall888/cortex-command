# Specification: land-dependency-pipelined-dispatch-and-close

## Problem Statement

Plan authors have no correct tool for "these tasks conflict on a file but are not dependent": the
only sanctioned remedies are disjoint `Files` or a fake `Depends on` edge, the guidance offering
them (`plan.md:86`) is textually scoped to same-batch sub-task siblings and gets over-generalized,
and the hub-file seam rule starts at ≥3 writers — so wild-light #358's author serialized two
independent phases with a non-logical edge (16 ← 12), collapsing graph width (24 tasks stretched
across 11 levels). Compounding it, the plan-approval picker protocol (plan.md §4) calls raw verbs
whose output cannot populate the rendering guards §4 claims are owned elsewhere, and fires
`dirty_tree` structurally (plan.md is always uncommitted at approval) — which invited #358's
session to wrongly conclude "worktree unavailable" and force trunk mode (the model had the
availability probe and still misread; an explicit guard payload reduces that failure mode, it
cannot eliminate it). The ticket's remaining
ask — land #401 item 2 (pipelined dispatch) — is **not** supported by the evidence: the 142/135/99
simulation is majority-placeholder in exactly the moved tasks, and every ADR-0030 blocker is still
live; that half lands as a decision record (ADR-0031) re-affirming the barrier with named
preconditions, not as dispatch prose. Benefits: plan authors get an honest, parser-compatible
vocabulary; approval surfaces stop steering operators into trunk mode blind; the pipelining
question gets a durable, evidence-graded answer instead of a third re-litigation.

## Phases

- **Phase 1: Plan-authoring rules** — give authors the ordering-only annotation, widen the
  hub-file guidance, and add graph-shape checks.
- **Phase 2: Picker surfaces** — fix plan.md §4's protocol defect and surface the trunk-mode
  serialization cost at both choice points.
- **Phase 3: Decision record and doc riders** — ADR-0031 and the stale-doc correction.

## Requirements

1. **Write-serialization edge annotation (ordering-only semantics)**: `plan.md`'s authoring rules
   gain a rule: when an edge exists only to serialize same-file writes (not a logical
   dependency), annotate it in the parenthetical dialect the parser already strips — canonical
   form `**Depends on**: [12] (write-serialization: night_rig.gd)` — with stated semantics:
   ordering-only (an executor running per-task isolation may relax it to not-before; no executor
   deletes it; the overnight pipeline treats it as a real edge). The rule shows the canonical form
   and warns that a single-hyphen suffix (`[12] - note`) fails overnight conformance (R4).
   Acceptance: `grep -c 'write-serialization' skills/lifecycle/references/plan.md` ≥ 1, AND the
   rule's text carries all three semantic anchors — a relax clause (`grep -ci 'relax'` ≥ 1), a
   never-delete clause (`grep -cE 'no executor deletes|never delet'` ≥ 1), and the real-edge
   clause (`grep -c 'real edge'` ≥ 1) — in plan.md's authoring rules; the sub-task-sibling remedy
   sentence at plan.md:86 survives in effect (siblings still directed to disjoint `Files` or an
   explicit edge); `just test` green. (Anchor greps bound the semantics lexically; the review
   phase verifies the assembled sentence reads correctly — prose semantics have no test.)
   **Phase**: Phase 1
2. **Hub-file guidance at two writers**: restate the hub-file seam rule (plan.md:84) from "≥3
   tasks" to fire on any file two tasks would both edit, staying authoring guidance (never a
   gate), and add the seam-resistant caveat: when a registration seam cannot apply (structural
   rework, deletions, re-pointing), the honest remedy is an annotated write-serialization edge.
   Acceptance: the Hub-file seam bullet names the 2-writer trigger and the caveat; `grep -c '≥3
   tasks' skills/lifecycle/references/plan.md` = 0. **Phase**: Phase 1
3. **Graph-width authoring rule**: `plan.md` gains a width rule beside Straggler isolation: prefer
   wide levels; treat as restructure signals any single-task level between multi-task levels and a
   level count approaching half the task count (calibrated to the motivating case — #358 ran 11
   levels for 24 tasks); never merge tasks to shrink depth (P1 oversized-task tension named).
   Every edge counts at face value when judging depth — an annotated write-serialization edge
   serializes identically today; annotated segments are instead named as the dissolve-first
   candidates (restructure the plan, or choose isolated dispatch at approval) because they are the
   edges isolation could remove. Acceptance: a width bullet exists in plan.md's authoring rules
   naming both signals, the no-merge caveat, and the face-value/dissolve-first rule. **Phase**:
   Phase 1
4. **Checklist rows**: `orchestrator-checklist-plan.md` gains P13 (flag a plan with single-task
   levels between multi-task levels, or a level count approaching half its task count — counting
   every edge at face value; the flag rationale lists any write-serialization-annotated segments
   as dissolve-first candidates, never as a discount on the measured depth), and P11 is updated to
   the 2-writer threshold with its remedy wording accepting either an early seam task or a
   serializing `Depends on` chain (annotated edges qualify). Acceptance: `grep -c 'P13'
   skills/lifecycle/references/orchestrator-checklist-plan.md` ≥ 1; P11 row no longer says `≥3`.
   **Phase**: Phase 1
5. **Plan §4 picker protocol fix**: replace §4's on-main raw verb pair
   (`cortex-lifecycle-branch-mode`, `cortex-lifecycle-picker-decision`) with the composed
   `cortex-lifecycle-branch-decision --feature {slug}` and render from its payload: apply
   `uncommitted_changes` (demote current-branch) and `worktree_option_available` (drop worktree
   only when the CLI is absent) exactly as implement §1 does. §4-specific state handling, by
   `source`: (a) `resolved`/`source: branch_mode` (config-pinned) — fold the fixed mode into the
   approval options per ADR-0012; (b) `resolved`/`source: dispatch_choice` — a **stale carryover**
   from a prior approval pass (the verb consults any existing `plan_approved` row before config or
   the picker gate): it never suppresses the option surface (§4 IS the approval surface — render
   the full option set with the carried mode as pre-selected default) and never authorizes
   worktree auto-entry (per ADR-0008, only a live selection at this surface does; a
   `dispatch_choice`-sourced `entry_mode: selected` at §4 is not a live selection); (c) `skip`
   (off-main, no `branch_mode` in payload) — route to §4's existing off-main collapse branch,
   which the composed verb does not replace. Document in-prose that `dirty_tree` at §4 is expected
   **for the just-written lifecycle artifacts** (plan.md is uncommitted until §5) and is not a
   worktree blocker — while the current-branch demotion warning still renders whenever the tree is
   dirty, and dirt beyond the feature's own artifacts (other sessions') is called out as the
   strongest case for isolation, not a reason to avoid it. Acceptance: §4's on-main command block
   contains `cortex-lifecycle-branch-decision` and no bare `cortex-lifecycle-picker-decision`; §4
   no longer attributes guard ownership to Implement §1; §4's text distinguishes the two
   `resolved` sources and names the stale-carryover rule; `just test` green (incl.
   `test_skill_section_citations.py`). **Phase**: Phase 2
6. **Trunk-cost tradeoff copy at both surfaces**: one-line cost note — no isolation means
   same-file tasks serialize and the plan must carry write-serialization edges — added to (a) the
   §4 approval surface's current-branch/trunk option, (b) implement §1's picker options block, and
   (c) `worktree-entry.md`'s framing. At §4 the note is plan-conditional where cheap: when the
   just-written plan.md contains write-serialization annotations, cite their count in the note
   (the orchestrator has plan.md in hand), so the nudge is strongest exactly on #358-shaped plans.
   Acceptance: `grep -l 'serialize'` matches all three files at the picker/entry prose;
   `tests/test_lifecycle_picker_label_pins_worktree.py` still passes (options keep the bold-label
   shape with a worktree label). **Phase**: Phase 2
7. **ADR-0031**: new ADR `cortex/adr/0031-*.md` that (a) re-affirms ADR-0030's batch barrier
   against the #358 evidence, grading that evidence honestly (single mid-run simulation, 12/24
   real durations, run 54% complete, citing artifact off-disk; the surviving fact is structural —
   one false edge cut DAG depth 11→8); (b) adopts the ordering-only annotation as the
   plan-authoring complement; (c) names the preconditions any future pipelining must clear
   (durable per-task dispatch/completion events, metrics batch-semantics decision, fused per-task
   checkpoint+merge-back closing the stale-base window, admission policy during the
   `implement-batch-failure` pause, a commit-serialization story, substrate pinnability, #39886
   mitigation, and — surfaced by this spec's own review — a freshness/re-record story for
   `plan_approved`'s `dispatch_choice`, whose emitter is idempotent on event name only, so a
   plan-redo pass can never re-record a changed choice); and (d) promotes ADR-0030 to `accepted`
   via the ADR-0004 precedent: an in-file amendment section written into ADR-0030 itself,
   co-promoting its Status field in the same commit and cross-referencing ADR-0031 — not a bare
   cross-file frontmatter flip. Acceptance: ADR-0031 file exists; ADR-0030 status is `accepted`
   AND contains an amendment section referencing ADR-0031; `tests/test_adr_citation_audit.py`
   passes. **Phase**: Phase 3
8. **Stale sdk.md line**: correct `docs/internals/sdk.md`'s `run_in_background` row (~:241) from
   "Interactive skill dispatch is synchronously coupled to the batch verify-and-merge loop" to the
   mode-agnostic rationale, citing ADR-0030. Nice-to-have rider: dropping it does not affect
   Phases 1–2. Acceptance: `grep -c 'synchronously coupled' docs/internals/sdk.md` = 0.
   **Phase**: Phase 3

## Non-Requirements

- **No dispatch-mechanics change**: the batch barrier stays; no in-flight Files-disjointness gate,
  no pipelined dispatch, no per-task dispatch/completion events, no `implement.md` §2 semantics
  change. (The ticket's item 1 as literally written — deliberately descoped on the evidence;
  ADR-0031 owns the preconditions. Research Alternative B rejected: overnight executor consumes
  the same plans gateless, mutex ≠ ordering, prose-TOCTOU.)
- **No wheel/code changes**: `should_fire_picker`, `branch_decision.py`, the `REASONS` frozenset,
  `pipeline/parser.py`, and the overnight executor are untouched; no new events, no
  PROTOCOL_VERSION bump.
- **No `Conflicts:`/pool field** — held in reserve for genuine non-file shared resources.
- **No computed width-lint verb** — P13 is orchestrator-applied; a verb is the named future
  upgrade if P13 misses in practice.
- **No scoped dirty-tree attribution** (own-feature vs foreign paths) — closed API surface, its
  own spec cycle if ever.
- **No #39886 mitigation** — pre-existing, tracked outside; this change adds no reliance on
  "isolation is in effect" today, and the annotation's forward relaxation clause stays
  precondition-gated behind ADR-0031 (which lists #39886 mitigation among its named
  preconditions) — a deferred dependency made explicit, not an eliminated one.
- **No `merge-back.md` change** — its per-batch ordering assumptions remain valid while the
  barrier stays.
- **No backlog #404 body rewrite** — the ADR corrects the evidentiary record; the ticket stays as
  filed.

## Edge Cases

- **Annotation written in a non-tolerated dialect** (single hyphen): overnight conformance R4
  fails the feature — the plan.md rule shows the canonical parenthetical form and names this
  failure mode explicitly.
- **Plan executed by an older skill/CLI snapshot**: annotated edges are ordinary `Depends on`
  edges to every executor (annotation strips at parse; no executor relaxes today) — conservative
  in both directions; no version-skew hazard.
- **Cycle detection**: an annotated edge is still an edge — implement §2's cycle check and
  topological batching are unaffected.
- **`dirty_tree` at §4 with genuinely foreign dirt** (the #358 shape — other sessions'
  uncommitted files): the composed verb demotes current-branch with the warning and keeps worktree
  offered; the new tradeoff copy makes the serialization cost visible at the moment of choice.
- **§4 `resolved` state, `source: branch_mode`** (repo config pins a mode): the fixed mode folds
  into the approval options rather than rendering a picker — matching ADR-0012's propagation.
- **§4 `resolved` state, `source: dispatch_choice`** (a prior `plan_approved` row exists — the
  plan-redo case): treated as stale carryover per R5(b) — full option surface still renders, the
  carried mode is default-only, and no worktree auto-entry is authorized from it. Known
  pre-existing limitation, named in ADR-0031: the emitter's name-only idempotency means a changed
  choice on redo is not re-recorded; implement §1 will read the original row.
- **P13 on a legitimately deep plan** (true logical chain): flag-only, like P1/P11 — the
  orchestrator notes it and may pass with rationale; annotated-edge discounting prevents false
  flags on honestly-marked serialization chains.

## Changes to Existing Behavior

- MODIFIED: `plan.md:84` hub-file seam threshold ≥3 → any 2-writer file, + seam-resistant caveat.
- ADDED: `plan.md` ordering-only write-serialization annotation rule (general tasks); sibling
  remedy at :86 retained in effect.
- ADDED: `plan.md` graph-width authoring rule; `orchestrator-checklist-plan.md` P13.
- MODIFIED: P11 threshold and remedy wording.
- MODIFIED: `plan.md` §4 picker assembly — raw verb pair → composed `cortex-lifecycle-branch-decision`
  with guard rendering and the §4 self-dirtying acknowledgment.
- MODIFIED: `implement.md` §1 picker options and `worktree-entry.md` — trunk-cost line.
- ADDED: `cortex/adr/0031-*.md`; MODIFIED: ADR-0030 status → `accepted` (amendment note).
- MODIFIED: `docs/internals/sdk.md` `run_in_background` rationale row.

## Technical Constraints

- Edit canonical `skills/lifecycle/references/*` only; `plugins/cortex-core/` mirrors regenerate
  via the pre-commit hook (`tests/test_plugin_mirror_parity.py`).
- Kept-pause markers in `implement.md` (`implement-branch-pick` :23, `implement-batch-failure`
  :81) must survive edits byte-identically or move in lockstep with `kept-pauses-data.toml`
  (`tests/test_lifecycle_kept_pauses_parity.py`); this spec adds no new pauses.
- Zero-sweep: `implement.md`/`plan.md`/`review.md` gain no raw event-emission surface
  (`tests/test_lifecycle_event_roundtrip.py` `ZERO_SWEEP_FILES`).
- MUST-escalation policy (docs/policies.md): new rules use soft positive-routing phrasing — no new
  MUST/CRITICAL language (no linked F-row evidence artifact exists).
- Prose budget: target ≤ ~25 net lines across the touched reference files (#401 precedent:
  implement ≤10 / plan ≤7 per file); reference growth is invisible to tests.
- Annotation examples must use only parser-tolerated shapes (parenthetical or em-dash trailing
  annotations, `pipeline/parser.py::_DEPENDS_ON_TRAILING_ANNOTATION`).
- `tests/test_lifecycle_picker_label_pins_worktree.py` pins the implement §1 options-block shape;
  `tests/test_skill_section_citations.py` pins plan.md §1b/§5 headings; `test_adr_citation_audit.py`
  pins ADR hygiene. Test command: `just test` (lifecycle.config.md).
- What/Why-not-How: new prose states decision criteria and intent, not procedural walkthroughs.

## Open Decisions

None — the research resolved each fork inline (annotation over deletion; §4 composed-verb fix;
2-writer threshold; P13-now/verb-later), and the remaining judgment (accepting the item-1 descope)
belongs to the spec-approval surface.

## Proposed ADR

### Proposed ADR: 0031-reaffirm-batch-barrier-and-ordering-only-serialization-annotation

ADR-0030 deferred dependency-pipelined dispatch pending a measured case surviving token
accounting; ticket #404 presented wild-light #358's 142/135/99-minute schedules as that case.
Forensics graded the evidence insufficient (single mid-run simulation, real durations for 12 of 24
tasks with the placeholders concentrated in exactly the tasks the disputed edge moves, run 54%
complete, citing artifact no longer on disk) — while confirming the structural fact that one
non-logical edge cut DAG depth 11→8. Decision: re-affirm the batch barrier; close the authoring
gap instead with an ordering-only write-serialization annotation (mustRunAfter semantics:
relaxable under per-task isolation by a future executor, never deletable, real edge to the
overnight pipeline) plus 2-writer hub guidance and graph-width checks; name the preconditions any
future pipelining attempt must clear (per-task events, metrics semantics, fused
checkpoint+merge-back, pause admission policy, commit serialization, substrate pinnability, #39886
mitigation); flip ADR-0030 to accepted. Trade-off: bounded straggler idling persists, in exchange
for prose correct on every runtime version, plans safe under both executors, and zero new
coordination machinery.
