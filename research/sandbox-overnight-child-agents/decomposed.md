# Decomposition: sandbox-overnight-child-agents

## Epic

- **Backlog ID**: 162
- **Title**: Sandbox overnight agents at the OS layer

## Work Items

| ID  | Title                                                                                                                                       | Priority | Size | Depends On       |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ---- | ---------------- |
| 163 | Apply per-spawn `sandbox.filesystem.denyWrite` at overnight orchestrator spawn                                                              | critical | M    | —                |
| 164 | Add sandbox-violation tracker hook for PostToolUse(Bash)                                                                                    | medium   | S    | 163              |
| 165 | Add Linux bubblewrap preflight and `failIfUnavailable` for overnight sandbox                                                                | low      | S    | 163              |
| 166 | Convert `dispatch.py` granular sandbox shape to simplified, fix cross-repo allowlist inversion at `feature_executor.py:603`                 | high     | M    | 163              |
| 167 | Document overnight sandbox threat-model boundary and Linux setup prereqs                                                                    | low      | S    | 163, 164, 165, 166 |
| 168 | Tighten overnight sandbox from deny-list to narrower allowOnly (deferred)                                                                   | low      | M    | 163, 164         |

## Suggested Implementation Order

1. **#163** (load-bearing, critical) — establishes the per-spawn `--settings` JSON pattern at `runner.py:905`. Includes empirical acceptance test that gates the entire epic.
2. **#166** (high, parallelizable with #164/#165) — fixes the two compounded bugs in the per-feature dispatch path (silent-no-op shape + cross-repo allowlist inversion). Once #163 establishes the simplified-shape pattern, #166 is a near-mechanical sibling change.
3. **#164** (medium) — observability hook. Adds telemetry to detect violations once #163 is enforcing.
4. **#165** (low) — Linux preflight. Cross-platform completeness.
5. **#167** (low) — docs sweep. Best run after #163/#164/#165/#166 land so all referenced behavior is in place.
6. **#168** (deferred) — V1c hybrid tightening. Activate only if #164's telemetry justifies it.

## Key Design Decisions

- **No epic consolidation triggered**: The 6 children touch different file sets (`runner.py:905` vs `dispatch.py:546` vs new hook vs platform preflight vs docs vs future hardening). Each delivers independent testable value. Decomposition records: same-file overlap absent; no-standalone-value-prerequisite absent (each child has independent observable value).
- **Cross-repo enumeration in V1 (not deferred)**: Per critical-review R4-B, OQ3's deferral relied on a non-existent safety net (`feature_executor.py:603` admits home repo into cross-repo allowlists). Enumeration is in #163 scope; the underlying allowlist-inversion bug is in #166.
- **Schema choice (simplified `filesystem.denyWrite`, NOT granular `write.denyWithinAllow`)**: Per DR-1 revision 3 + documentary verification of `@anthropic-ai/sandbox-runtime`. Drives both #163 (new) and #166 (conversion of existing dispatch.py shape).
- **No `--sandbox` CLI flag pairing**: Reviewer 3's revision-2 recommendation to pair with `--sandbox` was based on a misread of issue #32814; no such flag exists in v2.1.126. Activation is `sandbox.enabled: true` in JSON.
- **DR-7 acceptance-test gate (V1 ticket AC)**: Documentary verification (sandbox-runtime + production configs + cortex's own user settings.json) reduced residual structural risk enough to convert from pre-decompose blocker to V1 acceptance test. Pre-flight human empirical run remains recommended-not-blocking in #163's spec phase.

## R2 Flag Disposition

No items flagged. All Value statements have codebase-grounded `[file:line]` citations and corresponding research-side substantiation. The `[premise-unverified: not-searched]` marker about Linux user demographics (DR-4) was reframed during decompose so #165's Value rests on the codebase-local fact (silent-fall-open of V1 enforcement on Linux), not on the user-demographics premise.

## Created Files

- `backlog/162-sandbox-overnight-agents-at-the-os-layer.md` — Epic
- `backlog/163-apply-per-spawn-sandbox-denywrite-at-overnight-orchestrator-spawn.md` — V1 (load-bearing)
- `backlog/164-add-sandbox-violation-tracker-hook-for-posttooluse-bash.md` — V2 (observability)
- `backlog/165-add-linux-bubblewrap-preflight-and-failifunavailable-for-overnight-sandbox.md` — V3 (cross-platform)
- `backlog/166-convert-dispatch-sandbox-shape-and-fix-cross-repo-allowlist-inversion.md` — V4 (per-feature audit)
- `backlog/167-document-overnight-sandbox-threat-model-and-linux-setup-prereqs.md` — V5 (docs)
- `backlog/168-tighten-overnight-sandbox-from-deny-list-to-narrower-allowonly.md` — V6 (deferred hardening)
