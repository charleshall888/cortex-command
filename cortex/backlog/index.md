# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 228 | Wire daytime dispatch through cortex CLI + MCP with launchd detachment | refined | high | feature | — | — | ✓ |
| 237 | Swap daytime autonomous for worktree-interactive implement mode | backlog | high | epic | — | — | — |
| 238 | Swap implement-phase preflight option 2 to worktree-interactive | refined | high | feature | 240 | 237 | ✓ |
| 240 | Implement Variant A end-to-end (interaction model + PR-creation hook) | backlog | high | feature | — | 237 | — |
| 246 | Remove daytime autonomous pipeline and cancel #228/#230 | backlog | high | chore | 238, 240 | 237 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 186 | Clarify-critic schema validator + warning-template runtime validator (per #178 R7 follow-on) | proposed | medium | feature | — | 178 | — |
| 209 | Lead refine §4 complexity-value gate with recommended option + rationale | in_progress | medium | chore | — | — | ✓ |
| 211 | R8 should track installed-wheel-commit, not CWD-working-tree HEAD (#146 follow-up) | superseded | medium | bug | — | — | — |
| 212 | CLI_PIN drift lint (#146 hygiene) | superseded | medium | chore | — | — | — |
| 235 | Trigger cortex CLI reinstall at SessionStart on CLI_PIN drift | refined | medium | feature | — | — | ✓ |
| 248 | Convert bin/cortex-* and skill-embedded python3 -c callsites to use the cortex CLI | backlog | medium | feature | — | — | — |
| 156 | Make cortex-check-parity context-aware (skip tokens inside fenced code blocks) | deferred | low | feature | — | — | — |
| 247 | Offer consolidation clusters before R15 gate in discovery decompose | backlog | low | feature | — | — | — |

## Refined

- **228** Wire daytime dispatch through cortex CLI + MCP with launchd detachment
- **235** Trigger cortex CLI reinstall at SessionStart on CLI_PIN drift

## Backlog

- **237** Swap daytime autonomous for worktree-interactive implement mode
- **240** Implement Variant A end-to-end (interaction model + PR-creation hook)
- **248** Convert bin/cortex-* and skill-embedded python3 -c callsites to use the cortex CLI
- **247** Offer consolidation clusters before R15 gate in discovery decompose

## In-Progress

- **209** Lead refine §4 complexity-value gate with recommended option + rationale (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
