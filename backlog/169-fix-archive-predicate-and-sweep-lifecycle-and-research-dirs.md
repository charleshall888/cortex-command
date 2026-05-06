---
schema_version: "1"
uuid: 924ee1c9-96a9-42a7-8060-9fbf68451681
title: "Fix archive predicate and sweep lifecycle/ and research/ dirs"
status: in_progress
priority: medium
type: feature
tags: [repo-spring-cleaning, archive, lifecycle, research, justfile]
areas: []
created: 2026-05-05
updated: 2026-05-05
parent: "165"
blocks: []
blocked-by: [166, 168]
discovery_source: research/repo-spring-cleaning/research.md
session_id: 9989f0e6-17df-44ec-8f26-4e22c0face84
lifecycle_phase: implement
lifecycle_slug: fix-archive-predicate-and-sweep-lifecycle-and-research-dirs
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
3. Manually archive 4 dirs that lack feature_complete events but have complete backlog tickets or documentation roles:
   - `lifecycle/add-playwright-htmx-test-patterns-to-dev-toolchain/` (backlog #029 cites it as research source)
   - `lifecycle/define-evaluation-rubric-update-lifecycle-spec-template-create-dashboard-context-md/` (backlog #035 complete)
   - `lifecycle/run-claude-api-migrate-to-opus-4-7-on-throwaway-branch-and-report-diff/` (backlog #083 complete; parent epic #82 alive)
   - `lifecycle/clean-up-active-sessionjson-when-overnight-session-transitions-to-phasecomplete/` (round 2 disposition: contains only `review.md` — retroactive read-only review of inline hotfix commit `88f4885` for backlog #134; backlog complete; archive manually since no predicate variant matches)
4. Delete `lifecycle/feat-a/` only (genuine test detritus, no backlog ticket, 42 ERROR-loop events).

## Critical: rewrite-paths blast radius mitigation

Round 2 audit caught: `bin/cortex-archive-rewrite-paths` walks every `*.md` outside `.git/`/`.venv/`/`lifecycle/archive/`/`lifecycle/sessions/`/`retros/`. The recipe argparse exposes only `--slug`/`--dry-run`/`--root` — **no `--exclude-dir` flag exists**. Without mitigation, the recipe rewrites citations in:
- `research/repo-spring-cleaning/research.md` (this discovery's artifact)
- `research/opus-4-7-harness-adaptation/research.md` (alive epic #82 per CLAUDE.md)
- Any in-flight lifecycle artifacts of #166/#168
- Backlog ticket bodies that contain inline `lifecycle/<slug>` references (backlog frontmatter `lifecycle_slug:` fields use bare slugs without prefix, so frontmatter is safe)

**Mitigation options** (plan phase picks one):

1. **Add `--exclude-dir` flag to `bin/cortex-archive-rewrite-paths`** (small bin/ scope expansion within this lifecycle): accept a list of directories to prune from the walk; pass `--exclude-dir research/repo-spring-cleaning research/opus-4-7-harness-adaptation` during the sweep. Best defense for live cross-references.

2. **Sequence-and-accept**: stage all discovery + epic + cleanup-ticket artifacts to commit BEFORE running the recipe. Accept rewrites in archived research artifacts (post-archive citations still resolve correctly to `lifecycle/archive/<slug>/`). Verify post-run by visual diff that no live cross-refs break.

Recommended: Option 1 (the bin/ flag is simple to add and provides durable safety for future archive runs).

**Ordering constraint**: regardless of mitigation, sequence #169 last in the epic — after #166 and #168 commit so their in-flight lifecycle artifacts are not in the rewrite scope.

**Code-reference paired update**: `cortex_command/cli.py:268` runtime stderr message `"see docs/mcp-contract.md."` is being updated by #166's docs/internals/ move; verify it's done before #169's rewrite path crosses any archived path that touches `docs/internals/` paths.

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
