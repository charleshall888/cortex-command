# Live verification (Task 9, spec R15)

Run 2026-09-16 against `claude` 2.1.273 (Claude Code), through `cortex_command.claude_stream` (`build_argv` + `build_env` + `run_claude`) at HEAD `06c5528a`. The probe script lived in the session scratchpad and is not committed.

## Run 1 — sandbox deny through the seam

- argv: `claude -p --output-format stream-json --verbose --max-turns 3 --max-budget-usd 2.0 --permission-mode bypassPermissions --allowedTools Read,Write,Edit,Bash,Glob,Grep --system-prompt … --settings <work>/settings.json --effort low`; prompt on stdin.
- Settings: `build_sandbox_settings_dict(deny_paths=[<work>/target.txt], allow_paths=[<work>], soft_fail=False, excluded_commands=["git:*"])`.
- Frame order: `system/hook_started` ×2 → `system/hook_response` → `system/init` → `assistant` (tool_use Bash) → `rate_limit_event` → `system/task_summary` → `user` (tool_result) → `system/hook_response` → `assistant` (text) → `system/post_turn_summary` → `result` → `system/task_summary`. Two frames arrived after `result` (R7).
- Tool result: `is_error: true`, content `Exit code 1 / (eval):1: operation not permitted: <work>/target.txt`.
- Target byte-identical before/after (sha256 match).
- `result`: `is_error: false`, `subtype: "success"`, `num_turns: 2`, `stop_reason: "end_turn"`, `terminal_reason: "completed"`, `total_cost_usd: 0.320`. First key `duration_api_ms`.
- Exit code 0; stderr empty.
- `assistant.message.model`: `claude-opus-5`.
- `rate_limit_event` shape: `{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "resetsAt", "rateLimitType": "seven_day", "utilization": 0.89, "isUsingOverage", "surpassedThreshold", "unifiedWindows": {...}}, "uuid", "session_id"}` — matches Task 2's `rate_limit_frame` nesting and dispatch.py's `rate_limit_info.status` read.
- `classify_failure(0, result, rate_limit, "", 3)` → `None` (success).

## Run 2 — budget exhaustion

- Same shape with `--max-budget-usd 0.01`, `--allowedTools Read`.
- `result`: `is_error: true`, `subtype: "error_max_budget_usd"`, `terminal_reason: "budget_exhausted"`, `errors: ["Reached maximum budget ($0.01)"]`, `stop_reason: "end_turn"`, `num_turns: 1`, `total_cost_usd: 0.306` (the cap is checked after the first turn, so spend overshoots it).
- Exit code 1; stderr empty. One `system/hook_response` frame arrived after `result`.
- `classify_failure(1, result, None, "", 3)` → `budget_exhausted` — confirms Task 3's step 2 against the real CLI (research Open Question 3).

Total cost of both runs ≈ $0.63.

## Opt-in live test (spec R25)

`tests/test_claude_stream_live.py` on 2026-09-16 with `claude` 2.1.273 on an authenticated machine: without `--run-slow` → `1 skipped` (`opt-in via --run-slow`); with `--run-slow` → `1 passed in 4.14s`.
