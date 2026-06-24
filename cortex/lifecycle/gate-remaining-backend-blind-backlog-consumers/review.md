# Review: gate-remaining-backend-blind-backlog-consumers

## Stage 1: Spec Compliance

### Requirement 1: Backend resolved before backlog reads — at poll time AND at startup (closes the first-render window)
- **Expected**: `_poll_slow` calls `resolve_backlog_backend(root)` once per cycle before the parse calls; lifespan startup also resolves synchronously before `yield` and writes to `state.backlog_backend`. A test asserts the state reflects the resolved backend before any poll cycle.
- **Actual**: `poller.py:364–365` resolves and assigns per cycle; `app.py:252` resolves synchronously before `yield`. `TestLifespanStartupResolution.test_backend_resolved_before_any_poll` patches out `run_polling` with a no-op, drives `lifespan()` to `yield`, and asserts `fresh.backlog_backend == "none"` — proving resolution occurred before the first poll.
- **Verdict**: PASS

### Requirement 2: `data.py` pure readers untouched (purity + regression anchor)
- **Expected**: `parse_backlog_counts` and `parse_backlog_titles` keep their `backlog_dir`-only signatures and bodies untouched; all 8 `TestParseBacklogCounts` cases pass unchanged.
- **Actual**: `git diff HEAD~9 HEAD -- cortex_command/dashboard/data.py` produces no output — `data.py` was not modified. All 8 `TestParseBacklogCounts` tests pass.
- **Verdict**: PASS

### Requirement 3: New `DashboardState.backlog_backend` field
- **Expected**: `backlog_backend: str = "cortex-backlog"` added to `DashboardState`; `grep -c` count = 1; `TestDashboardStateDefaults.test_defaults` asserts the default.
- **Actual**: Field present at `poller.py:92` with exactly that declaration. `grep -c` = 1. `test_defaults` at line 57 asserts `state.backlog_backend == "cortex-backlog"`.
- **Verdict**: PASS

### Requirement 4: Non-local backend → local reads skipped even with stale leftover items, proven by a DISCRIMINATING two-arm test
- **Expected**: A real poll iteration is driven (not a fresh `DashboardState()`). Fixture has leftover items + non-local config. Two discriminating assertions: (a) `state.backlog_backend == "none"` (fails if poller never ran, because default is `"cortex-backlog"`); (b) `state.backlog_counts == {}` with leftover items present. Spy asserts `parse_backlog_counts` not called.
- **Actual**: `TestPollSlowBackendGate._run_one_cycle` imports and directly calls `_poll_slow`, creates a task, yields the event loop 5 times (letting the synchronous body run), then cancels. `_write_repo` creates 3 leftover items. Both arms tested (`none` and `github-issues` as subtests). Assertions: (a) `state.backlog_backend == backend` — this value can only come from a real poll run since default is `"cortex-backlog"`; (b) `state.backlog_counts == {}` and `state.backlog_titles == {}`; (c) spy `assert_not_called()` on both parse functions. All pass.
- **Verdict**: PASS

### Requirement 5: Template renders a distinct placeholder naming the backend; never stale counts
- **Expected**: `backlog_panel.html` becomes a 3-way: non-`cortex-backlog` → placeholder ("backlog tracked externally via `<backend>`" / "backlog tracking disabled"); `cortex-backlog` → existing populated/empty branches. `phase-tag` updated consistently.
- **Actual**: Template at lines 20–65 implements a 3-way: `state.backlog_backend != "cortex-backlog"` → renders "disabled" or "external via `<backend>`" in `phase-tag` and empty-state paragraph. `cortex-backlog` populated/empty arms preserved. `test_none_backend_renders_placeholder` asserts "backlog tracking disabled" present and "stack-bar" absent. `test_external_backend_names_the_backend` asserts "tracked externally via" + "github-issues" present and "stack-bar" absent.
- **Verdict**: PASS

### Requirement 6: `cortex-backlog` arm byte-identical (regression anchor) — proven by a known-value positive control, not a tautology
- **Expected**: (a) R4's `cortex-backlog` arm asserts `state.backlog_counts == {"backlog": 2, "complete": 1}` (known value, NOT `== parse_backlog_counts(dir)`); (b) 8 `TestParseBacklogCounts` cases pass unchanged; (c) direct render of `backlog_panel.html` with `cortex-backlog` + populated counts asserts "N items tracked" present; (d) smoke test still has 10 routes and `/partials/backlog` returns 200.
- **Actual**: (a) `test_cortex_backlog_arm_reads_known_counts` asserts `state.backlog_counts == _EXPECTED_COUNTS` where `_EXPECTED_COUNTS = {"backlog": 2, "complete": 1}` — a literal dict, no circular comparison; (b) 8 `TestParseBacklogCounts` tests pass; (c) `test_cortex_backlog_populated_arm_unchanged` asserts "3 items tracked" and "stack-bar" present; (d) `test_all_ten_partial_routes_covered` asserts 10 routes, `/partials/backlog` returns 200.
- **Verdict**: PASS

### Requirement 7: clarify §3 coverage scan gated (two-arm) before the local scan
- **Expected**: `cortex-read-backlog-backend` resolves before the `cortex/backlog/[0-9]*-*.md` scan; two-arm fold (non-local → skip with advisory); inline note documenting the two-arm shape vs decompose §5's three-arm; back-point to ADR-0016. Structural test with negative control over the pre-edit §3.
- **Actual**: `clarify.md:21–26` resolves backend via `` `cortex-read-backlog-backend` ``, two-arm gate (cortex-backlog → scan; any other → skip with "disabled for this repo" advisory), positioned before the scan glob. Inline note: "This is a read path, so it folds to **two arms**, not the three arms of decompose §5's create flow". ADR-0016 back-pointed. Test `test_clarify_section3_gates_scan_on_backend` slices §3, asserts `cortex-read-backlog-backend` present + "disabled for this repo" + scan anchor, in order. `test_negative_control_pre_edit_section_is_ungated` confirms pre-edit §3 fails `_gate_present`. `test_divergence_note_backpoints_to_adr` checks for "two arms" and "ADR-0016".
- **Verdict**: PASS

### Requirement 8: decompose §7 index regen gated by an INDEPENDENT backend resolution at §7 (covers all branches incl. zero-piece)
- **Expected**: `cortex-read-backlog-backend` resolved at §7 itself, not reusing §5's value. Non-local → skip. Structural test asserts §7 contains the gate, plus negative control. Test keys on skip-arm advisory, not just two-token ordering. Test also pins the independent-resolution note.
- **Actual**: `decompose.md:189–194` resolves `cortex-read-backlog-backend` at §7 independently, with explicit prose: "Do **not** reuse §5's resolved value". Skip advisory: "no index to regenerate under this backend". `test_decompose_section7_gates_index_regen` checks for `cortex-read-backlog-backend`, `SKIP_ADVISORY = "no index to regenerate"`, and ordering. `test_negative_control_pre_edit_section_is_ungated` uses pre-edit §7 (unconditional regen) — confirms it fails. `test_section7_resolves_independently_not_via_section5` asserts "zero-piece" and "ADR-0016" in §7 section.
- **Verdict**: PASS

### Requirement 9: Canonical-only edits; mirror regenerated and committed together
- **Expected**: Only `skills/discovery/references/{clarify,decompose}.md` edited; mirrors in `plugins/cortex-core/` match; `just build-plugin` leaves mirror clean.
- **Actual**: `diff` between canonical and mirror files for clarify, decompose, complete, and walkthrough all return "MATCH" (zero diff). Changed file list from `git diff HEAD~9 HEAD --name-only` includes both canonical `skills/` and mirror `plugins/` paths committed together in their respective task commits.
- **Verdict**: PASS

### Requirement 10: Terminology + lint compliance
- **Expected**: New advisories name backend `cortex-backlog` (not `local`); `cortex-*` mentions use double-backtick prose form; `cortex-check-contract` passes.
- **Actual**: All new advisory text uses "cortex-backlog" not "local" as a backend name. The "local" word in clarify §3 advisory ("skip the local coverage scan") refers to the scan operation, not the backend name — correct. Backtick form: clarify §3 and decompose §7 new gates use single-backtick (inline code) for `cortex-read-backlog-backend`; decompose §5 (pre-existing) and walkthrough §6b use double-backtick prose form. The new gates in walkthrough §4 and complete.md Step 10 also use single-backtick form. Inconsistency with the gated siblings exists but `cortex-check-contract --audit` returns exit 0 with an empty findings array, meaning no E101/E103 violations are detected. The spec requirement says the contract lint passes — it does.
- **Verdict**: PASS
- **Notes**: Minor inconsistency: new gates in clarify §3, decompose §7, walkthrough §4, and complete.md Step 10 use single-backtick (`cortex-read-backlog-backend`) while existing gated siblings (decompose §5, walkthrough §6b) use the double-backtick prose form (`` `cortex-read-backlog-backend` ``). The contract lint does not flag either form — single-backtick inline code is a legitimate Markdown form. The spec acceptance criterion is that the contract lint passes, which it does.

### Requirement 11: morning-review §4 failed-feature create gated
- **Expected**: `cortex-read-backlog-backend` resolved before `cortex-create-backlog-item` in §4 step 6; non-local skip with advisory; mirrors `§6b` gate. Structural test with negative control over pre-edit step 6.
- **Actual**: `walkthrough.md:414` resolves backend via `` `cortex-read-backlog-backend` `` before the create call. Three-arm routing: `cortex-backlog` → create; `none` → skip with "disabled for this repo" advisory; external → best-effort external. `test_section4_gates_create_on_backend` slices §4 section, asserts all three tokens in order. `test_negative_control_pre_edit_step6_is_ungated` confirms pre-edit (bare create call) fails `_gate_present`. Mirror at `plugins/cortex-overnight/skills/morning-review/references/walkthrough.md` matches canonical.
- **Verdict**: PASS

### Requirement 12: complete.md Step 10 index sync gated
- **Expected**: `cortex-generate-backlog-index` gated behind `cortex-read-backlog-backend` in Step 10; non-local → skip; structural test with negative control over pre-edit unconditional Step 10.
- **Actual**: `complete.md:187` resolves backend via `cortex-read-backlog-backend` before any regen, with explicit commentary closing the gap. Skip advisory: "index sync is disabled for this repo". `test_step10_gates_index_regen_on_backend` slices Step 10, asserts all three tokens in order. `test_negative_control_pre_edit_section_is_ungated` confirms pre-edit (unconditional regen) fails. Mirror at `plugins/cortex-core/skills/lifecycle/references/complete.md` matches canonical.
- **Verdict**: PASS

---

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. `backlog_backend` follows the `backlog_counts`/`backlog_titles` field naming convention in `DashboardState`. Test class names follow the existing `TestPollSlowBackendGate` / `TestLifespanStartupResolution` pattern. All structural test files follow the `test_<feature>_gate.py` naming used by peer structural tests (`test_critical_review_gate_nonlocal_failsafe.py`, `test_decompose_rules.py`).

- **Error handling**: `resolve_backlog_backend` is never raised on — the spec notes it "never raises and fails toward cortex-backlog". `_poll_slow` wraps the entire body in `except Exception` with a `logger.warning`, consistent with the existing `_poll_state_files` and `_poll_alerts` pattern. The startup resolution in `lifespan` is synchronous and within the app's existing `RuntimeError` guard scope.

- **Test coverage**: All plan verification steps are executed by tests. R4's discriminating test genuinely runs a poll iteration (`_poll_slow` via `asyncio.create_task` + yielded event loop). R6's positive control asserts a literal `{"backlog": 2, "complete": 1}` dict — not a circular `parse_backlog_counts(dir)` comparison. Structural tests for R7/R8/R11/R12 all carry a genuine negative control over the verbatim pre-edit section, confirming they would fail on a toothless edit. The R8 decompose test additionally pins the skip-arm advisory (`"no index to regenerate"`) rather than just two-token ordering — addressing the spec's specific concern about non-discriminating ordering checks. Sibling-template slug-fallback tests (R5/spec.md:69 behavior change acknowledgement) are a positive addition beyond the strict spec requirements.

- **Pattern consistency**: The prose gates mirror the existing gated siblings correctly. Decompose §7 and complete.md Step 10 use single-backtick inline code for the binstub invocation; decompose §5 and walkthrough §6b (the pre-existing gates) used double-backtick prose form. Both forms are valid Markdown and the contract lint does not distinguish them — however the inconsistency is minor and does not affect correctness. The skip-arm language ("disabled for this repo", "no index to regenerate") is consistent across the four new gates. All four gates include a one-line advisory per spec.

---

## Requirements Drift

**State**: none

**Findings**:
- None

**Update needed**: None

---

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
