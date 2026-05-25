# Plan: reconcile-sessionstart-lifecycle-phase-summary-against

## Overview

Extend the canonical phase detector with a `feature_paused` rung emitting `{phase}-paused` compound values, lockstep-update the seven closed-set consumers (`_encode_phase`, `_phase_label`, `_interrupted_hint`, statusline bash mirror, dashboard slow-flag classifier + template, lifecycle SKILL.md routing, `backlog/generate_index.py`'s closed-set field), then layer SessionStart reconciliation that reads `cortex/backlog/index.json` once per invocation, fires a terminal-vs-non-terminal mismatch annotation, sorts mismatch-first, truncates non-mismatch tail at a 9,000-char soft budget, appends a `mismatches: N total` header fragment, and writes a per-lifecycle session-bound JSONL diagnostic.

## Outline

### Phase 1: Detector extension + downstream ripple updates (tasks: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
**Goal**: Introduce `{phase}-paused` phase values without breaking any closed-set consumer.
**Checkpoint**: `python3 -m pytest tests/test_lifecycle_phase_parity.py tests/test_hooks_scan_lifecycle.py tests/test_lifecycle_kept_pauses_parity.py` exits 0 AND `--collect-only` shows ≥ 4 paused test cases collected; `claude/statusline.sh`, `cortex_command/dashboard/data.py`, `cortex_command/backlog/generate_index.py`, and `_interrupted_hint` all handle `*-paused` per their respective acceptance criteria; SKILL.md routing table updated.

### Phase 2: SessionStart reconciliation (tasks: 11, 12, 13)
**Goal**: Cross-check events-derived phase against backlog `status:` and surface terminal-vs-non-terminal disagreement.
**Checkpoint**: Fixture-based pytest covers (a) #075-shape mismatch fires, (b) #209-shape post-fix produces `Implement — paused` label with NO mismatch, (c) clean alignment renders without annotation; `pytest --collect-only` shows ≥ 6 reconciliation test cases.

### Phase 3: Cap mitigation + session-bound diagnostic (tasks: 14, 15, 16, 17)
**Goal**: Constrain output to fit the 10K cap with mismatch-first priority, emit operator-reachable diagnostics, capture latency baseline.
**Checkpoint**: All R11-R15 pytest acceptance criteria pass with positive collection counts; microbenchmark p50/p99 captured in PR description; end-to-end integration test exists at `tests/test_hooks_scan_lifecycle.py::test_e2e_session_start_envelope`.

## Tasks

### Task 1: Add paused fixtures and parity-test mirror updates (PRE-detector — TDD)
- **Files**: `tests/fixtures/lifecycle_phase_parity/paused-implement/{events.log,plan.md}`, `tests/fixtures/lifecycle_phase_parity/paused-review/{events.log,plan.md}`, `tests/fixtures/lifecycle_phase_parity/paused-then-resumed/{events.log,plan.md}`, `tests/test_lifecycle_phase_parity.py` (widen `_expected_wire_from_canonical` lines 409-428 and `_label_to_wire` lines 429-457 to handle `*-paused` wire-format and `— paused` labels)
- **What**: Build the parity-test infrastructure FIRST (TDD). Create three fixture lifecycles: (a) `paused-implement` — `events.log` with one `phase_transition` to implement and one trailing `feature_paused` (line-position-after); `plan.md` with 3 of 5 tasks checked. (b) `paused-review` — same shape but `plan.md` all tasks checked. (c) `paused-then-resumed` — `events.log` with `feature_paused` THEN a later `phase_transition` to `implement` (line-position-after the pause); `plan.md` with unchecked tasks. Then widen the parity test's mirror helpers `_expected_wire_from_canonical` (line 409) and `_label_to_wire` (line 429) to handle the new wire shapes `implement-paused:N/M`, `review-paused`, and the new label `… — paused`. With Task 2's detector not yet implemented, all three fixture tests fail RED — that's the TDD signal.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Existing fixture pattern under `tests/fixtures/lifecycle_phase_parity/` shows the schema (events.log NDJSON + plan.md markdown). `_expected_wire_from_canonical` (tests/test_lifecycle_phase_parity.py:409) maps canonical Python output to wire format; needs to recognize `implement-paused` → `implement-paused:N/M` and `review-paused` → `review-paused`. `_label_to_wire` (line 429) maps human-readable labels back to wire; needs to recognize `Implement (3/5 tasks done) — paused` → `implement-paused:3/5` and `Review — paused` → `review-paused`. The `Unrecognised hook phase label` AssertionError at line 457 is the failure mode if the helpers aren't widened.
- **Verification**: `ls tests/fixtures/lifecycle_phase_parity/paused-implement tests/fixtures/lifecycle_phase_parity/paused-review tests/fixtures/lifecycle_phase_parity/paused-then-resumed` exits 0 AND `python3 -m pytest tests/test_lifecycle_phase_parity.py --collect-only -q 2>&1 | grep -c "paused"` ≥ 3 (positive collection assertion — fixtures must produce ≥3 paused test cases) — pass if both.
- **Status**: [ ] pending

### Task 2: Extend `_detect_lifecycle_phase_inner` with `feature_paused` rung
- **Files**: `cortex_command/common.py` (modify `_detect_lifecycle_phase_inner` lines 223-402; factor existing rung 3-6 into a `_derive_base_phase()` helper if it simplifies; touch helper `_events_log_has_event` only if it needs `feature_paused` support)
- **What**: Add a rung that runs after the terminal-event checks (feature_complete, feature_wontfix): determine the most recent significant event among `phase_transition`, `feature_complete`, `feature_wontfix`, `feature_paused` by LINE POSITION in events.log (last line of that set wins — NOT by parsed `ts` because events may have malformed or missing ts). When the most recent significant event is `feature_paused`, compute the would-be phase from the remaining ladder (rungs 3-6) and append `-paused`. When the most recent significant event is a later `phase_transition`, the resume is current — do NOT apply the suffix.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Current ladder structure at common.py:223-402 is a sequence of independent rungs. The line-position determination uses the events.log file ordering (last occurrence of any event in the significant set wins). The output JSON shape from `detect_lifecycle_phase` is `{"phase": str, "checked": int, "total": int, "cycle": int}` per docstring at line 405 — keep `checked`/`total` populated when the base phase is `implement` so consumers can render `Implement (3/5 tasks done) — paused`.
- **Verification**: `python3 -m pytest tests/test_lifecycle_phase_parity.py -k paused 2>&1 | grep -E "passed|FAILED"` shows `passed` (Task 1's RED tests turn GREEN) AND `python3 -m pytest tests/test_lifecycle_phase_parity.py -k paused --collect-only 2>&1 | grep -c paused` ≥ 3 (positive collection assertion guarding against zero-collected pass) — pass if both.
- **Status**: [ ] pending

### Task 3: Extend `_encode_phase` to attach `:N/M` to `implement-paused`
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify `_encode_phase` lines 60-74)
- **What**: Widen the exact-string match so that `implement` AND `implement-paused` both attach the `:checked/total` payload. Wire format becomes `implement-paused:3/5`. Implementation: compute `base_phase = phase` stripped of a trailing `-paused`, switch on `base_phase`, then re-append `-paused` if it was present.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `_encode_phase(phase, checked, total, cycle)` signature at line 47; current logic returns `f"implement:{checked}/{total}"` only when `phase == "implement"`. Preserve both wire shapes: `implement:3/5` (existing) and `implement-paused:3/5` (new). The implementer chooses the idiom (`.removesuffix("-paused")`, regex, or explicit split).
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import _encode_phase; assert _encode_phase('implement-paused', 3, 5, 0) == 'implement-paused:3/5'; assert _encode_phase('implement', 3, 5, 0) == 'implement:3/5'; assert _encode_phase('review-paused', 0, 0, 0) == 'review-paused'"` — pass if exit 0.
- **Status**: [ ] pending

### Task 4: Extend `_phase_label` to render `-paused` suffix
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify `_phase_label` lines 77-129)
- **What**: Add a suffix-recognition rule: if `encoded_phase` ends with `-paused` (bare like `review-paused`) or contains `-paused:` (compound like `implement-paused:3/5`), strip the `-paused` portion, recursively (or inline) compute the base label via the existing rules, then append ` — paused`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `_phase_label(encoded_phase)` signature at line 77; current rules at lines 109-129 use exact-equality and `.startswith()`. Recursion bottoms out on existing rules; no new wire shapes besides `*-paused` and `*-paused:N/M`.
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import _phase_label; assert _phase_label('implement-paused:3/5') == 'Implement (3/5 tasks done) — paused'; assert _phase_label('review-paused') == 'Review — paused'"` — pass if exit 0.
- **Status**: [ ] pending

### Task 5: Extend `_interrupted_hint` to recognize `-paused` wire format
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify `_interrupted_hint` lines 132-191)
- **What**: The existing hint logic uses `encoded_phase.startswith("implement:")` at line 167 and `startswith("implement-rework:")` at line 184; neither matches `implement-paused:3/5`. Widen by stripping the `-paused` suffix before the startswith checks (using the same idiom as Task 3), so the resume hint continues to fire for paused implement features. The hint text itself does NOT need to mention pause (per spec R10 the hint is operator-actionable resume guidance — same guidance applies to a paused feature: "Resume with /cortex-core:lifecycle ...").
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Without this fix, paused implement features lose the "Interrupted: implementation in progress (3 of 5 tasks done). Resume with /cortex-core:lifecycle ..." line silently — exactly the user-visible affordance the SessionStart hook exists to provide. The fix mirrors Task 3's `_encode_phase` widening pattern.
- **Verification**: `python3 -c "from cortex_command.hooks.scan_lifecycle import _interrupted_hint; h = _interrupted_hint('implement-paused:3/5', 'my-feature'); assert 'Resume with' in h and '3 of 5' in h"` — pass if exit 0.
- **Status**: [ ] pending

### Task 6: Add unit tests for `_encode_phase`, `_phase_label`, `_interrupted_hint`
- **Files**: `tests/test_hooks_scan_lifecycle.py` (add `test_encode_paused`, `test_label_paused`, `test_interrupted_hint_paused`)
- **What**: Codify R2, R3 acceptance plus the `_interrupted_hint` widening. Test cases exercise the public functions of `_encode_phase`, `_phase_label`, `_interrupted_hint` with the new `-paused` wire shapes.
- **Depends on**: [3, 4, 5]
- **Complexity**: simple
- **Context**: Existing test patterns in `tests/test_hooks_scan_lifecycle.py` show pytest case structure. Each new test is a one-liner assertion using the function directly.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'encode_paused or label_paused or interrupted_hint_paused'` exits 0 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'encode_paused or label_paused or interrupted_hint_paused' --collect-only 2>&1 | grep -c "test_" ` ≥ 3 — pass if both.
- **Status**: [ ] pending

### Task 7: Extend statusline bash mirror with `feature_paused` rung
- **Files**: `claude/statusline.sh` (modify phase-detection ladder at lines 395-454)
- **What**: Mirror Task 2's Python detection logic in bash. Add `feature_paused` recognition that fires AFTER terminal-event checks. When the most recent significant event in events.log is `feature_paused`, set `_lc_paused=1`; proceed through the remaining ladder rungs to derive the base phase; append `-paused` to `_lc_phase` if the flag is set.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The structural-exception comment at claude/statusline.sh:382-394 acknowledges the bash mirror MUST stay in parity. The "most recent significant event" determination in bash should NOT use `tail -50` (truncation cap risk); instead, read the full events.log and grep across all lines for the significant-event set. For example: `_lc_last_sig=$(grep -oE '"event":"(phase_transition|feature_paused|feature_complete|feature_wontfix)"' "$_lc_fdir/events.log" 2>/dev/null | tail -1)` — scans the full file, takes the last match. Matches Python's full-file scan semantics in Task 2.
- **Verification**: `python3 -m pytest tests/test_lifecycle_phase_parity.py::test_statusline_ladder_matches_canonical` exits 0 — pass if exit 0. (Task 1 fixtures + Task 2's Python detector are upstream prereqs.)
- **Status**: [ ] pending

### Task 8: Widen dashboard `data.py` slow-flag classifier for `-paused`
- **Files**: `cortex_command/dashboard/data.py` (modify slow-flag classifier at lines 1191, 1197), `tests/test_dashboard_data.py` (add or create `test_slow_flag_paused`)
- **What**: Change `if current_phase in ("implement", "implement-rework"):` to compute `base_phase` first (stripping `-paused`), then test on `base_phase`. Same for `elif current_phase == "review":`. Semantics: a paused feature in implement is still slow-flag-tracked.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Closed-set membership at data.py:1191; the fix mirrors Task 3's `_encode_phase` widening. Check first whether `tests/test_dashboard_data.py` exists; create if absent.
- **Verification**: `python3 -m pytest tests/test_dashboard_data.py -k slow_flag_paused --collect-only 2>&1 | grep -c "test_" ` ≥ 1 AND `python3 -m pytest tests/test_dashboard_data.py -k slow_flag_paused` exits 0 — pass if both. (The collection check guards against the empty-test-suite pass.)
- **Status**: [ ] pending

### Task 9: Hoist phase-label rule into shared module + update dashboard template
- **Files**: `cortex_command/phase_labels.py` (new module — pure function `phase_label(encoded_phase: str) -> str` extracted from `_phase_label`), `cortex_command/hooks/scan_lifecycle.py` (replace `_phase_label` body with delegation to `phase_labels.phase_label`; keep `_phase_label` as a re-export for backward compat), `cortex_command/dashboard/templates/feature_cards.html` (replace raw `{{ current_phase }}` at lines 62 and 110 with `{{ current_phase | phase_label }}`), `cortex_command/dashboard/__init__.py` (or the FastAPI app factory — register the Jinja filter)
- **What**: Move the `_phase_label` rule (including Task 4's `-paused` suffix recognition) into `cortex_command/phase_labels.py` as a pure function. The scan_lifecycle.py `_phase_label` becomes a thin delegating wrapper. Register `phase_label` as a Jinja filter on the dashboard's environment. Replace the two raw interpolations in `feature_cards.html` with `| phase_label`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**: This task REFACTORS Task 4's `_phase_label` (turns it into a delegator) — flagged here explicitly so the implementer doesn't treat Task 9 as purely additive. The dashboard's Jinja2 environment setup lives in `cortex_command/dashboard/__init__.py` or the FastAPI app factory; filter registration is via `app.jinja_env.filters["phase_label"] = phase_label`. The `phase_order` list at templates/feature_cards.html:3 is a sort key and falls back gracefully on unknown values per Jinja's `|sort` semantics — confirm by manual inspection. The `fleet_cards` render path at data.py:523-527 also flows `current_phase` to a template; if that template renders raw, apply the same `| phase_label` filter (deferred check during implementation).
- **Verification**: `grep -c "phase_label" cortex_command/dashboard/templates/feature_cards.html` ≥ 2 AND `python3 -c "from cortex_command.phase_labels import phase_label; assert phase_label('implement-paused:3/5') == 'Implement (3/5 tasks done) — paused'"` exits 0 AND `python3 -c "from cortex_command.hooks.scan_lifecycle import _phase_label; assert _phase_label('implement-paused:3/5') == 'Implement (3/5 tasks done) — paused'"` exits 0 — pass if all three.
- **Status**: [ ] pending

### Task 10: Update lifecycle SKILL.md routing table + backlog index generator for `-paused` vocabulary
- **Files**: `skills/lifecycle/SKILL.md` (modify phase routing table at lines 93-96), `cortex_command/backlog/generate_index.py` (modify lines 161-165 closed-set comment and line 167 `detect_lifecycle_phase` consumer)
- **What**: Two related vocabulary-extension fixes. (1) SKILL.md routing: document a prose rule above the table: "When the detected phase ends in `-paused`, strip the suffix for routing-table lookup; display the full label including ` — paused` to the user." This survives future `-paused` additions without table updates. (2) `generate_index.py` decision: choose either (a) strip `-paused` suffix before writing to index.json's `lifecycle_phase` field (keeping the closed-set invariant documented at lines 161-165) and update the closed-set comment to clarify "the lifecycle_phase field in index.json stores the BASE phase; `-paused` state lives in the events.log and is recoverable via `cortex-common detect-phase`"; OR (b) widen the closed-set comment to include `*-paused` variants and write the suffixed value. **Recommend (a)** — it keeps index.json's vocabulary stable for downstream readers (morning-review report, dashboard merges, etc.). Suffix stripping happens only at the write boundary; in-memory and events.log values keep the full vocabulary.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: SKILL.md lines 93-96 are a markdown table. Per CLAUDE.md, edit canonical only — the mirror at `plugins/cortex-core/skills/` regenerates via pre-commit. The parity test `tests/test_lifecycle_kept_pauses_parity.py` is about `AskUserQuestion` call sites, not the routing table — running it is sanity-check only. For `generate_index.py:167`, the strip-on-write pattern is: `phase = detect_lifecycle_phase(lc_dir)["phase"]; lifecycle_phase = phase.removesuffix("-paused") if phase else None`.
- **Verification**: `grep -c "paused" skills/lifecycle/SKILL.md` ≥ 1 AND `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0 AND `grep -c "removesuffix\|paused" cortex_command/backlog/generate_index.py` ≥ 1 — pass if all three.
- **Status**: [ ] pending

### Task 11: Load `index.json` once per hook invocation
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (add helper `_load_backlog_status_map() -> dict[str, str]`; call in `main()` before per-candidate phase-detection loop), `tests/test_hooks_scan_lifecycle.py` (add `test_index_json_loaded`, `test_index_json_absent_empty_map`, `test_index_json_duplicate_first_wins`)
- **What**: Implement helper that reads `cortex/backlog/index.json`, iterates the array, builds dict keyed by `lifecycle_slug` (skipping null/absent), returns empty dict on file absent/unparseable/unreadable (fail-open). Duplicate `lifecycle_slug` first-wins; record duplicates as side output. Test cases via tmp_path with synthetic index.json files.
- **Depends on**: none (independent — pure data load)
- **Complexity**: simple
- **Context**: Repo root resolution via existing helper in scan_lifecycle.py. `index.json` schema: top-level array of objects with `id`, `title`, `lifecycle_slug`, `status` fields (verified against live file). Return signature: either `dict[str, str]` plus duplicates list as a tuple, or a dict subclass with `duplicates` attribute.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'index_json' --collect-only 2>&1 | grep -c "test_index_json"` ≥ 3 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'index_json'` exits 0 — pass if both.
- **Status**: [ ] pending

### Task 12: Implement terminal-vs-non-terminal mismatch predicate + render annotation
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (add `_is_terminal_mismatch(events_phase, backlog_status) -> bool`; modify `_build_additional_context` lines 345-457 to consume the predicate + the map from Task 11), `tests/test_hooks_scan_lifecycle.py` (add `test_terminal_mismatch_075_shape`, `test_terminal_mismatch_209_shape_no_annotation`, `test_active_header_mismatch`), `tests/fixtures/hooks/scan_lifecycle/075-shape/{events.log,plan.md}`, `tests/fixtures/hooks/scan_lifecycle/209-shape-post-fix/{events.log,plan.md}`, `tests/fixtures/hooks/scan_lifecycle/clean-alignment/{events.log,plan.md}`
- **What**: The predicate: `events_terminal = phase in {"complete", "escalated"} or phase.startswith("complete:")`; `backlog_terminal = (status is not None and status in TERMINAL_STATUSES)`; returns `events_terminal != backlog_terminal`. Render: when True, append ` [mismatch: backlog={status}]` to the entry line. Apply on both active-feature header (lines 405-413) and others enumeration. Synthetic fixtures: 075-shape (plan.md without feature_complete + backlog status:complete), 209-shape-post-fix (feature_paused + plan.md unchecked + backlog status:in_progress), clean-alignment (implement + in_progress).
- **Depends on**: [11]
- **Complexity**: complex
- **Context**: `_build_additional_context(incomplete: list[tuple[str, str]], ...)` signature. Extend the per-entry tuple to `(feature, encoded_phase, has_mismatch, backlog_status_or_None)`. Import `TERMINAL_STATUSES` from `cortex_command.common`. `_interrupted_hint()` text remains driven by events-derived phase per R10.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'terminal_mismatch or active_header_mismatch' --collect-only 2>&1 | grep -c "test_"` ≥ 3 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'terminal_mismatch or active_header_mismatch'` exits 0 — pass if both.
- **Status**: [ ] pending

### Task 13: Implement mismatch-first sort + soft-budget truncation + `mismatches: N total` header fragment
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (modify `_build_additional_context`), `tests/test_hooks_scan_lifecycle.py` (add `test_mismatch_first_sort`, `test_soft_budget_truncation`, `test_mismatches_header_fragment`)
- **What**: Three interlocking display-layer changes in `_build_additional_context`. (1) Sort: stable sort keyed by `(0 if has_mismatch else 1, original_index)`. (2) Truncation: compute fully-assembled-block size; when > 9,000, drop non-mismatch entries from end with `  … +N more` line. Never truncate mismatches. (3) Header fragment: count mismatches BEFORE truncation; if ≥1, append ` — mismatches: N total` to "Other incomplete lifecycles:" line.
- **Depends on**: [12]
- **Complexity**: complex
- **Context**: Block size = `len("\n".join(lines))` over all four contributors (active header + pipeline-state prepend + others enumeration + diagnostic summary). 9,000-char threshold leaves ~1,000 chars headroom over measured ~700-char actual overhead.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'mismatch_first_sort or soft_budget_truncation or mismatches_header_fragment' --collect-only 2>&1 | grep -c "test_"` ≥ 3 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'mismatch_first_sort or soft_budget_truncation or mismatches_header_fragment'` exits 0 — pass if both.
- **Status**: [ ] pending

### Task 14: Implement session-bound JSONL diagnostic + expose `_is_stale` fields
- **Files**: `cortex_command/hooks/scan_lifecycle.py` (add `_emit_diag(record: dict) -> None`; refactor `_is_stale` to expose `latest_event_ts` and `last_event` as side outputs OR add a sibling helper that returns the same; call `_emit_diag` from the per-candidate loop in `main()`), `tests/test_hooks_scan_lifecycle.py` (add `test_session_diagnostic_written`, `test_session_diagnostic_silent_when_session_id_unset`)
- **What**: Append one single-line JSON object per candidate to `cortex/lifecycle/sessions/${LIFECYCLE_SESSION_ID}/scan-lifecycle-diag.jsonl` (create parent dir if absent). Schema per spec R14: `ts`, `feature`, `decision`, `exclude_reason` (when excluded), `latest_event_ts`, `threshold_days`, `last_event`, `events_phase`, `backlog_status`, `index_json_resolved`, `mismatch`. Fail-open: try/except wrap; on `$LIFECYCLE_SESSION_ID` unset, silently drop. The `latest_event_ts` and `last_event` fields come from `_is_stale`'s parse — refactor that helper to expose them via a sibling function `_events_log_meta(feature_dir) -> dict` returning `{latest_ts, last_event}`, called from both `_is_stale` and the diagnostic.
- **Depends on**: [11, 12]
- **Complexity**: complex
- **Context**: `_is_stale` at scan_lifecycle.py:226-260 currently reads events.log and computes max-ts; expand to also return the most-recent-event-name. The diagnostic destination pattern matches existing `cortex/lifecycle/sessions/<id>/` files (per observability.md). `monkeypatch.setenv("LIFECYCLE_SESSION_ID", str(tmp_path))` is the test idiom; the diagnostic file lands at `{tmp_path}/scan-lifecycle-diag.jsonl`.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'session_diagnostic' --collect-only 2>&1 | grep -c "test_"` ≥ 2 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py -k 'session_diagnostic'` exits 0 — pass if both.
- **Status**: [ ] pending

### Task 15: End-to-end integration test for SessionStart envelope
- **Files**: `tests/test_hooks_scan_lifecycle.py` (add `test_e2e_session_start_envelope`)
- **What**: Construct a synthetic repo state via tmp_path with (a) one lifecycle dir in a true terminal-mismatch state (events=implement + backlog=complete), (b) one paused lifecycle (events ending with feature_paused + plan.md unchecked + backlog=in_progress), (c) one clean-alignment lifecycle, (d) a synthetic `cortex/backlog/index.json` listing all three. Invoke `scan_lifecycle.main()` as a subprocess (or in-process with stdin redirection) with the standard SessionStart envelope; parse the JSON output; assert (1) the additionalContext contains `Implement — paused` for the paused feature, (2) the mismatched feature carries `[mismatch: backlog=complete]`, (3) the mismatches-header fragment shows `mismatches: 1 total`, (4) the clean feature has no annotation.
- **Depends on**: [12, 13, 14]
- **Complexity**: complex
- **Context**: This is the end-to-end gate the spec's whole-feature Acceptance criterion implicitly requires. Without it, `just test` proves unit helpers work but does not prove the integrated hook envelope renders correctly. Existing pytest patterns show subprocess invocation; alternatively call `main()` in-process with mocked stdin and a captured stdout context.
- **Verification**: `python3 -m pytest tests/test_hooks_scan_lifecycle.py::test_e2e_session_start_envelope --collect-only 2>&1 | grep -c "test_e2e_session_start_envelope"` ≥ 1 AND `python3 -m pytest tests/test_hooks_scan_lifecycle.py::test_e2e_session_start_envelope` exits 0 — pass if both.
- **Status**: [ ] pending

### Task 16: Latency microbenchmark + capture in PR description
- **Files**: `scripts/benchmark_scan_lifecycle.py` (new)
- **What**: Construct a synthetic fixture set with N=90 candidate lifecycles (mix of mismatched, aligned, paused), run `scan_lifecycle.main()` end-to-end 10 times, report wall-clock p50/p99 to stdout in a machine-readable form (`p50=120ms p99=450ms`). The PR description must include the numbers. The benchmark itself has no hard threshold; it provides grounding for the Plan-phase decision rule per Technical Constraints.
- **Depends on**: [13, 14, 15]
- **Complexity**: simple
- **Context**: Use `time.perf_counter()`; synthesize fixtures via tmp_path + loop generating ~90 lifecycle dirs with varied phase shapes. Stdin envelope: minimal `{"session_id": "bench", "cwd": str(tmp_path)}`. Output format example: `iterations=10 p50=120ms p99=450ms n_candidates=90`.
- **Verification**: `python3 scripts/benchmark_scan_lifecycle.py 2>&1 | grep -cE 'p50=|p99='` ≥ 2 — pass if exit 0. Threshold-free per spec ("no fixed numeric target; instead, the PR description must include the measurement").
- **Status**: [ ] pending

### Task 17: Reconciliation regression fixtures recorded as canonical
- **Files**: ensure `tests/fixtures/hooks/scan_lifecycle/{075-shape,209-shape-post-fix,clean-alignment}/` (created in Task 12) are referenced from `tests/test_hooks_scan_lifecycle.py` from at least one passing test
- **What**: Verify R15 acceptance. The fixtures were built in Task 12; this task is the final-grep gate ensuring they exist and are referenced (no orphan fixtures).
- **Depends on**: [12]
- **Complexity**: trivial
- **Context**: `ls tests/fixtures/hooks/scan_lifecycle/` should show the three named dirs. `grep -r "075-shape\|209-shape-post-fix\|clean-alignment" tests/` should find references in test files.
- **Verification**: `ls tests/fixtures/hooks/scan_lifecycle/ | grep -cE '075|209|clean'` ≥ 3 AND `grep -rc "075-shape\|209-shape" tests/test_hooks_scan_lifecycle.py` ≥ 1 — pass if both.
- **Status**: [ ] pending

## Risks

- **Task 1 (TDD fixture pre-detector)**: Fixtures land before the detector that produces the expected output. Parity test runs RED until Task 2 lands. The TDD ordering is intentional — it forces Task 2 to satisfy a concrete pre-written assertion rather than a forward-referenced one. If overnight dispatches Task 1 + Task 2 as independent tasks with no shared context, Task 1's verification (positive collection count) succeeds in isolation; Task 2's verification (pytest -k paused passes) is the integration check.
- **Task 9 (label-helper hoist) refactors Task 4's deliverable**: `_phase_label` in scan_lifecycle.py becomes a delegating wrapper to the new `phase_labels.py`. A fresh sub-agent on Task 9 must read Task 4's edits before refactoring, NOT treat Task 9 as additive-only. The Task 9 Context explicitly flags this.
- **Task 10 (generate_index.py vocabulary decision)**: Choosing (a) strip-on-write vs (b) widen-vocabulary affects every downstream consumer of index.json's `lifecycle_phase` field. Recommendation (a) keeps the closed-set invariant for index.json readers; the trade-off is that the index.json `lifecycle_phase` field no longer reflects "the canonical detector's output verbatim" — it reflects the base phase. Decision is captured in the task; implementer follows the recommendation unless they find a concrete consumer that depends on the suffixed value being in index.json.
- **Task 14 (`_is_stale` refactor)**: Exposes `latest_event_ts` and `last_event` as side outputs from a function previously returning just a boolean. The refactor should preserve `_is_stale`'s call sites (staleness filtering at line 648) — the easiest pattern is to keep `_is_stale` unchanged and add a sibling `_events_log_meta` helper that both functions use.
- **End-to-end test (Task 15) may be slow**: Constructing 3 synthetic lifecycle dirs + index.json per test run is non-trivial. If p99 of `pytest test_e2e_session_start_envelope` exceeds 5s, consider caching via pytest's `session`-scoped fixture.
- **Latency budget (Task 16)**: Threshold-free measurement may surface that p99 is already significant (e.g., 600ms). If so, the implementer documents the number in the PR description; Plan-phase decision rule applies (move diagnostic emission to background thread or batch reads).

## Acceptance

The SessionStart additionalContext block, on a repo with ≥1 terminally-mismatched lifecycle (events-phase non-terminal AND backlog status terminal, or vice versa) and ≥1 paused lifecycle, renders (a) paused features with `— paused` in the phase label across SessionStart, statusline, and dashboard (including the active-feature header's interrupted-hint, which continues to fire); (b) terminally-mismatched lifecycles with `[mismatch: backlog=<status>]` annotation on both the active-feature header (when applicable) and the others enumeration; (c) the others enumeration sorted mismatch-first, truncated at 9,000-char soft budget with `… +N more`, header line carrying ` — mismatches: N total` fragment when N≥1; (d) per-lifecycle JSONL diagnostic written to `cortex/lifecycle/sessions/${LIFECYCLE_SESSION_ID}/scan-lifecycle-diag.jsonl` for post-mortem inspection. The integration test at `tests/test_hooks_scan_lifecycle.py::test_e2e_session_start_envelope` codifies (a) through (c) as a single pass/fail gate. The full pytest suite (`python3 -m pytest tests/`) exits 0.
