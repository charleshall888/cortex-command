---
schema_version: "1"
uuid: 6c21da16-1c97-4809-a389-7a87115b6483
title: "Consolidate cortex-command artifacts under a single cortex/ root"
status: complete
priority: medium
type: epic
created: 2026-05-11
updated: 2026-05-12
tags: [installer-experience, repo-layout, consolidate-artifacts-under-cortex-root]
complexity: complex
criticality: medium
areas: [init, overnight-runner, dashboard, backlog, skills]
session_id: null
discovery_source: cortex/research/consolidate-artifacts-under-cortex-root/research.md
---

# Consolidate cortex-command artifacts under a single cortex/ root

## Problem

`cortex init` currently deploys seven top-level paths into every initialized repo: `lifecycle/`, `research/`, `retros/`, `backlog/`, `requirements/`, `lifecycle.config.md`, `.cortex-init` (plus `debug/` for diagnose-skill artifacts). Sources at `cortex_command/init/scaffold.py:56-61` (`_CONTENT_DECLINE_TARGETS`) and `cortex_command/init/handler.py:125-153` (sandbox-registration) hardcode these as siblings of the user's project content. The result: visual clutter at repo root, no clean gitignore-as-a-unit option for users who don't want tool-managed state tracked, and conceptual blurring between tool-managed state and user-authored project content.

## Value

Consolidating under a single visible `cortex/` root lets end-users gitignore the entire tree wholesale and reduces the cortex-managed surface from 7+ path-roots at the repo root to 1 — addressing the user-stated framing of "polluting their repo" while keeping the tree discoverable for users who don't ignore it.

## Research Context

See `research/consolidate-artifacts-under-cortex-root/research.md` for the full three-round investigation, critical-review findings, and 10 decision records. Headline decisions:

- **DR-1**: Visible `cortex/` (not hidden `.cortex/`) per user preference — discoverable for non-gitignoring users.
- **DR-2**: Full relocation including user-authored `backlog/` and `requirements/` (one mental folder).
- **DR-5**: Umbrella sandbox grant — `cortex init` registers `cortex/` once.
- **DR-7**: Single atomic commit with explicit operational preconditions (`git add -A`, fresh sandbox preflight against pre-relocation HEAD, no overnight session active).
- **DR-9**: Plugin-version transition handled via major-version bump + `/plugin update cortex-core` cutover.
- **DR-10**: Add upward-walking project-root detection in parallel — DR-1's visibility rationale invites users into `cortex/lifecycle/<feature>/` where the existing cwd-only resolver at `cortex_command/common.py:80` would misfire.

Touchpoint scope is moderate at the code level (~30 Python files, mostly string-literal swaps) but large at the data level: 287 backlog YAML lines across 4 fields (`discovery_source:`, `spec:`, `plan:`, `research:`), 61 `critical-review-residue.json` `"artifact"` keys, structural `epic_research` keys in `events.log` payloads. See research §Codebase Analysis for the full inventory.

## Children

- #201 — Add upward-walking project-root detection (foundation, DR-10)
- #202 — Relocate cortex-command artifacts under cortex/ root (the relocation itself)
- #203 — Add path-hardcoding parity gate (post-relocation drift prevention)

## Suggested order

#201 → #202 → #203. #201 is independent and ships first to give the relocation a clean foundation. #202 is the single atomic commit. #203 follows to prevent drift.
