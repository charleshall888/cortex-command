# Debug Session Artifact — Location, Format, and Write Timing

## Location

Priority order for where to write the artifact:

1. **Explicit feature argument** (e.g., `/cortex-core:diagnose my-feature`): write to `cortex/lifecycle/{feature}/debug-session.md` if it exists, else warn and fall back to step 3.
2. **Active session scan**: if a `.session` file under `cortex/lifecycle/*/` matches `$LIFECYCLE_SESSION_ID`, write to that feature's `debug-session.md`.
3. **Fallback**: write to `debug/{date}-{slug}.md` (ISO date; kebab-case slug, or `diagnose` if none available). Create `debug/` if absent.

> **Note**: `$LIFECYCLE_SESSION_ID` propagation into overnight sub-agent sessions is unverified — in autonomous/overnight context, pass the feature name explicitly for reliable placement.

## Format

```markdown
# Debug Session: {context}
Date: YYYY-MM-DD
Status: In progress | Resolved | Escalated — investigation incomplete

## Phase N Findings
- **Observed behavior**: ...
- **Evidence gathered**: ...
- **Tests performed and outcomes**: ...
- **Dead-ends**: ... (call out explicitly)

## Current State
Root cause identified: X. Fix applied: Y.
— or —
Best current theory: X. Not yet tried: Y.

## Prior Attempts
(Prior content moves here; current investigation stays on top.)
```

## Write Timing

- **Phases 1–3**: create (Phase 1) or update (Phases 2–3) with Phase N Findings + Current State. Status stays `In progress`.
- **Phase 4 success**: add Phase 4 Findings, update Current State. Status: `Resolved`.
- **Autonomous escalation** (Phase 4 §5 skipped, no human available): write current findings with status `Escalated — investigation incomplete` before failing the task. This write is mandatory — do not exit without it.
