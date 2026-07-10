---
schema_version: "1"
uuid: 09539950-c01f-48d7-adbd-1a17934c4f3d
title: 'Build the verb-completion composition: wrapper verbs, generated pauses, shared overnight reducer'
status: backlog
priority: high
type: feature
created: 2026-07-10
updated: 2026-07-10
parent: "371"
tags: ['cli-served-lifecycle-state-machine']
discovery_source: cortex/research/cli-served-lifecycle-state-machine/research.md
blocked-by: 370
---
## Why

The lifecycle's recorded failure classes are hand-maintained prose drifting from code and multi-event transitions hand-written in prose-ordered sequences — an emit-before-commit ordering that stranded a completion row, an invented event schema, ordering invariants held only by a sentence, fuzzy pause-inventory anchors that need repointing after every nearby edit and have already drifted from their code constant once, and an overnight prompt that embeds its own inline reimplementation of the events.log criticality reduction. The exact-count pin test policing prose emission breaks on every corpus edit, the pause parity net misses three real sites, and the overnight duplication is kept honest only by a heading-citation test.

## Role

The verb-completion composition — the strict prefix of the eventual state machine that fixes every recorded failure class without building the loop. Four verbs own the four multi-emission decision clusters (the plan decision, review-verdict routing, spec approval, and implement transitions), each executing its gate check and ordered emissions inside one function body so the ordering invariant is the function body rather than prose; the plan and spec verbs record the operator's choice as a durable consent event, giving the two highest-stakes pauses an audit trail by construction, and the spec verb owns the refined-status backlog write-back so all lifecycle status writes become verb-owned. The kept-pauses inventory becomes generated output: pause sites carry stable in-prose identity markers with kind and rationale in a repo data file, a generator renders the document, parity collapses to exact marker-set equality, the three missed sites join the net, and the four pause kinds (question, phase-exit wait, config-conditional, relayed-consent) become data. The overnight orchestrator prompt reads criticality and tier through the shipped state verb instead of its inline reduction, so one reducer serves both execution modes. Write-side order tests replace the exact-count pin class per-verb, and environment-fixture tests cover the existing guard verbs on the same test seam.

## Integration

Each wrapper verb composes the existing event-emission contract and returns a state discriminant the skill prose routes on, exactly as the complete-route verb works today; the pause generator follows the established generate-markdown-from-data pattern used by the backlog index; the overnight prompt consumes the same state verb the interactive path uses, retiring the heading-citation pin's consumer. If the served loop ever funds, it composes these same verb bodies and this same pause data file unchanged — nothing here is rework under either gate outcome. Blocked by the identity-resolver fix, which the wrapper verbs' resolution path depends on.

## Edges

- Additive-only against events.log; the emission contract's hand-written exception class stays closed at three.
- Verbs stay caller-parameterized per the dumb-arg-actor rule — no self-resolved backends or config.
- Inherits the existing accepted skew posture — no protocol handshake; these are plain verbs like enter and finalize.
- The exact-count pin entries retire per-verb as each cluster lands, never wholesale ahead of coverage.
- Judgment content — what to approve, review criteria, prompt templates, the overnight plan-format contract — stays in prose; only sequencing, emission, and mechanical lookups move.
- Pause data is repo data, not wheel code: hot-editable, no release cycle, no version-skew surface; markers ride with the prose they annotate.
- The runtime pause tooth (refusing transitions without recorded pause events) and overnight execution unification are explicitly out of scope — both belong to the gated loop.

## Touch points

- `skills/lifecycle/references/plan.md:122-132` — plan_approved → feature_paused-on-wait → phase_transition, with the prose ordering invariant
- `skills/lifecycle/references/review.md:82-101` — review_verdict + drift_protocol_breach + three-way routed phase_transition
- `skills/refine/references/specify.md:143,151` and `skills/refine/SKILL.md:85-94` — spec_approved + phase_transition + status-refined write-back
- `skills/lifecycle/references/implement.md:54,102,120` — batch_dispatch and rework entry/exit transitions
- `tests/test_lifecycle_event_roundtrip.py:123-154` — FILE_EVENTS exact-count pins to retire per-verb
- `cortex_command/lifecycle/wontfix_cli.py:196-198`, `cortex_command/lifecycle/enter.py` — order-enforcement and needs-decision precedents
- `cortex/lifecycle/lifecycle-corpus-trim-wave-2/plan.md:72` — the documented pin-retirement mechanism (finalize precedent)
- `skills/lifecycle/references/kept-pauses.md:3-14` — the hand-maintained inventory that becomes generated output
- `tests/test_lifecycle_kept_pauses_parity.py:28,32-43` — line-tolerance validation (LINE_TOLERANCE=35) collapsing to marker equality
- `skills/lifecycle/references/implement.md:76`, `skills/lifecycle/references/complete-first-run.md:11`, `skills/lifecycle/references/concurrent-sessions.md:5` — the three pause sites the current regex misses
- `cortex_command/backlog/generate_index.py:220-240` — the generator precedent
- `cortex_command/overnight/prompts/orchestrator-round.md:238-260` — inline _read_criticality reduction to replace with a `cortex-lifecycle-state` call
- `skills/lifecycle/references/criticality-matrix.md:22-26` — the documented state-verb read contract
- `tests/test_skill_section_citations.py:40-54` — the §1a heading pin that loses its consumer
- `cortex_command/interactive_lock.py`, `cortex_command/lifecycle/prepare_worktree.py` — targets for the environment-fixture guard tests