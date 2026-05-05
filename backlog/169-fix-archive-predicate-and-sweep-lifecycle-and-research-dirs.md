---
schema_version: "1"
uuid: 924ee1c9-96a9-42a7-8060-9fbf68451681
title: "Fix archive predicate and sweep lifecycle/ and research/ dirs"
status: backlog
priority: medium
type: feature
tags: [repo-spring-cleaning, archive, lifecycle, research, justfile]
areas: []
created: 2026-05-05
updated: 2026-05-05
parent: "165"
blocks: []
blocked-by: []
discovery_source: research/repo-spring-cleaning/research.md
session_id: null
lifecycle_phase: null
lifecycle_slug: null
complexity: complex
criticality: medium
---

# Fix archive predicate and sweep lifecycle/ and research/ dirs

## Context from discovery

`research/repo-spring-cleaning/research.md` found 37 lifecycle dirs at `lifecycle/` top level (plus 111 already in `archive/`) and 32 research dirs at `research/` top level (no `archive/` exists). ~30 lifecycle dirs and ~30 research dirs are completed-and-stale; sweeping them into archive subdirs reduces GitHub root render clutter for installer audience.

The `justfile:212` archive predicate has a YAML-events blind spot — it greps for the JSON-quoted `"feature_complete"` token only, silently skipping ~11 modern lifecycle dirs that use YAML-form `event: feature_complete` entries.

Critical review caught that 3 of 4 originally-classified "orphan/test-detritus" delete candidates are actually archive candidates — `add-playwright-htmx-test-patterns-to-dev-toolchain/` (cited by `backlog/029-...md:59` as research source), `define-evaluation-rubric-...` (backlog #035 complete), `run-claude-api-migrate-to-opus-4-7-...` (backlog #083 complete; parent epic #82 alive per CLAUDE.md). Only `feat-a/` is genuine test detritus.

## Scope — F-9a: archive predicate fix

Replace `justfile:212` predicate with anchored alternation regex covering both event formats:

```
grep -qE '"event":[[:space:]]*"feature_complete"|^[[:space:]]*event:[[:space:]]*feature_complete[[:space:]]*$'
```

Document rejected options in commit message:
- Drop-JSON-quoting alone is line-noise fragile (any future task narrative mentioning "feature_complete" trips archive).
- Backlog-ticket-only defer accepts continuing silent skip.

## Scope — F-9b: per-dir disposition table

Produce a citation-backed table covering all 37 top-level lifecycle dirs with columns: slug → predicate-hit (json/yaml/none) → backlog-ref → has-cross-refs-in-research/ → recommended-action. Catches the `clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete/` edge case (no `events.log` at all — invisible to all predicate variants; needs separate inspection).

## Scope — F-9c: execute archive

After the disposition table is committed:
1. Run `just lifecycle-archive --dry-run` with new predicate; diff output against expectation.
2. Archive recipe-eligible (~19 strict + ~11 YAML-form once predicate is fixed) dirs.
3. Manually archive 3 mis-classified dirs that lack feature_complete events but have complete backlog tickets:
   - `lifecycle/add-playwright-htmx-test-patterns-to-dev-toolchain/` (backlog #029)
   - `lifecycle/define-evaluation-rubric-update-lifecycle-spec-template-create-dashboard-context-md/` (backlog #035)
   - `lifecycle/run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff/` (backlog #083; parent epic #82 alive)
4. Delete `lifecycle/feat-a/` only (genuine test detritus, no backlog ticket, 42 ERROR-loop events).
5. Investigate `clean-up-active-sessionjson-...` separately.

**Ordering constraint**: `bin/cortex-archive-rewrite-paths` walks every `*.md` outside `.git/`/`lifecycle/archive/`/`lifecycle/sessions/`/`retros/`. Running while sibling cleanup tickets (#166/#167/#168) have open lifecycle dirs creates churn (path renames in their lifecycle/<slug>/ artifacts). Sequence #169 last in the epic.

## Scope — F-10: research archive

Create `research/archive/` (does not exist). Move ~30 decomposed-and-stale research dirs into it. Keep at top level:
- `research/repo-spring-cleaning/` (this discovery — keep until epic #165 closes)
- `research/opus-4-7-harness-adaptation/` (epic #82 alive per CLAUDE.md)

Sample-classified dirs to archive include `post-113-repo-state/`, `overnight-runner-sandbox-launch/`, `sandbox-overnight-child-agents/`, `shareable-install/`, `user-configurable-setup/`, `permissions-audit/`, `docs-setup-audit/`, `harness-design-long-running-apps/`, `implement-in-autonomous-worktree-overnight-component-reuse/`. Plan phase produces full table.

## Out of scope

- DR-2 visibility cleanup (gitignore-hide / `.cortex/` relocation) — deferred per DR-2 = C; revisit after observing post-archive GitHub root render.
- README rewrite — child #166.
- Doc reorg — child #167.
- Code/script junk deletion — child #168.

## Acceptance signals

- `justfile:212` predicate matches both JSON- and YAML-form `feature_complete` events.
- Per-dir disposition table committed.
- ~30 lifecycle dirs in `lifecycle/archive/`; ~30 research dirs in `research/archive/`.
- `lifecycle/feat-a/` removed.
- `clean-up-active-sessionjson-...` no-events.log edge case has documented disposition.
- No load-bearing cross-references broken (verify `backlog/029-...md:59` still resolves to the archived path via `cortex-archive-rewrite-paths`).

## Research

See `research/repo-spring-cleaning/research.md` — Lifecycle / research archive state section, F-9a/9b/9c, F-10, archive recipe blind-spot analysis, and per-dir mis-classification corrections from critical review.
