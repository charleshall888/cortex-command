# Review: add-field-to-cortex-lifecycle-event

## Stage 1: Spec Compliance

### R1: Uniform field-driven row shape (`{ts, event, feature, <ordered fields>}`)
- **Expected**: `log_event`/`_run` emit ts-first, then event, feature, then extra fields in argv order; no `_SCHEMA_VERSION`, no fixed 5-key dict, no `--worktree-path`.
- **Actual**: `lifecycle_event.py` builds `row_dict` as `{ts, event, feature}` then appends `(kind,key,value)` triples in order (L144-150). No `_SCHEMA_VERSION` constant, no `--worktree-path` flag. `python3 -m pytest cortex_command/tests/test_lifecycle_event.py` → 28 passed.
- **Verdict**: PASS
- **Notes**: Key order preserved; verified directly through golden roundtrip (`event` precedes any `--set` field, satisfying the statusline `event`-before-`from` order constraint).

### R2: Canonical serialization (spaced `json.dumps` + `Z` second-precision)
- **Expected**: drop `separators=(",",":")`; `_now_iso()` → `%Y-%m-%dT%H:%M:%SZ`; emitted `ts` matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`; line contains `"event": ` (with space).
- **Actual**: `json.dumps(row_dict)` (no separators), `_now_iso` uses the exact strftime. Runtime emission shows `"ts": "2026-06-29T22:52:17Z", "event": "x", ...` (spaced + Z). `python3 -m pytest cortex_command/tests/` → 50 passed.
- **Verdict**: PASS

### R3: Typed `--set` / `--set-json` flags, order-preserving, value grammar
- **Expected**: shared dest via custom Action; split on first `=`; `=`-less token and malformed JSON are usage errors (exit≠0, NO partial row); duplicate last-wins.
- **Actual**: `_SetFieldAction` writes both flags to dest `set_fields`; validates at parse time (before `log_event`). Runtime: `--set foo` → exit 2, 0 rows; `--set-json k={bad` → exit 2, 0 rows (validate-before-append confirmed); `--set url=https://x?a=b` → full value preserved; `--set reason=` → `""`; dup `k=a k=b` → `"k":"b"`; `--set reason=null` → string `"null"`. Roundtrip suite → 33 passed.
- **Verdict**: PASS
- **Notes**: Malformed `--set-json` writes nothing because `parser.error` fires inside the Action, before any `_append_event_atomic` call.

### R4: Append via flock + `O_APPEND` (destructive read-modify-write + `os.replace` GONE)
- **Expected**: `_append_event_atomic` acquires sibling-lockfile flock, opens `O_APPEND`, single write; no `os.replace`/tempfile in live code.
- **Actual**: `_append_event_atomic` (L69-113) flocks `{log}.lock`, opens with `O_WRONLY|O_CREAT|O_APPEND`, writes, releases. `grep -c 'os.replace\|tempfile\|.tmp' lifecycle_event.py` = 0 (live code AND docstrings). Verb test suite (incl. concurrency arms) → 28 passed.
- **Verdict**: PASS

### R5: Backfill detection survives the `Z` switch (marker-based, not shape regex)
- **Expected**: `is_backfilled` must classify a real second-precision `Z` row (`2026-06-29T00:05:00Z`) as NOT backfilled while still detecting genuinely-backfilled rows; old `T00:0\d:00Z` regex gone; all call sites pass the correct argument type.
- **Actual**: `is_backfilled(event: dict)` returns `event.get("backfilled") is True` (marker-driven). `_BACKFILL_RE` shape regex removed (only referenced historically in comments). Both live call sites (metrics.py:192, :300) pass event dicts. Test (`test_backfill_detection_is_marker_driven_not_shape`) asserts the real `00:05:00Z` dict → False (exercised through `extract_feature_metrics` to confirm durations compute non-null), `{"backfilled": True}` → True, with `{"backfilled": False}` / `{"backfilled": "true"}` negative controls. `test_metrics.py` → 56 passed.
- **Verdict**: PASS
- **Notes**: Signature changed from `(ts: str)` to `(event: dict)`; the spec's literal `is_backfilled("...")` acceptance is satisfied in spirit by the dict-shaped fixture carrying that exact timestamp.

### R6: Migrate lone existing consumer — co-landing in the R1 commit
- **Expected**: implement.md §1a `interactive_worktree_entered` uses `--set worktree_path="$(pwd)"`; lands in the SAME commit that stages `lifecycle_event.py`.
- **Actual**: commit `f3248e04` stages `cortex_command/lifecycle_event.py` AND migrates the implement.md line from `--worktree-path "$(pwd)"` to `--set worktree_path="$(pwd)"` together. `grep -c worktree-path implement.md` = 0; `grep -c interactive_worktree_entered implement.md` = 1.
- **Verdict**: PASS

### R7: Events-registry scanner recognizes `--event <name>` (before any literal removed)
- **Expected**: scanner matches `--event <name>` / `--event=<name>`, anchored on a lowercase-snake token; a typo'd `--event bogus` fails the gate; merged before Phase 2.
- **Actual**: `EVENT_FLAG_RE = r"--event[ =]([a-z_][a-z0-9_]*)"`; `extract_emissions` scans both `EVENT_NAME_RE` and `EVENT_FLAG_RE`. Landed in `168d0a26` (before the migrations in `f2f3a4c5`+). `tests/test_check_events_registry.py` → 15 passed. Whole-repo scan `bin/cortex-check-events-registry --staged --root .` → exit 0.
- **Verdict**: PASS
- **Notes**: The spec's literal acceptance string `bin/cortex-check-events-registry --root .` omits the required mode flag and is a usage error in isolation (the parser mandates `--staged`|`--audit`); the functional whole-repo scan is `--staged --root .`, which exits 0. Spec-text shorthand, not an implementation gap.

### R8: Verb-level tests + docstring repair
- **Expected**: typing/format/concurrency/key-order tests; module + `_append_event_atomic` docstrings drop the tempfile/`os.replace` protocol prose and the false `settings_merge.py`/`_session_state.py` mirror claim; stale `pipeline.md:126` cite updated to live lines.
- **Actual**: `grep -c 'os.replace' lifecycle_event.py` = 0; `grep -c 'pipeline.md:126'` = 0; `grep -c 'settings_merge\|_session_state'` = 0. Docstring now cites `pipeline.md L143/146/151`. Verb tests → 28 passed.
- **Verdict**: PASS

### R9: New flags declared before use (contract lint)
- **Expected**: `--set`/`--set-json` declared in `_build_parser()` before any reference file uses them; `just check-contract` exits 0.
- **Actual**: both flags declared in `_build_parser` (L219-234). `just check-contract` → EXIT=0.
- **Verdict**: PASS

### R10: Route deterministic events through the verb, pinned per-event
- **Expected**: each migrated event's raw `{"event":"X"}` block replaced by a verb invocation; string fields via `--set`, numeric/array via `--set-json`; per-event `grep -c '"event":"X"'`=0 AND `grep -c '--event X'`=row-count; field sets preserved exactly.
- **Actual**: All 15 (file,event) pairs pass the pinned grep (raw=0, flag-count == expected) across plan.md (plan_approved×2, feature_paused, phase_transition), review.md (review_verdict, drift_protocol_breach, phase_transition×3), criticality-matrix.md, critical-review-gate.md, refine-delegation.md, backlog-writeback.md, implement.md (batch_dispatch, phase_transition×2), specify.md. Typing fidelity verified on disk: `batch`/`tasks` (implement.md:176), `cycle` (review.md:144), `retries` (review.md:166) all use `--set-json`; string fields use `--set`. Field-set preservation verified against `git show f3248e04^:<file>` for every row — including the `phase_transition` non-uniformity: implement.md:268 carries `tier` (matches pre-migration), implement.md:241 and review.md's three rows carry only `{from,to}` (match pre-migration).
- **Verdict**: PASS

### R11: Call-site-pinned round-trip tests (de-sealed)
- **Expected**: parametrized golden per migrated event (end-to-end `_run` in tmp root, monkeypatched `_now_iso`); cross-validation reads each `.md` and asserts on-disk flag-kind matches canonical; a deliberately-mistyped `--set batch=` fixture fails.
- **Actual**: `tests/test_lifecycle_event_roundtrip.py` has arm (i) inline golden byte strings pinning serialization/order/JSON-types, and arm (ii) `parse_invocations` reading each `.md` + `cross_validate` (count == expected, anti-vacuous; field-map ∈ allowed canonical). Negative controls run through the file-reading path: mistyped `--set batch=` raises and the corrected `--set-json batch=` accepts (witness); dropped `--set criticality=` raises and restoration accepts; wrong count (99) raises. → 33 passed.
- **Verdict**: PASS
- **Notes**: Genuinely discriminating, not self-sealing. Documented residual (canonical argv is author-supplied; arm ii detects drift-from-canonical, arm i is the independent type/spacing anchor) is acknowledged in the test module docstring.

### R12: Repoint registry producers to gate-scanned site; reconcile feature_paused
- **Expected**: migrated events' producer column cites the `skills/**/*.md` site (not `lifecycle_event.py`); single-source events stay gate-enforced; feature_paused reconciled accurately.
- **Actual**: producer columns for phase_transition, feature_complete, lifecycle_start, batch_dispatch, review_verdict, criticality_override, spec_approved, plan_approved, lifecycle_critical_review_skipped all name `skills/**/*.md` paths; none point at `lifecycle_event.py`. `feature_paused` is DUAL-target (`per-feature-events-log | overnight-events-log`) with both producers named (`plan.md` per-feature `--event` + `outcome_router.py`/`events.py:EVENT_TYPES` overnight) and a rationale documenting the dual emission — the accurate representation (commit `bff59747` restored the overnight target). `bin/cortex-check-events-registry --staged --root .` → exit 0.
- **Verdict**: PASS
- **Notes**: Two non-blocking free-text accuracy nits (outside R12's acceptance, zero gate/functional impact): (a) the `drift_protocol_breach` producer cell still cites `review.md:185`, but the `--event` now lives at line 166 (185 is now a `phase_transition` row); (b) the non-migrated `interactive_worktree_entered` row's "Schema:" rationale still lists `schema_version: 1`, though R6 dropped it from the emitted row. Both are line-number/schema-prose staleness in human-reference cells; the gate ignores them.

### R13: Mirror regen committed with canonicals
- **Expected**: `plugins/cortex-core/skills/{lifecycle,refine}/references/*` (and bin mirror) regenerate via `just build-plugin`; pre-commit drift hook passes.
- **Actual**: `just build-plugin && git diff --quiet plugins/` → clean, exit 0 (committed mirrors == freshly-built).
- **Verdict**: PASS

### R14: Harden the spacing-sensitive consumer (refine SKILL grep)
- **Expected**: `skills/refine/SKILL.md` phase_transition grep made separator-tolerant `grep -cE '"event":[[:space:]]*"phase_transition"'`; `grep -c '\[\[:space:\]\]\*"phase_transition"'` ≥ 1; mirror regenerates.
- **Actual**: `grep -c '\[\[:space:\]\]\*"phase_transition"' skills/refine/SKILL.md` = 1; mirror in sync (R13 drift-clean).
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project patterns. `_SetFieldAction`, `_build_parser`, `_run`, `_now_iso`, `_append_event_atomic`, `log_event` follow the existing `cortex_command` skill-helper idiom; console-script `cortex-lifecycle-event` invocation is used throughout the migrated skills (no bare-Python imports). The events-registry scanner additions (`EVENT_FLAG_RE`, dual extraction in `extract_emissions`) mirror the existing `EVENT_NAME_RE` style.
- **Error handling**: Appropriate and fail-loud. Grammar errors (`=`-less token, malformed JSON) surface as argparse usage errors (exit 2) at parse time, before any append — no partial rows (verified at runtime). `CortexProjectRootError` is caught and reported with exit 1. The flock/`O_APPEND` body releases the lock and closes fds in `finally` blocks. The registry gate fails closed on a missing registry.
- **Test coverage**: Strong and genuinely discriminating. R5's marker test exercises the real `extract_feature_metrics` path with backfill-shaped-but-real timestamps and includes strict-`is True` negative controls. R11 cross-validation reads the actual on-disk `.md` invocations (not author-transcribed argv) and proves rejection is triggered by the defect, not the fixture, via good/bad witness pairs for both mistyped flag-kind and dropped field-key, plus an anti-vacuous wrong-count guard. No vacuous/self-sealing cases observed.
- **Pattern consistency**: Follows project conventions — console-script invocation in skills, mirror parity enforced via `just build-plugin` (drift-clean), contract lint declaring flags first (`just check-contract` exit 0), events-registry gate coverage preserved across the literal→`--event` migration, ADR-0020 recording the load-bearing emission contract (status: proposed, no number collision). The two minor registry free-text staleness items noted under R12 are the only cosmetic gaps and carry no functional or gate impact.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
