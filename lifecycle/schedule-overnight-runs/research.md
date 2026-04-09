# Research: Schedule the local overnight runner with /overnight skill integration

## Codebase Analysis

### /overnight Skill Flow

The skill (`skills/overnight/SKILL.md`) runs an 8-step sequence:
1. Pre-flight checks
2. Collect refined backlog items
3. Evaluate dependencies
4. Generate overnight plan
5. Present plan for review
6. User approval (may adjust time limit, remove features)
7. Final approval
8. **Launch** — sub-steps:
   - 8.1: Spec consistency check
   - 8.2: `bootstrap_session()` — creates worktree, integration branch, writes `overnight-state.json` with `phase=executing`
   - 8.3-8.6: Various initialization
   - 8.7: **Presents the runner command** — `overnight-start <state-path> <time-limit>`

The scheduling prompt should be inserted at **Step 8.7** — after all planning/bootstrapping is complete, where the skill currently prints the `overnight-start` command. The skill asks "Run now or schedule for later?" and prints either `overnight-start` (now) or `overnight-schedule` (later).

### Bootstrap Timing Consideration

`bootstrap_session()` creates the worktree and sets `phase=executing` before the runner command is presented. For scheduled runs, this means the worktree exists hours before the runner starts. This is acceptable for typical overnight scheduling (a few hours gap). The `scheduled_start` field in `overnight-state.json` provides observability to distinguish "waiting to start" from "executing."

### overnight-state.json Schema

Top-level fields from `OvernightState` dataclass (`state.py`):
- `session_id`, `plan_ref`, `plan_hash`
- `current_round`, `phase` (planning/executing/complete/paused)
- `features` (dict of slug → feature status)
- `round_history`, `started_at`, `updated_at`
- `paused_from`, `paused_reason`
- `integration_branch`, `integration_branches`, `worktree_path`, `project_root`, `integration_worktrees`

New fields use `Optional[str] = None` with `raw.get()` for backward compatibility.

### bin/overnight-start

Positional args only: `[state-path] [time-limit] [max-rounds] [tier]`. Guards against `--flag` syntax. Creates a tmux session named `overnight-runner` (with collision avoidance). Delegates to `claude/overnight/runner.sh`.

### Justfile Integration

The justfile `overnight-start` recipe (line 610) is a separate implementation from `bin/overnight-start`. Both manage tmux sessions independently. The skill always instructs users to run `overnight-start` (the binary), not `just overnight-start`.

Three places need updating for a new bin entry:
1. `deploy-bin` recipe pairs array (~line 130)
2. `setup-force` recipe ln block (~line 46)
3. `check-symlinks` recipe check list (~line 784)

### Files That Will Change

**New files:**
- `bin/overnight-schedule` — sleep-based wrapper that delegates to `overnight-start`

**Modified files:**
- `skills/overnight/SKILL.md` — add scheduling prompt at Step 8.7
- `claude/overnight/state.py` — add `scheduled_start: Optional[str] = None` field
- `justfile` — add `overnight-schedule` recipe, update deploy-bin/setup-force/check-symlinks

## Web Research

### Anthropic API Rate Limit Headers

The official API documentation specifies response headers on every call:
- `anthropic-ratelimit-requests-limit` / `-remaining` / `-reset` — RPM limits
- `anthropic-ratelimit-tokens-limit` / `-remaining` / `-reset` — TPM limits
- `anthropic-ratelimit-input-tokens-limit` / `-remaining` / `-reset` — Input TPM
- `anthropic-ratelimit-output-tokens-limit` / `-remaining` / `-reset` — Output TPM
- `retry-after` — seconds to wait on 429 responses

**Critical**: These are **per-minute throughput limits** using a token bucket algorithm (continuously replenished). The `-reset` timestamps are near-future rolling times (seconds to minutes), NOT the subscription usage allowance reset.

### Claude Code Subscription Usage Resets (Separate System)

The user's actual concern — "tokens reset at 11:00 PM" — refers to the **5-hour rolling session window**, which is:
- Account-specific, starts from first request in a session
- NOT a fixed UTC time — varies by user and session start
- Displayed by Claude Code as "resets at Xpm (timezone)" when exhausted
- **No programmatic API exists** to detect this reset time
- No `~/.claude/usage-cache.json` or similar file (proposed in GitHub issues but not implemented)
- Community tools infer the window from local session log timestamps (`~/.claude/projects/*.jsonl`)

### Subscription Limit Layers

| Layer | Reset mechanism | Programmatic detection |
|-------|----------------|----------------------|
| Per-minute API rate limits | Continuous token bucket | Yes — response headers |
| 5-hour rolling window | From first request in session | No — no API, no file |
| Weekly hard caps | 7-day window | No — invisible to user |
| Monthly spend limit | UTC midnight, 1st of month | Predictable by calendar |

### Practical Implication

There is no reliable way to programmatically detect when the 5-hour subscription window resets. The user's stated workflow — "I know my tokens reset at 11:00 PM" — implies they've observed the reset time from Claude Code's message. The scheduling tool should accept this user-provided time. A `bin/check-reset` probe is not viable for subscription limits.

### macOS Scheduling (From Round 1)

- `at`: dead — atrun disabled on modern macOS, requires SIP manipulation
- `launchd`: overkill for one-shot, environment stripping, fragile self-cleanup
- `sleep`-based wrapper in tmux: simplest, inherits shell env, `caffeinate -i` prevents Mac sleep
- `cron`: unreliable (misses sleep windows), no precedent in repo

## Requirements & Constraints

### In-Scope

- Scheduling launch is part of "overnight execution framework, session management" (requirements/project.md)
- File-based state is permanent architectural constraint
- Complexity must earn its place — simpler preferred

### State File Constraints (requirements/pipeline.md)

- All state writes must be atomic (tempfile + os.replace)
- Session phases are forward-only: planning → executing → complete (+ paused)
- State file reads are not lock-protected by design
- New fields use Optional defaults with `raw.get()` for backward compatibility

### Environment Requirements

- `ANTHROPIC_API_KEY` must be ambient in the environment
- `TMUX` env var needed for session persistence and alerting
- tmux session required per requirements/remote-access.md

## Tradeoffs & Alternatives

### Skill Integration

**Recommended: Option A** — Ask "run now or schedule?" at Step 8.7.

| Option | Description | Verdict |
|--------|-------------|---------|
| A: Ask at Step 8.7 | Skill asks after approval, prints `overnight-start` or `overnight-schedule` | **Recommended** — clean UX, no friction for "now" case |
| B: Always use `overnight-schedule` | Single command, `--at` optional | Overlaps with `overnight-start`, forces migration |
| C: Skill handles scheduling internally | No new bin script | Violates skill-prints-command/bin-executes pattern, sandbox issues |

### API Reset Detection

**Recommended: User-provided time (no automated detection)**

| Option | Description | Verdict |
|--------|-------------|---------|
| Probe API headers | `max_tokens:1` call to read reset timestamps | Only works for per-minute limits, not subscription window |
| Parse session logs | Infer from `~/.claude/projects/*.jsonl` | Fragile, not authoritative |
| User input | User provides known reset time from Claude Code's message | **Recommended** — reliable, no API cost, no complexity |

The skill can display helpful context: "Claude Code shows your reset time when you hit the limit. Enter that time to schedule."

### Multi-Day Scheduling

Accept both `HH:MM` and `YYYY-MM-DD HH:MM`:
- `HH:MM`: today if future, tomorrow if past
- `YYYY-MM-DD HH:MM`: explicit date
- Validate: must be in the future, max 7-day horizon
- BSD `date -j -f` for parsing on macOS
- Print human-readable countdown in confirmation

## Adversarial Review

### Critical Issues

1. **Bootstrap creates worktree before runner starts**: For scheduled runs, worktree sits idle for hours. Stale base risk if main gets new commits. Acceptable for typical overnight gaps (a few hours); the runner rebases on start.

2. **Phase is `executing` during sleep window**: `bootstrap_session()` sets phase to executing. Status tools see "executing" when the runner hasn't started. **Mitigation**: `scheduled_start` field distinguishes "waiting" from "running." Status tools check this field.

3. **No programmatic subscription reset detection**: The entire motivation ("tokens reset at 11 PM") relies on a 5-hour rolling window with no API. User must observe and provide the time manually. Any automated detection would only cover per-minute rate limits, which isn't the user's concern.

4. **Session ID encodes planning time, not launch time**: A session planned at 10 PM and launched at 11:01 PM has ID `overnight-2026-04-08-2200`. Cosmetically confusing but functionally correct.

5. **Dual REPO_ROOT in overnight-start**: Line 15 resolves via `realpath`, line 51 overwrites with `pwd`. For scheduled runs, the CWD at scheduling time IS the CWD when `overnight-schedule` runs (inside tmux), so this is fine.

### Mitigated Concerns

- **Cancel mechanism**: `tmux kill-session -t overnight-scheduled` kills the sleep chain. Confirmation output includes this command.
- **Mac sleep**: `caffeinate -i` wrapping prevents sleep during the wait period.
- **Input validation**: Strict regex + future check + 7-day cap.
- **`at` daemon**: Not used — sleep-based approach avoids this entirely.

## Open Questions

- Should the /overnight skill display any context about the user's current usage or last reset time to help them choose a scheduling time, or just prompt for the time directly?
