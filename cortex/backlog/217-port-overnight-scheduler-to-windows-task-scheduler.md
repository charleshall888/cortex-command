---
id: 217
title: "Port overnight scheduler to Windows Task Scheduler"
type: feature
status: not-started
priority: low
parent: 215
blocked-by: [216]
tags: [windows-support, overnight, scheduler]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/windows-support/research.md
---

# Port overnight scheduler to Windows Task Scheduler

## Role

Make scheduled overnight runs work on native Windows. The existing macOS scheduler registers a launchd plist that fires a bash launcher script at scheduled times; the launcher prepares the environment, prevents host idle-sleep via caffeinate, launches the orchestrator detached from the shell, and surfaces launch failures via osascript notifications. The Windows equivalent registers a Task Scheduler entry that fires a PowerShell launcher script doing the same job with platform-appropriate primitives: SetThreadExecutionState or powercfg replaces caffeinate, BurntToast or msg.exe replaces osascript, Task Scheduler handles process detachment so the explicit setsid dance becomes implicit. The OS primitive differs, the daemonization sequence differs, but the contract is identical.

## Integration

Sibling to the existing macOS scheduler module under the overnight scheduler package. Consumes the platform abstraction package's process and lock primitives for any subprocess spawning or state-file mutation the scheduler does. The rest of the overnight runner subsystem (round loop, IPC, plan execution, morning report, dashboard polling) is platform-neutral once the platform package is in place; this piece only touches the scheduler subdirectory and the wheel-build force-include config that ships launcher scripts inside the wheel.

## Edges

- Breaks if the scheduler module's contract surface changes (register, unregister, status, fire-callback); both platform-specific modules conform to the same shape.
- Depends on Windows Task Scheduler being available; it ships in Windows 10 1809+ as a system component.
- The wheel-build force-include list must add the Windows launcher script alongside the existing bash launcher, or the Windows wheel ships without its launcher.
- The runtime sandbox warning from the posture surface piece must fire on scheduler-fired runner startup just as it does on interactive runner startup — the warning emission point is shared.

## Touch points

- `cortex_command/overnight/scheduler/macos.py` (existing pattern to mirror — register, unregister, status, fire)
- `cortex_command/overnight/scheduler/launcher.sh` (existing bash launcher; ~160 lines covering caffeinate, osascript, /dev/null daemonization)
- `pyproject.toml` (force-include section under `[tool.hatch.build.targets.wheel]` that currently ships launcher.sh in every wheel)
- `cortex_command/overnight/scheduler/lock.py` (consumed via the platform package's lock primitive after #216 lands)
