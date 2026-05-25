# Review: reconcile-sessionstart-lifecycle-phase-summary-against (cycle 2)

## Stage 1: Spec Compliance

Cycle 2 re-review focuses on R14 (the only PARTIAL from cycle 1) and the R8
minor cleanup. R1–R13 and R15 were PASS in cycle 1 and the full test suite
(94 tests) continues to pass — they remain PASS without re-reading each file.

### Requirement 14: Session-bound JSONL diagnostic (re-verified)
- **Expected** (cycle-1 unmet items): emission from each exclusion branch
  (stale, morning_review, complete-no-PR); `decision` ∈ {`"included"`,
  `"excluded"`}; `exclude_reason` field present; misleading comment
  removed; test covers excluded-candidate path.
- **Actual**:
  - New helper `_emit_candidate_diag` at `cortex_command/hooks/scan_lifecycle.py:349-395`
    centralises record construction with the spec's full schema, including
    `decision` and `exclude_reason`. It looks up `backlog_status` from the
    pre-loaded map and computes `mismatch` only when an `encoded_phase`
    exists (avoiding spurious `False` mismatch claims for stale/morning_review
    candidates that never reached phase detection).
  - **Stale branch** (`scan_lifecycle.py:900-905`): emits
    `decision="excluded"`, `exclude_reason="stale"`, `encoded_phase=None`.
  - **Morning-review branch** (`scan_lifecycle.py:906-914`): emits
    `decision="excluded"`, `exclude_reason="morning_review"`,
    `encoded_phase=None`.
  - **Complete-no-PR branch** (`scan_lifecycle.py:959-968`): emits
    `decision="excluded"`, `exclude_reason="complete_no_pr"`, and crucially
    passes the resolved `encoded="complete"` so the mismatch predicate can
    surface the inverse-#075 case (events=complete + backlog non-terminal)
    in the JSONL even though the entry is suppressed from the visible
    enumeration. This is a slight strengthening over the literal cycle-1
    ask and aligns with the Non-Requirements motivation.
  - **Included branch** (`scan_lifecycle.py:974-980`): `decision="included"`,
    `exclude_reason=None`. Decision token renamed from cycle-1's
    `"rendered"` to spec-compliant `"included"`.
  - **Comment cleanup** (`scan_lifecycle.py:974-976`): the previously
    misleading "emitted separately below by the same loop body's continue
    branches" sentence is replaced with "Excluded candidates (stale /
    morning_review / complete_no_pr) emit from their respective continue
    branches above" — now accurately describes the call-site geometry.
  - **Test** `test_session_diagnostic_excluded_stale` at
    `tests/test_hooks_scan_lifecycle.py:1676-1740` stages a 120-day-old
    feature with default 30-day threshold, asserts `decision="excluded"`,
    `exclude_reason="stale"`, `events_phase=None`, `latest_event_ts=old_ts`,
    `threshold_days=30`. Passes alongside the pre-existing
    `test_session_diagnostic_written` (updated for renamed `included` token)
    and `test_session_diagnostic_silent_when_session_id_unset`.
- **Verdict**: PASS
- **Notes**: The complete-no-PR branch passes the encoded phase through
  rather than `None`, which goes slightly beyond the literal cycle-1 ask
  but is the more useful design — it preserves the mismatch-surfacing
  capability for the inverse-#075 case in post-mortem review. The schema
  is consistent: `encoded_phase` is `None` only for pre-detection
  exclusions (stale, morning_review), and present for post-detection
  outcomes (complete-no-PR excluded, all included).

### Requirement 8: Index.json loaded once per hook invocation (R8 cleanup re-verified)
- **Expected** (cycle-1 minor finding): the previously-unused
  `_backlog_duplicate_slugs` either gets wired into a duplication
  diagnostic OR is dropped. Spec wording on duplication-diagnostic
  destination is ambiguous, so either resolution is acceptable.
- **Actual**: `scan_lifecycle.py:884` now reads
  `backlog_status_map, _ = _load_backlog_status_map(cwd)` — the duplicates
  list is explicitly discarded via underscore unpacking. The function
  signature still returns the tuple so the duplicate-detection logic
  remains exercised by `test_index_json_duplicate_first_wins` (which
  reads the list directly from the function).
- **Verdict**: PASS
- **Notes**: This is the simpler of the two acceptable resolutions. If a
  future iteration wants per-duplicate JSONL records, the call-site
  unpacking is trivial to change.

### Requirements 1-13, 15: Spot-check via full test suite
- **Actual**: 94 tests pass across the four affected files:
  - 39 in `tests/test_hooks_scan_lifecycle.py` (+1 vs cycle-1: the new
    `test_session_diagnostic_excluded_stale`)
  - 51 in `tests/test_lifecycle_phase_parity.py`
  - 2 in `tests/test_dashboard_data.py`
  - 2 in `tests/test_lifecycle_kept_pauses_parity.py`
- **Verdict**: PASS (carried forward from cycle 1)

## Requirements Drift

**State**: none
**Findings**:
- No new sandbox grants, no schema-of-record changes, no new
  backlog-status vocabulary introduced by the rework. The
  `_emit_candidate_diag` helper writes to the same already-documented
  session-bound path (`cortex/lifecycle/sessions/<id>/scan-lifecycle-diag.jsonl`)
  established in cycle 1. observability.md's read-only-observability
  posture and statusline performance discipline remain honored.
- The `exclude_reason` token vocabulary (`"stale"`,
  `"morning_review"`, `"complete_no_pr"`) is a new local schema element
  but is scoped strictly to the JSONL diagnostic — not surfaced in any
  user-facing string, backlog field, or events.log emission.
**Update needed**: None

## Stage 2: Code Quality (rework-specific)

- **Naming**: `_emit_candidate_diag` follows the leading-underscore
  module-internal convention; its name clearly distinguishes from
  `_emit_diag` (the low-level appender). The `exclude_reason` token
  vocabulary uses snake_case (`complete_no_pr`) matching events.log
  conventions and the spec's quoted examples (`"stale"`, `"morning_review"`).
- **Error handling**: `_emit_candidate_diag` adds no new failure modes —
  it delegates to `_events_log_meta` (already fail-open with default
  `{"latest_ts": None, "last_event": None}`) and `_emit_diag` (already
  try/except wrapped). The `_is_terminal_mismatch` call is guarded by
  the `encoded_phase is not None` predicate, avoiding a hypothetical
  TypeError if a future caller passes `None`.
- **Test coverage**: The new test exercises the stale path end-to-end
  (file creation, schema completeness, value correctness, threshold
  surfaced). Coverage gap from cycle 1 closed. Morning-review and
  complete-no-PR exclusion paths are not directly tested in isolation,
  but the helper is identical across all three call sites and the
  schema is verified by the stale test, so the marginal value of
  additional fixtures is low — acceptable scope discipline.
- **Pattern consistency**: The lazy `import datetime as _dt` inside
  `_emit_candidate_diag` mirrors the existing lazy-import discipline at
  the original `main()` call site (datetime is the only heavyweight
  stdlib import in the hook path). The helper signature with keyword-
  positional arguments matches the surrounding code's style. The
  decision to pass `encoded` through for complete-no-PR (rather than
  `None`) is documented inline at lines 366-372 of the docstring,
  preventing the next reader from "fixing" it back to `None`.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
