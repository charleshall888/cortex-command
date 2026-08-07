---
schema_version: "1"
uuid: 07d372b2-4aa6-4bdb-80bb-66f17beb395d
title: Escalated features fire a permanent unclearable terminal-mismatch warning at SessionStart
status: complete
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
tags: ['observability', 'lifecycle', 'escalation']
areas: ['lifecycle']
complexity: simple
---
## Why

Measured 2026-08-07 while closing #454:

```
_is_terminal_mismatch("escalated",              "in_progress") -> True
_is_terminal_mismatch("escalated:rework-cap:2", "in_progress") -> True
_is_terminal_mismatch("complete",               "in_progress") -> True
```

The detector (`cortex_command/hooks/scan_lifecycle.py`) flags features whose events say terminal while the backlog row says `in_progress`. For `complete` that is actionable and self-clearing: mark the ticket complete and the warning goes away. For `escalated` it is neither. An escalated feature is awaiting operator direction and is **not** done, so its ticket correctly stays `in_progress` — meaning the warning fires on every SessionStart and no correct operator action can clear it. The only ways to silence it are to lie about the ticket status or to abandon the feature.

SessionStart is among the highest-frequency operator surfaces in the harness, and permanent unclearable warnings there train operators to ignore the surface — which is what makes a real mismatch elsewhere easy to miss.

#454 deliberately widened the detector to the discriminated cap form (`startswith("escalated:")`), because its R3 required the new phase form to be held to the same terminal-check rule as the bare string. That was correct for consistency and is not the defect; it does mean the noise now covers capped features too.

Named as a follow-up in #454s spec (`spec.md:73`) and re-verified live before filing.

## Role

Stop the terminal-mismatch detector reporting an unresolvable condition, without weakening it for the case where it is genuinely actionable.

## Integration

The likely shape is to scope the check to terminal states whose expected backlog status is `complete` — i.e. exempt `escalated` and `cancelled` — rather than to suppress the warning generally. Note that `escalated` is the state #454 just taught four surfaces to narrate accurately, so the operator now learns the real cause from the SessionStart hint itself; the mismatch line adds nothing on top of that and arguably contradicts it by implying a bookkeeping error where there is none.

## Edges

- `cancelled` is also terminal with a non-complete ticket status; check whether it has the same problem before scoping the fix to `escalated` alone.
- Do not simply drop `escalated` from the terminal set — #454s R3 depends on the discriminated form counting as terminal for the `-paused` suppression, and there is now a mutation-verified test pinning that (`tests/test_lifecycle_phase_resolver.py`).
- Whatever changes, the detector still needs to fire for a genuinely stale `complete`.

## Touch-points

`cortex_command/hooks/scan_lifecycle.py` (`_is_terminal_mismatch` and its call site), `tests/test_lifecycle_phase_resolver.py`.
