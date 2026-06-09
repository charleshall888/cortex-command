# Review: morning-report-scans-all-lifecycle-dirs

## Stage 1: Spec Compliance

### Requirement 1: Generated ticket titles round-trip exactly through the strict parser and never abort it.
- **Expected**: `create_followup_backlog_items` serializes the `title` value so `Follow up: {name}` / `Retry deferred: {name}` (embedded `: `) parses via `resolve_item._parse_frontmatter` (`yaml.safe_load`) without raising and round-trips to the in-memory value. Test reads written files for a deferred + a failed colon-bearing feature and asserts the real strict parser returns the exact title.
- **Actual**: `report.py:339` now writes `f"title: {_yaml_safe_title_value(title)}\n"`. The helper (`report.py:238-264`) sanitizes control chars, dumps `{"title": sanitized}` via `yaml.safe_dump(default_flow_style=False, width=inf, allow_unicode=True)`, strips the trailing `\n`, asserts single-line, splits on first `": "`, returns the scalar. `test_generated_titles_round_trip_strict` builds `feat-fail:colon` (failed) + `feat-defer:colon` (deferred), writes via the real function, and asserts `resolve_item._parse_frontmatter(...)["title"]` equals the exact title for both.
- **Verdict**: PASS
- **Notes**: Verified serializer output by hand: colon-bearing titles emit a single-quoted single-line scalar that `yaml.safe_load` round-trips exactly. Test uses the REAL strict parser as the spec mandates.

### Requirement 2: The canonical backlog creator title is hardened.
- **Expected**: `create_item.py:112` (`f'title: "{title}"\n'`) serializes titles so embedded special characters do not break the strict parser; a test creates an item with an embedded double-quote + colon and asserts an exact round-trip through `resolve_item._parse_frontmatter` without raising.
- **Actual**: `create_item.py:139` now writes `f"title: {_yaml_safe_title_value(title)}\n"` using a helper (`create_item.py:53-77`) with the identical sanitize-then-`safe_dump`-then-split contract. `test_create_item_title_round_trips_strict` is parametrized over `'Weird: a "quoted" thing'` (quote + colon) and `"Fix: it's broken"` (apostrophe + colon), calls `create_item.create_item(...)` (the real public creator), neutralizes the index-regen subprocess for hermeticity, and asserts the strict parser returns the exact title.
- **Verdict**: PASS
- **Notes**: Apostrophe case serializes as YAML-doubled `''` and round-trips exactly through the strict parser, per the spec's accepted Edge Case.

### Requirement 3: The serialization does not corrupt the tolerant index parser.
- **Expected**: Realistic kebab titles round-trip exactly through `generate_index._parse_frontmatter` (first-colon split + `.strip("\"'")`); the serialized title is one physical line with no `...` marker; MUST NOT use `json.dumps` and MUST NOT emit a `...` / folded scalar.
- **Actual**: `test_generated_title_tolerant_round_trip` generates `Retry deferred: climb-gated-locomotion`, asserts the next physical line is `status:` (single-line title), asserts no `...` marker anywhere, and asserts `generate_index._parse_frontmatter(text)["title"].strip("\"'")` equals the title (mirroring the consumer's quote-strip at `generate_index.py:162`). The helper uses `yaml.safe_dump({"title": ...})` (not `json.dumps`) with `width=float("inf")` (no folding) and the mapping form (no `...` marker).
- **Verdict**: PASS
- **Notes**: Confirmed `generate_index.py:162` strips wrapping quotes; the test's quote-strip mirror is faithful to the real consumer.

### Requirement 4: Titles are serialized as a sanitized single-line scalar.
- **Expected**: Embedded newline/control chars in `name` are collapsed/stripped before serialization; a test with an embedded-newline name asserts the title field is single-line and round-trips through the strict parser.
- **Actual**: The helper's first step is `re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", name)` (sanitize before dump — ordering load-bearing). `test_generated_title_newline_sanitized_single_line` uses `name="line\nbreak"`, asserts the next line after `title:` is `status:` (no fold), writes the isolated title line to a temp file, and asserts the strict parser yields `Retry deferred: line break`.
- **Verdict**: PASS
- **Notes**: Sanitization precedes `safe_dump`, so `width=inf` plus collapsed newlines guarantee a single physical line.

### Requirement 5: Existing inline frontmatter layout is preserved.
- **Expected**: Generated frontmatter keeps inline `tags: [...]` and existing field order; only the title scalar is serialized (not a whole-block `safe_dump`).
- **Actual**: Only the `title` value is passed through the helper; the surrounding f-string block is unchanged. `test_generated_frontmatter_layout_preserved` asserts `text.count("tags: [") == 1` and that the field order is exactly `[title, status, priority, type, tags, created, updated, blocks, blocked-by, schema_version, uuid, lifecycle_slug, session_id]`.
- **Verdict**: PASS
- **Notes**: No whole-block serialization; inline list and pinned order intact.

### Requirement 6: Residue section is session-scoped.
- **Expected**: `render_critical_review_residue` renders only residue whose lifecycle dir name (`path.parent.name`) is in `data.state.features`; a test with `feat-a` in-session and `old-unrelated` not in-session shows `feat-a` present, `old-unrelated` absent.
- **Actual**: `report.py:1085-1087` computes `session_features` and filters `residue_paths` on `p.parent.name in session_features`. `TestResidueSessionScope.test_in_session_present_unrelated_absent` writes both dirs, sets `CORTEX_REPO_ROOT`, and asserts `feat-a` present / `old-unrelated` absent.
- **Verdict**: PASS
- **Notes**: Join key is the directory name, not the payload field — see R9.

### Requirement 7: Drift section is session-scoped as a narrowing gate, composed with existing exclusions.
- **Expected**: `render_pending_drift` renders only review.md whose dir name is in `data.state.features`, AND-composed with the pre-existing `merged`/`reimplementing` exclusions (never re-includes an already-excluded feature). Tests: unrelated dir absent; a keyset-member that is `merged` still excluded.
- **Actual**: `report.py:711-718` adds a second `continue` guard (`if session_features is not None and feature not in session_features: continue`) AFTER the existing `if feature in merged or feature in reimplementing: continue` — a monotonic narrowing gate. `test_in_session_drift_renders_unrelated_excluded` asserts unrelated absent; `test_merged_feature_still_excluded` asserts a `merged` in-session feature is omitted.
- **Verdict**: PASS
- **Notes**: The gate is additive and ordered after the exclusions, so it can only remove, never re-add.

### Requirement 8: The residue `(N)` header count equals the number of entries actually rendered.
- **Expected**: The `## Critical Review Residue (N)` count is recomputed from the rendered (filtered) set, never the raw glob count when a filter applied. Tests: `{feat-a, feat-b}` → `(2)`, `{feat-a}` → `(1)`.
- **Actual**: Filtering happens at `report.py:1087` BEFORE `total = len(residue_paths)` at `:1089` (ordering load-bearing, as the plan requires). `test_header_count_reflects_filtered_set` asserts `(2)` for both-in-session and `(1)` for one. `test_malformed_skip_respects_filter` further pins the count under the filter×skip interaction (in-session malformed counted; out-of-session malformed filtered out → `(1)`).
- **Verdict**: PASS
- **Notes**: Count derives from the filtered list on every path.

### Requirement 9: Join on directory name; filter on the full keyset; verify the join key.
- **Expected**: Membership uses `path.parent.name` (not `payload["feature"]`) and intersects the FULL `data.state.features` keyset (paused/deferred/failed surface). Tests: deferred feature renders; divergence test where dir name decides inclusion regardless of `payload["feature"]`.
- **Actual**: Filter is `p.parent.name in session_features` and `session_features = set(data.state.features)` (full keyset, no merged-only subset). `test_deferred_in_session_feature_renders` asserts a `deferred` feature surfaces. `test_join_on_dir_name_not_payload_feature` writes an in-session dir `feat-a` whose payload feature is `not-in-session-label` (renders) and an out-of-session dir `old-dir` whose payload feature is `feat-a` (excluded) — a true two-sided divergence discriminator.
- **Verdict**: PASS
- **Notes**: The divergence test cleanly proves the dir name (not the writer-controlled payload field) is the join key.

### Requirement 10: Present-but-empty state renders empty; only absent state renders unfiltered.
- **Expected**: `data.state` present (including `features == {}`) → filter by keyset → zero-feature session renders empty with `(0)` and an accurate empty body; only `data.state is None` renders unfiltered. Existing `state=None` residue tests unchanged.
- **Actual**: `session_features = set(...) if data.state is not None else None`; `filtered = session_features is not None`. Present-empty `{}` filters to empty → `(0)` and the new empty body "No in-session critical-review residue this cycle." (`report.py:1093`), distinct from the absent-state body. `test_present_empty_state_renders_empty_zero` asserts `(0)`, on-disk feature absent, and the accurate empty body. `test_state_none_renders_unfiltered` asserts unfiltered render under `None`. Drift parity: `test_present_empty_state_scopes_drift_to_zero` asserts `render_pending_drift(data) == ""` for `features == {}`. Pre-existing `state=None` residue suite (`Test_critical_review_residue`) still passes.
- **Verdict**: PASS
- **Notes**: The empty-vs-absent split is handled distinctly for both sections, with an accurate filtered-empty message that does not falsely claim total absence.

### Requirement 11: The entire drift path is CWD-independent.
- **Expected**: Re-anchor ALL `cortex/lifecycle`-relative constructions reachable from `render_pending_drift` to `_resolve_user_project_root()` (resolve at call time): two globs, inline `events_path`, `_read_requirements_drift`, `_read_drift_protocol_breaches`. Acceptance (a) the two file-global greps = 0; (b) a CWD-independence test.
- **Actual**: All FIVE drift-reachable sites are re-anchored: `lifecycle_root = _resolve_user_project_root() / "cortex/lifecycle"` (call-time, `report.py:692`), the two globs (`:697`, `:711`), the inline `events_path = lifecycle_root / feature / "events.log"` (`:700`), `_read_requirements_drift` (`:921`), and `_read_drift_protocol_breaches` (`:977`). `grep -c 'Path("cortex/lifecycle")'` = **0** (PASS). `grep -c 'Path(f"cortex/lifecycle/'` = **7** — these are the SEVEN deliberately-untouched NON-drift sites (plan reads at 832/849/874, recovery-log 991, progress 1008, session sidecars 1339/1485), which the plan's Risks section and the operator decision at plan approval explicitly narrowed out of scope (re-anchoring the session sidecars would be unsafe → silent data loss). Per the review instructions this narrowing is the approved spec interpretation and is NOT a FAIL. Tests: `test_drift_render_is_cwd_independent` (chdir elsewhere, `CORTEX_REPO_ROOT` at fixture → in-session drift resolves); `test_reimplementing_exclusion_is_cwd_independent` is a strong two-sided discriminator — the reimplementing pre-scan (read via the re-anchored events path) still excludes `feat-reimpl` off-CWD while a sibling `feat-ok` renders (a CWD-relative pre-scan would have surfaced `feat-reimpl`).
- **Verdict**: PASS
- **Notes**: The `grep = 0` literal for `Path(f"cortex/lifecycle/` is not met (7 remain), but this is the operator-narrowed acceptance from the plan, treated as the approved spec interpretation; the prose intent ("literals reachable from render_pending_drift") is fully satisfied — all five drift-reachable sites are re-anchored and proven CWD-independent.

### Requirement 12: Full suite passes.
- **Expected**: `just test` exits 0.
- **Actual**: `just test` reported 6/7 groups passing; the single failure is `tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, which is UNTOUCHED by this feature (no diff in `96ce04cc..HEAD`). The failure is a sandbox network restriction: its `uv run --script` could not reach `https://pypi.org/simple/pydantic/` ("dns error / failed to lookup address information"). Re-running that exact test with network access: **1 passed**. The five targeted suites (`cortex_command/overnight/tests/test_report.py`, `tests/test_report.py`, `tests/test_create_backlog_item.py`) all pass: 65 passed.
- **Verdict**: PASS
- **Notes**: The lone `just test` failure is an environment/network artifact, not a code regression in this feature. Confirmed the test passes when network is available, and it is outside this feature's changed-file set.

## Requirements Drift
**State**: none
**Findings**:
- None. The change touches the overnight report path (`report.py`) and the backlog creator (`create_item.py`). The relevant project.md constraints are honored: it does not alter the backlog status vocabulary (`TERMINAL_STATUSES` / `_TERMINAL`), preserves graceful partial failure (malformed-JSON per-file skip retained), and does not introduce a shared serializer (consistent with the spec's accepted in-place duplication). No new MUST/CRITICAL escalation was introduced. No project- or glossary-level requirement is contradicted or newly required by this work.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the module. `_yaml_safe_title_value` is descriptive and parallel across both writers; `session_features`, `filtered`, `lifecycle_root` read clearly. Test names encode the requirement (`test_*_round_trip_strict`, `test_join_on_dir_name_not_payload_feature`).
- **Error handling**: The serializer guarantees a valid single-line scalar via sanitize-then-`safe_dump`; the residue loop's malformed-JSON per-file skip is preserved inside the post-filter loop, so the filter wraps it without changing skip semantics. The drift path degrades correctly: `state is None` → unfiltered fallback (bias to over-show), present-empty → scope-to-zero. The `assert "\n" not in dumped` in both serializers is a defensive guard, not a correctness dependency: sanitization already strips all control chars (including `\n`) before `safe_dump`, and `width=float("inf")` disables folding, so the dumped output is provably single-line; the assert can only fire on a future logic regression in the helper. No `-O`/`PYTHONOPTIMIZE` is used anywhere in the runner/CLI invocation path (verified), so the assert is never stripped in practice. Acceptable.
- **Test coverage**: Strong and the plan's verification commands are satisfiable. Tests use the REAL strict (`resolve_item._parse_frontmatter`) and tolerant (`generate_index._parse_frontmatter`) parsers per the spec's explicit constraint, plus a whole-backlog `resolve()`-does-not-raise integration test that exercises the actual Bug B blast-radius surface (the eager loop at `resolve_item.py:426`). The drift CWD-independence tests are two-sided discriminators (a broken implementation would visibly fail, not silently pass). The divergence test for R9 and the malformed-skip×filter interaction test (R8) close the subtle edges.
- **Pattern consistency**: The two serializers are intentionally duplicated (spec Non-Requirements: no shared serializer extracted) with identical logic and docstrings noting the rationale. Re-anchoring uses the established call-time `_resolve_user_project_root()` idiom already present at `report.py:54`/`:128`/`:1075`. The session-scope filter mirrors between residue (list comprehension) and drift (`continue` guard) — both keyed on the directory name against the full keyset, with matching `None`-vs-empty semantics.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
