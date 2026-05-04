# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 162 | Sandbox overnight agents at the OS layer | refined | critical | epic | — | — | — |
| 163 | Apply per-spawn sandbox.filesystem.denyWrite at overnight orchestrator spawn | refined | critical | feature | — | 162 | — |
| 158 | Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight) | backlog | high | epic | — | — | — |
| 159 | Tighten §1b plan-agent prompt to require strategy-level distinction | backlog | high | chore | 160 | 158 | ✓ |
| 160 | Build shared synthesizer for critical-tier dual-plan flow (interactive + overnight) | in_progress | high | feature | — | 158 | ✓ |
| 166 | Convert dispatch.py granular sandbox shape to simplified, fix cross-repo allowlist inversion at feature_executor.py:603 | refined | high | feature | 163 | 162 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 161 | Add parent-epic alignment check to refine's clarify-critic | in_progress | medium | feature | — | — | — |
| 164 | Add sandbox-violation tracker hook for PostToolUse(Bash) | refined | medium | feature | 163 | 162 | — |
| 156 | Make cortex-check-parity context-aware (skip tokens inside fenced code blocks) | deferred | low | feature | — | — | — |
| 165 | Add Linux bubblewrap preflight and failIfUnavailable for overnight sandbox | refined | low | feature | 163 | 162 | — |
| 167 | Document overnight sandbox threat-model boundary and Linux setup prereqs | refined | low | feature | 163, 164, 165, 166 | 162 | — |
| 168 | Tighten overnight sandbox from deny-list to narrower allowOnly | deferred | low | feature | 163, 164 | 162 | — |
| 142 | Multi-session host concurrency registry for cortex overnight | backlog | contingent | feature | — | — | — |

## Refined

- **162** Sandbox overnight agents at the OS layer
- **163** Apply per-spawn sandbox.filesystem.denyWrite at overnight orchestrator spawn

## Backlog

- **158** Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight)
- **142** Multi-session host concurrency registry for cortex overnight

## In-Progress

- **160** Build shared synthesizer for critical-tier dual-plan flow (interactive + overnight) (in_progress)
- **161** Add parent-epic alignment check to refine's clarify-critic (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
