# Debug Session Artifact — Location, Format, and Write Timing

## Location

Resolve where the artifact lives, then act on the response:

```
cortex-debug-session-path [--feature {feature-slug}] [--slug {kebab-slug}]
```

Pass `--feature` when invoked with an explicit feature argument (e.g., `/cortex-core:diagnose my-feature`); omit it in autonomous/overnight context to resolve the active lifecycle session instead. Pass `--slug` for the fallback's kebab-case naming when neither applies.

The verb always exits 0 and prints one `{state, path, basis}` JSON object:

- `state: "lifecycle"` — write to `path`.
- `state: "fallback"` — write to `path` under `cortex/debug/`; if `basis` is `"explicit-feature-missing"`, surface the accompanying `warning` before writing.
- `state: "error"` — `message` explains what failed; do not write an artifact.

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
