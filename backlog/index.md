# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 128 | Install pre-commit hook rejecting main commits during overnight sessions | backlog | critical | feature | — | 126 | — |
| 82 | Adapt harness to Opus 4.7 (prompt delta + capability adoption) | backlog | high | epic | — | — | — |
| 112 | Migrate overnight-schedule to a LaunchAgent-based scheduler | in_progress | high | feature | — | — | — |
| 135 | Shared git index race between parallel Claude sessions causes wrong files to land in commits | backlog | high | bug | — | — | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 86 | Extend output-floors.md with M1 Subagent Disposition section | backlog | medium | feature | 85 | 82 | — |
| 92 | Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1) | backlog | medium | feature | — | 82 | — |
| 101 | Extract deterministic tool-call sequences into agent-invokable scripts | backlog | medium | epic | — | — | — |
| 108 | Extract /backlog pick ready-set into bin/backlog-ready | in_progress | medium | feature | — | 101 | ✓ |
| 110 | Unify lifecycle phase detection around claude.common with statusline exception | backlog | medium | feature | — | 101 | — |
| 111 | Extract overnight orchestrator-round state read into bin/orchestrator-context | backlog | medium | feature | — | 101 | — |
| 141 | Non-editable wheel install support for cortex-command | backlog | medium | feature | — | — | — |
| 149 | Fix runner.pid takeover race in ipc.py:write_runner_pid | backlog | medium | bug | — | — | — |
| 151 | Resolve cortex_command.backlog packaged-dispatch dead branch in bin/cortex-* wrappers | backlog | medium | bug | — | — | — |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | backlog | low | feature | 92 | 82 | — |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | backlog | low | chore | 85 | 82 | — |
| 98 | Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release | backlog | low | feature | — | — | — |
| 133 | Evaluate implement.md:180 progress-tail narration under Opus 4.7 | backlog | low | feature | — | 82 | — |
| 142 | Multi-session host concurrency registry for cortex overnight | backlog | contingent | feature | — | — | — |

## Refined


## Backlog

- **128** Install pre-commit hook rejecting main commits during overnight sessions
- **82** Adapt harness to Opus 4.7 (prompt delta + capability adoption)
- **135** Shared git index race between parallel Claude sessions causes wrong files to land in commits
- **86** Extend output-floors.md with M1 Subagent Disposition section
- **92** Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1)
- **101** Extract deterministic tool-call sequences into agent-invokable scripts
- **110** Unify lifecycle phase detection around claude.common with statusline exception
- **111** Extract overnight orchestrator-round state read into bin/orchestrator-context
- **141** Non-editable wheel install support for cortex-command
- **149** Fix runner.pid takeover race in ipc.py:write_runner_pid
- **151** Resolve cortex_command.backlog packaged-dispatch dead branch in bin/cortex-* wrappers
- **91** Decide and document post-4.7 policy settings (MUST-escalation, tone regression)
- **98** Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release
- **133** Evaluate implement.md:180 progress-tail narration under Opus 4.7
- **142** Multi-session host concurrency registry for cortex overnight

## In-Progress

- **112** Migrate overnight-schedule to a LaunchAgent-based scheduler (in_progress)
- **108** Extract /backlog pick ready-set into bin/backlog-ready (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
