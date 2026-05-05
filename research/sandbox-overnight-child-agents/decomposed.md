# Decomposition: sandbox-overnight-child-agents

## Epic

- **Backlog ID**: 162
- **Title**: Sandbox overnight agents at the OS layer

## Work Items

| ID  | Title                                                                                                              | Priority | Size | Depends On |
| --- | ------------------------------------------------------------------------------------------------------------------ | -------- | ---- | ---------- |
| 163 | Apply per-spawn `sandbox.filesystem.denyWrite` at all overnight spawn sites (orchestrator + per-feature dispatch)  | critical | L    | —          |
| 164 | Add sandbox-violation tracker hook for PostToolUse(Bash)                                                           | medium   | S    | 163        |

## Suggested Implementation Order

1. **#163** (load-bearing, critical) — establishes per-spawn `--settings` JSON pattern at `runner.py:905`, converts `dispatch.py:546`'s silent-no-op shape, fixes `feature_executor.py:603` cross-repo inversion, lands threat-model + design docs. One unified empirical acceptance test gates the entire epic.
2. **#164** (medium) — observability hook. Adds telemetry to detect violations once #163 is enforcing.

## Key Design Decisions

- **Aggressive consolidation**: Original decomposition had 6 children; restructured to 2 per user direction. Rationale:
  - **Linux preflight + `failIfUnavailable`** — dropped. No Linux/WSL2 user base for overnight today.
  - **Standalone docs ticket** — folded into #163 and #164. Each implementation ticket owns its own documentation surface; no separate docs sweep.
  - **Per-feature dispatch audit (`dispatch.py:546` shape conversion + `feature_executor.py:603` cross-repo inversion fix)** — folded into #163. Both spawn sites apply the same shape pattern with the same kernel-layer EPERM acceptance test; bundling them avoids artificial sequencing across spawn sites.
  - **Allowlist tightening (V1c)** — dropped as a pre-filed placeholder. Re-discover from #164's telemetry if data shows the deny-list is insufficient.
- **Schema choice (simplified `filesystem.denyWrite`, NOT granular `write.denyWithinAllow`)**: per DR-1 revision 3 + documentary verification of `@anthropic-ai/sandbox-runtime`. Drives both spawn-site applications inside #163.
- **Cross-repo enumeration in scope**: per critical-review R4-B, OQ3's deferral relied on a non-existent safety net (`feature_executor.py:603` admits home repo into cross-repo allowlists). Enumeration is in #163.
- **No `--sandbox` CLI flag pairing**: revision-2 recommendation retracted; no such flag exists in v2.1.126.
- **DR-7 acceptance-test gate (#163 ticket AC)**: documentary verification reduced residual structural risk enough to convert from pre-decompose blocker to ticket acceptance test. Pre-flight human empirical run remains recommended-not-blocking in #163's spec phase.

## R2 Flag Disposition

No items flagged. All Value statements have codebase-grounded `[file:line]` citations and corresponding research-side substantiation.

## Created Files

- `backlog/162-sandbox-overnight-agents-at-the-os-layer.md` — Epic
- `backlog/163-apply-per-spawn-sandbox-denywrite-at-all-overnight-spawn-sites.md` — #163 (load-bearing, absorbs original #166 + #167 docs)
- `backlog/164-add-sandbox-violation-tracker-hook-for-posttooluse-bash.md` — #164 (observability, includes its own docs subsection)

## Restructure history

Initial decomposition (1 epic + 6 children) was restructured per user direction into 1 epic + 2 children:
- Dropped: Linux preflight (#165), allowlist tightening (#168)
- Folded: per-feature dispatch audit (#166) into #163; standalone docs (#167) into #163 and #164
- Result: tighter scope, shippable as 2 PRs (load-bearing implementation + observability follow-up).
