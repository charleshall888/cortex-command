# Critical Review Gate

Shared skip-path protocol for the §3b Critical Review gate in Specify and Plan phases. Consulted after the inline command pair has been run and the run/skip condition evaluated — only when the skip branch applies.

## Corrupted State Rule

If either `cortex-lifecycle-state` read's output contains `"corrupted": true`, the events.log is corrupted and tier/criticality are unknowable — treat the feature as requiring review (run the critical-review skill rather than skipping).

## Run/Skip Matrix

| Tier    | low         | medium  | high    | critical |
|---------|-------------|---------|---------|----------|
| simple  | skip-silent | skip-silent | skip-silent | skip-silent |
| complex | log+skip    | review  | review  | review   |

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`.

**Skip-silent** when `tier = simple` (any criticality): proceed directly to user approval with no event logged.

**Log+skip** when `tier = complex` AND `criticality = low`: append the event below to `cortex/lifecycle/{feature}/events.log` so the skip rate is observable, then proceed to user approval:

```
{"ts": "<ISO 8601>", "event": "lifecycle_critical_review_skipped", "feature": "<name>", "phase": "<phase>", "tier": "complex", "criticality": "low"}
```

Substitute `<phase>` with the active phase name (`specify` or `plan`).
