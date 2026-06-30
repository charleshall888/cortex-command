---
schema_version: "1"
uuid: fe1043fe-3145-4faf-9fba-0f7e5d696ea1
title: Route bare phase tokens to the active feature in /cortex-core:lifecycle
status: wontfix
priority: low
type: feature
created: 2026-06-29
updated: 2026-06-30
---
## Why

Split out of #329 (wire-cortex-corelifecycle-wontfix-invocation-and) at completion. #329 made bare phase tokens (`/cortex-core:lifecycle plan`, `review`, `research`, `specify`, `implement`) non-broken: `cortex-lifecycle-parse-args` classifies them as `mode=phase` and SKILL.md Step 1 surfaces a feature-required message instead of silently creating a phantom lifecycle. It deliberately stopped short of routing a bare phase token to *the active feature*, because that needs an **active-feature concept that does not exist today** (the lifecycle has no notion of a single "current" feature when multiple incomplete lifecycles exist).

## Role

Give `/cortex-core:lifecycle <phase>` (no feature) a useful behavior: resolve the active feature and enter the named phase, rather than the current feature-required fallback.

## Integration

- Parser: `cortex_command/lifecycle/parse_args.py` already emits `mode=phase` with the token in `phase`; this ticket adds the routing that consumes it.
- SKILL.md Step 1 `phase` route currently surfaces "specify a feature"; it would instead resolve the active feature.
- Needs a defined active-feature selection (e.g. the single incomplete lifecycle, the most-recently-touched `.session`, or an explicit marker) — design that concept first.

## Edges

- Ambiguity when multiple incomplete lifecycles exist (the case the SessionStart picker already surfaces).
- Must not reintroduce the phantom-lifecycle creation #329 removed.

## Touch-points

- `cortex_command/lifecycle/parse_args.py`, `skills/lifecycle/SKILL.md` Step 1, `tests/test_lifecycle_invocation_grammar_parity.py`.

Cross-ref: #329; ADR-0018 (structural invocation grammar) scope-honesty note records this as deferred.

## Resolution

Wontfix (2026-06-30, via `/cortex-core:refine` clarify gate). Multiple incomplete lifecycles are the normal working state, so any repo-wide "active feature" resolution degrades to a list-and-ask picker almost every time — trading "type the feature slug" for "click a picker" (which does not cleanly carry the phase), for near-zero net convenience plus new logic on the shared lifecycle entrypoint. The only sub-case immune to that — session-scoped `.session` continuation — has thin value (phases already auto-advance within a session). Given priority:low and that #329's feature-required fallback is already safe, the chosen behavior is to keep requiring an explicit feature arg. #329's `mode=phase` "specify a feature" fallback stands as the intended terminal behavior.