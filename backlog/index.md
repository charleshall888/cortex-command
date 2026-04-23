# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 128 | Install pre-commit hook rejecting main commits during overnight sessions | backlog | critical | feature | — | 126 | — |
| 82 | Adapt harness to Opus 4.7 (prompt delta + capability adoption) | backlog | high | epic | — | — | — |
| 100 | Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism | backlog | high | feature | 88 | 82 | — |
| 102 | Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations | backlog | high | feature | 115 | 101 | — |
| 103 | Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7) | backlog | high | feature | 115 | 101 | — |
| 104 | Instrument skill-name on dispatch_start for per-skill pipeline aggregates | backlog | high | feature | 115 | 101 | — |
| 105 | Extract /commit preflight into bin/commit-preflight | backlog | high | feature | 102, 103 | 101 | — |
| 112 | Migrate overnight-schedule to a LaunchAgent-based scheduler | in_progress | high | feature | — | — | — |
| 113 | Distribute cortex-command as cortex CLI + plugin marketplace | backlog | high | epic | — | — | — |
| 114 | Build cortex CLI skeleton with uv tool install entry point | backlog | high | feature | — | 113 | — |
| 115 | Rebuild overnight runner under cortex CLI | backlog | high | feature | 114, 117 | 113 | — |
| 116 | Build MCP control-plane server with versioned runner IPC contract | backlog | high | feature | 115 | 113 | — |
| 117 | Build cortex setup subcommand and retire shareable-install scaffolding | backlog | high | feature | 114 | 113 | — |
| 118 | Ship curl | sh bootstrap installer for cortex-command | backlog | high | feature | 114, 117 | 113 | — |
| 120 | Publish cortex-interactive plugin (non-runner skills + hooks + bin utilities) | backlog | high | feature | 114, 117 | 113 | — |
| 121 | Publish cortex-overnight-integration plugin (overnight skill + runner hooks) | backlog | high | feature | 115, 116, 120 | 113 | — |
| 122 | Publish plugin marketplace manifest for cortex-command | backlog | high | feature | 115, 116, 117, 120, 121 | 113 | — |
| 123 | Lifecycle skill gracefully degrades autonomous-worktree option when runner absent | backlog | high | feature | 120 | 113 | — |
| 135 | Shared git index race between parallel Claude sessions causes wrong files to land in commits | backlog | high | bug | — | — | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 86 | Extend output-floors.md with M1 Subagent Disposition section | backlog | medium | feature | 85 | 82 | — |
| 92 | Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1) | backlog | medium | feature | — | 82 | — |
| 101 | Extract deterministic tool-call sequences into agent-invokable scripts | backlog | medium | epic | — | — | — |
| 106 | Extract morning-review deterministic sequences (C11-C15 bundle) | backlog | medium | feature | 102, 103 | 101 | — |
| 107 | Extract /dev epic-map parse into bin/build-epic-map | backlog | medium | feature | 102, 103 | 101 | — |
| 108 | Extract /backlog pick ready-set into bin/backlog-ready | backlog | medium | feature | 102, 103 | 101 | — |
| 109 | Extract /refine resolution into bin/resolve-backlog-item with bailout | backlog | medium | feature | 102, 103 | 101 | — |
| 110 | Unify lifecycle phase detection around claude.common with statusline exception | backlog | medium | feature | 102, 103 | 101 | — |
| 111 | Extract overnight orchestrator-round state read into bin/orchestrator-context | backlog | medium | feature | 104 | 101 | — |
| 119 | Add cortex init per-repo scaffolder for lifecycle/backlog/retros/requirements | backlog | medium | feature | 114 | 113 | — |
| 124 | Migration guide + script for existing symlink-based installs | backlog | medium | chore | 115, 116, 117, 118, 121, 122 | 113 | — |
| 137 | Harden /discovery citation grounding and external-endorsement value gating | backlog | medium | epic | — | — | — |
| 139 | Add vendor-endorsement value gating to /discovery decompose phase | backlog | medium | chore | — | 137 | — |
| 140 | Investigate daytime pipeline blockers: subprocess auth + task-selection re-runs completed tasks | in_progress | medium | bug | — | — | — |
| 90 | Adopt xhigh effort default for overnight lifecycle implement | backlog | low | feature | 92 | 82 | — |
| 91 | Decide and document post-4.7 policy settings (MUST-escalation, tone regression) | backlog | low | chore | 85 | 82 | — |
| 98 | Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release | backlog | low | feature | — | — | — |
| 125 | Homebrew tap as thin wrapper around the curl installer | backlog | low | feature | 118 | 113 | — |
| 133 | Evaluate implement.md:180 progress-tail narration under Opus 4.7 | backlog | low | feature | — | 82 | — |

## Refined


## Backlog

- **128** Install pre-commit hook rejecting main commits during overnight sessions
- **82** Adapt harness to Opus 4.7 (prompt delta + capability adoption)
- **100** Rewrite verification-mindset.md to positive-routing structure under 4.7 literalism
- **113** Distribute cortex-command as cortex CLI + plugin marketplace
- **114** Build cortex CLI skeleton with uv tool install entry point
- **135** Shared git index race between parallel Claude sessions causes wrong files to land in commits
- **8** Auto-rename Claude Code session to active lifecycle feature name
- **86** Extend output-floors.md with M1 Subagent Disposition section
- **92** Remove progress-update scaffolding from long-running prompts (DR-3 Wave 1)
- **101** Extract deterministic tool-call sequences into agent-invokable scripts
- **137** Harden /discovery citation grounding and external-endorsement value gating
- **139** Add vendor-endorsement value gating to /discovery decompose phase
- **91** Decide and document post-4.7 policy settings (MUST-escalation, tone regression)
- **98** Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release
- **133** Evaluate implement.md:180 progress-tail narration under Opus 4.7

## In-Progress

- **112** Migrate overnight-schedule to a LaunchAgent-based scheduler (in_progress)
- **140** Investigate daytime pipeline blockers: subprocess auth + task-selection re-runs completed tasks (in_progress)
