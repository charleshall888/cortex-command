---
schema_version: "1"
uuid: 44fe5e7d-7ad7-42c4-bf1a-9741c9689c4f
title: Orchestrator-review mandates a whole-artifact rewrite for precision-only flags, so practitioners route around it
status: refined
priority: low
type: chore
created: 2026-08-03
updated: 2026-08-03
tags: ['skills', 'orchestrator-review', 'process']
areas: ['skills']
complexity: complex
criticality: high
spec: cortex/lifecycle/orchestrator-review-mandates-a-whole-artifact/spec.md
---
## Why

`skills/build/references/orchestrator-review.md` §3 makes **whole-artifact rewrite by a fresh subagent** the
only sanctioned repair for a flagged rule when no user input is needed:

> The orchestrator does not edit phase artifacts directly — dispatching preserves separation of concerns and
> creates an audit trail. […] It must **rewrite the entire artifact** to address the flag while preserving
> all correct existing content — never patch sections.

The rationale is sound for a substantive flaw. It is disproportionate for the most common flag class:
**an acceptance criterion that is correct in substance but not binary-checkable** — a missing file path, an
unquantified run count, a criterion phrased as intent. Those are one- or two-sentence repairs.

The cost of the mandated route on a large artifact is real. A ~200-line spec rewritten wholesale by an agent
that has not seen the reasoning behind it risks dropping content the flag never touched, and the instruction
"preserving all correct existing content" is exactly the kind of requirement that fails quietly and is
expensive to verify — you have to diff the whole artifact to trust it.

**Observed 2026-08-03 (wild-light #432 refine).** Orchestrator review flagged two acceptance criteria on a
14-requirement spec: one naming no grounding file, one riding a ~6/10-flaky probe arm without a run count.
Both were precision repairs. Rather than dispatch a whole-artifact rewrite, the orchestrator routed through
§3's *other* branch — "rework needing user input → revise in place" — on the grounds that one of the two
genuinely was an operator call (the acceptance bar). That was defensible, but it was **routing around the
rule**, and the second fix rode along on the first. A reviewer following the protocol literally would have
faced a whole-spec rewrite to add a filename.

## Role

Decide whether the whole-artifact-rewrite mandate should acquire a proportionality escape hatch, and if so
what bounds it. This needs a judgment about what the rule is protecting, not a patch.

Candidate directions (none pre-selected):

- **A scoped-repair branch**: when every flag is confined to a single requirement or bullet, allow a
  targeted edit, still dispatched, still returning the `verdict/files_changed/rationale` envelope. Keeps the
  audit trail, drops the blast radius.
- **Keep the mandate, add a diff obligation**: the subagent returns a summary of what it changed *beyond*
  the flagged rule, so silent content loss becomes visible rather than assumed-absent.
- **Keep the mandate unchanged** and record explicitly that small flags are expected to cost a full rewrite
  — a legitimate answer, but it should be a decision rather than something practitioners quietly route
  around.

## Integration

- `skills/build/references/orchestrator-review.md` §3 (Fix dispatch) and §2 (verdict handling).
- Any skill propagating the orchestrator-review target: `skills/refine/references/specify.md` §3a,
  `skills/build/` plan/implement/review phases.

## Edges

- **The separation-of-concerns rationale is load-bearing** — the orchestrator not editing its own artifact
  is what makes the review meaningful. A scoped-repair branch must stay *dispatched*; the escape hatch is
  about blast radius, not about who holds the pen.
- **"Preserving all correct existing content" is unverifiable as stated.** Whichever direction wins, that
  clause needs an observable form, or it stays a hope.
- The 2-cycle cap (§4) already bounds iteration; a proportionality branch must not become a way to take
  more cycles on smaller fixes.
- Watch for the failure this rule exists to prevent: patch-only repairs that fix the cited line and leave
  the artifact internally inconsistent. Any scoped branch needs a consistency obligation.

## Touch points

- `skills/build/references/orchestrator-review.md` §2-§4
- `skills/refine/references/specify.md` §3a (a propagating consumer)
