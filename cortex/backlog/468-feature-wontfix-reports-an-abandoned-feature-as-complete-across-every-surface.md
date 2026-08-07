---
schema_version: "1"
uuid: bd73ae5b-578e-4ca8-b1f6-84aea79dcadb
title: feature_wontfix reports an abandoned feature as Complete across every surface
status: backlog
priority: medium
type: bug
created: 2026-08-07
updated: 2026-08-07
tags: ['lifecycle', 'phase-vocabulary', 'observability']
areas: ['lifecycle']
---
## Why

Measured 2026-08-07 while closing #454. A lifecycle dir whose events.log carries only `{"event": "feature_wontfix"}` resolves as:

```
resolve_lifecycle_phase -> phase: complete | route: complete
phase_label("complete")  -> "Complete"
```

So a feature the operator deliberately abandoned is reported as finished. Root cause is `_TERMINAL_EVENT_TO_STATE` (`cortex_command/common.py:524-528`), which maps `feature_wontfix -> complete` alongside `feature_complete -> complete`. The wontfix path is not obscure: `wontfix_cli.py` archive-moves the lifecycle dir, so the abandonment is also dropped from the SessionStart scan.

This is the same class of defect #454 just fixed for `escalated` — one terminal state carrying two different operator meanings, with every surface narrating whichever one is hardcoded.

**Compounding gap, verified the same day:** `_TERMINAL_EVENT_TO_STATE` has **zero** references anywhere in the test corpus, while its sibling `_MACHINE_STATE_NAMES` has two and is pinned equal to the transition table by the resolver tests. A phase routed through this dict is therefore invisible to `tests/test_transition_table.py`. Any fix here needs that tripwire, or the next mapping change regresses silently the same way.

Named as a follow-up in #454s spec (`spec.md:71-72`) and re-verified live before filing.

## Role

Make an abandoned feature distinguishable from a completed one on the surfaces that report completion, and put a regression guard on the mapping that conflates them.

## Integration

#454 added a governing clause to `cortex/requirements/project.md` Architectural Constraints that prices the options: a new **display** form on `phase` costs one `phase_labels` branch and zero new machine states, whereas a new `route` value costs a transition-table row plus every enumerating surface. #454s spec Non-Requirements priced the state-addition route in detail. Read both before choosing, and prefer the discriminated-phase pattern #454 established (`complete:wontfix` is the obvious shape, mirroring the existing `complete:awaiting-merge`).

## Edges

- `wontfix_cli.py` archive-moves the dir, so a fix must decide whether the archived lifecycle is still readable by the reporting surfaces.
- Completion **metrics** should probably continue excluding abandoned features from throughput, which is a separate question from what the operator label says.
- `_is_terminal_mismatch` treats `complete` as terminal; a new `complete:` sub-form inherits that via the existing `startswith("complete:")` clause.

## Touch-points

`cortex_command/common.py` (`_TERMINAL_EVENT_TO_STATE`), `cortex_command/phase_labels.py`, `cortex_command/pipeline/metrics.py`, `cortex_command/dashboard/data.py`, `claude/statusline.sh`, plus a new tripwire test beside the `_MACHINE_STATE_NAMES` pin.
