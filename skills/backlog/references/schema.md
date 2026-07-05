# Backlog Item Schema

## Frontmatter Schema

Every backlog item file uses this YAML frontmatter contract. Frontmatter must be under 20 lines.

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 identifier |
| `title` | string | yes | Short human-readable name |
| `status` | enum | yes | `backlog`, `ready`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics are non-implementable, produced by /cortex-core:discovery) |
| `tags` | array | no | Inline YAML only: `[tag1, tag2]`. The `deferred` tag is an index-view signal: the generator renders Status as `<status> (deferred)` and excludes the item from the `## Refined`/`## Backlog` groupings. It does NOT affect overnight selection — to park from overnight, set a non-eligible `status` (e.g. `abandoned`). |
| `areas` | list[str] | no | Inline YAML only: `[overnight-runner, backlog]`. Overnight scheduling separates features with overlapping areas into different rounds. Written by `/cortex-core:refine` at spec approval; absent/empty = separation skipped. Canonical names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs` |
| `created` | date | yes | `YYYY-MM-DD` |
| `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Slug of associated lifecycle feature, or `null` |
| `lifecycle_phase` | string | no | Current lifecycle phase, or `null`. Value set: `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated`. |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` | array | no | Inline YAML only: `[1, 5]` (numeric IDs) |
| `blocked-by` | array | no | Inline YAML only: `[3, 7]` (numeric IDs) |
| `parent` | integer | no | Numeric ID of parent item |
| `research` | string | no | Path to lifecycle research doc, set by discovery |
| `spec` | string | no | Path to lifecycle spec doc, set by /cortex-core:refine (cortex/lifecycle/{slug}/spec.md) |
| `discovery_source` | string | no | Path to discovery research artifact; set by /cortex-core:discovery on epics and child tickets |

**Array fields (`tags`, `areas`, `blocks`, `blocked-by`) must use inline `[a, b]` form**, never multiline `- item` — the shell parser expects a single regex.

## Item Template

```markdown
---
schema_version: "1"
uuid: <uuid4>
title: Short descriptive name
status: backlog
priority: medium
type: feature
tags: [relevant, tags]
areas: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
---

Optional markdown body for description and acceptance criteria.

**Frame implementation approaches as suggestions, not instructions** ("one approach might be...", "consider...") — the lifecycle's research and plan phases evaluate them. Prescribe an exact solution only when (1) an external constraint dictates it (API shape, platform requirement, sole library) or (2) it replicates an established repo pattern. Prior investigation ("I checked and it's correct") does not qualify — that confidence is the starting point for the research phase, not a reason to skip it.
```
