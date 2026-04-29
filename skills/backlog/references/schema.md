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
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics are non-implementable, produced by /cortex-interactive:discovery) |
| `tags` | array | no | Inline YAML only: `[tag1, tag2]` |
| `areas` | list[str] | no | Inline YAML only: `[overnight-runner, backlog]`. Area-separation constraint for overnight scheduling — features with overlapping areas are assigned to different rounds. Written by `/cortex-interactive:refine` at spec approval time. If absent or empty, separation constraint is silently skipped (identical to current algorithm). When all items in a session share an area, every item runs in its own single-item batch (fully serialized execution) — this is intended. Zero effect until populated; protection scales with how many items have the field. Canonical names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs` |
| `created` | date | yes | `YYYY-MM-DD` |
| `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Slug of associated lifecycle feature, or `null` |
| `lifecycle_phase` | string | no | Current lifecycle phase, or `null`. Value set: `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated`. (`implement-rework` was added when lifecycle phase detection was unified around `claude/common.py`.) |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` | array | no | Inline YAML only: `[1, 5]` (numeric IDs) |
| `blocked-by` | array | no | Inline YAML only: `[3, 7]` (numeric IDs) |
| `parent` | integer | no | Numeric ID of parent item |
| `research` | string | no | Path to lifecycle research doc, set by discovery |
| `spec` | string | no | Path to lifecycle spec doc, set by /cortex-interactive:refine (lifecycle/{slug}/spec.md) |
| `discovery_source` | string | no | Path to discovery research artifact; set by /cortex-interactive:discovery on epics and child tickets |

**Inline array syntax is mandatory.** All array fields (`tags`, `areas`, `blocks`, `blocked-by`) must use `[value1, value2]` form. Never use the multiline `- item` form. This keeps shell parsing tractable with a single regex pattern.

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

**Implementation approaches must use exploratory framing by default.** Frame approaches as suggestions, not instructions. Use language like "one approach might be...", "consider...", or "research could explore..." — the lifecycle's research and planning phases exist to evaluate approaches critically. Backlog items that prescribe exact solutions bypass the thinking that makes lifecycle valuable.

**Prescriptive framing is acceptable only in two narrow cases:**
1. **No viable alternatives exist** — the solution is dictated by an external constraint (API shape, platform requirement, sole available library).
2. **The approach exactly follows an already-established codebase pattern** — the ticket is asking to replicate something the repo already does elsewhere, and the pattern is the point.

"I investigated this and believe it is correct" does not meet either exception. That level of confidence is precisely what the lifecycle research and plan phases exist to establish — it is the *starting point* for investigation, not the conclusion that justifies skipping it.
```
