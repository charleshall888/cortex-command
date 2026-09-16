---
name: morning-review
description: Walk the morning report after an overnight run — verify features, answer deferred questions, advance lifecycles, merge the PR, close tickets. Use for "/morning-review" or "what happened overnight".
disable-model-invocation: true
---

# Morning Review

## 1. Close the session

`~/.local/share/overnight-sessions/active-session.json` with `"phase": "executing"` → use its `state_path` and pass `--pointer <that file>`; otherwise `cortex/lifecycle/sessions/latest-overnight/overnight-state.json` without `--pointer`; neither readable → skip. The verb no-ops unless the phase is `executing`.

```
cortex-morning-review-complete-session <state_path> [--pointer <pointer_path>]
session_id="$(jq -r '.session_id' <state_path>)"
cortex-morning-review-gc-demo-worktrees "$session_id"
```

## 2. Locate the report

First that exists: `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/latest-overnight/morning-report.md`, `cortex/lifecycle/sessions/latest-overnight/morning-report.md`, `cortex/lifecycle/morning-report.md`. None → no overnight session has run, or the report was not generated; suggest `cortex-report` and stop. A session id in the report heading that differs from the state file's → warn the report may be stale and ask whether to proceed or regenerate.

## 3. Walk it

Follow [walkthrough.md](${CLAUDE_SKILL_DIR}/references/walkthrough.md) in order, skipping sections with no entries.

Out of scope: resuming sessions (`/overnight resume`), regenerating the report (`cortex-report`), resuming a half-done review (restart it). `overnight-state.json` is read-only after §1.
