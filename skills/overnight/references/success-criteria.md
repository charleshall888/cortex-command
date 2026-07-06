# Success Criteria

## `/overnight` (new session)

1. **Session plan written**: `overnight-plan.md` exists with the approved feature list and round assignments.
2. **State initialized**: `overnight-state.json` exists with `phase: executing` and all selected features `pending`.
3. **Session manifest written**: `session.json` exists with correct `session_id`, `type: overnight`, feature slugs.
4. **Integration branch created**: `git branch overnight/{session_id}` exists.
5. **Symlink deferred to runner**: `latest-overnight` is updated by the runner on startup, not by the skill.
6. **Runner command executed**: `cortex overnight start` ran via Bash with `--state <absolute path>` and `--time-limit <seconds>`.
7. **Session start event logged**: `overnight-events.log` has a `session_start` entry.

## `/overnight resume`

1. **Session state reported**: current phase, per-feature statuses, completed rounds.
2. **Deferred questions surfaced**: any blocking deferred questions presented before resume options.
3. **Correct action offered**: runner command (executing/paused), morning report link (complete), or restart option (planning), by phase.
