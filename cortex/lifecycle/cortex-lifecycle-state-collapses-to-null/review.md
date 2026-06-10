# Review: cortex-lifecycle-state-collapses-to-null

## Stage 1: Spec Compliance

### Requirement 1: Shared tolerant, vocabulary-validating reducer
- **Expected**: One `reduce_lifecycle_state(events_path)` in `common.py` reading with `errors="replace"`, skipping `json.loads` failures (continue), accumulating tier/criticality per the canonical rule, accepting a value only if in the known vocabulary (out-of-vocab does NOT supersede a prior valid value and counts as skipped), recording whether >=1 line was skipped, never returning `None`, never raising on non-UTF-8.
- **Actual**: `cortex_command/common.py:660-738` implements exactly this. `Path.read_text(encoding="utf-8", errors="replace")` wrapped in a broad except returning an empty `LifecycleStateReduction` (never raises). `json.JSONDecodeError` records the 1-based line number and continues. Non-dict JSON is skipped silently (NOT flagged), matching the prior readers. Module constants `TIER_VOCABULARY`/`CRITICALITY_VOCABULARY` (`:619-620`) gate per-value: an out-of-vocab value does not enter `state` and flags its line via `line_rejected`. `grep -c "def reduce_lifecycle_state"` = 1. `pytest tests/test_reduce_lifecycle_state.py` = 13 passed, covering non-UTF-8-no-raise, out-of-vocab-override-ignored, torn-line line-numbering, clean-no-skips, and the mixed-line per-value case (`:84`) that distinguishes per-value from per-line rejection.
- **Verdict**: PASS
- **Notes**: Per-value (not per-line) rejection is the chosen semantics, pinned by the mixed-line test — consistent with the plan's stated tradeoff.

### Requirement 2: read_tier/read_criticality rewired as thin wrappers
- **Expected**: Project the accumulator to defaulted bare strings (`tier`->`simple`, `criticality`->`medium`), preserving `@lru_cache(maxsize=128)` and `.__wrapped__`.
- **Actual**: `_read_tier_inner` (`:563-582`) and `_read_criticality_inner` (`:506-526`) now delegate to `reduce_lifecycle_state(...).state.get(axis, default)`. Both retain `@lru_cache(maxsize=128)`, the `(events_path_str, exists, mtime_ns, size)` stat-key signature, the `if not exists: return default` early return, and the `.__wrapped__` module-level assignments (`:556`, `:610`). Runtime introspection confirms `read_tier.__wrapped__ is _read_tier_inner` (True), `cache_info().maxsize == 128`, `cache_clear` present. `grep -c "read_tier.__wrapped__"` = 1 and `read_criticality.__wrapped__` = 1. Pinning tests (`test_bin_lifecycle_state_parity.py`, `test_lifecycle_state.py`, `test_feature_executor.py`) = 29 passed.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 3: state_cli consumes the shared reducer; return None branch removed
- **Expected**: Torn log emits last-valid accumulator dict, never `null`; `grep -c "return None"` = 0.
- **Actual**: `state_cli._reduce_events` (`:74-86`) is a thin wrapper returning `reduce_lifecycle_state(events_path).state`. `main()` (`:152-179`) reduces, writes the dict via compact JSON, exits 0. `grep -c "return None"` = 0. Torn-line fixture stdout is `{"criticality":"high","tier":"complex"}` (last-valid, no `null`). `_reduce_events` retained as a compatibility oracle for out-of-scope test files (`test_refine_module.py`, `test_refine_reconcile_clarify.py`) as the plan specified.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 4: refine._reduce_current_state rewired to the shared reducer
- **Expected**: Delegate to `reduce_lifecycle_state`, projecting to the `(tier, criticality)` tuple with `("simple","medium")` defaults; R12 test includes the refine path; stale "diverges from" docstring removed.
- **Actual**: `refine.py:114-127` delegates and projects with the correct defaults; signature `(events_log: Path) -> tuple[str, str]` unchanged. `grep -c "reduce_lifecycle_state" refine.py` = 3 (>= 1). `grep -c "diverges from" tests/test_refine_module.py` = 0. The R12 agreement matrix (`test_bin_lifecycle_state_parity.py:281`) calls `_reduce_current_state` on every axis. `test_refine_module.py` = passing.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 5: Uniform encoding contract closes the latent runner crash
- **Expected**: A non-UTF-8 byte no longer raises `UnicodeDecodeError` from `read_tier`/`read_criticality`.
- **Actual**: All reads flow through the shared helper's `errors="replace"`. `test_read_tier_non_utf8_does_not_raise` (`test_reduce_lifecycle_state.py:103`) passes; the R12 `non-utf8-structure` axis confirms all three readers tolerate a structure-breaking byte with no exception. `pytest -k non_utf8` = passing.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 6: Field-precedence standardized on .to-only — state_cli's dead fallback removed
- **Expected**: Shared helper reads `.to` only; `state_cli`'s `.to or .tier` / `.to or .criticality` fallback removed; `grep -c 'record.get("to") or record.get("tier")'` = 0.
- **Actual**: The reducer reads override target from `.to` only (`common.py:721-733`); no field-named fallback. `grep -c 'record.get("to") or record.get("tier")' state_cli.py` = 0. The R12 `to-keyed-override` axis uses real `.to`-keyed overrides and asserts they win everywhere.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 7: Corruption signal (gate-relevant)
- **Expected (literal R7)**: Signal true iff >=1 line skipped AND tier absent. Surface via reducer return, `state_cli` output, and a `common.py` predicate. Spec records (and the plan Risks document) a deliberate symmetric amendment to "tier OR criticality absent."
- **Actual**: `LifecycleStateReduction.corrupted` (`common.py:643-657`) = `bool(skipped_lines) and ("tier" not in state or "criticality" not in state)` — the symmetric form. `lifecycle_state_corrupted(feature, ...)` predicate at `:741-761` (no lru_cache, gate path). `state_cli.main()` appends `"corrupted": true` after the field filter (`:175-176`) so it rides both the unfiltered and `--field`-filtered paths. Tests cover torn-start-only -> true (incl. the `--field tier` -> `{"corrupted":true}` assertion the gates actually read, `:148-149`), symmetric criticality axis -> true (`:152`), clean-no-state -> false/no-key, torn-mid-recovered -> false, missing-file -> false. `grep -c "def lifecycle_state_corrupted"` = 1; `pytest -k corrupt` = passing.
- **Verdict**: PASS
- **Notes**: The symmetric amendment is sound and properly reconciled. `requires_review` gates on `tier == "complex" OR criticality in ("high","critical")`, so a torn/vocab-rejected criticality with tier intact is equally gate-corrupting; the literal tier-only signal would silently skip the gate on the criticality axis — the original bug shape relabelled. All three literal-R7 acceptance cases still pass under the symmetric definition. The amendment is recorded both in plan Risks and in the `corrupted` docstring. Widening (not narrowing) the fail-safe trigger is the conservative direction, consistent with the ADR-0010 fail-safe intent.

### Requirement 8a: Gate fail-safe wiring (overnight)
- **Expected**: The overnight `requires_review` path ORs in the corruption signal at the review-decision sites; the sync-merge guard (the raise-RuntimeError site) is EXCLUDED.
- **Actual**: `_review_required(name)` (`outcome_router.py:990-1004`) does one `reduce_lifecycle_state` pass (snapshot coherence for the OR's two legs), projects tier/criticality with defaults, returns `requires_review(...) or reduction.corrupted`. Wired into the three review-decision sites: `:1044` (recovery gate), `:1359` (repair-completed gate), `:1695` (primary apply path) — all keeping the `tier`/`criticality` assignments that downstream `dispatch_review(complexity=, criticality=)` calls consume. The sync-merge invariant guard `_guard_no_review_qualifying_sync_merge` (`:1259`) correctly still uses bare `requires_review(read_tier(name), read_criticality(name))` with NO corruption OR — excluded exactly as required, since its only action on True is `raise RuntimeError` after the merge landed (ORing corruption there would produce merged-but-marked-failed divergence). `_repair_review_or_revert` (`:1435`) reads tier/criticality only as dispatch arguments (decision already made upstream) — correctly not a gate site. `grep -c "_review_required"` = 7 (def + 3 calls + 3 doc/comment refs >= 4). `pytest -k requires_review_corrupt` = passing.
- **Verdict**: PASS
- **Notes**: The single-pass design and the exclusion are both implemented and documented inline (`:1240` guard message, `:1004` comment). `runner.py:2717` left un-wired per the plan's explicit out-of-scope note (follow-up candidate).

### Requirement 8b: Skill prose names the corruption-fires-the-gate rule
- **Expected**: §3a/§3b (specify.md / orchestrator-review.md), plan.md, refine SKILL.md §3b name the rule; soft positive-routing phrasing (no new MUST/CRITICAL/REQUIRED per the MUST-escalation policy).
- **Actual**: Four sites carry the rule: `orchestrator-review.md:9` (where specify §3a's read physically lives), `specify.md:172` (§3b), `plan.md:280` (§3b), `refine/SKILL.md:172` (§3b). Each uses soft phrasing — "treat the feature as requiring review (run the gate) rather than defaulting" — with no MUST/CRITICAL/REQUIRED escalation, so no escalation-evidence artifact is required. All four canonical files are byte-identical to their `plugins/cortex-core/` mirrors (dual-source drift hook satisfied). `grep -c "corrupt"` >= 1 in specify.md and plan.md.
- **Verdict**: PASS
- **Notes**: MUST-escalation policy compliant. The spec's Non-Requirements enumeration was amended to name `refine` §3b (`spec.md:31`), keeping the "consumed ONLY by gate-deciding consumers" claim true — a sound reconciliation since refine §3b is genuinely gate-deciding.

### Requirement 9: CLI-only human-readable observability
- **Expected**: `main()` emits a stderr warning per skipped line naming `events.log:<lineno>`, exit 0; library readers stay silent.
- **Actual**: `main()` iterates `reduction.skipped_lines` emitting `cortex-lifecycle-state: warning: skipped unusable line at <path>:<lineno>` (`:159-163`), exit stays 0. The path is built from a cwd-relative `Path("cortex")/"lifecycle"/feature/"events.log"` (`:146`), deterministic under the harness's staged tmp cwd. `test_reduce_lifecycle_state_library_readers_silent_on_stderr` (`:202`) pins that `read_tier` on a torn file writes nothing to stderr. Torn-line fixture stderr now byte-compares to the exact line-2 warning.
- **Verdict**: PASS
- **Notes**: "unusable" wording (not "malformed") correctly covers vocab-rejected-but-parseable lines.

### Requirement 10: Flip the bug-pinning fixture and re-found its README
- **Expected**: `torn-line.stdout` changes from `null` to last-valid; README "Torn-line behavior" section retires the jq-1.8.1 reduce-to-null parity framing and documents the common.py-agreement contract. `grep -c "null" stdout` = 0; `grep -c "parity failure" README.md` = 0.
- **Actual**: `torn-line.stdout` = `{"criticality":"high","tier":"complex"}` (no `null`). README's "Torn-line behavior" section (`:53-70`) is fully re-founded on the shared-reducer agreement contract and explicitly notes the jq oracle is gone. Both acceptance greps pass (stdout `null` = 0; README "parity failure" = 0).
- **Verdict**: PASS
- **Notes**: Minor stale-doc gap (does not affect verdict): the README's "Applicable parity tolerances" table (`:87`) still lists the torn-line tolerance as `error-formatter-shape, key-reorder`, and the `error-formatter-shape` description (`:101-105`) still says torn-line "currently emits empty stderr." Task 6 changed the actual tolerance to `{"stdout": ["key-reorder"], "stderr": []}` (byte-identical stderr) and the fixture stderr is now the non-empty warning line. The implementation, tests, and fixtures are correct and consistent; only this secondary README table lags. Logged as a quality nit under Stage 2.

### Requirement 11: Harden test_bin_lifecycle_state_parity.py
- **Expected**: Fail cleanly (assertion, not `AttributeError`) on `null`/`None` stdout; survive non-UTF-8 staging; pin the bin subprocess to working-tree code.
- **Actual**: `grep -c "isinstance(bin_out, dict)"` = 2 (explicit dict assertions with diagnostic messages). `grep -c "CORTEX_COMMAND_FORCE_SOURCE"` = 2; a `_pinned_env()` helper prepends `REPO_ROOT` to `PYTHONPATH` and sets `CORTEX_COMMAND_FORCE_SOURCE=1`, applied to the bin subprocess calls. Byte-oriented staging via `write_bytes`/`copy2` survives non-UTF-8 axes. `pytest tests/test_bin_lifecycle_state_parity.py` = passing.
- **Verdict**: PASS
- **Notes**: None.

### Requirement 12: Multi-reader agreement-test matrix
- **Expected**: A test asserting `state_cli` (via bin), `read_tier`/`read_criticality`, and refine return identical EFFECTIVE values across 7 axes: torn-mid-file, torn-start-only (corruption true), non-UTF-8 structure-breaking, non-UTF-8 in-string (vocab-rejected, not accumulated), `.to`-keyed override, missing-file, empty-but-valid.
- **Actual**: `test_all_readers_agree_on_effective_state` (`test_bin_lifecycle_state_parity.py:249`) is parametrized over all 7 `_AGREEMENT_AXES` and asserts `bin_tier == py_tier == refine_tier == exp_tier` and the criticality analog (effective-value comparison after each reader's own default projection), plus the `corrupted` signal on the bin output. The in-string axis (`:211`, `tier:"\xff"`) expects tier defaults to `simple` (mojibake rejected, NOT accumulated) with `corrupted: True` — the symmetric criticality remains `high` — proving vocab-rejection rather than silent acceptance. `grep -rc "def test_.*agree"` = 1; `just test`/the file = passing. Build via `write_bytes` so non-UTF-8 axes survive.
- **Verdict**: PASS
- **Notes**: Strong, non-self-sealing matrix — each axis cross-checks three independent reader implementations against an explicit expected tuple.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `reduce_lifecycle_state` / `LifecycleStateReduction` / `lifecycle_state_corrupted` mirror the existing `read_tier`/`read_criticality` naming and signature shape (feature slug + `lifecycle_base` default). Vocabulary constants are module-level frozensets matching the `_TELEMETRY_ONLY_EVENT_TYPES` style already in `common.py`. `_review_required` follows the file's `_helper` convention.
- **Error handling**: Appropriate. The reducer's read is wrapped in a broad-but-justified `except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError, OSError)` returning an empty reduction — honors "never raises / never None." `errors="replace"` is the deliberate encoding contract (the vocabulary gate, not strict decoding, closes silent acceptance, per the spec). `json.JSONDecodeError` is the only parse exception caught (correct — a broader catch would mask logic errors). The CLI keeps exit 0 on skipped lines (observability without failure), and the library readers stay silent — the two-mechanism separation (warning vs. signal) is preserved end to end.
- **Test coverage**: The plan's per-task verification greps and pytest selectors all pass (R1 13/13; corrupt/non_utf8/requires_review_corrupt/agree 45 passed + 1 unrelated environmental skip; the four directly-affected files 99 passed). Tests are genuine, not self-sealing: the R12 matrix cross-checks three independent reader implementations against explicit expected tuples; the mixed-line test isolates per-value vs. per-line semantics; the `--field tier` -> `{"corrupted":true}` assertion pins the exact path the gates read. `just test` was green except one test (`test_mcp_subprocess_contract.py:123`) that failed only on a sandbox DNS block to pypi.org and passes with network access — unrelated to this changeset.
- **Pattern consistency**: `@lru_cache(maxsize=128)` + stat-key inner signature + `.__wrapped__` introspection contract are fully preserved (verified at runtime). The `_review_required` single-pass design correctly gives the OR's two legs snapshot coherence (avoiding the up-to-three-independent-reads race the plan flags). The stderr warning path is cwd-relative and deterministic under the staged tmp cwd. Dual-source mirrors for all four skill files are byte-identical to canonical. One minor quality nit: the torn-line fixture README's tolerance table (`:87`) and `error-formatter-shape` description (`:101-105`) are stale relative to Task 6's tolerance change to byte-identical stderr — documentation-only drift inside the deliverable; the code, tests, and fixtures are correct and consistent.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
