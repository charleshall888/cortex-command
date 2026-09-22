# Backlog Item Schema

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `schema_version` | string | yes | `"1"` |
| `uuid` | string | yes | UUID v4 |
| `title` | string | yes | Human-readable name |
| `status` | enum | yes | `backlog`, `ready`, `refined`, `in_progress`, `implementing`, `review`, `complete`, `abandoned` |
| `priority` | enum | yes | `critical`, `high`, `medium`, `low` |
| `type` | enum | yes | `feature`, `bug`, `chore`, `spike`, `idea`, `epic` (epics: non-implementable, from `/cortex-core:discovery`) |
| `tags` | array | no | `deferred` shows Status as `<status> (deferred)` and hides the item from `## Refined`/`## Backlog`. Overnight selection ignores it; to park an item, give it a non-eligible `status` |
| `areas` | list[str] | no | Features that share an area run in different overnight rounds. Set by `/cortex-core:refine`; absent/empty = skipped. Canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs` |
| `created` / `updated` | date | yes | `YYYY-MM-DD` |
| `lifecycle_slug` | string | no | Associated lifecycle-feature slug, or `null` |
| `lifecycle_phase` | string | no | `null`, or `research`, `specify`, `plan`, `implement`, `implement-rework`, `review`, `complete`, `escalated` |
| `session_id` | string | no | Overnight session ID, or `null` |
| `blocks` / `blocked-by` | array | no | Numeric IDs |
| `parent` | integer | no | Parent item's numeric ID |
| `research` | string | no | Lifecycle research doc path, set by discovery |
| `spec` | string | no | `cortex/lifecycle/{slug}/spec.md`, set by `/cortex-core:refine` |
| `discovery_source` | string | no | Discovery research artifact path, set by `/cortex-core:discovery` on epics and children |

**Write arrays inline as `[a, b]`**, never as multiline `- item`: the shell parser matches one regex. New items carry every required field. Optional arrays default to `[]`, other optional fields to `null`.

**Write implementation approaches as suggestions, not instructions** ("one approach might be…"); research and plan judge them. Name an exact solution only when an outside constraint (API shape, platform requirement, sole library) forces it.
