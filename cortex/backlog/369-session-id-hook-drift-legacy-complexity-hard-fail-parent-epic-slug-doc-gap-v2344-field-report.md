---
schema_version: "1"
uuid: 71aae6f6-9d18-4611-8dfb-a94b787e543c
title: Session-ID hook drift, legacy-complexity hard-fail, parent-epic slug doc gap (v2.34.4 field report)
status: complete
priority: medium
type: bug
created: 2026-07-06
updated: 2026-07-06
tags: ['hooks', 'lifecycle', 'refine', 'docs']
areas: ['hooks', 'skills']
---
## Why

Found during a live `/cortex-core:lifecycle` run in the wild-light repo (2026-07-06). Plugin and CLI were verified in sync — cortex-core plugin cache at commit `450bce0e` ("Release v2.34.4") and the uv-tool CLI reporting 2.34.4 — so none of these are version-skew artifacts: one is a real bug, one a fail-closed gap on legacy data, one a doc ambiguity. All three cost live-session time; the first silently corrupts a documented contract.

## Scope

**(1) `LIFECYCLE_SESSION_ID` is never set — empty `.session` files (bug).** lifecycle SKILL.md Step 2 registers the session by writing `$LIFECYCLE_SESSION_ID` to `cortex/lifecycle/{feature}/.session`, and `skills/lifecycle/references/concurrent-sessions.md` states it is "set by the SessionStart hook". But `hooks/hooks.json` registers only SessionStart / PreToolUse / WorktreeCreate / WorktreeRemove, and the SessionStart hook (`cortex-session-start-path-bootstrap.sh`) is a pure PATH bootstrap — nothing anywhere exports the variable. Every lifecycle session therefore writes an **empty** `.session` file, silently breaking the concurrent-session association and any consumer of the variable (e.g. `bin/cortex-invocation-report` references it). Related drift in the same doc: `.session` is described as "SessionEnd-cleaned", but no SessionEnd hook is registered, so stale files are also never cleaned. Fix direction: have the SessionStart hook emit `LIFECYCLE_SESSION_ID` via `CLAUDE_ENV_FILE` (the same contract the PATH bootstrap already uses) and add the SessionEnd cleaner — or correct both doc claims and give the skill a real derivation for the ID.

**(2) `cortex-refine emit-lifecycle-start` hard-fails on legacy `complexity: moderate` (exit 64).** Pre-two-tier backlog items (observed: wild-light #111, created 2026-03-28 with `complexity: moderate`) abort the lifecycle_start seed with `invalid complexity value 'moderate' (allowed: complex, simple)`, requiring manual frontmatter surgery before refine can proceed. This is inconsistent with the harness's own legacy-tolerance posture (clarify-critic.md's event-schema rule: readers MUST tolerate every prior shape forever). Fix direction: coerce legacy values with a stderr warning (`moderate` → `complex` is the conservative map per clarify.md §5's "when in doubt, prefer complex" — Clarify re-assesses and writes back anyway), or at minimum emit an actionable remediation naming the exact `cortex-update-item <slug> --complexity <value>` command.

**(3) `cortex-load-parent-epic <child-slug>` — ambiguous slug kind in clarify-critic.md.** The Parent Epic Loading section says to call it with `<child-slug>`; the verb actually requires the **backlog-filename slug** and returns "not found" for the lifecycle slug (first thing a caller holding refine's Step-1 JSON is likely to pass). refine SKILL.md's Constraints table already documents this exact pitfall class for `cortex-update-item` — add the same one-line clarification (and ideally the same Constraints-table row) at this call site.

## Done when

(1) A SessionStart-provided `LIFECYCLE_SESSION_ID` actually reaches the session's Bash environment (or the docs stop claiming it does and specify the real derivation), and the `.session` write/clean lifecycle is coherent end-to-end. (2) `emit-lifecycle-start` either accepts legacy complexity values via documented coercion or fails with a remediation message naming the exact fix command. (3) clarify-critic.md names the backlog-filename slug explicitly for `cortex-load-parent-epic`.
