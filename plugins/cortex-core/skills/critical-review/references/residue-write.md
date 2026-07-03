# Step 2e: Residue Write — Resolver and Payload Schema

After synthesis (or Step 2c.5 pass-through), atomically write any B-class
findings to a sidecar JSON for the morning report. Skip silently when zero
B-class findings remain.

## Feature Resolution

Resolve `{feature}` from `$LIFECYCLE_SESSION_ID` against `cortex/lifecycle/*/.session` files (whitespace-stripped match):

```bash
FEATURE=$(cortex-critical-review-resolve-feature "$LIFECYCLE_SESSION_ID")
```

Route on the console-script's exit code; propagate any failure:

- **One match** (exit 0): `$FEATURE` = resolved slug; proceed to atomic write.
- **Zero matches** (non-zero exit, or no repo root): ad-hoc mode — if B-class findings exist, emit `Note: B-class residue not written — no active lifecycle context.`; skip write.
- **Multiple matches** (non-zero exit): emit `Note: multiple active lifecycle sessions matched $LIFECYCLE_SESSION_ID; B-class residue write skipped.`; skip write.

## Atomic Write

Only when `{feature}` resolved AND ≥1 B-class finding — invoke the `cortex-critical-review-write-residue` console-script, writing `cortex/lifecycle/{feature}/critical-review-residue.json`. The payload JSON is piped in via stdin:

```bash
cortex-critical-review-write-residue --feature "$FEATURE" <<< "$PAYLOAD_JSON"
```

## Payload Schema (R4)

```
{
  "ts": "<ISO 8601>",
  "feature": "<slug>",
  "artifact": "<path>",
  "synthesis_status": "ok|failed",
  "reviewers": {"completed": N, "dispatched": M},
  "findings": [
    {
      "class": "B",
      "finding": "<text>",
      "reviewer_angle": "<angle>",
      "evidence_quote": "<text>"
    }
  ]
}
```

## Gates

- Zero B-class findings → no file, no note.
- Synthesis failure → write `synthesis_status: "failed"` with B-class findings from Step 2c reviewers' envelopes.
- Path-argument (`/cortex-core:critical-review <path>`) and auto-trigger invocations (specify.md §3b / plan.md) both obey session-bound resolution — the argument path does not re-bind `{feature}`.
