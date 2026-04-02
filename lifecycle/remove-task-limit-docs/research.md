# Research: Remove Task Limit Docs

## Summary

The overnight runner documentation contains two conservative guidance blocks in `docs/overnight.md` that discourage running many features per session. The user asserts these limits are inaccurate — the runner scales well with many tasks. This research locates all instances.

## Codebase Analysis

### `docs/overnight.md` — Session size section (lines 380–387)

```
### Session size

**3–5 features per session** is the sweet spot. Too few (1–2) wastes the overhead of
spinning up the session infrastructure; too many (8+) increases the chance that a single
failure in a shared file causes cascading conflicts that waste the session. The upper
bound is also driven by context budget: each orchestrator agent reads all selected
features' specs and plans, and loading too many at once risks overflowing the agent's
context window.
```

This is the primary target. States "3–5 features" as the sweet spot and gives two rationales for an upper bound: conflict probability and context overflow. Both rationales will be removed per user direction.

### `docs/overnight.md` — Concurrency section (lines 407–410)

```
...which is why 2 is the safe default and 3 should only be used for clearly
non-overlapping feature sets.
```

This closing sentence treats 2 as "the safe default" and 3 as exceptional. This is overly conservative guidance that conflicts with the user's assertion that the runner scales. The rest of the conflict-detection explanation (merge time, trivial fast-path, repair agent) is factually accurate and should be preserved.

### `skills/overnight/SKILL.md` — Concurrency limit note (line 148)

```
- **Concurrency limit**: Default is 2 (number of features executing in parallel per round). User can increase or decrease.
```

This is purely informational — states the default without advising users to keep it low. No change needed.

### `requirements/project.md`

No session-size limits or task-count advisories present. No change needed.

## Scope

One file with two edits: `docs/overnight.md`
1. Replace the Session size block (lines 380–387) with positive scaling guidance
2. Remove the closing "2 is the safe default and 3 should only be used..." sentence from the Concurrency section (lines 407–410)

## Open Questions

None.
