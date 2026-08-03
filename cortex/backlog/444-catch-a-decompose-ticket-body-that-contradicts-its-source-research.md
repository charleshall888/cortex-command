---
schema_version: "1"
uuid: 7bbed9f5-1716-4b4f-88b2-865f6f8fcb53
title: Catch a decompose ticket body that contradicts its source research
status: superseded
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
---
## Why

A decompose-authored ticket body can assert the opposite of the research it was derived from, and nothing catches it. Epic #434 shipped that way: `research.md:31` established that `_check_and_close_parent` reads raw, unnormalized status and cited `:299` and `:333`; #435 and #437 quoted it accurately; #436's Integration said the cascade "reads the same normalized status". That single contradicted fact made #436's unwedge arm unachievable as scoped, sent #437's narrowing rationale after the wrong precondition, and was only caught because a reader happened to open the function. This is not an uncertainty problem — the answer was already written down — so ADR-0034's fog mechanism explicitly does not cover it.

## Role

Catches a ticket body that contradicts its source research before the ticket is worked.

## Integration

Sits at the decompose boundary, where `### Pieces` and `### How they connect` are already the mandated inputs and the R15 gate already blocks on the operator. Both the research artifact and the drafted bodies exist in one place at that moment, which is the only point where the comparison is cheap.

## Edges

- Not a fog problem and not fixable by more research. The fact was researched correctly and cited with line numbers; the body diverged from it afterwards.
- The check is a comparison, not an investigation: every load-bearing claim in a drafted body should trace to the research, and a claim that contradicts it is the defect. What "load-bearing" means needs defining before anything is built.
- An agent-authored comparison of prose against prose is exactly the kind of judgment that produces false confidence. Weigh a narrow mechanical check (do the cited `file:line` references and their stated behavior match the research's?) against a general one.
- `discovery_source` already links a ticket back to its research artifact, so the pairing needs no new field.
- Cost discipline: #434's four other tickets were faithful. A check that fires on 1 in 5 must be cheap enough to be worth running on the other four.
- **Overlaps #429 and should probably be folded into it.** #429 audits `file:line` citations in backlog, requirements and lifecycle prose, on the same premise — *"downstream work treats them as verified"* — with four instances from a single wild-light refine run. This ticket is the adjacent case where the citation resolves but the claim contradicts its source, and #411 shows the third: the research itself asserted an unverified fact (one shared parse boundary; six parsers exist). Decide whether one auditor covers all three before building either.
- `skills/discovery/` is lifecycle-gated, so this routes through `/cortex-core:dev`.

## Touch points

- `skills/discovery/references/decompose.md` — the piece-set contract and the R15 gate.
- `cortex/research/staged-epic-gate-tickets/research.md:31` — the correct statement.
- `cortex/backlog/436-surface-work-parked-by-status-and-unwedge-the-epics-it-blocks.md` — its Correction section records the divergence.
- `cortex/adr/0034-fog-becomes-a-piece-and-dependents-declare-the-blocker.md` — the decision that scopes this out.

## Disposition (2026-08-03): superseded by #429

Folded into #429 as a recorded scope boundary, not as a feature. The ticket's own closing Edge
asked whether one auditor covers this case, #429's, and #411's; the answer is no, and checking
it first is what closed this ticket rather than building it.

**This ticket's own founding incident is out of reach of the auditor it proposed folding into.**
#436's contradicting sentence carried no `file:line` citation. The research it contradicted did
(`cortex/research/staged-epic-gate-tickets/research.md:31`, citing `:299` and `:333`). A citation
auditor had nothing to audit. The heuristic fallback — flag a factual claim that names no line —
does not fire either, because the sentence names no backticked symbol.

What remains is the general prose-against-prose comparison this ticket's third Edge already
warned about. It is the only instrument that reaches the case, it is an LLM judgment on a hot
path, and by the ticket's own cost discipline it must be cheap enough to run on the four
faithful tickets in five. Declined on that basis.

The durable version, if this recurs: require load-bearing claims in a decompose-authored body to
carry a citation, which converts the problem into #429's and gets coverage for free. That is a
convention change with an authoring tax, needs "load-bearing" defined, and is deliberately not
filed on a single incident — the front-door evidence bar in `CLAUDE.md` wants a measured cost or
a repeated failure, and this is one.

`discovery_source` was verified real and populated (230 tickets; `refine.py:492`,
`generate_index.py:208`), so that claim in the Edges above stands. #429 absorbs it as a scan target.
