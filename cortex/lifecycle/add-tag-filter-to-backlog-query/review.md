# Review: add-tag-filter-to-backlog-query

## Stage 1: Spec Compliance

### Requirement 1: CLI accepts `--tag <TAG>` argument, repeatable
- **Expected**: `--tag` registered in `_parse_args` using `action="append"` with `default=None`; coerced to `[]` after parsing; `cortex-backlog-ready --tag phase2-trigger; echo $?` prints `0`.
- **Actual**: `_parse_args` at `cortex/backlog/ready.py:404–415` registers `--tag` with `action="append"`, `default=None`, `dest="tag"`. Post-parse coercion at lines 417–418: `if args.tag is None: args.tag = []`. Exit 0 confirmed by test suite and manual `--help` invocation.
- **Verdict**: PASS

### Requirement 2: Single `--tag` filters ready set to items whose `tags` array contains the tag (case-sensitive exact match)
- **Expected**: Items matching the specified tag appear in output; non-matching items excluded.
- **Actual**: Filter at `_build_result` lines 328–330 applies `required_set <= set(r.get("tags") or [])` pre-partition. `test_single_tag_match` passes: fixture with items tagged `["phase2-trigger"]`, `["other"]`, and `[]` — only item 1 appears in output with `--tag phase2-trigger`.
- **Verdict**: PASS
- **Notes**: Acceptance criterion #232 staleness is an acceptance-criterion staleness issue, not an implementation defect (per review brief). The filter correctly operates against active index items; #232 moved to terminal status after spec authorship and is excluded by `generate_index.py` before the filter sees it. The filter itself is correct.

### Requirement 3: Multiple `--tag` flags use AND semantics
- **Expected**: Items must carry every listed tag; `--tag tooling-gap --tag X` returns only items tagged with both.
- **Actual**: `required_set <= set(...)` is strict subset-equality (AND). `test_multi_tag_and_semantics` passes: fixture with items tagged `["tooling-gap"]`, `["X"]`, `["tooling-gap", "X"]`, and `[]` — only item 3 (carrying both) appears.
- **Verdict**: PASS

### Requirement 4: Tag matching is case-sensitive and exact
- **Expected**: `--tag PHASE2-TRIGGER` does not match `phase2-trigger`.
- **Actual**: Matching is byte-exact set membership. `test_case_sensitive_match` passes: fixture has item 1 tagged `["phase2-trigger"]` and item 2 tagged `["PHASE2-TRIGGER"]`; `--tag PHASE2-TRIGGER` returns only item 2, `--tag phase2-trigger` returns only item 1.
- **Verdict**: PASS

### Requirement 5: Zero-match exits 0 with empty groups (not exit 1)
- **Expected**: `cortex-backlog-ready --tag nonexistent-tag-xyz; echo $?` = `0`; every group's `items` array is empty.
- **Actual**: Filter produces an empty `records` list; the rest of the pipeline runs normally emitting empty groups. `test_zero_match_exits_zero_with_empty_groups` passes: exit code 0, JSON parses, all `group["items"] == []`.
- **Verdict**: PASS

### Requirement 6: `--tag` composes with `--include-blocked` by filtering both `groups` and `ineligible` arrays
- **Expected**: Both `groups[*].items` and `ineligible[*].items` restricted to items whose `tags` contain the requested tag.
- **Actual**: Tag filter runs pre-partition at lines 328–330; `_build_result` then applies `partition_ready` over the already-filtered `records`. Both ready and ineligible buckets naturally inherit the restriction because they draw from the same filtered records pool. `test_filter_applies_to_ineligible` passes: fixture with items 1 (ready, tagged `phase2-trigger`), 2 (ready, tagged `other`), 3 (blocked, tagged `phase2-trigger`), 4 (blocker, tagged `other`) — `--tag phase2-trigger --include-blocked` returns ready=[1], ineligible=[3].
- **Verdict**: PASS

### Requirement 7: Existing behavior is preserved when `--tag` is not passed
- **Expected**: `tests/test_backlog_ready_render.py` snapshot test passes unchanged.
- **Actual**: `args.tag` coerces to `[]` when absent; `_build_result` skips the filter block (`if required_tags:` is false for empty list). `tests/test_backlog_ready_render.py::test_backlog_ready_render_snapshot` passes (1 passed, 0 failures).
- **Verdict**: PASS

### Requirement 8: CLI `--help` documents the new flag
- **Expected**: `cortex-backlog-ready --help | grep -c '\-\-tag'` ≥ 1; help text explains repeatable AND semantics.
- **Actual**: `--help` output includes `--tag TAG` with text "Filter to items carrying this tag. Repeatable; all specified tags must be present (AND semantics). Matching is case-sensitive. Example: --tag phase2-trigger --tag my-label". `grep -c '\-\-tag'` = 3 (≥ 1). AND semantics and repeatability documented explicitly.
- **Verdict**: PASS

### Requirement 9: Upstream spec Req 15's literal grep is amended to use `cortex-backlog-ready --tag`
- **Expected**: `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` = 0; `grep -c 'cortex-backlog-ready --tag phase2-trigger' ...` ≥ 1.
- **Actual**: Both acceptance criteria confirmed: former grep = 0, latter grep = 2. Req 15 acceptance text reads "cortex-backlog-ready --tag phase2-trigger | grep -c 'discovery-output-density' ≥ 1".
- **Verdict**: PASS

### Requirement 10: Upstream review.md references are amended consistently
- **Expected**: `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` = 0.
- **Actual**: Grep = 0 confirmed. Req 15 entry in review.md updated to reflect the resolved wiring: references `cortex-backlog-ready --tag phase2-trigger` and includes the forward-pointer "Resolved by ticket #233 (add-tag-filter-to-backlog-query) on 2026-05-18 — cortex-backlog-ready --tag phase2-trigger now functions."
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `required_tags` parameter name is descriptive and matches the `required_` prefix convention used elsewhere in the module. `_build_result` signature extension follows the `*`, keyword-only style already in use. Test helpers (`_make_record`, `_write_md`, `_build_backlog`, `_run`, `_all_ids`, `_all_ineligible_ids`) follow the leading-underscore module-private convention. Test function names are verb-phrase descriptions matching the existing `test_backlog_ready_render.py` naming style.

- **Error handling**: Appropriate for context. The filter introduces no new error paths — it operates on the already-loaded, already-validated `records` list inside `_build_result`. `r.get("tags") or []` handles both missing keys and `None` values defensively without introducing branches that could alter exit codes. The existing `_emit_error` / exception-catch hierarchy in `main()` is untouched and covers all error cases before and after the filter.

- **Test coverage**: All six named behavior tests pass (6/6). Coverage maps cleanly to the spec's requirements: Reqs 2–6 each have a dedicated test, and the `all_items_ns` scoping invariant (that the corpus used for blocker resolution is intentionally left unfiltered) is covered by `test_blocker_resolution_uses_unfiltered_corpus`. The invariant test is a meaningful regression guard — it would catch any future refactor that incorrectly applies the tag filter to `all_items_ns`. Req 7 is covered by the pre-existing snapshot test. The test file is correctly placed in `tests/` per the `pyproject.toml` testpaths configuration.

- **Pattern consistency**: Pre-partition filter placement (lines 328–330) matches the spec's preferred approach and avoids any need for separate plumbing to filter the `ineligible` projection. The `set(required_tags) <= set(r.get("tags") or [])` predicate uses the spec-canonical `issubset` form (via `<=`) rather than the slower `all(t in ...)` form. Shim files (`bin/cortex-backlog-ready`, `plugins/cortex-core/bin/cortex-backlog-ready`) are pass-through `exec "$@"` wrappers and correctly require no changes. `tags` is not added to `_item_payload`, preserving the wire-contract snapshot test.

## Acceptance-Criterion Staleness Note (Plan-level Acceptance #1)

The review brief correctly characterizes the #232 situation as acceptance-criterion staleness, not an implementation defect. The filter operates correctly: `generate_index.py` excludes terminal-status items from `index.json` before `cortex-backlog-ready` reads the file, so the filter never encounters #232. This is the intended behavior — the ready script operates over active items only, and terminal items are not candidates for the ready set. The spec's operational arming intent (make phase2-trigger-tagged items queryable) is satisfied by active ticket #233 (`cortex-backlog-ready --tag tooling-gap` returns #233 as the review brief confirms). No implementation change is warranted: accommodating terminal-status items in `index.json` would be a schema change to `generate_index.py`, which is explicitly a non-requirement.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
