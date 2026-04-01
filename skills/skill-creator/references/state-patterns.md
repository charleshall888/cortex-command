# State Patterns

Reference for skills that persist state across invocations. Use these patterns when a skill must resume from where it left off after interruption, or when phase progress needs to survive context loss.

## Pattern 1: JSONL Append-Only Log

**When to use**: Audit trails, phase transition history, event streams. Never needs to be overwritten — new information is always appended.

**Format**: One JSON object per line. Each entry has at minimum a timestamp and an event type.

```
{"ts": "2026-01-15T10:30:00Z", "event": "lifecycle_start", "feature": "my-feature", "tier": "simple"}
{"ts": "2026-01-15T10:45:00Z", "event": "phase_transition", "feature": "my-feature", "from": "research", "to": "specify"}
{"ts": "2026-01-15T11:00:00Z", "event": "phase_transition", "feature": "my-feature", "from": "specify", "to": "plan"}
```

**Append idiom**: Use shell redirection to append a single line.

```bash
echo '{"ts": "...", "event": "...", ...}' >> path/to/events.log
```

**Read-last-matching-event idiom**: To find the most recent event matching a condition (e.g., the last phase transition), read all lines and scan in reverse for the first match.

**Never overwrite**: Once written, log entries are permanent. If a value changes (e.g., criticality override), append a new event — do not modify the old one.

**File naming convention**: `events.log` for a single-skill log, `{feature}/events.log` for per-feature logs.

---

## Pattern 2: Mutable JSON State File

**When to use**: Current-state snapshots that need to be updated as the skill progresses. Unlike the JSONL log, this file is overwritten at each checkpoint.

**Format**: A single JSON object with the current state.

```json
{
  "phase": "implement",
  "feature": "my-feature",
  "tasks_completed": [1, 2, 3],
  "tasks_remaining": [4, 5],
  "last_updated": "2026-01-15T11:30:00Z"
}
```

**Read/update/write idiom**:
1. At invocation start, read the state file (or initialize if it does not exist).
2. Determine current phase from the `phase` field.
3. After completing a phase, update the state object and overwrite the file.

**Initialization**: If the file does not exist, create it with the initial state (phase = first phase, empty progress).

**File naming convention**: `{skill-name}-state.json` or `{feature}/state.json`. Place in the same directory as other skill artifacts (e.g., `lifecycle/{feature}/`).

---

## Pattern 3: Checkbox-in-Markdown

**When to use**: Human-visible progress tracking where the user or agent checks off completed items. The file doubles as a readable artifact (e.g., a plan) and a progress tracker.

**Format**: Standard markdown task list syntax.

```markdown
- [ ] Task 1: Do the first thing
- [x] Task 2: Do the second thing (done)
- [ ] Task 3: Do the third thing
```

**Completion detection idiom**: Count unchecked items to determine whether the phase is complete.

```
unchecked = count of lines matching "- [ ]"
if unchecked == 0:
    phase is complete
else:
    phase is in progress, N tasks remaining
```

**Updating**: When a task completes, change `- [ ]` to `- [x]` in the file. Do not delete or reorder tasks — position matters for dependency references (Task N is identified by its position).

**File naming convention**: Typically the primary artifact file itself (e.g., `plan.md`), not a separate file.

---

## Pattern 4: Phase Detection at Invocation

**When to use**: Any skill using Pattern 1 or 2 that must resume correctly after interruption.

**The canonical pattern** — run this at the start of every invocation for a resumable skill:

```
1. Read the state source (JSONL log or JSON state file).
   - If neither exists: initialize. Phase = first phase.

2. Determine current phase:
   - From JSONL log: scan for the most recent phase_transition event. Current phase = the "to" field of that event.
   - From JSON state file: read the "phase" field directly.

3. Branch:
   - Resume: announce the detected phase, confirm with the user if appropriate, then execute that phase.
   - Restart: if the user requested a fresh start, delete/reset state and begin from phase 1.
   - Complete: if the final phase is already marked done, report completion and offer to re-run or archive.
```

**Announcing the resume**: Always tell the user what was detected. "Resuming from the specify phase — research.md was found, spec.md not yet written."

---

## Ephemeral vs. Durable Files

| File type | Durable? | Gitignored? | Example |
|-----------|----------|-------------|---------|
| JSONL event log | Yes — append only | No (commit for history) | `events.log` |
| JSON state file | Yes — overwritten | Usually no | `pipeline-state.json` |
| Checkbox markdown | Yes — updated in place | No (commit as artifact) | `plan.md` |
| Session file | No — ephemeral | Yes | `.session` |

**Session files** (`.session`): written at the start of each session to record which agent is working on which feature. Overwritten on every resume. Never committed — gitignore `**/.session`.

**Durable artifacts** (logs, state, plans): committed as part of the feature's history. Provide recovery context if the session is interrupted.
