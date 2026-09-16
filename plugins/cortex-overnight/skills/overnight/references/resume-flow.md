# Resume Flow (`/overnight resume`)

## 1. Load

Newest `$CORTEX_COMMAND_ROOT/cortex/lifecycle/sessions/*/overnight-state.json` whose `phase` is not `complete`, skipping files that fail to parse. None → "No active overnight session found. Use `/overnight` to start a new session." All corrupted → say so and suggest manual repair or `/overnight`. Stop either way.

## 2. Report

Session id and start time; phase; per-feature status; rounds completed (`round_history` length) and current round. Phase `paused` with a `paused_reason`: `budget_exhausted` → resume when the Anthropic budget resets; `stall_timeout` → inspect logs before resuming; `signal` → resume when ready; anything else → show the reason bare.

Read the session's `deferred/*.md` and present each question, flagging blocking ones as paused features awaiting a human. Unreadable → note it and continue.

## 3. Act

| Phase | Offer |
|---|---|
| `executing` | resume, or view progress |
| `paused` | address the cause (answers, failures), then resume |
| `complete` | the morning report — `/morning-review` |
| `planning` | should not occur — offer to restart |

**Resume** runs via Bash with `dangerouslyDisableSandbox: true`:

```
cortex overnight start --state {state_path} --time-limit 21600
```

The runner skips merged features. Report: "Overnight session resumed. Inspect progress with `cortex overnight status` and `cortex overnight logs <session-id>`."
