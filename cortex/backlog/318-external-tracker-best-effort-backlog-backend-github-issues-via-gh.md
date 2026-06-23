---
schema_version: "1"
uuid: b3edf48d-b1bd-41e5-9813-ff81b0474829
title: External-tracker best-effort backlog backend (GitHub Issues via gh)
status: backlog
priority: medium
type: feature
created: 2026-06-23
updated: 2026-06-23
parent: "315"
blocked-by: [317]
tags: ['backlog-optional-plugin']
discovery_source: cortex/research/backlog-optional-plugin/research.md
---
## Why

With the seam in place, a user who declares an external tracker still has no behavior behind it — discovery, lifecycle, and morning-review need to actually create and update tickets in that tracker. Doing so naively risks duplicate issues, lost write-back round-trips, and silent authentication failures.

## Role

Implement the external arm of the backend branch: when the configured backend is an external tracker, the interactive consumers drive it best-effort through the LLM and the user's own CLI, with no per-tracker code adapter. It covers creating tickets (compose the body with the existing composer, then create in the tracker per the user's config instructions), finding a ticket again for write-back, and failing safely. After this lands, a GitHub-Issues user gets working ticket creation and close-out from discovery and morning-review without cortex maintaining a typed client. The LLM is the adapter; this ticket gives its judgment the cautions it needs to avoid the known foot-guns.

## Integration

The external arm hangs off the backend branch from the config seam and reuses the body composer that stays in cortex-core. Create composes a body and then invokes the tracker via the user's instructions. Round-trip write-back has the LLM search the tracker for a cortex-controlled marker, read the candidates, and pick the match — the same judgment the local resolver applies to slug drift, expressed as prose the LLM follows, not a new resolver module. The path is interactive-only by construction; the overnight guard already forecloses unattended external writes.

## Edges

- Best-effort and explicitly lossy: rich local fields without a tracker analog (areas, complexity, criticality, lifecycle linkage) map to labels or body prose at best, and this is documented, not promised as parity.
- Duplicate-creation hazard: tracker search is fuzzy and eventually-consistent, so the create path must search-before-create on a cortex-controlled marker and treat a single fuzzy match as ambiguous-until-verified rather than create-then-immediately-search.
- The cortex slug or UUID is embedded in the issue body so round-trip re-resolution survives human title edits.
- Authentication must be confirmed with a positive functional probe, not a trusted exit code; on any external-write failure the composed body is surfaced to the user rather than dropped.
- Jira and other freeform backends stay unverified — the user's instructions field is the only adapter, and no canonical Jira CLI is assumed.
- The scope wall holds: this guidance is prose for the LLM, and no typed per-tracker client is added.

## Touch points

- cortex_command/backlog/resolve_item.py (local fuzzy-resolution behavior the external round-trip prose mirrors in judgment, not in code)
- skills/discovery/references/decompose.md, skills/morning-review/SKILL.md:91 (external create-path consumers)
- External CLI guidance: gh v2.94+ create/edit/list flags for type, parent, blocked-by, with the org-level issue-types caveat noted in the example instructions