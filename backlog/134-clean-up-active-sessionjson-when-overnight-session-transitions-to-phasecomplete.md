---
schema_version: "1"
uuid: ec141696-e5f5-4a7f-b1a8-06f5bf9411b2
title: "Clean up active-session.json when overnight session transitions to phase:complete"
status: complete
priority: medium
type: bug
created: 2026-04-22
updated: 2026-04-22
---

## Problem

`~/.local/share/overnight-sessions/active-session.json` persists past session completion with `phase: complete` and `pid: null`, instead of being cleared (or transitioned to a `completed/` archive) when the runner finishes.

Observed during lifecycle 127 completion on 2026-04-22: the file pointed at `overnight-2026-04-21-1708` (a session that completed the previous day) with `"phase": "complete"`, `"pid"` field absent. The R8b precondition (`ls ~/.local/share/overnight-sessions/active-session.json 2>/dev/null` must return empty, OR the recorded PID must not be alive) had to fall through to the secondary PID-alive check, and the PID was `null` which isn't a real value for `ps -p`.

## Impact

- R8b-style preconditions that check the file as a proxy for "is a runner active right now?" have to implement their own secondary logic to distinguish "file is stale" from "runner is genuinely live".
- Any tooling that trusts the file as "pointer to the currently-running session" (e.g., `bin/overnight-status`) sees a dead pointer until a new session starts and overwrites it.
- Fails silently — there's no visible breakage, just ambiguity.

## Proposed fix

Either:
1. Session cleanup (end-of-run) deletes `active-session.json` when `phase` transitions to `complete`; subsequent tooling treats "file absent" as the signal for no active runner.
2. OR the file is archived to `~/.local/share/overnight-sessions/completed/{session_id}.json` and the canonical `active-session.json` symlink/pointer is removed.

Option 1 is simpler. The cleanup path likely lives in `hooks/cortex-cleanup-session.sh` or `claude/overnight/runner.sh`'s cleanup trap.

## Acceptance criteria

- After an overnight session reaches `phase: complete`, `~/.local/share/overnight-sessions/active-session.json` is either absent OR the file's canonical path is understood by downstream tooling to mean "the file itself is the signal of activity — absence means no runner".
- A test covering the "session-complete triggers active-session.json cleanup" path.
- No regression in session resume or status-check tools.
