# Wontfix workflow

Use when an operator decides a lifecycle should be terminated without shipping — typically because the premise has been rejected, the work is superseded by another lifecycle, or the cost/value gate has flipped against the feature. The goal is twofold: drop the lifecycle from SessionStart's "incomplete lifecycles" enumeration immediately, and leave a terminal-state marker that both `cortex_command.common.detect_lifecycle_phase` and `claude/statusline.sh` recognize as `phase=complete`.

The workflow has three sequential steps. **Step order is load-bearing**: putting `git mv` first means even if step (b) or (c) fails partway, the lifecycle is correctly excluded from SessionStart enumeration via the existing archive-skip at `hooks/cortex-scan-lifecycle.sh:227`. R13's detector patch (the JSON-parsing-loop extension in `cortex_command/common.py`) is defense-in-depth for archive-internal phase queries — tools that inspect archived lifecycles' phase fields directly.

## Steps (in order)

### (a) First — archive the lifecycle directory

```bash
git mv cortex/lifecycle/{feature} cortex/lifecycle/archive/{feature}
```

Moving the directory FIRST drops the lifecycle from SessionStart enumeration immediately, before any later step can fail. `hooks/cortex-scan-lifecycle.sh:227`'s archive-skip is the convention that makes this work.

### (b) Second — append the terminal-state event

Append a `feature_wontfix` event to the now-archived `events.log`. The path is under `archive/` because step (a) already moved the directory:

```bash
printf '%s\n' '{"ts": "2026-05-13T00:00:00Z", "event": "feature_wontfix", "feature": "{feature}", "reason": "<short rationale>"}' \
  >> cortex/lifecycle/archive/{feature}/events.log
```

The event is a single-line JSONL record with these fields:

- `ts` — ISO-8601 timestamp
- `event` — literal `"feature_wontfix"`
- `feature` — the lifecycle slug
- `reason` — optional short rationale string

A literal example row, exactly as it appears in the log:

```json
{"ts": "2026-05-13T00:00:00Z", "event": "feature_wontfix", "feature": "example-feature", "reason": "premise-rejected"}
```

The `"event": "feature_wontfix"` literal is what both the events-registry scanner and the phase detector match on.

### (c) Third — update the backlog item

```bash
cortex-update-item {backlog-slug} status=wontfix lifecycle_phase=wontfix session_id=null
```

This clears the originating backlog item's status so the dashboard, backlog index, and any operator-facing lists reflect the terminal decision. `session_id=null` releases any concurrent-session lock that was held by the lifecycle.

## Why the step order matters

The ordering is the simplification chosen during refine: putting `git mv` first means a partial-failure mode (steps b/c fail) still delivers the most important outcome — the lifecycle drops out of SessionStart enumeration. The alternative (event-first, archive-last) leaves a window where the wontfix'd lifecycle keeps surfacing in the "incomplete lifecycles" list because the archive-skip hasn't fired yet.

R13's detector patch is the belt: it returns `phase=complete` if it sees a `feature_wontfix` event even when the directory hasn't been moved (e.g., an in-flight workflow that hand-emitted the event but hasn't completed step (a)). That covers archive-internal phase queries too — tools that inspect archived events.log files directly get a coherent answer.
