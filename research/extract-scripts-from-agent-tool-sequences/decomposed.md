# Decomposition: extract-scripts-from-agent-tool-sequences

## Epic
- **Backlog ID**: 101
- **Title**: Extract deterministic tool-call sequences into agent-invokable scripts

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 102 | Ship DR-5 SKILL.md-to-bin parity linter with zero existing violations | high | S-M | — |
| 103 | Add runtime adoption telemetry via PreToolUse Bash hook matcher (DR-7) | high | S | — |
| 104 | Instrument skill-name on dispatch_start for per-skill pipeline aggregates | high | S | — |
| 105 | Extract /commit preflight into bin/commit-preflight (C1) | high | S | 102, 103 |
| 106 | Extract morning-review deterministic sequences (C11–C15 bundle) | medium | M | 102, 103 |
| 107 | Extract /dev epic-map parse into bin/build-epic-map (C4) | medium | S | 102, 103 |
| 108 | Extract /backlog pick ready-set into bin/backlog-ready (C7) | medium | S | 102, 103 |
| 109 | Extract /refine resolution into bin/resolve-backlog-item with bailout (C5) | medium | S | 102, 103 |
| 110 | Unify lifecycle phase detection around claude.common with statusline exception (C2+C3) | medium | L | 102, 103 |
| 111 | Extract overnight orchestrator-round state read into bin/orchestrator-context (C8) | medium | M | 104 |

## Suggested Implementation Order

1. **102 + 103 + 104** in parallel (S-effort, no predecessors). Together cover all three adoption-failure modes (day-one, drift, runtime non-invocation) plus pipeline observability.
2. **105** — fastest visible win; `/commit` is the hottest interactive path.
3. **106, 107, 108, 109** — S-wave interactive extractions.
4. **110** — L refactor depending on 102+103 for safety signals; preserves statusline bash exception per DR-6.
5. **111** — pipeline-side extraction; confirms ROI with 104's aggregator before closing.

## Key Design Decisions

### Consolidation — 103 (retrofit) merged into 102 (linter)
The original decomposition had a separate "retrofit existing under-used scripts" ticket sequenced after the linter ships. Consolidated into 102 because:
- Shipping a linter with existing violations requires either blanket allowlisting (defeats the enforcement point) or landing the linter red (tech debt from day one).
- The retrofit IS the linter's day-one violation list — same surface, same acceptance criterion ("linter runs clean").
- Per Decompose §3(b), the retrofit had no standalone value without the linter.

### Consolidation — C11–C15 bundled into ticket 106
Rejected the alternative of one ticket per candidate:
- C11+C12+C13 all modify `skills/morning-review/SKILL.md` (same-file overlap per Decompose §3(a)).
- All five candidates fire during a single morning-review invocation; the acceptance test is one morning-review run.
- CR2 flagged the cross-file edges (C14 → `bin/git-sync-rebase.sh`; C15 → `skills/lifecycle/references/complete.md`). Trade-off accepted; split may happen at plan phase if scope proves too large.

### Not consolidated — 104/105/106/107/108/109
Single-skill S extractions across distinct skills and distinct `bin/` targets. Zero file overlap. Combining would create a bag-of-extractions ticket with no coherent acceptance criterion.

### Not consolidated — 102 and 103
Both are adoption infrastructure but cover different failure modes (static lint vs runtime hook), touch different files, and each has standalone value. Ship in parallel ≠ combine.

## Scope Boundaries

### In scope for this epic
- 15 candidates (C1–C15) from discovery research.
- Static + runtime enforcement (DR-5 + DR-7).
- Pipeline observability instrumentation (ticket 104).

### Out of scope / deferred
- **C6** (daytime polling loop) — blocked on ticket #94's daytime subprocess-lifecycle restructure.
- **C9** (plan-gen dispatch) — judgment-at-endpoints; revisit after 104 pipeline data.
- **C10** (merge-conflict classify + dispatch) — judgment-interleaved, not a collapse candidate.
- **Subagent dispatch in `/research`, `/critical-review`, `/discovery`** — mechanical shell around judgment synthesis; future candidate after first wave lands.

## Created Files

- `backlog/101-extract-deterministic-tool-call-sequences-into-agent-invokable-scripts.md` — Epic
- `backlog/102-ship-dr-5-skillmd-to-bin-parity-linter-with-zero-existing-violations.md`
- `backlog/103-add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7.md`
- `backlog/104-instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates.md`
- `backlog/105-extract-commit-preflight-into-bin-commit-preflight.md`
- `backlog/106-extract-morning-review-deterministic-sequences-c11-c15-bundle.md`
- `backlog/107-extract-dev-epic-map-parse-into-bin-build-epic-map.md`
- `backlog/108-extract-backlog-pick-ready-set-into-bin-backlog-ready.md`
- `backlog/109-extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout.md`
- `backlog/110-unify-lifecycle-phase-detection-around-claudecommon-with-statusline-exception.md`
- `backlog/111-extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context.md`
