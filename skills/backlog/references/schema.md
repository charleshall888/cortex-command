# Backlog Item Schema

Read this file when creating or validating backlog items.

## Frontmatter Schema

Every backlog item file uses this YAML frontmatter contract. Frontmatter must be under 20 lines.

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 identifier |
| `title` | string | yes | Short human-readable name |
| `status` | enum | yes | `backlog`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics are non-implementable, produced by /discovery) |
| `tags` | array | no | Inline YAML only: `[tag1, tag2]` |
| `created` | date | yes | `YYYY-MM-DD` |
| `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Slug of associated lifecycle feature, or `null` |
| `lifecycle_phase` | string | no | Current lifecycle phase, or `null` |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` | array | no | Inline YAML only: `[1, 5]` (numeric IDs) |
| `blocked-by` | array | no | Inline YAML only: `[3, 7]` (numeric IDs) |
| `parent` | integer | no | Numeric ID of parent item |
| `research` | string | no | Path to lifecycle research doc, set by discovery |
| `spec` | string | no | Path to lifecycle spec doc, set by /refine (lifecycle/{slug}/spec.md) |
| `discovery_source` | string | no | Path to discovery research artifact; set by /discovery on epics and child tickets |

**Inline array syntax is mandatory.** All array fields (`tags`, `blocks`, `blocked-by`) must use `[value1, value2]` form. Never use the multiline `- item` form. This keeps shell parsing tractable with a single regex pattern.

## Enum Reference

**status:** `backlog` | `refined` | `in_progress` | `implementing` | `review` | `complete` | `abandoned`

**priority:** `critical` | `high` | `medium` | `low`

**type:** `feature` | `bug` | `chore` | `spike` | `idea` | `epic`

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
created: YYYY-MM-DD
updated: YYYY-MM-DD
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
---

Optional markdown body for description and acceptance criteria.

When describing potential implementation approaches, frame them as **suggestions to explore**, not prescriptions. Use language like "one approach might be..." or "consider..." — the lifecycle's research and planning phases exist to evaluate approaches critically. Backlog items that prescribe exact solutions bypass the thinking that makes lifecycle valuable.
```
