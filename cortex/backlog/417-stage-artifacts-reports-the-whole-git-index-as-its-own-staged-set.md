---
schema_version: "1"
uuid: 175d6634-192a-4ca6-8b95-4d593da16b26
title: Stage-artifacts reports the whole git index as its own staged set
status: complete
priority: high
type: bug
created: 2026-07-27
updated: 2026-07-27
tags: ['lifecycle', 'git', 'concurrency']
areas: ['lifecycle']
---
## Why

`stage()` runs its explicit `git add -- <paths>` correctly — the module's documented "no-directory-glob discipline" holds — and then derives **both** its return values from the entire index:

```python
diff = _run(["diff", "--cached", "--name-only"], cwd=str(root))
staged = sorted(...)
return {"signal": "staged" if staged else "nothing_staged", "staged_paths": staged}
```

On a trunk repo where two lifecycles share one worktree — the documented normal case — the index also holds whatever a **concurrent session** has staged. So the verb attributes another session's files to itself. Two harms follow:

1. **`staged_paths` is not this verb's staged set.** Consumers are told to "act on its `signal`" and commit, and the reported set is the obvious commit target. A skill that commits it commits a sibling session's in-flight work.
2. **`signal` can be a false positive.** Because it is derived from the whole index rather than this verb's own paths, `stage-artifacts` returns `signal: "staged"` even when it staged *nothing* — every one of its artifacts already committed — purely because another session has files staged. That triggers a spurious commit on an otherwise-clean phase exit.

Observed 2026-07-27 (wild-light #332 refine): the verb returned `signal: "staged"` with `scenarios/probe/weapon_spatial_depth_behind.json` in `staged_paths` — an untracked file belonging to a concurrent session's in-flight work on a different ticket. Only an explicit-pathspec commit, naming the five artifact paths after a bare double-dash, kept it out of the refine commit. The misreport also induced a second-order error: the operator tried to unstage the "stray" file and interfered with the other session's live staging, hitting its `index.lock`.

## Role

Makes `staged_paths` and `signal` describe what this invocation actually staged, so consumers can commit the reported set without auditing it against a concurrent session first.

## Integration

Scope the post-add read to the verb's own path list — pass the same resolved paths after a double-dash to the `diff --cached --name-only` call — so both return values are an intersection of the index with what `collect_paths` resolved, not the whole index. `collect_paths` already filters to paths present on disk, so it is the right basis. `signal` then means "this verb staged something", which is what every call site assumes today.

## Edges

- `nothing_staged` must keep meaning "nothing of *ours* to stage" (all artifacts already committed) and must not start meaning "index empty" — the two differ once the read is scoped.
- The refine cancel path omits `spec.md` from `collect_paths`; scoping the read must not resurrect it into `staged_paths`.
- Consumer skills phrase the commit step as acting on the signal without an explicit pathspec. Scoping the report does not by itself stop a bare commit from sweeping the index, so the explicit-pathspec commit form should be stated wherever the flow is documented.
- A file legitimately in both this verb's set and a concurrent session's staging is genuinely ambiguous — scoping reports it as ours, which is the safe direction, but worth a note.

## Touch points

- `cortex_command/lifecycle/stage_artifacts.py:313-323` — the whole-index read that produces both return values
- `cortex_command/lifecycle/stage_artifacts.py:235-284` — `collect_paths`, the correct scoping basis
- `cortex_command/lifecycle/stage_artifacts.py:52-66` — the "Explicit-add discipline" docstring, accurate about the add and silent about the read
- `skills/refine/SKILL.md` Step 6 and `skills/build/references/complete.md` Step 11a — consumers that act on `signal` and commit
- `tests/` — a regression test needs a second staged path outside the verb's set to reproduce