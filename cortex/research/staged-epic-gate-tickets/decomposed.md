# Decomposition: staged-epic-gate-tickets

## Epic

- **Backlog ID**: 434
- **Title**: Stop the backlog recording states that contradict reality

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 435 | Recognize finished work spelled outside the canonical status set | high | S | — |
| 436 | Surface work parked by status, and unwedge the epics it blocks | high | S | — |
| 437 | Collapse the five competing status vocabularies into one | medium | M | 435, 436 |
| 438 | Make an epic's recorded outcome and membership reflect reality | medium | M | — |
| 439 | Decide how to prevent work against a superseded understanding | medium | M | 438 |

## Suggested Implementation Order

435 and 436 first, in either order — both are read-time, both close a distinct observed failure, and neither depends on anything. 435 fixes the only damage with a named victim outside this repo.

437 third, and only after both land. The ordering is load-bearing rather than stylistic: the parent-closing cascade reads raw unnormalized status while every other reader normalizes, so narrowing the terminal set before the corpus normalizes would make finished items read as active. Migrate, then narrow.

438 is independent of the vocabulary chain and can run in parallel with it. Its visibility arm is what makes the epic corpus measurable at all, so the earlier it lands the sooner the census behind 439 can be taken.

439 last. It is blocked by 438 in the schedule and in substance — the census that decides between its two candidate mechanisms cannot be taken while the epic map sees one epic out of thirty-four.

## Created Files

- `cortex/backlog/434-stop-the-backlog-recording-states-that-contradict-reality.md` — Stop the backlog recording states that contradict reality (epic)
- `cortex/backlog/435-recognize-finished-work-spelled-outside-the-canonical-status-set.md` — Recognize finished work spelled outside the canonical status set
- `cortex/backlog/436-surface-work-parked-by-status-and-unwedge-the-epics-it-blocks.md` — Surface work parked by status, and unwedge the epics it blocks
- `cortex/backlog/437-collapse-the-five-competing-status-vocabularies-into-one.md` — Collapse the five competing status vocabularies into one
- `cortex/backlog/438-make-an-epics-recorded-outcome-and-membership-reflect-reality.md` — Make an epic's recorded outcome and membership reflect reality
- `cortex/backlog/439-decide-how-to-prevent-work-against-a-superseded-understanding.md` — Decide how to prevent work against a superseded understanding
