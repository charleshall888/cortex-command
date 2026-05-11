# Step 2e: Residue Write — Resolver and Payload Schema

After synthesis (or Step 2c.5 pass-through), atomically write any B-class
findings to a sidecar JSON for the morning report. Skip silently when zero
B-class findings remain.

## Feature Resolution

Resolve `{feature}` from `$LIFECYCLE_SESSION_ID` against `lifecycle/*/.session` files (whitespace-stripped match):

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$REPO_ROOT" ] || MATCHES=$(python3 -c "
import os, glob
sid = os.environ.get('LIFECYCLE_SESSION_ID', '')
print('\n'.join(p for p in glob.glob(os.path.join('$REPO_ROOT','lifecycle','*','.session')) if open(p).read().strip()==sid))")
```

- **One match**: `{feature}` = parent dir of matched `.session`; proceed to atomic write.
- **Zero matches** (or no `REPO_ROOT`): ad-hoc mode — if B-class findings exist, emit `Note: B-class residue not written — no active lifecycle context.`; skip write.
- **Multiple matches**: emit `Note: multiple active lifecycle sessions matched $LIFECYCLE_SESSION_ID; B-class residue write skipped.`; skip write.

## Atomic Write

Only when `{feature}` resolved AND ≥1 B-class finding — inline `python3 -c` performing a tempfile + `os.replace` atomic rename to `lifecycle/{feature}/critical-review-residue.json`:

```bash
python3 -c "
import json, os, sys, tempfile
from pathlib import Path
final = Path('$REPO_ROOT')/'lifecycle'/'$FEATURE'/'critical-review-residue.json'
final.parent.mkdir(parents=True, exist_ok=True)
data = json.dumps(json.loads(sys.stdin.read()), indent=2)+'\n'
with tempfile.NamedTemporaryFile('w', dir=str(final.parent), delete=False) as tmp:
    tmp.write(data)
    tmp_path = tmp.name
os.replace(tmp_path, final)
" <<< "$PAYLOAD_JSON"
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
