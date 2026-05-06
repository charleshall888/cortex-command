# Backlog Index

| ID | Title | Status | Priority | Type | Blocked By | Parent | Spec |
|-----|-------|--------|----------|------|------------|--------|------|
| 165 | Repo spring cleaning: share-readiness for installer audience | backlog | high | epic | — | — | — |
| 172 | Lifecycle skill + artifact densification + vertical-planning adoption | backlog | high | epic | — | — | — |
| 173 | Fix duplicated-block bug in refine/SKILL.md + 5 stale skill references | backlog | high | chore | — | 172 | — |
| 174 | Collapse byte-identical refine/references files (orchestrator-review.md + specify.md → lifecycle canonical) | backlog | high | chore | — | 172 | — |
| 175 | Promote refine/references/clarify-critic.md to canonical with schema-aware migration | backlog | high | feature | — | 172 | — |
| 176 | Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md | backlog | high | feature | — | 172 | — |
| 177 | Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression) | backlog | high | chore | — | 172 | — |
| 182 | Vertical-planning adoption as REPLACEMENT: ## Outline absorbs Scope Boundaries + Verification Strategy; ## Risks preserves Veto Surface; tier-conditional ## Acceptance | backlog | high | feature | 174, 175, 176 | 172 | — |
| 8 | Auto-rename Claude Code session to active lifecycle feature name | backlog | medium | feature | anthropics/claude-code#34243 | — | — |
| 169 | Fix archive predicate and sweep lifecycle/ and research/ dirs | in_progress | medium | feature | 166, 168 | 165 | — |
| 170 | Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh | backlog | medium | bug | — | — | — |
| 171 | Remove /fresh, /evolve, and /retro skills | in_progress | medium | chore | — | — | ✓ |
| 178 | Apply skill-creator-lens improvements (TOCs, descriptions + disambiguators, per-MUST OQ3 disposition, U1/U2/U4 HOW trims, frontmatter symmetry) | backlog | medium | chore | — | 172 | — |
| 179 | Extract conditional content blocks to references/ (a-b-downgrade-rubric + implement-daytime — trimmed scope) | backlog | medium | chore | 174, 175, 176, 177 | 172 | — |
| 180 | Artifact template cleanups (Architectural Pattern optional, index.md body-trim + frontmatter preserved, D4 Open Decisions optional) | backlog | medium | chore | — | 172 | — |
| 181 | Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget) | backlog | medium | chore | — | 172 | — |
| 183 | Migrate Gate 1 (research→specify Open-Questions escalation) to Python hook; remove Gate 2 entirely | backlog | medium | feature | 174, 177 | 172 | — |
| 184 | Merge clarify and research lifecycle phases into single investigate phase | backlog | medium | feature | — | — | — |
| 185 | Audit /cortex-core:research skill output shape for token waste in research.md sections | backlog | medium | chore | — | — | — |
| 156 | Make cortex-check-parity context-aware (skip tokens inside fenced code blocks) | deferred | low | feature | — | — | — |
| 142 | Multi-session host concurrency registry for cortex overnight | backlog | contingent | feature | — | — | — |

## Refined


## Backlog

- **165** Repo spring cleaning: share-readiness for installer audience
- **172** Lifecycle skill + artifact densification + vertical-planning adoption
- **173** Fix duplicated-block bug in refine/SKILL.md + 5 stale skill references
- **174** Collapse byte-identical refine/references files (orchestrator-review.md + specify.md → lifecycle canonical)
- **175** Promote refine/references/clarify-critic.md to canonical with schema-aware migration
- **176** Lifecycle adopts cortex-resolve-backlog-item, delete refine/references/clarify.md
- **177** Trim verbose lifecycle skill content (implement.md §1a + plan.md §1b.b + SKILL.md gate compression)
- **170** Fix pre-existing scan-lifecycle test failures in tests/test_hooks.sh
- **178** Apply skill-creator-lens improvements (TOCs, descriptions + disambiguators, per-MUST OQ3 disposition, U1/U2/U4 HOW trims, frontmatter symmetry)
- **180** Artifact template cleanups (Architectural Pattern optional, index.md body-trim + frontmatter preserved, D4 Open Decisions optional)
- **181** Skill-design test infrastructure (description snapshots + cross-skill handoff + ref-file path resolution + skill-size budget)
- **184** Merge clarify and research lifecycle phases into single investigate phase
- **185** Audit /cortex-core:research skill output shape for token waste in research.md sections
- **142** Multi-session host concurrency registry for cortex overnight

## In-Progress

- **169** Fix archive predicate and sweep lifecycle/ and research/ dirs (in_progress)
- **171** Remove /fresh, /evolve, and /retro skills (in_progress)

## Warnings

- **8**: external blocker (anthropics/claude-code#34243)
