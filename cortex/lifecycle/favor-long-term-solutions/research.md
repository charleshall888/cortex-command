# Research: favor-long-term-solutions

## Scope anchor

Add a "Solution horizon" principle that biases agents toward fixes already known to be durable — using a *known-redo* test, not a *predicted-redo* test — with an explicit carve-out for deliberately-scoped phases of multi-phase lifecycle work. Canonical statement in `cortex/requirements/project.md` Philosophy of Work; short pointer + one-sentence operational trigger in `CLAUDE.md`. Soft positive-routing language only (no MUST/NEVER/REQUIRED).

## Target file inventory

### `cortex/requirements/project.md` — canonical statement

Existing Philosophy of Work section uses bold-prefixed paragraph style:

- **Day/night split** (line 11)
- **Handoff readiness** (line 13)
- **Failure handling** (line 15)
- **Daytime work quality** (line 17)
- **Complexity** (line 19) — "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **Quality bar** (line 21)
- **Workflow trimming** (line 23)

Natural insertion: a new bold-prefixed paragraph **Solution horizon**, placed adjacent to **Complexity** (which it constrains). Style is short paragraph, no bullet lists, no procedural how-to.

### `CLAUDE.md` — operational pointer

Existing top-level section structure (line numbers approximate):

- `## What This Repo Is`
- `## Repository Structure`
- `## Distribution`
- `## Commands`
- `## Dependencies`
- `## Conventions`
- `## Skill / phase authoring guidelines`
- `## Design principle: prescribe What and Why, not How`
- `## MUST-escalation policy (post-Opus 4.7)`

The new content is a principle, sibling to **Design principle**. Natural insertion: a new `## Solution horizon` section placed before the **Design principle** section (so principles flow newest → most mature). One-sentence operational trigger + cross-reference to project.md for the canonical statement.

## Reconciliation with existing principles

Two principles in `project.md` need explicit reconciliation in the new prose:

1. **"When in doubt, the simpler solution is correct"** (line 19, Complexity philosophy).
   - The new principle does not contradict this; it adds a *when* condition. Simpler is correct **until you already know** redo is coming (because a follow-up is already planned, the same patch would apply in multiple known places, or it sidesteps a constraint you can already name). Uncertainty about future redo still routes to simpler.
   - This must be stated explicitly in the new prose — the surface tension is real and the critic correctly flagged that glossing it as a "nuance" understates the conflict.

2. **"Iterative improvement … some design will be discovered through use"** (Quality Attributes, line 39).
   - The carve-out: a deliberately-scoped phase of a multi-phase lifecycle plan is *known* to be revisited and is therefore not a stop-gap. Stop-gap means *unplanned-redo*. The repo's entire operating model (backlog tickets, phased lifecycles, refinement passes) depends on this carve-out being explicit; without it, the principle reads as opposing the repo's incremental philosophy.

System-prompt anti-over-engineering rules ("Don't design for hypothetical future requirements"; "Three similar lines is better than a premature abstraction") are *complementary* — they govern the case where redo is **not** known. The known-redo test only fires on **known**, not speculative, redo. No reconciliation needed beyond making the "known" framing explicit.

## MUST-escalation interaction

CLAUDE.md lines 68–77 require an F-row evidence artifact or transcript excerpt before adding any MUST/CRITICAL/REQUIRED escalation. The user confirmed this is a general principle with no specific incident, so no F-row evidence exists. The new prose must therefore use soft positive-routing phrasing throughout (e.g., "Before suggesting a fix, ask…", "Prefer…", "A deliberately-scoped phase … is not a stop-gap"). No imperative escalation language.

## Operational test (the heuristic)

The principle's operational core, phrased for inclusion verbatim or near-verbatim:

> Before suggesting a fix, ask: do I currently know this fix will need to be redone — because a follow-up is already planned, the same patch would apply in multiple known places, or it sidesteps a constraint I can already name? If yes, propose the durable version (or surface both choices with the tradeoff). If no, the simpler fix is correct — don't speculate about future redo.
>
> A deliberately-scoped phase of a multi-phase lifecycle plan is not a stop-gap — stop-gap means unplanned-redo.

This phrasing satisfies:
- Soft positive-routing (no MUST/NEVER).
- Anchored on current knowledge, not prediction (compatible with system-prompt anti-speculation).
- Explicit phased-lifecycle carve-out.
- Reconciles with project.md "simpler is correct" by adding a *when* condition.

## Insertion-point summary

| File | Insertion point | Style |
|---|---|---|
| `cortex/requirements/project.md` | New `**Solution horizon**:` paragraph in Philosophy of Work, immediately after **Complexity** | Bold-prefixed paragraph, ~5–8 sentences |
| `CLAUDE.md` | New `## Solution horizon` section, immediately before `## Design principle: prescribe What and Why, not How` | Short section: operational trigger + cross-reference to project.md |

## Open Questions

None. The clarify Q&A round resolved both gaps (heuristic and surface placement). Insertion points and style are determined by reading existing structure.
