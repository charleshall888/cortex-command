---
schema_version: "1"
uuid: d0b527f7-1e3d-432b-97ab-8126f357882e
title: cortex-lifecycle-resolve mis-resolves numeric backlog ID to state:new when a slug-keyed lifecycle already exists
status: backlog
priority: high
type: bug
created: 2026-07-07
updated: 2026-07-10
tags: ['resolver', 'lifecycle-resolve', 'dogfood']
areas: ['lifecycle']
parent: 371
---
## Why

`cortex-lifecycle-resolve` mis-resolves a **numeric backlog ID** whose lifecycle already exists — it reports `state: "new"` (phase `research`) even for a finished feature. Observed with `cortex-lifecycle-resolve "308"` in the wild-light repo: #308 is `status: complete`, `feature_complete` logged, PR merged, and its lifecycle dir `cortex/lifecycle/renderstack-layer-registry-renderpassregistry-with-ratified/` holds research/spec/plan/pr.json — yet the resolver returns `new`. Invoking with the **slug** resolves correctly (`state: "resume"`, `route: "complete"`).

Because `/cortex-core:lifecycle`'s Step 1 documents the numeric ID as the primary invocation (`cortex-lifecycle-resolve "308"`), this means re-invoking any already-started or completed lifecycle by its ticket number silently restarts it as a fresh feature at research — a data-loss / rework hazard, not just a completed-feature edge case.

## Role

The resolver locates the lifecycle dir purely by the raw feature token, but lifecycle dirs are **slug-keyed**, never numeric-ID-keyed, so the numeric-token path can never exist. The backlog resolution that runs immediately afterward already carries `lifecycle_slug` pointing at the **real, existing** dir. The resolver has everything it needs but ignores `lifecycle_slug` when locating the lifecycle dir, so the numeric path always falls through to `state: "new"`. After this lands, numeric-ID and slug invocations converge on the same identity — the slug is the canonical key and the numeric ID is input normalization.

## Integration

Fix in `resolve_invocation`: when `not dir_exists` **and** the resolved `backlog` carries a `lifecycle_slug` whose dir *does* exist, remap `feature_dir`/`feature` to that slug and fall through to the existing `resume` branch (`detect_lifecycle_phase`, staleness, criticality/tier — all of which already work correctly under the slug, verified). Only emit `state: "new"` when neither the numeric-token dir nor the backlog-slug dir exists. This makes numeric-ID and slug invocations converge, which the skill body already assumes.

## Edges

- Preserve today's true-new behavior: a backlog ID with no lifecycle dir under its slug must still resolve `new`.
- An explicit `phase_override` should keep working after the remap (the resume branch already threads it).
- `mode == "resume"` currently hard-errors `no-such-lifecycle` when `cortex/lifecycle/<feature>/` is absent (line ~161) — the same numeric-vs-slug blindness. Decide whether the slug remap should also cover the explicit-resume verb, or leave it scoped to the plain-feature path.
- Note: a stale `lifecycle_phase` field in the *backlog frontmatter* does NOT drive this — the resolver reads phase from the lifecycle dir via `detect_lifecycle_phase`, not from backlog frontmatter, so correcting that field does not change the numeric-path output.

## Touch points

- `cortex_command/lifecycle/resolve.py` — `resolve_invocation` (numeric-token → `lifecycle_slug` remap before the `not dir_exists` return; and the `mode == "resume"` `no-such-lifecycle` guard). The failing lookup:

```python
feature_dir = lifecycle_base / feature      # feature == "308"
dir_exists = feature_dir.is_dir()           # cortex/lifecycle/308 never exists
...
if not dir_exists:
    return {"state": "new", ...}
```

- `cortex_command/backlog/resolve_item.py` — `_build_json` already surfaces `lifecycle_slug` (the field to key off).
- Tests: add coverage that a numeric ID for a started/completed lifecycle resolves `resume` (not `new`), keyed via `lifecycle_slug`.

## Repro

```
# in a repo with a slug-keyed lifecycle dir + numeric backlog file
cortex-lifecycle-resolve "308"   # BUG: state=new, phase=research
cortex-lifecycle-resolve "renderstack-layer-registry-renderpassregistry-with-ratified"  # OK: state=resume, route=complete
```