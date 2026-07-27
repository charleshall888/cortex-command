# Backlog Item Schema

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 |
| `title` | string | yes | Human-readable name |
| `status` | enum | yes | `backlog`, `ready`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics: non-implementable, from `/cortex-core:discovery`) |
| `tags` | array | no | `deferred` renders Status as `<status> (deferred)` and excludes the item from `## Refined`/`## Backlog`; it does not affect overnight selection — park via a non-eligible `status` instead |
| `areas` | list[str] | no | Splits overlapping-area features into different overnight rounds; set by `/cortex-core:refine`, absent/empty = skipped. Canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs` |
| `created` / `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Associated lifecycle-feature slug, or `null` |
| `lifecycle_phase` | string | no | `null`, or `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated` |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` / `blocked-by` | array | no | Numeric IDs |
| `parent` | integer | no | Parent item's numeric ID |
| `research` | string | no | Lifecycle research doc path, set by discovery |
| `spec` | string | no | `cortex/lifecycle/{slug}/spec.md`, set by `/cortex-core:refine` |
| `discovery_source` | string | no | Discovery research artifact path, set by `/cortex-core:discovery` on epics and children |

**Array fields must use inline `[a, b]` form**, never multiline `- item` — the shell parser expects a single regex. New items carry every required field; optional arrays default to `[]`, other optional fields to `null`.

**Frame implementation approaches as suggestions, not instructions** ("one approach might be…") — research and plan evaluate them. Prescribe an exact solution only when an external constraint (API shape, platform requirement, sole library) dictates it.
