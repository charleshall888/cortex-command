# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 82 | Adapt harness to Opus 4.7 (prompt delta + capability adoption) | backlog | high | epic | — | — | — |
| 83 | Run /claude-api migrate to opus-4-7 on throwaway branch and report diff | refined | high | spike | — | 82 | ✓ |
| 84 | Verify claude/reference/*.md conditional-loading behavior under Opus 4.7 | in_progress | high | spike | — | 82 | ✓ |
| 85 | Audit dispatch-skill prompts and reference docs for 4.7 at-risk patterns | backlog | high | feature | 83, 84 | 82 | — |
| 93 | Modernize lifecycle implement-phase pre-flight options | backlog | high | epic | — | — | — |
| 94 | Fix daytime pipeline worktree atomicity and stderr logging | backlog | high | feature | — | 93 | — |
| 95 | Replace daytime log-sentinel classification with structured result file | backlog | high | feature | — | 93 | — |
| 96 | Add uncommitted-changes guard to lifecycle implement-phase pre-flight | backlog | high | feature | — | 93 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 86 | Extend output-floors.md with M1 Subagent Disposition section | backlog | medium | feature | 85 | 82 | — |
| 87 | Instrument events.log aggregation for turns and cost per tier | in_progress | medium | feature | — | 82 | — |
| 88 | Collect 4.7 baseline rounds and snapshot the aggregated data | backlog | medium | feature | 87 | 82 | — |
| 92 | Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1) | backlog | medium | feature | 88 | 82 | — |
| 97 | Remove single-agent worktree dispatch and flip recommended default to current branch | backlog | medium | feature | 96 | 93 | — |
| 89 | Measure xhigh vs high effort cost delta on representative task | backlog | low | spike | 87 | 82 | — |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | backlog | low | feature | 89, 92 | 82 | — |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | backlog | low | chore | 85 | 82 | — |

## Refined

- **83** Run /claude-api migrate to opus-4-7 on throwaway branch and report diff

## Backlog

- **82** Adapt harness to Opus 4.7 (prompt delta + capability adoption)
- **93** Modernize lifecycle implement-phase pre-flight options
- **94** Fix daytime pipeline worktree atomicity and stderr logging
- **95** Replace daytime log-sentinel classification with structured result file
- **96** Add uncommitted-changes guard to lifecycle implement-phase pre-flight
- **8** Auto-rename Claude Code session to active lifecycle feature name

## In-Progress

- **84** Verify claude/reference/*.md conditional-loading behavior under Opus 4.7 (in_progress)
- **87** Instrument events.log aggregation for turns and cost per tier (in_progress)
