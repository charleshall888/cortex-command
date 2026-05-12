# Task 7 — `tags:` Backfill Audit Memo

**Phase A deliverable.** This memo enumerates every lifecycle `index.md` lacking a `tags:` field and the proposed tag-array value derived from the corresponding backlog item. The operator reviews this memo BEFORE the index.md edits land (Phase B). The Phase 1 PR body references this file for sign-off.

## Scope

- Source query: `find cortex/lifecycle -maxdepth 2 -name index.md -not -path "*/archive/*" -exec grep -L "^tags:" {} \;`
- Affected files: **10** (matches spec R6 estimate).
- Excluded: `cortex/lifecycle/archive/**` per spec.
- Tag source: the `tags:` array in the parent backlog item's frontmatter (`cortex/backlog/{id}-*.md`).

## Schema-variance note (operator-attention item)

The Task 7 prose (and spec R6) refers to a `parent_backlog_id` frontmatter field on each lifecycle `index.md`. In practice, **none of the 10 affected files use that exact field name**. The schema is heterogeneous:

| Field used                              | Count | Slugs                                                                 |
| --------------------------------------- | ----- | --------------------------------------------------------------------- |
| `backlog_filename: "<id>-<slug>.md"`    | 7     | `audit-cortex-coreresearch...`, `clean-up-eventslog...`, `consolidate-commonpyread...`, `promote-lifecycle-state...`, `reduce-sub-agent-dispatch...`, `shared-git-index-race...`, `trim-cortex-log-invocation...` |
| `backlog_id: <int>` (no "parent_")      | 2     | `lifecycle-and-hook-hygiene-one-offs`, `reference-file-hygiene...`    |
| `backlog_item: null` (no parent)        | 1     | `auto-progress-lifecycle-phases-when-no-blockers`                     |

Backfill treats any of these as the de-facto parent reference. **Operator: confirm this interpretation is acceptable**; harmonizing the field name to `parent_backlog_id` is out of scope for Task 7 (would be a separate schema-migration ticket).

## Mapping table

| # | lifecycle-slug | parent_backlog_id (de facto) | source backlog file | derived tags | notes |
|---|---|---|---|---|---|
| 1 | `audit-cortex-coreresearch-skill-output-shape-for-token-waste-in-researchmd-sections` | 185 (via `backlog_filename`) | `cortex/backlog/185-audit-cortex-core-research-skill-output-shape-for-token-waste.md` | `[research-skill, token-efficiency, artifact-densification, sub-agent-output-shape]` | Direct copy from backlog frontmatter. |
| 2 | `auto-progress-lifecycle-phases-when-no-blockers` | null (`backlog_item: null`) | — | `[]` | No parent backlog. Insert `tags: []` with inline comment that loader falls back to `project.md`-only. |
| 3 | `clean-up-eventslog-emission-and-reader-discipline` | 189 (via `backlog_filename`) | `cortex/backlog/189-clean-up-events-log-emission-and-reader-discipline.md` | `[events-log, emission-discipline, escalations, clarify-critic, token-efficiency]` | Direct copy. |
| 4 | `consolidate-commonpyread-tier-and-overnight-reportpy-read-tier` | 199 (via `backlog_filename`) | `cortex/backlog/199-consolidate-commonpyread-tier-and-overnight-reportpy-read-tier.md` | `[refactor, lifecycle, deduplication]` | Direct copy. |
| 5 | `lifecycle-and-hook-hygiene-one-offs` | 193 (via `backlog_id`) | `cortex/backlog/193-lifecycle-and-hook-hygiene-one-offs.md` | `[lifecycle, hooks, hygiene, scan-script, auto-scan]` | Direct copy. |
| 6 | `promote-lifecycle-state-out-of-eventslog-full-reads` | 190 (via `backlog_filename`) | `cortex/backlog/190-promote-lifecycle-state-out-of-events-log-full-reads.md` | `[lifecycle, state-storage, events-log, data-model]` | Direct copy. |
| 7 | `reduce-sub-agent-dispatch-artifact-duplication` | 188 (via `backlog_filename`) | `cortex/backlog/188-reduce-sub-agent-dispatch-artifact-duplication.md` | `[dispatch, critical-review, plan, review, token-efficiency]` | Direct copy. |
| 8 | `reference-file-hygiene-cross-skill-ceremonial-179-extractions` | 192 (via `backlog_id`) | `cortex/backlog/192-reference-file-hygiene-cross-skill-and-ceremonial-content.md` | `[skills, references, cross-skill-collapse, ceremony, process-gap]` | Direct copy. Note: backlog filename slug ("reference-file-hygiene-cross-skill-and-ceremonial-content") differs from lifecycle slug ("reference-file-hygiene-cross-skill-ceremonial-179-extractions"); resolved by `backlog_id: 192` lookup. |
| 9 | `shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits` | 135 (via `backlog_filename`) | `cortex/backlog/135-shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits.md` | `[]` | **Edge case**: parent backlog item exists but has **no `tags:` field** in its frontmatter (status `wontfix`, created pre-tagging). Per R6 fallback semantics, the loader falls back to `project.md`-only. Operator review point: confirm `[]` is correct vs. inferring tags from `type: bug` / title keywords. Memo recommendation: stay literal — `[]`. |
| 10 | `trim-cortex-log-invocation-shim-cost-per-call-21ms` | 198 (via `backlog_filename`) | `cortex/backlog/198-trim-cortex-log-invocation-shim-cost-per-call-21ms.md` | `[bin, performance, shim]` | Direct copy. |

## Items requiring extra operator attention

1. **Row 2 (`auto-progress-lifecycle-phases-when-no-blockers`)**: only `backlog_item: null` lifecycle in the set. Inserts `tags: []` with the loader-falls-back-to-`project.md`-only inline comment exactly as R6 mandates.
2. **Row 9 (`shared-git-index-race-...`)**: the parent backlog item (135) exists but predates tagging and is `wontfix`. No tags to copy. Memo proposes `tags: []` (literal) with inline comment noting backlog has no tags. Alternative: infer tags from areas/type — **not recommended** because it introduces a heuristic R6 explicitly avoids.
3. **Schema-naming variance** (see "Schema-variance note" above): the Task 7 prose says "derive tags from `parent_backlog_id` lookup" but no affected file uses that field name. Backfill resolves the parent backlog by whichever field is present (`backlog_filename`, `backlog_id`, or absence-implies-null). If the operator wants strict `parent_backlog_id` field-name harmonization, that is a separate ticket — Task 7 should not silently rewrite field names alongside the tag insert.
4. **Row 8 (`reference-file-hygiene-...`)**: backlog filename slug doesn't match the lifecycle slug. Resolved via `backlog_id: 192` lookup, not filename. Recorded for traceability.

## Phase B plan (NOT executed in this dispatch)

After operator sign-off on this memo:

- Insert one new frontmatter line `tags: <array>` into each of the 10 `index.md` files at the position immediately after the existing identity fields (slug/feature/title) and before `artifacts:`. Preserve all other frontmatter keys and values verbatim.
- For Row 2 and Row 9, the inserted line is `tags: []  # loader falls back to project.md-only (R1)` per R6 wording.
- Verification: `find cortex/lifecycle -maxdepth 2 -name index.md -exec grep -L "^tags:" {} \;` returns empty.
- Phase 1 PR body cites this memo by relative path so reviewers can re-derive each tag decision.
