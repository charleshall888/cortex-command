# Post-Plan Checklist

Orchestrator-review `plan`-phase checklist (`plan.md`); rate each item **pass** or **flag**. Shared protocol and Binary-checkable rule: `orchestrator-review.md`.

| # | Item | Criteria |
|---|------|----------|
| P1 | Task sizing | Each task targets 5-15 min, 1-5 files; flag outliers. |
| P2 | Dependency graph complete | Every task has `**Depends on**`; no missing edge where one task's output feeds another. |
| P3 | Structural context sufficient | Each Context field lets a fresh subagent execute without reading unrelated files. |
| P4 | Binary-checkable verification | Satisfies the Binary-checkable rule (shared protocol); "verify it works" fails. |
| P5 | Code budget respected | Prose and structural context only — no function bodies, imports, or copy-paste code. |
| P6 | Files/Verification consistency | Every file Verification implies is listed in Files. |
| P7 | No self-sealing verification | An artifact the task itself creates is benign only if it's the primary deliverable — harmful (flag) if it's a side-channel recording an external condition. Carve-out: a rig task's validated-discarded-sample rehearsal is the primary-deliverable exercise, not a self-sealing flag. |
| P8 | Architectural Pattern present + in taxonomy | `**Architectural Pattern**` valued in {event-driven, pipeline, layered, shared-state, plug-in}; gated on `criticality = critical` (when §1b ran), N/A otherwise. Semantic fit belongs to the synthesizer. |
| P9 | Outline present | `## Outline`; ≥2 phases for `complexity=complex`, ≥1 for `simple`. Each phase names its task IDs plus `**Goal**` and `**Checkpoint**`. |
| P10 | Acceptance on complex plans | `complexity=complex` plans have a `## Acceptance` whole-feature criterion. Skip on simple — the last-phase Checkpoint is the contract there. |
| P11 | Hub-file seam | Flag any file appearing in ≥3 tasks' `Files` lists with no early seam task and no serializing `Depends on` chain. |
| P12 | Trivial-consistency | Flag any task tagged `trivial` whose What/Verification implies a commit — plan.md defines `trivial` as no-commit and the interactive loop fails zero-commit tasks at §2d; remedy: retag `simple`. |
