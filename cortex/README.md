# cortex/ — Tool-managed working area for cortex-command. Safe to gitignore as a unit.

This directory is the umbrella for all runtime artifacts produced by the cortex-command
harness — lifecycle state, research scratch work, backlog items, project requirements,
retrospectives, and debug output. Nothing here is hand-edited during normal operation;
the harness writes and reads these files on your behalf.

## lifecycle/

Holds per-feature lifecycle directories (`lifecycle/{feature}/`). Each feature directory
contains the phase artifacts produced by `/cortex-core:lifecycle` and `/cortex-core:refine`:
`research.md`, `spec.md`, `plan.md`, `review.md`, `events.log`, `index.md`, and `.session`.
The overnight runner reads from and writes into these directories during autonomous execution.

## research/

Scratch research output written by `/cortex-core:research` when invoked standalone (outside
a lifecycle context). Files here are ephemeral working material and are not referenced by
the overnight runner's plan-execution loop.

## backlog/

Backlog item files managed by `cortex-update-item` and the backlog tooling. Each file is a
Markdown document with YAML frontmatter tracking status, complexity, criticality, linked
spec, and discovery source. The `cortex-generate-backlog-index` utility regenerates the
index from this directory.

## requirements/

Project and area-level requirements documents: vision statements, priorities, and scope
constraints. Read by the harness during Clarify and Research phases to align feature work
with stated goals.

## retros/

Retrospective notes written after feature completion or overnight run post-mortems. Not
consumed by the harness automatically; used for human review and continuous improvement.

## debug/

Diagnostic output and structured logs written by harness internals for troubleshooting
failed overnight runs, hook errors, or pipeline anomalies. Safe to delete between sessions.

## .cortex-init

Sentinel file written by `cortex init` to mark that this directory has been registered in
the sandbox allowlist. Its presence indicates the harness has write access to `cortex/`.

## lifecycle.config.md

Optional project-level configuration file read by `/cortex-core:lifecycle` at startup.
Overrides complexity defaults, test commands, phase-skipping rules, and review criteria
for this project. Absent by default; create it to customize lifecycle behavior.
