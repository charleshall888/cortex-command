---
id: 216
title: "Add platform abstraction package for Windows"
type: feature
status: not-started
priority: medium
parent: 215
tags: [windows-support, platform, locking, processes]
created: 2026-05-15
updated: 2026-05-15
discovery_source: cortex/research/windows-support/research.md
---

# Add platform abstraction package for Windows

## Role

Introduce a small platform abstraction package that hides POSIX-only syscalls cortex's overnight runner, pipeline, init flow, and dashboard use today. Today these calls (advisory file locks via fcntl flock, detached-session process spawning via start_new_session, signal-group kills via os.killpg, SIGHUP handler registration, the `lsof` subprocess in stale-lock cleanup, and a few `/tmp` fallbacks) fail to even import or invoke on Windows. The package's role is to provide a uniform cross-platform contract for those primitives so callers in init, auth bootstrap, the overnight runner, the pipeline worktree manager, and the cortex-overnight MCP server stop branching at every call site. The existing macOS-only durable-fsync helper in common is folded in to consolidate the file-conditional pattern that already exists at one site. A repo-wide WINDOWS boolean in common covers the rest of the codebase's thin glue (TMPDIR fallback in pipeline/conflict, pipeline/worktree, and init/handler; settings.local.json path resolution; the dashboard's user-cache-dir resolution).

## Integration

Callers move from direct POSIX calls to the package's lock-acquire, process-spawn-detached, signal-group, and stale-lock-detect contract surfaces. The package is the foundation that the overnight scheduler port, the install-and-hooks piece, and the posture surface all consume; it must land first. The hybrid pattern (separate Windows file for the syscall hot spot, inline WINDOWS flag for thin glue) is documented in a one-paragraph package README so future contributors know the rule: abstract when the syscall doesn't import; inline otherwise.

## Edges

- Breaks if the lock contract changes shape (argument signature for acquire, return type of the context manager, exception semantics on timeout).
- Breaks if SIGHUP handler registration is not guarded — SIGHUP does not exist on Windows; bare signal.signal(SIGHUP, …) throws AttributeError on import.
- Depends on the platformdirs library (or equivalent) for cross-platform user-cache-dir resolution that replaces the dashboard's XDG_CACHE_HOME lookup.
- Depends on filelock or stdlib msvcrt as the Windows-side lock backend; the choice is made within the piece.
- Stale-lock detection currently uses lsof; on Windows the substitute is psutil's open-files iteration or a graceful no-op (skip stale-lock cleanup), with the contract being "best-effort detect-and-clean."
- The existing macOS-conditional durable-fsync helper in common moves into the package; callers update their imports.

## Touch points

- `cortex_command/init/settings_merge.py` (lock callsite on the settings.local.json sibling lockfile)
- `cortex_command/init/handler.py` (TMPDIR `/tmp` fallback for worktree-root sandbox-registration check)
- `cortex_command/auth/bootstrap.py` (lock + os.open POSIX-flags callsites)
- `cortex_command/overnight/ipc.py` (lock callsite)
- `cortex_command/overnight/runner.py` (lock + start_new_session + killpg + SIGHUP callsites)
- `cortex_command/overnight/sandbox_settings.py` (lock callsite on the event-log writer)
- `cortex_command/overnight/scheduler/lock.py` (lock callsite on the schedule lockfile)
- `cortex_command/overnight/cli_handler.py` (start_new_session + killpg callsites)
- `cortex_command/overnight/runner_primitives.py` (SHUTDOWN_SIGNALS tuple includes SIGHUP)
- `cortex_command/pipeline/conflict.py` (TMPDIR `/tmp` fallback)
- `cortex_command/pipeline/worktree.py` (TMPDIR `/tmp` fallback + lsof-based stale-lock cleanup at ~lines 349-353 in inventory snapshot)
- `plugins/cortex-overnight/server.py` (lock + ps-probe callsites)
- `cortex_command/common.py` (existing macOS-conditional durable_fsync helper to fold into the new package; ~lines 651-670 in inventory snapshot)
- `cortex_command/dashboard/app.py` (XDG_CACHE_HOME PID-path resolution to swap for platformdirs)
