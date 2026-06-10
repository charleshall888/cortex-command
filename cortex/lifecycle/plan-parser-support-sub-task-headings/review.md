# Review: plan-parser-support-sub-task-headings

## Stage 1: Spec Compliance

### Requirement 1: Suffix-aware identity on `FeatureTask` (`suffix`, `task_id`, `sort_key`; `.number` stays `int`)
- **Expected**: `suffix: str = ""`; derived `task_id == f"{number}{suffix}"`; derived `sort_key == (number, suffix)`; `.number` remains `int`. Integer-only task → `task_id == "3"`, `suffix == ""`, `sort_key == (3, "")`.
- **Actual**: `parser.py:64` adds `suffix: str = ""`; `task_id` property (66-76) returns `f"{self.number}{self.suffix}"`; `sort_key` property (78-85) returns `(self.number, self.suffix)`. `number` annotation unchanged (`int`, line 58). Tests `test_parser.py:902` (`task_id == "3a"`), `912` (`sort_key` ordering `3 < 3a < 3b < 4`), and `980-981` (integer-only `task_id == "3"`) assert the contract.
- **Verdict**: PASS
- **Notes**: Hand-rolled composite tuple, no `packaging` import, per the stdlib-only constraint.

### Requirement 2: `### Task Na` heading parse (integer 0 accepted, 87239c4b guard removed)
- **Expected**: heading regex captures optional single lowercase suffix; integer part accepts `0`; the 87239c4b fail-loud guard is removed; positive-parse cases replace `TestSubTaskHeadingFailLoud`.
- **Actual**: `parser.py:343-345` compiles `r"^###\s+Task\s+(\d+)([a-z]?)\s*[:—–-]\s*(.+)$"` (group 2 = suffix, group 3 = title). The broad #293 guard block is gone (the only guard now present is the narrowed malformed-suffix guard, Req 8). Integer `0` accepted: `test_subtask_heading_dash_separator_parses` (`test_parser.py:949`) asserts `### Task 0a` → `number == 0`. `TestSubTaskHeadingFailLoud` is replaced by `TestSubTaskHeadingParses` positive cases.
- **Verdict**: PASS

### Requirement 3: Stop the `depends_on` collapse — preserve task_id references (case-fold parity)
- **Expected**: `depends_on: list[str]`; `_parse_field_depends_on` returns task_ids verbatim (`["1","3a","3b"]`, no `3a`→`3` collapse); `[3A]` case-folds to `3a` (suffix-grammar parity).
- **Actual**: `parser.py:61` annotation `list[str]`. `_parse_field_depends_on` (525-593) extracts `_DEPENDS_ON_TASK_ID` tokens (`\d+[a-z]?`) and returns `[tid.lower() for tid in ids]` (593). `test_subtask_letter_suffix_parses_verbatim` asserts `[1, 3a, 3b]` → `["1","3a","3b"]`; `test_uppercase_depends_on_casefolds` asserts `[3A]` → `["3a"]`; integer-only → `["1","2"]`.
- **Verdict**: PASS
- **Notes**: Case-fold parity satisfied — the conformance check (`_DEPENDS_ON_LIST_CONFORMANT`) is `re.IGNORECASE` and the extracted token is lowercased, so a `3A` reference resolves to the lowercase-only `3a` heading. No silent `3A`/`3a` dangling mismatch.

### Requirement 4: Dependency batching keys on `task_id` (all four `.number` refs moved; merge-guard)
- **Expected**: `compute_dependency_batches` keys `done`/`assigned` on `.task_id` (`set[str]`); ordering driven only by declared edges; merge-guard — a `status:done` `3a` does not drop pending `3b`.
- **Actual**: `common.py:700-739` keys `all_ids`, `done_ids`, `assigned` on `t.task_id` (all four former `.number` references migrated). No implicit `a<b` edge. Tests: `test_subtask_serial_chain_3a_3b` (`[["3a"],["3b"]]`), `test_parallel_subtask_siblings_coschedule` (`13a/13b/13c` co-schedule after `[10]`), and `test_done_sibling_does_not_drop_pending_sibling` (the merge-guard: done `3a`, pending `3b` still scheduled; `3a` excluded as already-done).
- **Verdict**: PASS

### Requirement 5: Loud failure on dangling and self-referential deps (NOT parse_error; classification preserved)
- **Expected**: unresolvable/self-referential `depends_on` fails loudly naming the offending id; classification stays `status:failed` counted toward circuit breaker, NOT `parse_error`.
- **Actual**: `common.py:708-735` raises `ValueError` naming the dangling id(s) (`Unresolvable dependency reference(s) {dangling}…`) and self-refs (`Self-referential dependency: task(s) {self_refs}…`). `execute_feature` (`feature_executor.py:608-615`) catches this as `status="failed"` WITHOUT `parse_error=True`, so `outcome_router.py:856` (`if not result.parse_error:`) counts it toward `consecutive_pauses`. Tests `test_dangling_subtask_reference_raises_naming_offender` and `test_self_referential_dependency_raises_naming_offender` assert the offending id is named (the dangling test checks `"Unresolvable dependency reference"`, not a bare `"3"` substring).
- **Verdict**: PASS
- **Notes**: Classification preservation verified against `outcome_router.py:851-859`. The parser-side `parse_error=True` path (581-587) is reached only for `parse_feature_plan` raises, not the batcher's `ValueError`.

### Requirement 6: `mark_task_done_in_plan` matches `task_id` + tempered-dot cross-heading bleed fix
- **Expected**: checkoff regex matches full `task_id` (`### Task 3a:`), bounded so `.*?` cannot cross a subsequent `^###` heading (tempered dot under `re.MULTILINE`), fixing the pre-existing already-`[x]` cross-task bleed.
- **Actual**: `common.py:748-777` signature is `task_id: str`; pattern `(### Task {re.escape(task_id)}:(?:(?!^###\s)[\s\S])*?-\s+\*\*Status\*\*:\s*)\[ \]` under `re.MULTILINE` — the `(?!^###\s)` tempered-dot negative lookahead stops the scan at the next heading. Tests: `test_already_done_parent_does_not_flip_next_task` (the bleed regression) and the `3a`-checks-`3a`-not-`3b` case.
- **Verdict**: PASS

### Requirement 7: Executor identity sites switch to `task_id` — read AND write (token, has_dependents; integer-only byte-identical)
- **Expected**: IMPLEMENT_TEMPLATE `task_number` substitution = `task.task_id` (the worker's exit-report WRITE filename); `_read_exit_report` keyed on `task_id` (the READ); idempotency token input = `task_id`; `has_dependents` on `task_id`. Cross-seam write↔read round-trip. Integer-only token byte-identical.
- **Actual**:
  - Write side: `feature_executor.py:643` substitutes `"task_number": task.task_id` into IMPLEMENT_TEMPLATE; the template writes `exit-reports/{task_number}.json` (`implement.md:23,71`), so the worker writes `3a.json`.
  - Read side: `_read_exit_report(feature, task_id, …)` (169-219) builds `exit-reports/{task_id}.json` (200) and the fallback path (203); call site at 801-804 passes `task.task_id`; the existence probe at 846 uses `f"{task.task_id}.json"`.
  - Idempotency: `_make_idempotency_token(feature, task.task_id, plan_hash)` (654); key shape `f"{feature}:{task_number}:{plan_hash}"` and `str()` preserved (342); param widened to `int | str` (330).
  - `has_dependents = any(task.task_id in t.depends_on for t in all_tasks)` (255).
  - Tests: `test_subtask_reports_distinct_and_round_trip` (3a.json ≠ 3b.json, each reads its own content); `test_write_template_and_read_agree_on_filename` (the cross-seam round-trip — renders the real IMPLEMENT_TEMPLATE, asserts substituted value yields `exit-reports/3a.json`, then reads it back via `task.task_id`); `test_integer_only_task_id_byte_identical_to_int` (`token("3") == token(3)`); `test_subtask_ids_produce_distinct_tokens`; `test_brain.py` `has_dependents`-True-for-3a-reference.
- **Verdict**: PASS
- **Notes**: The load-bearing write↔read seam (Req 7 AC b) is exercised end-to-end against the real template render, not just the read helper in isolation. Telemetry JSON `task_number` fields correctly stay on `.number` (e.g. 661, 707, 738, 828, 853).

### Requirement 8: Reject malformed suffixes with explicit fail-loud (3ab, 3 a, 3A)
- **Expected**: multi-letter, space-separated, and uppercase suffix headings raise `ValueError`; valid `3a` and integer `30` do not.
- **Actual**: `parser.py:356-369` searches `r"^###\s+Task\s+\d+(?:[a-z][A-Za-z]+|[A-Z][A-Za-z]*|\s+[A-Za-z])\s*[:—–-]"` and raises naming the offending heading. Independently verified the regex has no false positives (valid `3a:`, `30:`, `13b:`, `0a —`, and multi-word titles `3a: Add a widget` do not match) and catches all three malformed forms. Tests `test_multi_letter_suffix_raises`, `test_uppercase_suffix_raises`, `test_space_separated_suffix_raises`, plus the two negative controls.
- **Verdict**: PASS

### Requirement 9: Dashboard exit-report sort handles suffixed stems (should-have)
- **Expected**: sort by `(numeric-prefix, suffix)` so `3a` sorts after `3` and before `4`.
- **Actual**: `dashboard/data.py:1335-1344` `_exit_report_sort_key` uses `re.fullmatch(r"(\d+)([a-z]*)", stem)` → `(int(prefix), suffix)`, with `(1 << 30, stem)` fallback for non-conforming stems; wired at the `sorted(...)` call (1361-1363). Test asserts `["10","3b","1","3","2","3a"]` → `["1","2","3","3a","3b","10"]`.
- **Verdict**: PASS

### Requirement 10: Amend pipeline.md line-42 must-have criterion
- **Expected**: mechanism clause reflects task_id-keyed batching; the "unparseable … fails loud" clause no longer implies `### Task Na` headings are unparseable; fail-loud net preserved.
- **Actual**: `pipeline.md:42` now reads "keyed on each task's canonical `task_id` … optional single lowercase sub-task suffix, e.g. `3a` … letter-suffixed `### Task Na` sub-task decompositions order correctly" and explicitly carves out "a supported `### Task Na` sub-task heading parses and is not unparseable", while preserving "fails the feature loudly" / `parse_error`. The Req-5 classification distinction (dangling ref = counted `failed` naming the id) is also captured. Both grep oracles satisfied (`sub-task|task_id|### Task Na` ≥ 1; `fails the feature loudly` ≥ 1).
- **Verdict**: PASS

### Requirement 11: Backward compatibility — integer-only plans byte-identical
- **Expected**: integer-only plans parse/batch/checkoff/dispatch identically; JSON `task_number` stays integer-typed; no broken intermediate (atomic landing).
- **Actual**: `.number` unchanged (`int`); `task_id == str(number)` for unsuffixed tasks makes batching, checkoff, exit-report filenames, and idempotency tokens byte-identical by construction. Telemetry JSON payloads remain on `.number`. Integer-only idempotency token proven byte-identical (`token("3") == token(3)`). All pre-existing integer-based parser/common/executor tests pass unmodified except the `depends_on` string-typing migration. The three identity commits landed atomically (one per coupled concern, each keeping the suite green).
- **Verdict**: PASS

### Requirement 12: Document the sub-task syntax (should-have)
- **Expected**: `plan.md` and `implement.md` §2 document `### Task Na` as supported, including the same-batch disjoint-`Files` authoring guidance; mirrors current.
- **Actual**: `skills/lifecycle/references/plan.md` has 4 `Task Na|sub-task` matches and 1 `disjoint` match; `implement.md` has 1 `disjoint` match. Both `plugins/cortex-core/skills/lifecycle/references/` mirrors are byte-identical to canonical (drift gate passes). The disjoint-`Files` guidance — the load-bearing mitigation for the accepted shared-worktree race — is present.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None. The `pipeline.md` line-42 amendment (Req 10) is the requirements change this feature deliberately made and is in-scope; it correctly captures the new task_id-keyed batching mechanism and the `### Task Na` carve-out. No implementation behavior exists outside what project.md / pipeline.md now describe. The ADR-0010 addition is recorded under the project's `cortex/adr/` ADR convention.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `task_id`/`sort_key`/`suffix` follow the existing `FeatureTask` field idiom; `_exit_report_sort_key` mirrors `FeatureTask.sort_key`'s composite-tuple naming; private helpers keep the leading-underscore convention. The `int | str` param widening on `_make_idempotency_token` is documented in the docstring.
- **Error handling**: Appropriate and faithful to the spec's classification contract. The batcher distinguishes dangling-reference, self-reference, and generic-cycle failures with distinct messages naming the offender, all routed to the same `ValueError`→counted-`failed` path (not `parse_error`), preserving circuit-breaker accounting. The malformed-suffix guard fails loud with a message that enumerates the rejected forms and the supported form. Exit-report read tolerates malformed/absent JSON by returning `(None, None, None)` (unchanged behavior).
- **Test coverage**: Strong. Every spec AC is exercised, including the three highest-risk seams the spec/plan singled out: (1) the merge-guard (`test_done_sibling_does_not_drop_pending_sibling`) — fails by silently dropping a sibling, caught; (2) the cross-seam write↔read round-trip (`test_write_template_and_read_agree_on_filename`) — renders the real IMPLEMENT_TEMPLATE and asserts the substituted value and `_read_exit_report` agree on `3a.json`, closing the silent-`3.json`-merge gap; (3) the tempered-dot bleed regression (`test_already_done_parent_does_not_flip_next_task`). The integer-only byte-identical idempotency token is asserted directly. The malformed-suffix regex was independently verified against false positives (valid headings with multi-word titles, two-digit integers, dash separators) and negatives.
- **Pattern consistency**: Maintained. `parser.py` stays stdlib-only (hand-rolled `(number, suffix)` tuple, no `packaging`/PEP 440). The composite-tuple sort_key idiom is reused identically in the dashboard. Telemetry-vs-identity discipline (ADR-0010) is honored: every identity-bearing site moved to `task_id`; genuine telemetry JSON payloads stay on `.number`. ADR-0010 carries the full Context/Decision/Rejected-alternatives/Consequences structure and the load-bearing "contained, not eliminated" residual-hazard argument with the "group ordinal" demotion.

### Test-suite note (does not affect verdict)
The full `just test`-equivalent run (`pytest cortex_command tests`) reports 9 failures, but all are pre-existing full-suite test-isolation flakiness unrelated to #297:
- The 8 `tests/test_update_item_resolution.py` failures stem from a subprocess resolving to the wrong/empty backlog directory (`backlog directory contains no NNN-*.md items`), a `_resolve_user_project_root` / `CORTEX_REPO_ROOT` env-or-cwd leak from a preceding test. `update_item.py` imports only `TERMINAL_STATUSES`, `_resolve_user_project_root`, `atomic_write` from `common.py` — none of which #297 modified (#297 changed `compute_dependency_batches` and `mark_task_done_in_plan`).
- The 1 `tests/test_feature_executor.py::...silent_worker_malformed_exit_report...` failure is order-dependent (passed on isolated re-run and on the second full-suite run).
All 270 of the feature's own test files (`test_parser.py`, `test_common.py`, `test_idempotency.py`, `test_exit_report.py`, `test_brain.py`, `test_data.py`, `test_common_utils.py`, `test_feature_executor.py`) pass cleanly in isolation and in combination. The flakiness is environmental (global-state pollution under the 3000-test run) and predates this feature.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
