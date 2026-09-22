# Resume Flow (`/overnight resume`)

## 1. Load

Use the newest `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/*/overnight-state.json` whose `phase` is not `complete`. Skip files that fail to parse. None → "No active overnight session found. Use `/overnight` to start a new session." All corrupted → say so and suggest manual repair or `/overnight`. Stop in both cases.

## 2. Report

Show session id, start time, phase, per-feature status, rounds completed (`round_history` length), and the current round. For phase `paused`, explain `paused_reason`:

- `budget_exhausted` → resume when the Anthropic budget resets
- `stall_timeout` → inspect logs before resuming
- `signal` → resume when ready
- else → show the reason as is

Read the session's `deferred/*.md` and show each question. Mark blocking ones: their features wait for a human. Unreadable → note it and continue.

## 3. Act

| Phase | Offer |
|---|---|
| `executing` | resume, or view progress |
| `paused` | fix the cause (answers, failures), then resume |
| `complete` | the morning report — `/morning-review` |
| `planning` | should not occur — offer to restart |

**Resume** runs via Bash with `dangerouslyDisableSandbox: true`:

```
cortex overnight start --state {state_path} --time-limit 21600
```

The runner skips merged features. Report: "Overnight session resumed. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`."
