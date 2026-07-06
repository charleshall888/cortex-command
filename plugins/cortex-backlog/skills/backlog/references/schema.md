# Backlog Item Schema

Every item uses this YAML frontmatter contract, under 20 lines.

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 |
| `title` | string | yes | Human-readable name |
| `status` | enum | yes | `backlog`, `ready`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics: non-implementable, from `/cortex-core:discovery`) |
| `tags` | array | no | Inline `[tag1, tag2]` only. `deferred` renders Status as `<status> (deferred)`, excluded from `## Refined`/`## Backlog`; doesn't affect overnight selection (park via a non-eligible `status` instead) |
| `areas` | list[str] | no | Inline `[overnight-runner, backlog]` only. Splits overlapping-area features into different overnight rounds; set by `/cortex-core:refine`, absent/empty = skipped. Canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs` |
| `created` | date | yes | `YYYY-MM-DD` |
| `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Associated lifecycle-feature slug, or `null` |
| `lifecycle_phase` | string | no | `null`, or one of `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated` |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` | array | no | Inline `[1, 5]` only (numeric IDs) |
| `blocked-by` | array | no | Inline `[3, 7]` only (numeric IDs) |
| `parent` | integer | no | Parent item's numeric ID |
| `research` | string | no | Lifecycle research doc path, set by discovery |
| `spec` | string | no | Lifecycle spec path, set by `/cortex-core:refine` (`cortex/lifecycle/{slug}/spec.md`) |
| `discovery_source` | string | no | Discovery research artifact path, set by `/cortex-core:discovery` on epics and child tickets |

**Array fields (`tags`, `areas`, `blocks`, `blocked-by`) must use inline `[a, b]` form**, never multiline `- item` — the shell parser expects a single regex.

New items carry every required field above; optional arrays default to `[]`, other optional fields to `null`. The body is optional markdown for description and acceptance criteria.

**Frame implementation approaches as suggestions, not instructions** ("one approach might be...", "consider...") — the lifecycle's research and plan phases evaluate them. Prescribe an exact solution only when an external constraint (API shape, platform requirement, sole library) or an established pattern dictates it.
