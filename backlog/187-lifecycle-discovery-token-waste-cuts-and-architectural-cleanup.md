---
schema_version: "1"
uuid: 44c71e96-4f6a-4308-b045-785ac0d7822a
title: "Lifecycle/discovery token-waste cuts and architectural cleanup"
type: epic
status: open
priority: high
blocked-by: []
tags: [lifecycle, discovery, token-efficiency, architectural-cleanup]
created: 2026-05-11
updated: 2026-05-11
discovery_source: research/lifecycle-discovery-token-audit/research.md
---

# Lifecycle/discovery token-waste cuts and architectural cleanup

A breadth-first audit of cortex-command's lifecycle, discovery, and overnight flows identified hot-path token waste and structural debt beyond what epic #172 and ticket #185 addressed. The audit ran four parallel codebase agents, a critical-review pass that corrected one major numeric claim, and a second-round alternative-exploration pass that reshaped three of the bigger architectural proposals.

The result is seven child tickets covering distinct problem-spaces. Each ticket's research phase will commit to an approach using the audit findings + alternative-exploration outputs as evidence; this epic does not pre-bake mechanisms.

## Context from discovery

`research/lifecycle-discovery-token-audit/research.md` documents the breadth audit + critical review + alternative-exploration. Headline findings carried forward into this epic:

- **Sub-agent dispatch duplicates artifact content** across reviewers + synthesizer + main context (N+2 copies). Per-dispatch range: ~3-15k tokens depending on artifact size and reviewer count.
- **Events.log has ~10 verified-dead event types** with zero non-test Python consumers; `clarify_critic` payloads accumulate ~500 tok/feature with no consumer; `escalations.jsonl` is re-inlined every orchestrator-round. The emission-side discipline gap lets dead types accumulate.
- **Lifecycle state** (criticality, tier, task counts, rework cycles) lives in events.log and artifact files but is extracted at read-time via full-file reads — wrong-layer storage.
- **Always-on boot context**: CLAUDE.md policy blocks (~400 tok) and 13 SKILL.md descriptions (~2,300 tok) load every session; some skills may be low-value and consolidation is the lighter fix than compression.
- **Reference-file duplication**: discovery/lifecycle `orchestrator-review.md` duplicates ~130 lines cross-skill; small ceremonial references (`requirements-load.md`, the clarify-critic 5-branch table) cost more in indirection than inlining; ticket #179 was marked complete but the deliverable files were never produced.
- **Lifecycle and hook hygiene**: lifecycle SKILL.md Step 2 re-globs the backlog 4× per entry; scan-lifecycle hook unconditionally regenerates metrics; auto-scan walks 183 backlog files in code that may never be invoked; skill-edit-advisor runs the full test suite on every SKILL.md edit.
- **Process gap**: #179's closure-inaccuracy may or may not be systemic; one verified case is not enough evidence for a project-wide gate.

Critical-review of the audit corrected the original `~700 KB residue glob` claim (the glob is depth-1; actual ~36 KB), corrected SKILL.md description size from ~1,000 to ~2,300 tok, and tightened DR-1's mechanism (worktree cwd; TOCTOU pin; path-argument invocation). Alternative-exploration reshaped three structural proposals:

- The lifecycle-state-storage rethink (originally "promote to index.md frontmatter") was challenged on grounds that index.md is a passive wikilink hub and the project already uses JSON for state — child ticket leaves the storage choice open for its research phase.
- The SKILL.md description compression (originally "introduce `triggers:` frontmatter field") was challenged because no evidence exists that Anthropic's loader routes against non-`description` fields — child ticket leaves the surface-reduction approach open.
- The events-emission registry (originally "runtime rejection") was challenged in favor of a CI-time check that inverts the cost asymmetry — child ticket leaves the discipline mechanism open.

## Scope

Seven child tickets covering distinct problem-spaces:

- **#188** — Reduce sub-agent dispatch artifact duplication (critical-review, critical-tier plan, review)
- **#189** — Clean up events.log emission and reader discipline (dead-event removal, clarify_critic, escalations passing, write-side discipline)
- **#190** — Promote lifecycle state out of events.log full-reads
- **#191** — Reduce boot-context surface (CLAUDE.md + SKILL.md descriptions/bodies/skill set)
- **#192** — Reference-file hygiene (cross-skill duplication + ceremonial content + #179 extractions + injection-resistance hoist)
- **#193** — Lifecycle and hook hygiene one-offs
- **#194** — Investigate epic-172 closure-inaccuracy base rate (DR-5 spike)

## Out of scope

- Retroactive cleanup of archived `lifecycle/<feature>/` directories or archived `events.log` payloads (audit scope was going-forward only)
- Full 2-tier events.log split (deferred per #172, pending per-event consumer audit)
- Migration from file-based state to a database
- Closure-gate tooling (gated by #194's outcome)

## Suggested sequencing

- **#194 first** — closure-inaccuracy spike informs whether #192's #179-extraction component is one-off cleanup or part of a systemic issue
- **#192 before #193** — cross-skill collapse settles canonical files before in-place hygiene edits
- **#189 before #190** — events.log emission and reader cleanup gives #190 a clean baseline to design the state-storage move against
- **#188, #191, #193 in parallel** — minimal file-overlap between them

## Aggregate value

Token savings are real but secondary to architectural cleanup. The audit estimates per-week marginal savings ~50-60k tokens at typical usage; the load-bearing value is the architectural cleanup (lifecycle data model rationalization; events.log discipline; cross-skill collapse continuation; boot-context floor reduction) that makes the next audit smaller and prevents the same wrong-layer fixes from recurring.
