# Review: unified-backlog-lifecycle-slug-resolver-extend

## Stage 1: Spec Compliance

### Requirement 1: Library function `resolve()` exists in `cortex_command/backlog/resolve_item.py`
- **Expected**: Module exposes pure `resolve(input_str, backlog_dir) -> ResolutionResult`; `ResolutionResult` is a frozen dataclass with `status`, `item`, `candidates`; IO/parse failures raise `ResolutionError`. Acceptance: import-line returns 0.
- **Actual**: `cortex_command/backlog/resolve_item.py:52-68` defines `@dataclass(frozen=True) ResolutionResult(status, item, candidates)`; `:44-49` defines `ResolutionError`; `:382-495` defines `resolve()` with the required signature. Acceptance probe `uv run python -c "from cortex_command.backlog.resolve_item import resolve, ResolutionResult, ResolutionError; print('ok')"` exits 0 and prints `ok`. The CLI shim at `:519-530` catches `ResolutionError` and maps it to exit-70.
- **Verdict**: PASS

### Requirement 2: 5-step deterministic resolution order implemented in `resolve()`
- **Expected**: Order UUID prefix → numeric → kebab (with/without NNN-) → lifecycle_slug → title-substring; first step with ≥1 match returns; ≥2 → ambiguous, 1 → ok. Acceptance: `test_resolution_order` exits 0.
- **Actual**: `resolve_item.py:432-490` implements the order verbatim with the documented return semantics. The parametrized `test_resolution_order` at `tests/test_resolve_backlog_item.py:754-798` covers one positive case per step (UUID `dadaf6b6` → step 1, `3` → step 2, `alpha`/`001-alpha` → step 3, `step-four-lifecycle-slug` → step 4, `Gamma` → step 5) and `test_resolution_order_fall_through` (`:801-827`) exercises the negative branch. Targeted pytest run passes.
- **Verdict**: PASS

### Requirement 3: UUID-prefix branch requires minimum 8 hex characters
- **Expected**: Pure-hex regex `^[0-9a-fA-F]+(-[0-9a-fA-F]+)*$` + hex-length ≥8 (hyphens stripped), case-insensitive prefix match; len 1-7 falls through. Acceptance: `test_uuid_prefix_minimum_length` exits 0 covering len-7 (falls through), len-8 unique resolve, ambiguous 8-char prefix.
- **Actual**: `_resolve_uuid_prefix` at `:192-214` gates on `_UUID_PREFIX_RE.match(input_str)` and `len(hex_only) >= _UUID_PREFIX_MIN_HEX_LEN` (8); returns `[]` on fail-gate so caller falls through. `test_uuid_prefix_minimum_length` (`:690-728`) parametrizes the exact three cases: `"a3b9ae8"` (len 7) → `not_found`; `"dadaf6b6"` (len 8 unique) → `ok`; `"a3b9ae8a"` (len 8, shared by three corpus items) → `ambiguous` with 3 candidates. Plus `test_uuid_prefix_case_insensitive` and `test_uuid_prefix_non_hex_falls_through` add coverage. All pass.
- **Verdict**: PASS

### Requirement 4: `cortex-resolve-backlog-item` CLI preserves its current exit-code contract
- **Expected**: Exits {0, 2, 3, 64, 70} preserved; UUID-prefix and lifecycle_slug-frontmatter resolutions feed the same surface; no regression on existing curated corpus.
- **Actual**: CLI shim at `resolve_item.py:504-579` returns exactly those exit codes mapped from `ResolutionResult` status / `ResolutionError`. Full `tests/test_resolve_backlog_item.py` (61 tests) passes including the legacy R5-R11 suite and the new T3/T4 tests.
- **Verdict**: PASS

### Requirement 5: Frozen 3-step baseline snapshot + order-drift regression test
- **Expected**: `tests/fixtures/predicate_3step_baseline.json` exists and non-empty; `test_no_order_drift_against_baseline` exits 0.
- **Actual**: Fixture present (`tests/fixtures/predicate_3step_baseline.json`, 116 lines, 24 rows with `source_sha=6ee7d51b78c5f036a2617dfd098e16b3a8e0f769`, `captured_at=2026-05-25T23:03:00.525939+00:00`). The capture happened at commit 79fb9c65 before T2/T3 mutated the resolver, satisfying the structural sequential gate. `test_no_order_drift_against_baseline` (`tests/test_resolve_backlog_item.py:1340-1406`) runs three checks (capture-ordering, drift, allowlist) and passes against the post-5-step resolver. Source-SHA divergence between baseline and current resolver source is observed as expected, confirming the gate fires structurally.
- **Verdict**: PASS

### Requirement 6: `cortex_command/backlog/update_item.py:_find_item` consumes `resolve()` directly
- **Expected**: `_find_item` reduces to a `resolve()` call; inline UUID-prefix and unranked substring branches removed. Acceptance: `grep -c "slug_or_uuid in p.stem"` = 0 AND `grep -c "uuid_val.startswith"` = 0.
- **Actual**: `_find_item` at `update_item.py:114-141` is now a thin shim that calls `resolve(slug_or_uuid, backlog_dir)` and maps the result. Inline UUID branch and unranked substring branch are gone. Both grep counts return 0. A companion `_find_item_with_status` at `:144-149` returns the full `ResolutionResult` for the CLI handler to surface ambiguity.
- **Verdict**: PASS

### Requirement 7: `cortex-update-item` surfaces ambiguity as exit-2 + stderr candidate list
- **Expected**: On `status="ambiguous"`, CLI exits 2 and writes `_format_candidates`-shaped output to stderr; no file mutation. Acceptance: `test_ambiguous_exits_2_with_candidate_list` exits 0 asserting exit code, regex shape, and mtime non-mutation.
- **Actual**: `update_item.py:564-584` handles the ambiguous branch by invoking `_format_candidates` (imported from `resolve_item`) to stderr and returning 2 — and crucially, this happens before `update_item()` is ever called, so no mutation occurs. The parametrized `test_ambiguous_exits_2_with_candidate_list` at `tests/test_update_item_resolution.py:218-289` asserts `returncode == 2`, regex-matches the candidate-list format (`^ambiguous:\s+\d+\s+matches\n…`), confirms the header lists the correct match count, asserts each filename appears in stderr, and verifies mtime is unchanged for every candidate file. All cases pass.
- **Verdict**: PASS

### Requirement 8: `cortex-update-item` not-found case stays exit-1
- **Expected**: On `status="not_found"`, CLI exits 1 with `Item not found: <input>` on stderr.
- **Actual**: `update_item.py:586-588` returns 1 and emits exactly `f"Item not found: {slug_or_uuid}"` on stderr. `test_not_found_exits_1` (`tests/test_update_item_resolution.py:292-329`) parametrizes two missing inputs, asserts exit-1, message, and mtime non-mutation. Passes.
- **Verdict**: PASS

### Requirement 9: Shared test corpus fixture (`CURATED_INPUTS` promoted to `backlog_resolution_corpus`)
- **Expected**: Corpus extracted verbatim into `tests/conftest.py` or new module; consumed by both test files; `grep -c "backlog_resolution_corpus"` = 2 across both files; pytest passes.
- **Actual**: `tests/conftest.py:96-128` defines `BACKLOG_RESOLUTION_CORPUS` with the verbatim 25-entry corpus from the previous in-file definition. A pytest fixture `backlog_resolution_corpus` (`:131-138`) re-exports the constant. The `make_item` helper (formerly `_make_item`) is also promoted (`:141-157`). Both `tests/test_resolve_backlog_item.py` and `tests/test_update_item_resolution.py` import from `tests.conftest`. Grep count returns 22 (test_resolve_backlog_item.py) + 6 (test_update_item_resolution.py) = 28, well above the ≥2 minimum. Both pytest files pass.

  Note on T3 deviation flagged in the brief: the agent did not literally extend `CURATED_INPUTS` with new cases (UUID-prefix 7/8, ambiguous 8-char, prefix-stripped stem ambiguity). Instead, those cases are covered by `_make_item`-backed synthetic backlogs in dedicated parametrized tests (`test_uuid_prefix_minimum_length`, `test_stem_with_or_without_prefix`, `test_substring_ambiguity_exit_2`, etc.). The rationale is sound: extending `CURATED_INPUTS` would break T1's source-SHA-pinned baseline parity, and the synthetic-backlog approach offers tighter per-case isolation than mixing into a shared corpus. R2/R3/R5 are satisfied in spirit because the new cases ARE exercised, just via dedicated synthetic backlogs rather than the live-backlog corpus.
- **Verdict**: PASS

### Requirement 10: Six skill files updated for exit-2 handling
- **Expected**: One new sentence (or bullet) per file specifying exit-2 ambiguity + user action; `grep -cE "exit[ -]?2|ambiguous|disambiguat"` ≥ 6 (one per file).
- **Actual**: Per-file grep counts are wontfix.md:1, refine SKILL.md:6, complete.md:1, clarify.md:7, morning-review SKILL.md:2, backlog-writeback.md:1 — every file has ≥1, total ≥ 6 with all six files contributing. The added prose is consistent across files: "If `cortex-update-item` exits with code 2, the slug was ambiguous: present the candidate list on stderr to the user and ask them to re-invoke with a disambiguated slug." Refine and clarify get the addition in two call sites each (complexity/criticality write-back + status/areas write-back; resolver branch + write-back, respectively).
- **Verdict**: PASS

### Requirement 11: Resolver does NOT verify lifecycle directory existence
- **Expected**: Step-4 reads frontmatter only; no on-disk lifecycle-directory check introduced. Acceptance: `grep -c "cortex/lifecycle"` in `resolve_item.py` returns the same count post-change as pre-change.
- **Actual**: `_resolve_lifecycle_slug_frontmatter` at `resolve_item.py:217-232` checks only `fm.get("lifecycle_slug", "")` and string equality — no filesystem call. `grep -c "cortex/lifecycle"` returns 0 in both pre-change and post-change source (verified via `git show 79fb9c65^:...`). `test_lifecycle_slug_frontmatter_step_no_directory_check` (`:848-864`) confirms the resolver matches a `lifecycle_slug` pointing at a nonexistent directory.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with the project's existing patterns. The new `resolve()` public function and `ResolutionResult` / `ResolutionError` types follow PEP-8 and the module's existing convention (private helpers underscored, public surface clean). The promoted helper renamed from `_make_item` to `make_item` per the conftest comment ("no leading underscore so cross-file imports are idiomatic") aligns with the project's broader convention for shared test utilities. `_find_item_with_status` as a parallel surface to `_find_item` is a clean way to expose `ResolutionResult` to the CLI while preserving the legacy `Path | None` contract for external callers (e.g., `outcome_router._find_backlog_item_path`). Documented in the docstring at `update_item.py:114-128`.

- **Error handling**: Appropriate for the boundary. The library `resolve()` raises `ResolutionError` for IO/parse failures and the CLI catches it at `resolve_item.py:519-530`, mapping to exit-70. The shim `_find_item` swallows `ResolutionError` and returns `None` to preserve the legacy `Path | None` contract for external callers — a conservative choice (the docstring explicitly notes ambiguity also degrades to "no match" for legacy callers, "safer than the historic silent-first-match behavior being replaced"). The bare-`except Exception` wrap inside `resolve()` at `:494-495` re-raises as `ResolutionError`, ensuring downstream catchers see a consistent type. Frontmatter-parse errors during the eager-load phase at `:425-430` propagate cleanly with the offending filename in the message.

- **Test coverage**: Verification steps from the spec's acceptance gates are all executed and passing. Confirmed by direct test execution:
  - `tests/test_resolve_backlog_item.py`: 61 tests pass (includes the 3-step baseline capture/divergence pair, the new T3 5-step order tests, T4 order-drift gate, plus the original R5-R11 suite).
  - `tests/test_update_item_resolution.py`: 15 tests pass (library-level `_find_item_with_status` shape across the 5-step order; subprocess-level exit-0/1/2 surface with mtime non-mutation checks).
  - Acceptance probes: import line for R1 (passes), grep gates for R6 (both return 0), R9 (returns 28 ≥ 2), R10 (six files all ≥ 1), R11 (returns 0 = pre-change count).
  - The order-drift regression test `test_no_order_drift_against_baseline` exercises both the capture-ordering gate and the documented_3step_to_5step_divergences allowlist; the allowlist contains the three spec-anticipated transitions (`fix`, `add`, `overnight`). The brief flagged that these inputs empirically were already exit-2 under the 3-step order (so the "silent-first-match → exit-2" transition described in the spec is over-stated for those inputs) — but the over-inclusion is benign as the brief acknowledges, and the allowlist provides the structural lock the spec's R5 intent calls for.

- **Pattern consistency**: Follows existing project conventions cleanly. The pure-library-function-plus-CLI-shim split mirrors the standard Python CLI design pattern referenced in the spec's "Proposed ADR" section. The shared-test-corpus extraction into `tests/conftest.py` follows the existing pattern of `enumerate_skills` / `enumerate_canonical_skills` helpers already present in the file. The skill-prose update is uniform across the six files (same sentence shape, same handoff to the user). Plugin mirrors at `plugins/cortex-core/skills/lifecycle/references/{backlog-writeback,clarify,complete,wontfix}.md`, `plugins/cortex-core/skills/refine/SKILL.md`, and `plugins/cortex-overnight/skills/morning-review/SKILL.md` are byte-identical to canonical sources (`diff -q` clean) per the project's dual-source enforcement.

  One quality observation (not a blocker): `skills/morning-review/SKILL.md:99,107,109` contains pre-existing stale prose ("`cortex-update-item` script accepts backlog file slugs or numeric IDs — not lifecycle slugs", "IDs must be zero-padded to 3 digits", "does substring matching and may still find a match") that pre-dated this lifecycle (`git show 79fb9c65^` confirms) and contradicts the new resolver semantics — lifecycle_slug is now a first-class step, numeric resolution accepts both padded and unpadded IDs, and substring matching now exits-2 on ambiguity. The spec R10 only required adding the exit-2 prose, which was done correctly. The legacy stale prose is out of scope for this ticket but would be a clean follow-up under a doc-hygiene ticket.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
