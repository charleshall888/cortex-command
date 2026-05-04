---
schema_version: "1"
uuid: 767f7775-136d-4c4b-99ab-3e7e87964fd0
title: "Convert dispatch.py granular sandbox shape to simplified, fix cross-repo allowlist inversion at feature_executor.py:603"
status: ready
priority: high
type: feature
parent: 162
tags: [overnight-runner, pipeline, sandbox, cross-repo]
areas: [overnight-runner, pipeline]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [163]
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Convert dispatch.py granular sandbox shape to simplified, fix cross-repo allowlist inversion at feature_executor.py:603

## Context from discovery

Two compounded bugs in the per-feature dispatch path surfaced during discovery + critical review:

**Bug 1 — granular shape silent no-op** (R1-A1 from critical review): `cortex_command/pipeline/dispatch.py:546` writes `{"sandbox": {"write": {"allowOnly": _write_allowlist}}}` — the granular shape. Per documentary verification of the open-source [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime), the package consumes ONLY the simplified shape `filesystem.{allowRead, denyRead, allowWrite, denyWrite}`. The granular `write.allowOnly` shape is the runtime's internal IR after merging permissions rules, NOT a recognized settings input. Existing `tests/test_dispatch.py:306-637` only verifies the JSON is *written*, not that enforcement *applies*. Conclusion: per-feature sandbox narrowing is structurally a silent no-op today.

**Bug 2 — cross-repo allowlist inversion** (R4-B from critical review): `cortex_command/overnight/feature_executor.py:603` passes `integration_base_path=Path.cwd()` to `dispatch_task`. For a cross-repo feature, `Path.cwd()` is the home repo (the runner runs from home-repo cwd). `dispatch.py:540-549` unconditionally appends `integration_base_path` to `_write_allowlist`. Net effect: a cross-repo dispatch's write allowlist includes the home repo, **granting cross-repo agents write access to the home repo's working tree** — the inverse of multi-repo isolation intent.

## Findings from discovery

- The simplified shape `sandbox.filesystem.allowWrite` is the canonical input shape (DR-1).
- Cross-repo features carry `repo_path` in `OvernightFeatureStatus` (`cortex_command/overnight/state.py:127`); `integration_worktrees[repo_path]` data exists and can be threaded to the dispatch call.
- Once #163 establishes the simplified-shape pattern at the orchestrator spawn, dispatch.py:546's conversion is a near-mechanical sibling change.

## Value

Per-feature sandbox narrowing is currently a no-op — overnight per-feature spawns have no kernel-level write isolation despite the appearance of one (the JSON write at `dispatch.py:546` exists but is structurally ignored). Cross-repo features additionally have home-repo inversion. Citations: `cortex_command/pipeline/dispatch.py:546` (silent-no-op shape), `cortex_command/overnight/feature_executor.py:603` (cross-repo allowlist inversion).

## Acceptance criteria (high-level)

- `dispatch.py:546` is converted from `{"sandbox": {"write": {"allowOnly": ...}}}` to the documented `{"sandbox": {"enabled": true, "filesystem": {"allowWrite": ...}}}` shape.
- `feature_executor.py:603` uses `integration_worktrees[repo_path_str]` (the cross-repo's integration worktree) when `repo_path` is non-None; falls back to `Path.cwd()` only for same-repo features.
- An empirical acceptance test verifies a per-feature dispatch's write to a path outside its allowlist returns EPERM at the kernel layer.
- `tests/test_dispatch.py` is updated to verify the new shape AND to include an enforcement test (not just JSON-write verification).

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: DR-1 (schema pivot), DR-6 (per-feature audit), critical review R1-A1 + R4-B.
