---
schema_version: "1"
uuid: b293c58a-0fa8-451e-ab7d-7b5b19f4b4ef
title: Requirements loader matches index tags against area triggers, so 72% of lifecycles load project.md only
status: refined
priority: medium
type: bug
created: 2026-08-07
updated: 2026-08-07
tags: ['requirements-loading']
areas: ['lifecycle', 'requirements']
complexity: complex
criticality: high
spec: cortex/lifecycle/requirements-loader-matches-index-tags-against/spec.md
---
## Why

`cortex-load-requirements` selects area docs by matching a lifecycle's `index.md` `tags:` as
substrings against the trigger text in `project.md`'s `## Conditional Loading`
(`load_requirements_cli.py:_read_tags`, `resolve`). Two things are wrong with that, and together they
mean most features are refined, planned, and reviewed against `project.md` alone — silently, with only
a stderr note nobody is required to act on.

**Measured on this repo, 2026-08-07** (ran the installed verb across every lifecycle with an
`index.md`):

- **134 of 186 lifecycles (72.0%) print `no area docs matched` and load `project.md` only.**
- 78 of those have `tags: []` outright.
- The other 56 have populated tags that still match nothing — because the tags in use are epic and
  topic slugs (`cli-served-lifecycle-state-machine`, `tooling-gap`, `research-skill`,
  `artifact-densification`), not area names.

**The field mismatch is the root cause.** The area concept already exists on the backlog item as
`areas:` — #465 carries `areas: ['overnight-runner', 'report']` — and the loader never reads it. It
reads `tags:`, which is a different field holding a different vocabulary for a different purpose.

**And the vocabularies would not match even if wired up.** Matching is
`tag.lower() in trigger_lower`, so the hyphenated area name misses the spaced trigger:

```
'overnight-runner' in 'pipeline/overnight runner/conflict resolution/deferral'  -> False
'overnight runner' in 'pipeline/overnight runner/conflict resolution/deferral'  -> True
```

So a fix that only syncs `areas:` into `tags:` would still fail for every multi-word area.

**Observed cost.** On #465 this went unnoticed until Review: the feature edits
`cortex/requirements/pipeline.md`, and `pipeline.md` is exactly the doc the loader failed to select.
Both review cycles had to be handed it by hand. The drift check is the thing that catches an
implementation contradicting its area requirements — at a 72% miss rate it is mostly not running,
and its silence is indistinguishable from a clean result.

## Role

One selection path, correct by construction, so a feature's governing area doc loads without the
orchestrator knowing to intervene.

## Integration

- `cortex_command/lifecycle/load_requirements_cli.py` — `_read_tags`, `resolve`, and the
  `no area docs matched` note.
- `cortex/requirements/project.md` `## Conditional Loading` — the trigger vocabulary.
- The lifecycle index writer that populates `index.md` `tags:`, and `cortex-lifecycle-enter`'s
  `--backlog-file` index repair (it returned `"index": "skipped"` for #465, so the documented repair
  does not cover this case).

## Edges

- **Deciding the source of truth is the actual design work.** Read `areas:` from the backlog item;
  or keep reading index `tags:` but populate them from `areas:`; or match on a normalized form of
  both. Context B / ad-hoc lifecycles have no backlog file at all and no index — see the existing
  constraint that `create-index` requires `--backlog-file` — so whatever is chosen must degrade to
  today's project.md-only behavior rather than erroring.
- Normalization must handle hyphen/space/case at minimum. Prefer an explicit area vocabulary over
  substring matching, which silently succeeds on accidental containment.
- `cortex/requirements/lifecycle.md` is referenced by a trigger but **not yet written**; that arm is
  expected to match nothing and must not be counted as a failure.
- Some of the 134 legitimately have no governing area doc. The fix is not "drive the number to
  zero" — it is that a feature which *has* an area doc gets it.
- The stderr note should probably become louder than a note if it survives the fix.

## Touch-points

Every `/cortex-core:refine` and `/cortex-core:build` run: the requirements load feeds spec authoring,
plan review, and the Review phase's drift assessment.

## Evidence trail

Found during #465 Review (`cortex/lifecycle/overnight-session-worktree-lives-in-tmpdir/review.md`),
where both cycles record the manual `pipeline.md` hand-off.
