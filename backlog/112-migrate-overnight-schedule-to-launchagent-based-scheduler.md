---
schema_version: "1"
uuid: 3565ffe8-5041-4c2b-9f91-d14fa9d4c1cd
title: Migrate overnight-schedule to a LaunchAgent-based scheduler
status: backlog
priority: high
type: feature
tags: [overnight, scheduler, sandbox]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-21
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
discovery_source: research/overnight-runner-sandbox-launch/research.md
---

# Migrate overnight-schedule to a LaunchAgent-based scheduler

## Context from discovery

Today `bin/overnight-schedule` spawns a detached tmux session that holds a `caffeinate -i sleep N` and then execs `overnight-start` at the target time. This is brittle in a way that research has now characterized:

- `caffeinate -i` prevents only idle sleep — **not lid-close sleep, not low-battery sleep**. A laptop with its lid closed at 22:30 will fail a 23:00 scheduled run. This is a present-tense defect, not a future-survival concern.
- The mechanism does not survive reboot.
- tmux had to be added to `sandbox.excludedCommands` to let the skill launch it from a sandboxed session. That exemption has now been reverted (see sibling change that switched `/overnight` to per-call `dangerouslyDisableSandbox: true` for run-now launches). The scheduled path currently relies on the same per-call bypass, but it inherits the `caffeinate+tmux` brittleness.

Research identified macOS LaunchAgents as the canonical primitive for this class of scheduling. `launchd.plist(5)`'s `StartCalendarInterval` coalesces missed firings on wake-from-sleep, and `launchctl bootstrap`-spawned jobs do not inherit the submitting process's Seatbelt profile — so the scheduled runner launches clean without any sandbox concession on the runner subtree itself.

## Desired outcome

Scheduled overnight runs:

- Survive reboot (plist on disk is re-bootstrapped on login)
- Tolerate lid-close and wake-from-sleep (calendar-interval coalescing)
- Launch the runner in a sandbox-clean context (launchd is the parent, no seatbelt inheritance)
- Retire the `caffeinate -i sleep + tmux` mechanism

## Research context

See `research/overnight-runner-sandbox-launch/research.md` — specifically the LaunchAgent section of "Web & Documentation Research", DR-5, and the "Feasibility Assessment" row for Option E. The research verified launchd inheritance behavior against Apple docs, `launchd.plist(5)`, `launchctl(1)`, and CVE-2022-26706 writeups.

## Exploratory framing for planning

The planning phase should consider:

- Where the generated plist lives (`~/Library/LaunchAgents/{label}.plist` is conventional; needs `sandbox.filesystem.allowWrite` entry for the skill to write it from a sandboxed session)
- Whether `launchctl:*` belongs in `sandbox.excludedCommands` (short-lived transactional — consistent with the contract documented in `claude/rules/sandbox-behaviors.md`) or whether per-call `dangerouslyDisableSandbox: true` on the `launchctl bootstrap` call is tighter
- `ProgramArguments` quoting (argv array, not shell line), PATH/WorkingDirectory inheritance gotchas, and self-unload on job completion to prevent unwanted re-fires
- How the `/overnight` skill's Step 7 "Schedule for specific time" branch should construct and submit the plist (target-time validation already lives in the current `bin/overnight-schedule` — reusable)
- Whether `bin/overnight-schedule` stays as a CLI surface (rewritten around `launchctl`) or is subsumed by the skill calling `launchctl bootstrap` directly
- Whether the current-but-stale `scheduled_start` state-file write should persist as an observability hook alongside the plist

## Out of scope

- Run-now launch path (`overnight-start`) — already handled via per-call `dangerouslyDisableSandbox: true`
- Revisiting sandbox-on-runner for non-scheduled paths (DR-2 in the research; deferred)
- Reboot-recovery of in-flight sessions — out of scope per the runner's existing "don't auto-restart mid-session" semantics
