---
schema_version: "1"
uuid: a64f0544-0663-451e-8da5-3de0339f70e6
title: "Document overnight sandbox threat-model boundary and Linux setup prereqs"
status: ready
priority: low
type: feature
parent: 162
tags: [overnight-runner, sandbox, docs]
areas: [overnight-runner, docs]
created: 2026-05-04
updated: 2026-05-04
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: [163, 164, 165, 166]
discovery_source: research/sandbox-overnight-child-agents/research.md
---

# Document overnight sandbox threat-model boundary and Linux setup prereqs

## Context from discovery

Per CLAUDE.md, `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/pipeline.md` owns pipeline-module internals, and `docs/sdk.md` owns SDK model-selection mechanics. After #163-#166 land, these docs do not yet describe (a) the per-spawn sandbox enforcement design, (b) the explicit threat-model boundary (Bash-only enforcement; Write/Edit/MCP bypass per [anthropics/claude-code#29048]), or (c) Linux/WSL2 sandbox prerequisites.

The reverted ticket-128 spec at `lifecycle/install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions/spec.md` was explicit about its threat-model boundary in Req 7 ("Phase 0 catches accidental and tooling-bug escapes only. Adversarial agents can bypass via..."). The discovery's critical review (R2-C) flagged that the per-spawn sandbox approach owes equivalent honest accounting in user-facing docs.

## Findings from discovery

- `docs/overnight-operations.md` is the canonical threat-model + operational story doc.
- `docs/setup.md` currently has no Linux sandbox prereq.
- `docs/pipeline.md` should reference the per-spawn sandbox shape used at `dispatch.py` post-#166 (links rather than duplicates content).
- The threat-model boundary needs explicit enumeration of out-of-scope escape paths (Write/Edit/MCP/plumbing-via-Write) so users do not assume coverage parity with ticket-128.

## Value

Operational documentation is the source-of-truth gate for users running overnight sessions; without explicit threat-model boundary, users won't know to expect Bash-only enforcement and may assume coverage parity with the reverted ticket-128 hook. Citations: `docs/overnight-operations.md` (no current threat-model section for sandbox), `docs/setup.md` (no Linux sandbox prereq).

## Acceptance criteria (high-level)

- `docs/overnight-operations.md` includes a section on per-spawn sandbox enforcement, the explicit threat-model boundary (in/out of scope), and the operational story when commits fail under sandbox denial.
- `docs/setup.md` has Linux/WSL2 prerequisites with `apt-get install bubblewrap socat` instructions.
- `docs/pipeline.md` documents the simplified `sandbox.filesystem.{allowWrite,denyWrite}` shape installed at `dispatch.py` post-#166.
- All three docs cross-reference each other at the appropriate sections (per CLAUDE.md guidance: "update the owning doc and link from the others rather than duplicating content").

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: threat-model boundary section at the top of the artifact, RQ5 (cross-platform), critical review R2-C (framing).
