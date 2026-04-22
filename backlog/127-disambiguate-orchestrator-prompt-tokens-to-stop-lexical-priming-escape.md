---
schema_version: "1"
uuid: 65cbc5a4-ae71-4763-9a9c-f5cf4847480d
title: "Disambiguate orchestrator prompt tokens to stop lexical-priming escape"
status: complete
priority: critical
type: feature
parent: 126
tags: [overnight-runner, orchestrator, prompt, orchestrator-worktree-escape]
areas: [overnight-runner]
created: 2026-04-21
updated: 2026-04-22
lifecycle_slug: disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape
lifecycle_phase: implement
session_id: null
blocks: []
blocked-by: []
discovery_source: research/orchestrator-worktree-escape/research.md
complexity: complex
criticality: critical
spec: lifecycle/disambiguate-orchestrator-prompt-tokens-to-stop-lexical-priming-escape/spec.md
---

# Disambiguate orchestrator prompt tokens to stop lexical-priming escape

## Context from discovery

The acute root cause of session `overnight-2026-04-21-1708`'s `feature_start` failure is *lexical priming + token name collision* in `claude/overnight/prompts/orchestrator-round.md`:

- The session-level portion of the prompt (lines 14, 128-133, 185, 244, 254, 311, 321) repeatedly shows `Path("{token}")` patterns where `{token}` has been pre-filled by `fill_prompt()` (`runner.sh:386-391`) with an absolute home-repo path.
- The per-feature dispatch block at lines 258-285 uses the identical `{token}` syntax for `{slug}`, `{spec_path}`, and `{plan_path}` — but these are expected to be substituted by the orchestrator agent at runtime from `state.features[<slug>]`, not by `fill_prompt()`.
- `{plan_path}` at line 14 (session-level) and at line 269 (per-feature) is the worst offender: same token name, different semantics, no marker to distinguish them.

The result: the orchestrator agent either (a) replicates the absolute-path style from the in-context prior and generates `/Users/.../lifecycle/{slug}/plan.md` with literal `{slug}`, or (b) forgets to substitute at all. Both hybrid failures produced the session 1708 symptom.

## Value

This is the cheapest fix that addresses the observed failure mechanism directly. Research feasibility table estimates ~30 minutes of prompt editing + minimal runner change. Research Decision Record DR-1 names it as Critical and highest-leverage.

## Research context

- Full analysis: `research/orchestrator-worktree-escape/research.md` §"The substitution contract (RQ1, RQ2) — mechanism is lexical priming"
- DR-1 in the research establishes this as the primary substitution-contract fix rather than the abstract "contract rewrite" framing initially considered
- Fact correction: per-feature tokens existed since initial commit `428e54e` (2026-04-01), not introduced by backlog 048

## Acceptance criteria

- After this ticket lands, the session-level and per-feature plan tokens are distinguishable by name in `orchestrator-round.md`
- The per-feature dispatch block (lines 258-285 in current file) contains an explicit instruction naming which tokens the orchestrator agent substitutes from `state.features[<slug>]`
- A re-run of a failed-plan-parse style scenario (with the orchestrator prompted from state) produces correctly-substituted per-feature paths
- The `fill_prompt()` function in `runner.sh` is updated to handle any renamed session-level tokens so existing substitution behavior is preserved
