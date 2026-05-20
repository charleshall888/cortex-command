---
schema_version: "1"
topic: harness-friction-triage
decomposed: 2026-05-20
decomposition_verdict: epic-plus-children
---

# Decomposition: harness-friction-triage

## Epic

- **Backlog ID**: 251
- **Title**: Harness friction triage: distribution, contracts, slugs, gates

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 252 | Installation integrity layer | high | L (M-coded in research; honest sizing is L) | Coordinates with #235 (`refined`) for SessionStart-hook |
| 253 | Skill-prose ↔ CLI argparse contract lint | medium | M | — |
| 254 | Unified slug resolver: extend to `cortex-update-item` | medium | M | 252 (closes `install_guard` boundary per DR4) |
| 255 | Gate-policy taxonomy + critical-review gate fixes | high | M+ | — |
| 256 | Fix `validate_brief` substring anchors | high | S | — |

## Suggested Implementation Order

The five children are independent for correctness and can ship in any order, but the user-visible payoff varies. Recommended sequence by value-per-effort:

1. **256 first** — S effort, immediate UX restoration. The brief-gen pipeline has a 0/7 production success rate; fixing the anchor sets makes the gate produce briefs instead of always falling back to the dense Architecture display.
2. **255 next** — M+ effort but contains one mechanical bug fix (under-root symlink scoping) that closes the recurring `/tmp/claude/` rejection on macOS. The verifier rename and `_adhoc/` auto-resolve are smaller wins; the taxonomy annotation is auditability-only.
3. **252 in parallel** — L effort, load-bearing. Closes the class of "command not found" bugs by promoting bash scripts to Python entry points and adding the SessionStart PATH self-test. Coordinates with ticket 235 for the install-version pin probe sub-deliverable. Plan phase should explicitly decompose into sub-tickets at the start.
4. **253 after 252's surface stabilizes** — M effort. Pre-commit lint that catches new contract drift. Depends on a stable argparse-introspection surface; landing it before 252's bash→entry-point migration risks lint coverage of a moving target.
5. **254 last** — M effort. Depends on 252 closing the `install_guard` boundary for the resolver (per DR4). Daily-life polish, not load-bearing.

## Reconciliation: fold-via-comment items

These 9 friction items fold into existing tickets rather than producing new ones. They are recorded here for downstream amendment routing:

- B1.1 (brief-gen failure) → comment on 227; 256 covers the root validator cause
- B1.5 (`cortex-check-prescriptive-prose` not on PATH) → comment on 208; 252 closes the gap
- B1.7 (`verify-reviewer-output` architectural drift) → already covered by 229
- OF1 / B2.5 (backlog-index race) → already covered by 135 (elevate priority)
- B2.1 (critical-review binary missing in plugin install) → comment on 235; 252 closes the wheel-tier surface
- B2.4 (`cortex-create-backlog-item --tags`) → comment on 233 with write-side counterpart
- B2.6 (PATH split user-bin vs plugin-cache) → comment on 235; 252 closes
- B2.9 (worktree-dispatch silent fallback) → already covered by 208
- B2.10 (lifecycle-event helper vs printf inconsistency) → comment on 248

## Policy decisions deferred

- B2.7 `[partial]` task counter semantics — lifecycle-policy question
- B2.8 reviewer agent vs strict Requirements schema — needs MUST-escalation evidence per CLAUDE.md before prescriptive-prompt fix; forgiving-parser route otherwise

## Out of scope

- OF2 stale `palette_editor.py` processes — user's own app, not cortex

## Created Files

- `cortex/backlog/251-harness-friction-triage-distribution-contracts-slugs-gates.md` — Epic
- `cortex/backlog/252-installation-integrity-layer-bash-to-entry-point-migration-path-self-test-install-version-pin-probe.md` — Installation integrity layer
- `cortex/backlog/253-skill-prose-to-cli-argparse-contract-lint.md` — Skill-prose contract lint
- `cortex/backlog/254-unified-backlog-lifecycle-slug-resolver-extend-to-cortex-update-item-consumer.md` — Unified slug resolver
- `cortex/backlog/255-gate-policy-taxonomy-and-critical-review-gate-fixes.md` — Gate-policy taxonomy + fixes
- `cortex/backlog/256-fix-validate-brief-substring-anchors-that-reject-natural-prose.md` — `validate_brief` substring anchors

## Index regen status

Deferred. The repo has uncommitted modifications to `cortex/backlog/205-*.md`, `index.json`, and `index.md` from a parallel session. Running `cortex-generate-backlog-index` now would regenerate the index against those modifications and either commit references to file content not in git (the race documented as friction item OF1) or overwrite the other session's work. A clean session should run the regen after the parallel work commits.
