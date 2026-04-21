---
schema_version: "1"
uuid: c5cf3e45-4ed2-495e-afda-aebacbf5490f
title: "Extract /refine resolution into bin/resolve-backlog-item with bailout"
status: backlog
priority: medium
type: feature
parent: "101"
blocked-by: ["102", "103"]
tags: [harness, scripts, refine]
created: 2026-04-21
updated: 2026-04-21
discovery_source: research/extract-scripts-from-agent-tool-sequences/research.md
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

- New `bin/resolve-backlog-item <fuzzy>` with distinct exit codes:
  - `0` — unambiguous match; JSON on stdout with `{filename, slug, title, lifecycle_slug, frontmatter}`.
  - Non-zero distinct codes for: ambiguous, no-match.
- Fuzzy matching must exactly mirror canonical `claude/common.py:slugify()`.
- Deploy via `just deploy-bin`.
- Update `skills/refine/SKILL.md` Step 1 to invoke the script; fall through to existing disambiguation flow on non-zero.

## Out of scope

- Changes to the ambiguous-path UX (agent still prompts the user when the script bails).
- Telemetry to observe happy-path rate — covered by ticket 103 (DR-7) post-ship.
