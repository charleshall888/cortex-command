---
name: evolve
description: Identify recurring problems across retro logs and route each trend to the appropriate skill for investigation or resolution. Use when user says "/evolve", "evolve", "find trends in retros", "process retros", "what keeps going wrong", or wants to analyze session retrospectives to surface patterns and route improvements to the right workflow.
disable-model-invocation: true
argument-hint: "[N]"
---

# Evolve

Limit: $ARGUMENTS (empty = process all eligible retros up to the default of 5)

Read unprocessed retro logs, cluster recurring problems into trends, and route each trend to the right workflow — after explicit user approval.

## Invocation

- `/evolve` — process up to the last 5 unprocessed retros
- `/evolve N` — process up to the last N unprocessed retros (e.g., `/evolve 10`)

## Steps

### 1. Check for retros

If `retros/` does not exist or contains no `*.md` files (excluding dot-files):
> "No retros found — run /retro to start the feedback loop"

Stop.

### 2. Read state file

Read `retros/.evolve-state.json` if it exists:

```json
{
  "last_processed": "2026-02-26-1430.md",
  "processed_at": "2026-02-26T14:35:00"
}
```

`last_processed` is the filename of the newest retro from the previous `/evolve` run. Only retro files with filenames **lexicographically greater** than `last_processed` are unprocessed. If no state file exists, all retros are unprocessed.

### 3. Collect retros to analyze

From the unprocessed set, take the most recent N files (sorted descending by filename — YYYY-MM-DD-HHmm format is lexicographic-safe). N is the Limit value from above: use $ARGUMENTS if non-empty, otherwise default to 5.

If no unprocessed retros exist:
> "No new retros to process since last run."

Stop.

### 4. Read MEMORY.md

Derive the memory path from this skill file's own location:

1. **Resolve this skill file's real path** by following symlinks (e.g., `~/.claude/skills/evolve/SKILL.md` is typically a symlink to the repo's `skills/evolve/SKILL.md`). Use `readlink` or equivalent to get the canonical path.
2. **Derive the repo root** by stripping `skills/evolve/SKILL.md` from the resolved path.
3. **Compute the project slug** from the repo root's absolute path: replace the leading `/` with nothing, then replace all remaining `/` with `-` (e.g., `/Users/jane/repos/my-project` becomes `Users-jane-repos-my-project`).
4. **Construct the memory path**: `~/.claude/projects/-<project-slug>/memory/MEMORY.md`

Read the file at the constructed path. Extract any patterns, lessons, or known issues already captured there — these will be used to avoid re-surfacing solved problems.

### 5. Read retro files

Read each retro file in the collected set. For each problem entry, note:
- The problem description
- Which retro file(s) it appears in

### 6. Cluster into trends

Group problems by topic/theme. A **trend** requires ≥2 occurrences across different retro files. Single-occurrence problems are noted but not routed automatically.

Skip any trend that is already clearly addressed by content in MEMORY.md.

### 7. Classify routes

For each trend, assign the most appropriate route:

| Situation | Route |
|-----------|-------|
| Unknown or complex root cause | `/discovery <topic>` |
| Understood, non-trivial fix | `/lifecycle <feature>` |
| Simple, scoped improvement | `/backlog add` |
| Immediate config or memory update | `/claude-md-improver` or direct MEMORY.md/CLAUDE.md edit |

Before proposing `/backlog add`, scan `backlog/*.md` for an open item with matching title keywords. If one exists, note it rather than creating a duplicate.

### 8. Present for approval

Show the user a summary table before taking any action:

```
## Trends found across last N retros

| # | Problem pattern | Occurrences | Proposed route |
|---|-----------------|-------------|----------------|
| 1 | <description>   | 2 (retros: YYYY-MM-DD-HHmm, ...) | /discovery <topic> |
| 2 | ...             | 3 | /lifecycle <feature> |

### Single-occurrence problems (not routed)
- <problem> (retro: YYYY-MM-DD-HHmm)

Approve to dispatch the routes above, or adjust before proceeding.
```

**Do not dispatch any route until the user explicitly approves.**

### 9. Dispatch approved routes

After approval, invoke each route in the order listed. For each:
- `/discovery <topic>` — invoke the discovery skill
- `/lifecycle <feature>` — invoke the lifecycle skill
- `/backlog add` — create a backlog item following the repo's backlog format (`backlog/NNN-title.md` with YAML frontmatter)
- Direct edit — apply the MEMORY.md or CLAUDE.md change; use `/claude-md-improver` for structural rewrites

If `/skill-creator` or `/claude-md-improver` is unavailable, describe the proposed change in prose so the user can apply it manually.

### 10. Update state file

After all dispatches complete, write `retros/.evolve-state.json` with the filename of the newest retro in the processed set:

```json
{
  "last_processed": "YYYY-MM-DD-HHmm.md",
  "processed_at": "<ISO 8601 UTC>"
}
```

## Edge cases

- **No trends** (all problems are one-offs or already in MEMORY.md): "No new trends found across the last N retros."
- **Existing backlog item**: Note it — don't create a duplicate.
- **Unavailable skills**: Describe the proposed change in prose.
- **Stale state file** (referenced retro no longer exists): Treat all present retros as unprocessed.
