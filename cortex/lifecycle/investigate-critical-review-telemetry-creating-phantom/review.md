# Review: investigate-critical-review-telemetry-creating-phantom

## Stage 1: Spec Compliance

### Requirement 1 [Must]: Shared guard helper
- **Expected**: `_lifecycle_dir_exists(lifecycle_root, feature) -> bool` in `critical_review/__init__.py`, `# gate-class: hygiene` annotation, grep count ≥1 over baseline, import + phantom-guard test green.
- **Actual**: `_lifecycle_dir_exists` defined at `__init__.py:537` returning `(Path(lifecycle_root) / feature).is_dir()`, carrying `# gate-class: hygiene` at `:536`. `EXIT_TELEMETRY_SKIPPED = 4` added at `:52`. `grep -c 'gate-class: hygiene'` = 10 vs baseline 6 (the +4 = helper def + 3 writer sites). Import resolves; tests pass.
- **Verdict**: PASS
- **Notes**: Helper sits at module level, outside `append_event`, exactly as required.

### Requirement 2 [Must]: Write-guard is write-only and verdict-preserving
- **Expected**: Guard suppresses only the mkdir+append when `cortex/lifecycle/{feature}/` absent; integrity verdict unchanged; (a) skip observably distinct from real invalidation (exit 3); (b) skipped `record-exclusion` must not signal persistence; no dir/no events.log created; guard in callers not `append_event`.
- **Actual**: In all three writers (`_cmd_check_synth_stable:716`, `_cmd_check_artifact_stable:787`, `_cmd_record_exclusion:830`) the guard is checked immediately before `append_event`. The genuine verdict reaches stdout *before* the guard returns: `check-synth-stable` writes the `Critical-review pass invalidated…` diagnostic at `:708`; `check-artifact-stable` writes `EXCLUDED {reason}` at `:779`; both then return `EXIT_TELEMETRY_SKIPPED` (4) on dir-absence — distinct from the real-invalidation exit 3. `record-exclusion` returns 4 (not 0) on absence, so a skipped record never reads as persisted. Each emits a one-line stderr note naming the feature. `append_event` retains its unconditional `mkdir` at `:476` for Site A. Tests assert no dir created, no events.log written, and exit 4 (`TestDirAbsentSkip`, `TestSkipExitCodeDistinctness`).
- **Verdict**: PASS
- **Notes**: Exit-4 mechanism cleanly satisfies invariants (a) and (b). The Plan-deferred exit-code/stdout contract is settled as a distinct non-3, non-0 exit with stderr note — verdict still on stdout.

### Requirement 3 [Must]: Auto-trigger invariant preserved
- **Expected**: When `cortex/lifecycle/{feature}/` exists, all three writers append normally and a genuine drift/absence returns its real verdict.
- **Actual**: `TestAutoTriggerInvariant` pre-creates the feature dir and asserts: synth → exit 3 + one `synthesizer_drift` row; artifact → exit 3 + one `sentinel_absence` row (`reason: absent`); record-exclusion → exit 0 + one `sentinel_absence` row. `test_variant_a_writer_sites_baseline.py` (pre-creates dir, asserts `rc==3`) still passes unchanged.
- **Verdict**: PASS

### Requirement 4 [Should]: Prose tightening (complementary)
- **Expected**: `verification-gates.md` + SKILL.md updated so `<path>`-arg/no-`--feature`/skip-telemetry contract is unambiguous with a note that the guard enforces it; no new MUST imperative; preamble MUST/MUST-NOT lines at `:1-7` unchanged; grep `guard|structurally enforced|skipped` ≥1.
- **Actual**: Both Phase-1 (`:48,:55`) and Step 2d.5 (`:80,:86`) routes updated to treat exit 4 as a benign skip, distinct from exit 3, with the "write-guard now enforces this structurally" note. SKILL.md mirrors the wording in both Step 2c.5 and Step 2d.5. grep = 6 (≥1). Preamble MUST count `:1-7` = 2, identical to baseline. The diff adds no new MUST imperative (the new prose is positive-routing, e.g. "Treat the reviewer as a normal pass"). `skills/discovery/references/research.md` correctly untouched (plan rationale: `:130` has no `--feature`/`<path>` distinction to tighten).
- **Verdict**: PASS

### Requirement 5 [Must]: Phantom predicate on the existing tolerant reader
- **Expected**: `is_phantom_lifecycle_dir` True iff no `research.md`/`spec.md`/`plan.md` AND events.log event-set is non-empty subset of `{synthesizer_drift, sentinel_absence}`; reuse the project's JSONL reading path (no whole-file `yaml.safe_load`, no mis-reading YAML blocks); reconcile case (ii) (empty/absent/unparseable) with `_is_stale` — cite subsume-or-defer; legacy YAML-block-only file → empty JSONL set → NOT a phantom.
- **Actual**: Predicate in `common.py:430` returns early False if any artifact file present, then reads events.log line-by-line with `json.loads` (skipping unparseable lines and non-dict events), collecting the `event` field, returning `bool(event_types) and event_types <= _TELEMETRY_ONLY_EVENT_TYPES`. Matches the JSONL-per-line approach used by `_detect_lifecycle_phase_inner` and `scan_lifecycle` (`startswith("{")` gate); no `yaml.safe_load`. The plan's spec-vs-reality reconciliation is sound: the spec assumed a YAML-tolerant reader and a predicate-owned empty branch, but the actual readers are JSONL-only and `_is_stale` (`scan_lifecycle.py:419-420, :445-446`) already returns True for missing/unreadable/empty/no-parseable-ts events.log regardless of age — so the predicate **defers** case (ii) to `_is_stale` rather than duplicating it. Docstring explicitly states this delegation. A YAML-block-only file yields an empty JSONL set → `bool(event_types)` False → NOT a phantom (conservative); confirmed by inspection and by test (d)'s hybrid case where the YAML lines are skipped.
- **Verdict**: PASS
- **Notes**: The OSError/ValueError catch in the predicate also returns False (defers to `_is_stale`), consistent with the delegation.

### Requirement 6 [Must]: Discriminator wired into SessionStart; birth-signature fixtures
- **Expected**: `scan_lifecycle.py` does not surface a predicate-classified phantom; predicate runs after `_is_stale`; fixtures (a) birth signatures of known phantoms (lone `synthesizer_drift`, 3× `sentinel_absence`), (b) fresh legit lifecycle with `lifecycle_start`/`clarify_critic` but no artifacts, (c) empty-events.log — phantoms+empty suppressed, fresh lifecycle still surfaced.
- **Actual**: Wired at `scan_lifecycle.py:915`, gated **after** the `_is_stale` check at `:903` (both inside the candidate loop, before the dir is appended to `candidate_dirs`), emitting an `excluded`/`phantom` diagnostic and `continue`. `archive`/`sessions` exclusion preserved at `:901`. Tests encode birth signatures synthetically with a recent ts (`_recent_ts()` = one hour ago, so they pass `_is_stale`): `test_lone_synthesizer_drift_is_phantom`, `test_three_sentinel_absence_is_phantom`. `test_fresh_legitimate_lifecycle_not_phantom` asserts the `lifecycle_start`+`clarify_critic` dir is NOT a phantom (still surfaced). The empty-events.log case is correctly delegated to `_is_stale` (out of predicate scope per the reconciliation) and is not asserted against the predicate — consistent with the plan's narrowing of the spec; the comment at `:909-914` documents the after-`_is_stale` ordering and the recent-ts gap.
- **Verdict**: PASS
- **Notes**: The spec text said the empty-events.log dir is "suppressed" by the discriminator; the plan reconciled this to "suppressed by `_is_stale` upstream, not by the predicate." Net behavior (empty dir not surfaced) is identical; the reconciliation is documented and the test scope matches.

### Requirement 7 [Must]: No false-positive on real lifecycles
- **Expected**: Zero real dirs (any non-telemetry event, or any artifact) classified as phantoms; a real dir lacking `lifecycle_start` must NOT be flagged (the "has lifecycle_start" discriminator was refuted).
- **Actual**: `test_real_dir_without_lifecycle_start_not_phantom` asserts a dir with only a `clarify_critic` event (no `lifecycle_start`, no artifacts) is NOT a phantom — the predicate keys on the telemetry allow-set, not on `lifecycle_start` presence. `test_hybrid_yaml_block_plus_jsonl_not_phantom` and `test_telemetry_only_with_artifact_not_phantom` cover the non-telemetry-JSONL and artifact-present cases. All False as required.
- **Verdict**: PASS

### Requirement 8 [Should]: Events-registry pointer fix
- **Expected**: Correct module path (`critical_review.py` → `critical_review/__init__.py`) AND stale line ranges for `sentinel_absence`/`synthesizer_drift`; `grep -c 'critical_review/__init__.py'` ≥2; `grep -c 'critical_review.py:'` = 0.
- **Actual**: `sentinel_absence` row → `cortex_command/critical_review/__init__.py:573-632` (`_build_sentinel_absence_event`); verified the function starts at `:573` in current source. `synthesizer_drift` row → `cortex_command/critical_review/__init__.py:687-706` (`_cmd_check_synth_stable`); verified the event dict is within `:687-706`. grep `__init__.py` = 2; grep `critical_review.py:` = 0.
- **Verdict**: PASS

### Requirement 9 [Should]: Sibling-gate audit recorded
- **Expected**: Note recording the broad sibling audit found `residue-write` (resolver-exit-gated), `complexity_escalator` (R11-guarded), `lifecycle_critical_review_skipped` (fires only where the dir exists) already protected, no conversion needed; grep `residue-write|already guarded|R11|sibling` ≥1.
- **Actual**: Appended to the `synthesizer_drift` rationale cell in `bin/.events-registry.md`: "Sibling-gate audit (2026-06-01, #274 …): residue-write (resolver-exit-gated …), complexity_escalator (R11-guarded), and lifecycle_critical_review_skipped (fires only where the dir exists) were audited and found already structurally protected — no write-guard conversion needed." grep = 1 (≥1).
- **Verdict**: PASS

### Requirement 10 [Should]: Plugin-mirror parity
- **Expected**: `plugins/cortex-core/skills/critical-review/` regenerated; `test_plugin_mirror_parity.py` green.
- **Actual**: `diff -r skills/critical-review/ plugins/cortex-core/skills/critical-review/` exits 0 (byte-identical); `test_plugin_mirror_parity.py` passes.
- **Verdict**: PASS

### Requirement 11 / 12 [Should / Must]: Full suite green
- **Expected**: `just test` exits 0.
- **Actual**: `just test` → 6/6 passed (test-pipeline, test-overnight, test-init, test-install, tests, tests-takeover-stress). New modules: `test_critical_review_phantom_guard.py` (10 tests) and `test_phantom_dir_discriminator.py` (6 tests) green within the suite.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None. The implementation adds a localized write-site guard and a scanner-side content predicate that match the spec's A+C shape. It introduces a new exit code (4) on the critical-review CLI surface, but that is a spec-mandated mechanism (Req 2), not new behavior unreflected in requirements. The `# gate-class: hygiene` annotations honor the existing #255 parity convention; the prose uses positive-routing phrasing and adds no new MUST, honoring the MUST-escalation policy in `project.md`. The reconciliation of the spec's YAML-reader assumption against the JSONL-only reality (delegating the empty/absent case to `_is_stale`) is a Plan-phase implementation detail, not a requirements change, and the scoped Phase 1 + Phase 2 split aligns with the Philosophy of Work's "deliberately-scoped phase is not a stop-gap" principle.
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent. `_lifecycle_dir_exists` and `is_phantom_lifecycle_dir` follow the module's private-helper / public-predicate split (private writer helper in the critical_review package; public predicate in `common.py` imported by the scanner). `EXIT_TELEMETRY_SKIPPED` is an explicit named constant with a doc-comment explaining its distinctness from 0/2/3. `_TELEMETRY_ONLY_EVENT_TYPES` is a module-level `frozenset` with an explanatory comment.
- **Error handling**: Appropriate. The predicate's JSONL loop catches `json.JSONDecodeError` per line and skips non-dict events / empty event names, so a hybrid file degrades gracefully (test (d)). The events.log read catches `(OSError, ValueError)` and returns False, deferring the empty/absent case to `_is_stale` rather than misclassifying. The guard emits an operator-visible one-line stderr note (asserted by `test_dir_absent_skip_emits_stderr_note`) rather than suppressing silently. `append_event`'s existing `OSError` handling is untouched.
- **Test coverage**: The plan's verification steps were executed and pass. Tests exercise the REAL guard and REAL predicate — no mocks of the guard/predicate; `test_critical_review_phantom_guard.py` drives the actual argparse entry point (`cr_main`) with a `tmp_path` `--lifecycle-root`, and `test_phantom_dir_discriminator.py` calls `is_phantom_lifecycle_dir` directly on `tmp_path` fixtures. Both dir-absent (skip, exit 4) and dir-present (exit 3 / exit 0 + recorded) paths are covered, plus exit-4 distinctness from both 3 and 0. The discriminator covers birth signatures, fresh-legit, no-`lifecycle_start`, hybrid YAML+JSONL, and artifact-present cases.
- **Pattern consistency**: `# gate-class: hygiene` annotations present at the helper definition and all three guard sites (#255 parity; grep +4 over baseline). No new MUST imperative added to the prose (positive-routing only); canonical preamble MUST/MUST-NOT lines at `verification-gates.md:1-7` unchanged (MUST count 2, identical to baseline). The predicate reuses the JSONL-per-line reading idiom already used by `_detect_lifecycle_phase_inner` / `scan_lifecycle`; no new parser, no `yaml.safe_load`. The unrelated golden-fixture refresh (904bb80f) is a count-only bump (32→33, "27 more"→"28 more") committed separately as hygiene; it masks nothing — resolver behavior is unchanged and the 73 resolver/title-phrase tests pass.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
