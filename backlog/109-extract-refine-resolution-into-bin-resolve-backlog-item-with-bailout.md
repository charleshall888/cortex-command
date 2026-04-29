---
schema_version: "1"
uuid: c5cf3e45-4ed2-495e-afda-aebacbf5490f
title: "Extract /refine resolution into bin/resolve-backlog-item with bailout"
status: complete
priority: medium
type: feature
parent: "101"
blocked-by: []
tags: [harness, scripts, refine]
created: 2026-04-21
updated: 2026-04-28
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
complexity: complex
criticality: high
spec: lifecycle/extract-refine-resolution-into-bin-resolve-backlog-item-with-bailout/spec.md
areas: [skills]
session_id: null
lifecycle_phase: complete
---

# Extract /refine resolution into bin/resolve-backlog-item with bailout (C5)

## Context from discovery

`/refine` Step 1 (`skills/refine/SKILL.md:22-35`) resolves fuzzy input (numeric ID / kebab-slug / title phrase / ad-hoc topic) into a backlog item, producing three distinct slugs (`backlog-filename-slug`, `item-title`, `lifecycle-slug`).

**Ship unconditionally with a graceful bailout exit code.** If input resolves unambiguously, the script returns the three slugs and structured frontmatter — happy path faster. If ambiguous, the script exits non-zero and the agent proceeds with the inline disambiguation flow as it does today — unhappy path unchanged. Pure Pareto improvement; no telemetry gate needed. (CR2 reframe.)

## Research context

- C5 in `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Determinism: MECHANICAL-PARSE on happy path.
- Heat: warm (low-frequency skill, but net benefit is immediate on happy path).

## Scope

- New `bin/cortex-resolve-backlog-item <fuzzy>` with distinct exit codes:
  - `0` — unambiguous match; JSON on stdout with `{filename, slug, title, lifecycle_slug, frontmatter}`.
  - Non-zero distinct codes for: ambiguous, no-match.
- Fuzzy matching must exactly mirror canonical `cortex_command/common.py:slugify()` (function at L59).
- Top-level `bin/cortex-resolve-backlog-item` is source-of-truth; `just build-plugin` ships it via `plugins/cortex-interactive/bin/`.
- Update `skills/refine/SKILL.md` Step 1 to invoke the script; fall through to existing disambiguation flow on non-zero.

## Out of scope

- Changes to the ambiguous-path UX (agent still prompts the user when the script bails).
- Telemetry to observe happy-path rate — covered by ticket 103 (DR-7) post-ship.
