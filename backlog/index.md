# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 165 | Repo spring cleaning: share-readiness for installer audience | backlog | high | epic | — | — | — |
| 172 | Lifecycle skill + artifact densification + vertical-planning adoption | backlog | high | epic | — | — | — |
| 175 | Promote refine/references/clarify-critic.md to canonical with schema-aware migration | backlog | high | feature | — | 172 | — |
| 177 | Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression) | backlog | high | chore | — | 172 | — |
| 182 | Vertical-planning adoption as REPLACEMENT: ## Outline absorbs Scope Boundaries + Verification Strategy; ## Risks preserves Veto Surface; tier-conditional ## Acceptance | backlog | high | feature | 175 | 172 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 169 | Fix archive predicate and sweep lifecycle/ and research/ dirs | in_progress | medium | feature | 166, 168 | 165 | — |
| 170 | Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh | backlog | medium | bug | — | — | — |
| 179 | Extract conditional content blocks to references/ (a-b-downgrade-rubric + implement-daytime — trimmed scope) | backlog | medium | chore | 175, 177 | 172 | — |
| 180 | Artifact template cleanups (Architectural Pattern optional, index.md body-trim + frontmatter preserved, D4 Open Decisions optional) | backlog | medium | chore | — | 172 | — |
| 181 | Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget) | refined | medium | chore | — | 172 | ✓ |
| 183 | Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook; remove Gate 2 entirely | backlog | medium | feature | 177 | 172 | — |
| 184 | Merge clarify and research lifecycle phases into single investigate phase | backlog | medium | feature | — | — | — |
| 185 | Audit /cortex-core:research skill output shape for token waste in research.md sections | backlog | medium | chore | — | — | — |
| 186 | Clarify-critic schema validator + warning-template runtime validator (per #178 R7 follow-on) | proposed | medium | feature | — | 178 | — |
| 156 | Make cortex-check-parity context-aware (skip tokens inside fenced code blocks) | deferred | low | feature | — | — | — |
| 142 | Multi-session host concurrency registry for cortex overnight | backlog | contingent | feature | — | — | — |

## Refined

- **181** Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)

## Backlog

- **165** Repo spring cleaning: share-readiness for installer audience
- **172** Lifecycle skill + artifact densification + vertical-planning adoption
- **175** Promote refine/references/clarify-critic.md to canonical with schema-aware migration
- **177** Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)
- **170** Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh
- **180** Artifact template cleanups (Architectural Pattern optional, index.md body-trim + frontmatter preserved, D4 Open Decisions optional)
- **184** Merge clarify and research lifecycle phases into single investigate phase
- **185** Audit /cortex-core:research skill output shape for token waste in research.md sections
- **142** Multi-session host concurrency registry for cortex overnight

## In-Progress

- **169** Fix archive predicate and sweep lifecycle/ and research/ dirs (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
