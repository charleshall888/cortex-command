# Re-run Slug-Collision Semantics (spec R13)

On a re-run-from-scratch (not resume or update in place) of an existing `cortex/research/{topic}/`, do NOT overwrite the prior artifact:

(a) **Fresh slug**: `{topic}-N`, N the smallest integer ≥ 2 unique against every entry directly under `cortex/research/` (e.g. `plugin-system` → `plugin-system-2`).
(b) **`superseded:` frontmatter**: the new `cortex/research/{topic}-N/research.md` opens with YAML frontmatter whose `superseded:` key holds the relative path of the artifact it supersedes — the immediately-prior `-N` artifact when re-running over one, not the original.
(c) **Prior artifact untouched**: the existing directory is read-only for this re-run — nothing renamed, moved, or deleted; `decomposed.md` (if any) stays as a durable audit trail.
(d) **Reconciliation is manual**: the agent does not auto-reconcile the new architecture with the prior one. Surfacing differences, choosing which slug `discovery_source:` should point at, and archiving the prior artifact are explicit user decisions outside the skill.

Re-run events resolve through the helper's `resolve-events-log-path` (never hardcode the log path), landing in the `-N` log.
