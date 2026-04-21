# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 82 | Adapt harness to Opus 4.7 (prompt delta + capability adoption) | backlog | high | epic | — | — | — |
| 83 | Run /claude-api migrate to opus-4-7 on throwaway branch and report diff | refined | high | spike | — | 82 | ✓ |
| 85 | Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns | refined | high | feature | 83 | 82 | ✓ |
| 93 | Modernize lifecycle implement-phase pre-flight options | backlog | high | epic | — | — | — |
| 94 | Fix daytime pipeline worktree atomicity and stderr logging | refined | high | feature | — | 93 | ✓ |
| 95 | Replace daytime log-sentinel classification with structured result file | refined | high | feature | — | 93 | ✓ |
| 96 | Add uncommitted-changes guard to lifecycle implement-phase pre-flight | refined | high | feature | — | 93 | ✓ |
| 100 | Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism | backlog | high | feature | 88 | 82 | — |
| 102 | Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations | backlog | high | feature | — | 101 | — |
| 103 | Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7) | backlog | high | feature | — | 101 | — |
| 104 | Instrument skill-name on dispatch_start for per-skill pipeline aggregates | backlog | high | feature | — | 101 | — |
| 105 | Extract /commit preflight into bin/commit-preflight | backlog | high | feature | 102, 103 | 101 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 86 | Extend output-floors.md with M1 Subagent Disposition section | backlog | medium | feature | 85 | 82 | — |
| 88 | Collect 4.7 baseline rounds and snapshot the aggregated data | refined | medium | feature | 99 | 82 | ✓ |
| 92 | Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1) | backlog | medium | feature | 88 | 82 | — |
| 97 | Remove single-agent worktree dispatch and flip recommended default to current branch | backlog | medium | feature | 96 | 93 | — |
| 99 | Operator gate: #088 baseline measurement window is complete | backlog | medium | task | — | 82 | — |
| 101 | Extract deterministic tool-call sequences into agent-invokable scripts | backlog | medium | epic | — | — | — |
| 106 | Extract morning-review deterministic sequences (C11-C15 bundle) | backlog | medium | feature | 102, 103 | 101 | — |
| 107 | Extract /dev epic-map parse into bin/build-epic-map | backlog | medium | feature | 102, 103 | 101 | — |
| 108 | Extract /backlog pick ready-set into bin/backlog-ready | backlog | medium | feature | 102, 103 | 101 | — |
| 109 | Extract /refine resolution into bin/resolve-backlog-item with bailout | backlog | medium | feature | 102, 103 | 101 | — |
| 110 | Unify lifecycle phase detection around claude.common with statusline exception | backlog | medium | feature | 102, 103 | 101 | — |
| 111 | Extract overnight orchestrator-round state read into bin/orchestrator-context | backlog | medium | feature | 104 | 101 | — |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | backlog | low | feature | 92 | 82 | — |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | backlog | low | chore | 85 | 82 | — |
| 98 | Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release | backlog | low | feature | — | — | — |

## Refined

- **83** Run /claude-api migrate to opus-4-7 on throwaway branch and report diff
- **94** Fix daytime pipeline worktree atomicity and stderr logging
- **95** Replace daytime log-sentinel classification with structured result file
- **96** Add uncommitted-changes guard to lifecycle implement-phase pre-flight

## Backlog

- **82** Adapt harness to Opus 4.7 (prompt delta + capability adoption)
- **93** Modernize lifecycle implement-phase pre-flight options
- **102** Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations
- **103** Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7)
- **104** Instrument skill-name on dispatch_start for per-skill pipeline aggregates
- **8** Auto-rename Claude Code session to active lifecycle feature name
- **99** Operator gate: #088 baseline measurement window is complete
- **101** Extract deterministic tool-call sequences into agent-invokable scripts
- **98** Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release

## In-Progress

