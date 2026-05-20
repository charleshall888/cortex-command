# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 135 | Shared git index race between parallel Claude sessions causes wrong files to land in commits | backlog | high | bug | — | — | — |
| 251 | Harness friction triage: distribution, contracts, slugs, gates | backlog | high | epic | — | — | — |
| 252 | Installation integrity layer: bash-to-entry-point migration, PATH self-test, install-version pin probe | refined | high | feature | — | 251 | ✓ |
| 258 | Surface aggregated signal on daytime-pipeline sandbox/EPERM cascade failures | backlog | high | feature | — | — | — |
| 260 | Revert TMPDIR worktree placement and restore .claude/worktrees/ default | refined | high | bug | — | — | ✓ |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 186 | Clarify-critic schema validator + warning-template runtime validator (per #178 R7 follow-on) | proposed | medium | feature | — | 178 | — |
| 248 | Convert bin/cortex-* and skill-embedded python3 -c callsites to use the cortex CLI | backlog | medium | feature | — | — | — |
| 250 | Lifecycle implement: auto-enter worktree via EnterWorktree (Approach A, deferred design surface) | backlog | medium | feature | — | — | — |
| 253 | Skill-prose to CLI argparse contract lint | backlog | medium | feature | — | 251 | — |
| 254 | Unified backlog/lifecycle slug resolver: extend to cortex-update-item consumer | backlog | medium | feature | — | 251 | — |
| 259 | Reconcile SessionStart lifecycle-phase summary against on-disk truth | backlog | medium | chore | — | — | — |
| 156 | Make cortex-check-parity context-aware (skip tokens inside fenced code blocks) | deferred | low | feature | — | — | — |
| 205 | Auto-derive lifecycle slug from prose-style invocation args | foo | low | enhancement | — | — | ✓ |
| 247 | Offer consolidation clusters before R15 gate in discovery decompose | backlog | low | feature | — | — | — |
| 257 | Make cortex-update-item accept --flag value syntax for consistency with sibling CLIs | backlog | low | chore | — | — | — |

## Refined

- **252** Installation integrity layer: bash-to-entry-point migration, PATH self-test, install-version pin probe
- **260** Revert TMPDIR worktree placement and restore .claude/worktrees/ default

## Backlog

- **135** Shared git index race between parallel Claude sessions causes wrong files to land in commits
- **251** Harness friction triage: distribution, contracts, slugs, gates
- **258** Surface aggregated signal on daytime-pipeline sandbox/EPERM cascade failures
- **248** Convert bin/cortex-* and skill-embedded python3 -c callsites to use the cortex CLI
- **250** Lifecycle implement: auto-enter worktree via EnterWorktree (Approach A, deferred design surface)
- **253** Skill-prose to CLI argparse contract lint
- **254** Unified backlog/lifecycle slug resolver: extend to cortex-update-item consumer
- **259** Reconcile SessionStart lifecycle-phase summary against on-disk truth
- **247** Offer consolidation clusters before R15 gate in discovery decompose
- **257** Make cortex-update-item accept --flag value syntax for consistency with sibling CLIs

## In-Progress


## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
