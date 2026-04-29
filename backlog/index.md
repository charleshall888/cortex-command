# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 128 | Install pre-commit hook rejecting main commits during overnight sessions | refined | critical | feature | — | 126 | ✓ |
| 82 | Adapt harness to Opus 4.7 (prompt delta + capability adoption) | backlog | high | epic | — | — | — |
| 112 | Migrate overnight-schedule to a LaunchAgent-based scheduler | in_progress | high | feature | — | — | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 149 | Fix runner.pid takeover race in ipc.py:write_runner_pid | refined | medium | bug | — | — | ✓ |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | refined | low | feature | — | 82 | ✓ |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | refined | low | chore | — | 82 | ✓ |
| 98 | Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release | refined | low | feature | — | — | ✓ |
| 133 | Evaluate implement.md:119 progress-tail narration under Opus 4.7 | refined | low | feature | — | 82 | ✓ |
| 142 | Multi-session host concurrency registry for cortex overnight | backlog | contingent | feature | — | — | — |

## Refined

- **128** Install pre-commit hook rejecting main commits during overnight sessions
- **149** Fix runner.pid takeover race in ipc.py:write_runner_pid
- **90** Adopt xhigh effort default for overnight lifecycle implement
- **91** Decide and document post-4.7 policy settings (MUST-escalation, tone regression)
- **98** Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release
- **133** Evaluate implement.md:119 progress-tail narration under Opus 4.7

## Backlog

- **82** Adapt harness to Opus 4.7 (prompt delta + capability adoption)
- **142** Multi-session host concurrency registry for cortex overnight

## In-Progress

- **112** Migrate overnight-schedule to a LaunchAgent-based scheduler (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
