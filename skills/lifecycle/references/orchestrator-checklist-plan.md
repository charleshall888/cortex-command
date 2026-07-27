# Post-Plan Checklist

Rate each item **pass** or **flag**. Shared protocol and the binary-checkable rule: `orchestrator-review.md`.

| # | Item |
|---|------|
| P1 | Each task targets 5-15 min and 1-5 files; flag outliers |
| P2 | Every task has `**Depends on**`, with no missing edge where one task's output feeds another |
| P3 | Each Context field lets a fresh subagent execute without reading unrelated files |
| P4 | Verification satisfies the binary-checkable rule; "verify it works" fails |
| P5 | Prose and structural context only — no function bodies, imports, or copy-paste code |
| P6 | Every file a Verification implies is listed in Files |
| P7 | No self-sealing verification. An artifact the task creates is benign only as the primary deliverable — flag it as a side-channel recording an external condition. A rig task's validated-discarded-sample rehearsal is the primary-deliverable exercise, not a flag |
| P8 | `**Architectural Pattern**` valued in {event-driven, pipeline, layered, shared-state, plug-in}; gated on `criticality = critical`, N/A otherwise. Semantic fit belongs to the synthesizer |
| P9 | `## Outline` present — ≥2 phases for complex, ≥1 for simple, each naming its task IDs plus `**Goal**` and `**Checkpoint**` |
| P10 | Complex plans carry a `## Acceptance` whole-feature criterion. Skip on simple — the last-phase Checkpoint is the contract there |
| P11 | No file two tasks would both edit without an early seam task or a serializing `Depends on` chain (an annotated write-serialization edge qualifies) |
| P12 | No task tagged `trivial` whose What/Verification implies a commit — `trivial` means no-commit, and the loop fails zero-commit tasks at checkpoint; retag `simple` |
| P13 | No single-task level between multi-task levels, and no level count approaching half the task count. Count every edge at face value; list write-serialization-annotated segments as dissolve-first candidates, never as a depth discount |
