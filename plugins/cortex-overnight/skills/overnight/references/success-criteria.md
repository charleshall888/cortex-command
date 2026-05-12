# Success Criteria

## `/overnight` (new session)

A successful `/overnight` invocation satisfies all of the following:

1. **Session plan written**: `cortex/lifecycle/sessions/{session_id}/overnight-plan.md` exists and contains the approved feature list with round assignments.
2. **State initialized**: `cortex/lifecycle/sessions/{session_id}/overnight-state.json` exists with `phase: executing` and all selected features in `pending` status.
3. **Session manifest written**: `cortex/lifecycle/sessions/{session_id}/session.json` exists with correct `session_id`, `type: overnight`, and feature slugs.
4. **Integration branch created**: `git branch overnight/{session_id}` exists in the repository.
5. **Symlink deferred to runner**: The `latest-overnight` symlink is updated by the runner on startup, not by the skill.
6. **Runner command executed**: `overnight-start` was executed via Bash tool with an absolute state path using `$CORTEX_COMMAND_ROOT` and the correct time limit.
7. **Session start event logged**: `overnight-events.log` has a `SESSION_START` entry.

## `/overnight resume`

A successful `/overnight resume` satisfies:

1. **Session state reported**: Current phase, per-feature statuses, and completed rounds are shown to the user.
2. **Deferred questions surfaced**: Any blocking deferred questions are presented before offering resume options.
3. **Correct action offered**: Runner command (executing/paused), morning report link (complete), or restart option (planning) is presented based on phase.
