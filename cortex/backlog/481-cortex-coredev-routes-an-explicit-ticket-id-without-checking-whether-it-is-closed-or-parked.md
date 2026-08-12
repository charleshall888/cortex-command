---
schema_version: "1"
uuid: 934178c9-28ca-4f67-8641-8ab5dd6c6312
title: /cortex-core:dev routes an explicit ticket id without checking whether it is closed or parked
status: complete
priority: high
type: bug
created: 2026-08-12
updated: 2026-08-12
tags: ['dev-skill', 'routing', 'backlog-status']
areas: ['skills']
---
## Why

`/cortex-core:dev <id>` never consults whether the ticket it was handed is finished or parked. Step 3's triage is the only step that renders that state, and rule 1 routes there only when there are no arguments — so an explicit ticket number bypasses it entirely. Rule 5 then routes on the `spec:` field alone: absent `spec:` means `/cortex-core:refine`, whether the item is fresh, closed, or deliberately parked.

Observed 2026-08-12 in a consumer repo (wild-light): `/cortex-core:dev 329` on a ticket carrying `status: deferred` routed to refine. That ticket records a decision already made, one option rejected permanently, and a revisit trigger that has not fired. Triage was correct about it in the same session — `cortex-backlog-triage` omits it from every block — but the explicit-id path never reached triage.

Rule 5's stated tiebreak does not catch it either: "When unsure, `cortex-lifecycle-next <feature>` reports the served phase". That resolver has the same blind spot (sibling ticket), so on a parked or closed id it confirms the wrong route rather than correcting it.

## Role

Makes the explicit-id path respect the same closure and parking that the no-argument path already respects, so a named ticket is checked against its recorded outcome before a route is proposed.

## Integration

Sits on the boundary between rule 1 and rule 5 in Step 1, where the two paths through the same skill currently disagree. Reuses the state triage already computes rather than introducing a second notion of parked.

## Edges

- Independent of the resolver fix: rule 5 routes deterministically on `spec:` without calling `cortex-lifecycle-next`, so a corrected resolver leaves this path unchanged. Either ticket can land first.
- A parked item is not necessarily unworkable — an operator naming it explicitly may be deliberately unparking it. Surfacing the recorded state and its trigger, then asking, is likely better than refusing to route.
- Running full triage for a single named id is heavier than the check needs; the cheap read is the item's own frontmatter.
- Rule 4 closes a resolved item without reading its status either, though the failure mode there is narrower.
- #456 established that closed items must be marked where they are rendered; this is the same requirement one layer earlier, at the point of routing rather than display.

## Touch points

- `plugins/cortex-core/skills/dev/SKILL.md:14` — rule 1, the only route into Step 3 triage, gated on having no arguments.
- `plugins/cortex-core/skills/dev/SKILL.md:18` — rule 5, routing on `spec:` alone, plus the `cortex-lifecycle-next` tiebreak that shares the blind spot.
- `plugins/cortex-core/skills/dev/SKILL.md:28-41` — Step 3, which acts on triage's `state` and is where parked items are already correctly suppressed.
- `cortex_command/backlog/generate_index.py:89-103` — `_is_deferred`, the predicate that already recognizes both sanctioned parking spellings.

Observed on wild-light #329 (`status: deferred`, `type: chore`, no `spec:`).
