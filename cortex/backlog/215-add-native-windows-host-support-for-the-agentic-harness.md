---
id: 215
title: "Add native Windows host support for the agentic harness"
type: epic
status: not-started
priority: medium
tags: [windows-support, platform, port]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/windows-support/research.md
---

# Add native Windows host support for the agentic harness

## Context

cortex-command is macOS-primary today. Native Windows support is feasible across all four in-scope subsystems (interactive skills + hooks, CLI utilities, overnight runner + pipeline, dashboard + notifications). Claude Code itself is generally available on native Windows; the cortex-command port reduces to four workstreams below.

The sandbox gap on native Windows is transitional: Anthropic has explicitly committed to native-Windows sandbox enforcement on the roadmap, so the cortex-side bridge is a startup warning that gets deleted once Claude Code ships the feature. The forward-compatible JSON write that cortex performs today becomes live automatically at that point.

## Scope

- Platform abstraction package (lock, process, WINDOWS flag, dashboard XDG substitute, lsof substitute, fold existing `durable_fsync`)
- Overnight scheduler Windows port (Task Scheduler instead of launchd)
- Windows installer bootstrap + empirical hook execution validation (one combined piece since the hook test requires the installer to have run on a Windows VM)
- Posture surface (best-effort docs wording, runtime sandbox warning, advisory Windows-smoke CI, observability.md spec/implementation reconciliation)

## Children

- 216: Add platform abstraction package for Windows
- 217: Port overnight scheduler to Windows Task Scheduler
- 218: Bootstrap Windows install and validate hook execution
- 219: Add Windows posture surface and advisory CI

## Suggested Sequencing

Ship 216 + 218 + 219 together as "Windows v1" — delivers interactive cortex on Windows (skills, lifecycle, CLI utilities, dashboard, hooks). Follow with 217 as "Windows v2" — adds overnight-runner scheduling. The dependency order is 216 first, then 218 (needs cortex on PATH via installer), with 217 and 219 dependent on 216.

## Out of Scope

- **cortex-ui-extras plugin port** — marked EXPERIMENTAL in README; depends on bash glob expansion, `uv run --script` shebangs, Husky setup. Defer to a separate follow-up epic if pursued.
- **cortex-pr-review's evidence-ground.sh** — single bash script in an optional plugin. Stays bash; documented under "requires Git for Windows on Windows hosts" alongside `tests/test_*.sh` and `.githooks/pre-commit`.
- **Test scripts under `tests/test_*.sh`** — eight bash test scripts invoked by the justfile `test` recipe. Require Git for Windows to run on Windows clones. Documented; not rewritten in this epic.
- **Contributor pre-commit hook (`.githooks/pre-commit`)** — 13.6KB bash script activated via `just setup-githooks`. Runs under Git for Windows' bundled bash on Windows clones. Documented; not rewritten.

## Research

See `cortex/research/windows-support/research.md` for full findings, decision records, and feasibility assessment.
