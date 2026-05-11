# Debug Session Artifact — Location, Format, and Write Timing

This reference defines the debug-session artifact written during the 4-phase debugging protocol.

## Location

Determine where to write the artifact using this priority:

1. **Explicit feature argument** (e.g., `/cortex-core:diagnose my-feature`): write to `lifecycle/{feature}/debug-session.md` if the directory exists. If not, warn verbally and fall back to step 3.
2. **Active session scan**: check `lifecycle/*/` for a `.session` file whose content matches `$LIFECYCLE_SESSION_ID`. If found, write to `lifecycle/{feature}/debug-session.md`.
3. **Fallback**: write to `debug/{date}-{slug}.md` where `{date}` is ISO date (YYYY-MM-DD) and `{slug}` is a short kebab-case description of what is being debugged (use `diagnose` if no slug is available). Create the `debug/` directory if absent.

> **Note**: `$LIFECYCLE_SESSION_ID` propagation into overnight sub-agent sessions is unverified. In autonomous/overnight context, pass the feature name explicitly (e.g., `/cortex-core:diagnose my-feature`) for reliable lifecycle-coupled artifact placement.

## Format

```markdown
# Debug Session: {context}
Date: YYYY-MM-DD
Status: In progress | Resolved | Escalated — investigation incomplete

## Phase N Findings
- **Observed behavior**: ...
- **Evidence gathered**: ...
- **Tests performed**: ...
- **Outcomes**: ...
- **Dead-ends**: ... (call out explicitly)

## Current State
Root cause identified: X. Fix applied: Y.
— or —
Best current theory: X. Not yet tried: Y.

## Prior Attempts
(Move prior content here if the file previously existed; current investigation stays on top.)
```

## Write Timing

- **Phase 1**: create the file with Phase 1 Findings + Current State. Status: `In progress`.
- **Phases 2–3**: update file — add Phase N Findings, update Current State. Status: `In progress`.
- **Phase 4 success**: add Phase 4 Findings, update Current State. Status: `Resolved`.
- **Autonomous escalation** (Phase 4 §5 skipped, no human available): write current findings with status `Escalated — investigation incomplete` before failing the task. This write is mandatory — do not exit without it.
