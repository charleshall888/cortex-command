# Specification: add-tag-filter-to-backlog-query

## Problem Statement

`cortex-backlog-ready` cannot filter its output by tag. The upstream spec `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` Req 15 arms the Phase 2 trigger by tagging ticket #232 with `phase2-trigger` and asserting that `cortex-backlog list --tag phase2-trigger | grep -c "discovery-output-density" ≥ 1` returns the ticket. The literal grep cannot pass today: no `cortex-backlog list` command exists, and `cortex-backlog-ready` does not accept `--tag`. The Phase 2 trigger is named in spec prose but is not actually queryable by tag — operational arming is partial. Adding `--tag` to `cortex-backlog-ready` and amending the upstream spec's grep closes the arming gap.

## Phases

- **Phase 1: CLI filter** — add `--tag` argument to `cortex-backlog-ready` and exercise it under tests.
- **Phase 2: Upstream spec hygiene** — amend the upstream `discovery-output-density-investigate-author-centric` spec and review to reference `cortex-backlog-ready --tag` instead of the never-existed `cortex-backlog list --tag`.

## Requirements

1. **CLI accepts `--tag <TAG>` argument, repeatable**: `cortex-backlog-ready --tag phase2-trigger` runs without an argparse "unrecognized arguments" error. The flag is registered in `_parse_args` at `cortex/backlog/ready.py` using `action="append"` with `default=None` (then coerced to `[]` after parsing). **Acceptance**: `cortex-backlog-ready --tag phase2-trigger; echo $?` prints `0`. **Phase**: Phase 1.

2. **Single `--tag` filters the ready set to items whose `tags` array contains the specified tag (case-sensitive exact match)**: When ticket #232 (`tags: [phase2-trigger]`) is in the active backlog with an eligible status, it appears in the output. **Acceptance**: `cortex-backlog-ready --tag phase2-trigger | python3 -c 'import json,sys; d=json.load(sys.stdin); ids=[i["id"] for g in d["groups"] for i in g["items"]]; print(232 in ids)'` prints `True`. **Phase**: Phase 1.

3. **Multiple `--tag` flags use AND semantics — items must carry every listed tag**: `--tag tooling-gap --tag X` returns only items tagged with both `tooling-gap` and `X`. **Acceptance**: a unit test in `tests/test_backlog_ready_tag_filter.py` builds a fixture with items tagged `[tooling-gap]`, `[X]`, and `[tooling-gap, X]`, then asserts that `--tag tooling-gap --tag X` returns only the `[tooling-gap, X]` item; `pytest tests/test_backlog_ready_tag_filter.py::test_multi_tag_and_semantics -q` exits 0. **Phase**: Phase 1.

4. **Tag matching is case-sensitive and exact**: `--tag PHASE2-TRIGGER` does not match items tagged `phase2-trigger`. **Acceptance**: a unit test asserts `--tag PHASE2-TRIGGER` returns zero items when fixtures include `phase2-trigger`-tagged records; `pytest tests/test_backlog_ready_tag_filter.py::test_case_sensitive_match -q` exits 0. **Phase**: Phase 1.

5. **Zero-match exits 0 with empty groups (not exit 1)**: `cortex-backlog-ready --tag nonexistent-tag-xyz; echo $?` prints `0`, and stdout JSON parses with every group's `items` array empty. **Acceptance**: `cortex-backlog-ready --tag nonexistent-tag-xyz | python3 -c 'import json,sys; d=json.load(sys.stdin); print(all(len(g["items"])==0 for g in d["groups"]))'` prints `True`. **Phase**: Phase 1.

6. **`--tag` composes with `--include-blocked` by filtering both `groups` and `ineligible` arrays**: `cortex-backlog-ready --tag phase2-trigger --include-blocked` emits stdout JSON in which both `groups[*].items` and `ineligible[*].items` are restricted to items whose `tags` array contains `phase2-trigger`. **Acceptance**: a unit test builds a fixture where one ready item and one ineligible item both carry `[phase2-trigger]`, runs the CLI with `--tag phase2-trigger --include-blocked`, and asserts both arrays contain the expected items only; `pytest tests/test_backlog_ready_tag_filter.py::test_filter_applies_to_ineligible -q` exits 0. **Phase**: Phase 1.

7. **Existing behavior is preserved when `--tag` is not passed**: `cortex-backlog-ready` (no `--tag`) and `cortex-backlog-ready --include-blocked` produce stdout byte-identical to pre-change output. **Acceptance**: `tests/test_backlog_ready_render.py` (existing snapshot test against `tests/fixtures/backlog_ready_render.json`) passes unchanged; `pytest tests/test_backlog_ready_render.py -q` exits 0. **Phase**: Phase 1.

8. **CLI `--help` documents the new flag**: `cortex-backlog-ready --help` includes `--tag` in its output with help text explaining repeatable AND semantics. **Acceptance**: `cortex-backlog-ready --help | grep -c '\-\-tag'` ≥ 1. **Phase**: Phase 1.

9. **Upstream spec Req 15's literal grep is amended to use `cortex-backlog-ready --tag`**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` no longer contains the string `cortex-backlog list --tag`. **Acceptance**: `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` = 0; `grep -c 'cortex-backlog-ready --tag phase2-trigger' cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` ≥ 1. **Phase**: Phase 2.

10. **Upstream review.md references are amended consistently**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` no longer contains `cortex-backlog list --tag`. **Acceptance**: `grep -c 'cortex-backlog list --tag' cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` = 0. **Phase**: Phase 2.

## Non-Requirements

- **Does NOT introduce a `cortex-backlog` umbrella CLI**. No new `[project.scripts]` entry, no new bin shim, no new `plugins/cortex-core/bin/` mirror. Scope-locked to extending the existing `cortex-backlog-ready` script.
- **Does NOT introduce a `cortex-backlog-list` alias** or alternative spelling. One name, one surface.
- **Does NOT change the `index.json` schema or `cortex_command/backlog/generate_index.py`**. The generator already propagates `tags` (line 177); no upstream change is needed.
- **Does NOT add `tags` to `_item_payload`'s wire-format output**. The `tags` field is filter-input only; surfacing it in stdout would force fixture regeneration in `tests/test_backlog_ready_render.py` for orthogonal reasons.
- **Does NOT modify `_ELIGIBLE_STATUSES`, reason-string contracts, sort keys, or priority grouping**. The filter is layered on top of the existing pipeline, not woven into it.
- **Does NOT add a `--no-tag` exclude flag, OR-mode opt-in, or any other filter modifier**. AND-mode is the only mode. Additional modes are deferred until demand exists.
- **Does NOT add tag-normalization helpers** (lowercase coercion, whitespace strip). Matching is byte-exact; YAML frontmatter is already lowercase by convention.
- **Does NOT modify ticket #232's frontmatter** or the originating ticket #233. Only the `cortex/lifecycle/discovery-output-density-investigate-author-centric/` artifacts are amended in Phase 2.

## Edge Cases

- **Item with empty or missing `tags` field**: filtered out when any `--tag` is specified. The filter reads `raw.get("tags") or []` and applies AND semantics on the empty list → never matches a non-empty `--tag` set.
- **Item with whitespace or capitalization variant of the requested tag** (e.g., `tags: [" phase2-trigger"]` or `[Phase2-Trigger]`): does NOT match. Matching is byte-exact case-sensitive. Existing tags are lowercase; surfacing zero results forces the user to fix malformed tag input.
- **`--tag` passed with empty string** (`--tag ""`): the empty string matches no items (no real frontmatter tag is the empty string), so the result is zero matches with exit 0. The CLI does not reject empty values explicitly — argparse accepts them and the filter naturally excludes them.
- **`--tag` with duplicate values** (`--tag X --tag X`): equivalent to `--tag X` (set-membership AND of `{X}` with itself). No special handling; the filter deduplicates via `set()` membership testing.
- **`--tag` combined with `--include-blocked`** applied to a fixture where the same tag spans both ready and ineligible items: both buckets are returned, filtered consistently. Per Requirement 6.
- **Stale-index warning fires while `--tag` is in use**: warnings go to stderr per existing `_check_stale_index` behavior; the `--tag` filter does not suppress or alter them. Stdout JSON behavior is independent of stale-index warnings.
- **`--tag` with a tag value containing special shell characters** (`--tag 'foo bar'`): the filter compares the exact post-argparse string against tag-list entries. Tag values with spaces are not currently used in any backlog item, but the filter does not break — they simply never match.
- **`backlog/index.json` is malformed or missing**: existing error contract (`_emit_error`) fires first, returning exit 1 with `{"error": ..., "schema_version": 1}` before any `--tag` filtering. `--tag` does not change error-path behavior.

## Changes to Existing Behavior

- **ADDED**: `cortex-backlog-ready --tag <TAG>` argument; repeatable; AND semantics across multiple `--tag` flags; case-sensitive exact match against each item's `tags` frontmatter array; filters both `groups` and `ineligible` (when `--include-blocked` is also passed); zero matches exits 0 with empty groups (consistent with the no-`--tag` path).
- **MODIFIED**: `cortex-backlog-ready --help` output now lists `--tag`.
- **MODIFIED**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` Req 15 acceptance grep now references `cortex-backlog-ready --tag` instead of `cortex-backlog list --tag` (and any related body text adjusted for consistency).
- **MODIFIED**: `cortex/lifecycle/discovery-output-density-investigate-author-centric/review.md` Req 15 entries updated to match the amended spec.

## Technical Constraints

- **Filter placement**: apply the `--tag` filter inside `cortex/backlog/ready.py:_build_result` (lines 307–372). The filter must run BEFORE `partition_ready` is called, OR after partition but before `_group_by_priority`. Pre-partition placement is preferred — it avoids classifying ineligible items that won't be emitted, reduces work, and ensures the `--include-blocked` ineligible projection naturally inherits the same filter without separate plumbing.
- **Wire-format pruning**: `_item_payload` (lines 139–148) must NOT include `tags` in its output projection. The fixture `tests/fixtures/backlog_ready_render.json` is silent on tags by design; adding `tags` to wire output would force snapshot regeneration for unrelated reasons.
- **Argparse pattern**: use `parser.add_argument("--tag", action="append", default=None, help="Filter to items whose tags array contains all specified --tag values (repeatable, AND semantics, case-sensitive)")`. Avoid `default=[]` per [Python bug 16399](https://bugs.python.org/issue16399) — append-on-default mutates a shared list. Coerce `args.tag = args.tag or []` after parsing.
- **`tags` field availability**: `cortex_command/backlog/generate_index.py:177` already propagates `tags` into `index.json` via `_parse_inline_str_list`. No upstream generator change required. The filter reads `raw.get("tags") or []` per record.
- **AND semantics implementation**: `set(args.tag).issubset(set(raw.get("tags") or []))` is the canonical predicate. Avoid `all(t in raw.get("tags",[]) for t in args.tag)` — equivalent in semantics but slower for repeated `--tag` invocations.
- **Stdlib-only**: `cortex/backlog/ready.py` has no external dependencies. Preserve that — use `set` from stdlib, no third-party set-ops libraries.
- **Read-only emitter**: the CLI is described as a "lightweight read-only JSON emitter" (lines 60–65). The filter preserves this — no writes, no event emissions, no telemetry.
- **JSON error contract**: malformed inputs route through existing `_emit_error(reason)` returning exit 1 with `{"error": ..., "schema_version": 1}`. The `--tag` filter does not invent new error paths.
- **Dual-source mirror unchanged**: `bin/cortex-backlog-ready` and `plugins/cortex-core/bin/cortex-backlog-ready` are pass-through bash shims (`exec ... "$@"`). The filter addition does not require shim edits.
- **Test home convention**: new tests go in `tests/test_backlog_ready_tag_filter.py` — separate from `tests/test_backlog_ready_render.py` to keep behavior tests distinct from wire-contract snapshot tests. Both files are collected per `pyproject.toml [tool.pytest.ini_options] testpaths`.
- **Reason-string contract preserved**: `cortex_command/backlog/readiness.py` reason-string formats remain untouched. `--tag` is a scope-narrowing filter, not blocker classification.

## Open Decisions

None. All four research-surfaced open questions were resolved during the spec interview.

## Proposed ADR

None considered.
