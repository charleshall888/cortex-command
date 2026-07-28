---
schema_version: "1"
uuid: 21a08006-ba43-4456-98cd-ed42cec6087c
title: Make the review-verdict transition record instead of silently refusing
status: refined
priority: high
type: bug
created: 2026-07-28
updated: 2026-07-28
tags: ['harness', 'overnight', 'lifecycle', 'observability']
areas: ['overnight-runner']
complexity: complex
criticality: high
spec: cortex/lifecycle/make-the-review-verdict-transition-record/spec.md
---
## Why

**An APPROVED overnight review can record nothing, and the loss is structural rather than intermittent.**

Session `overnight-2026-07-28-1216` reviewed #415. The agent produced a 19.7 KB `review.md` covering 13 commits across 9 files, executed every acceptance check, and closed with `{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}`. No `review_verdict` row ever reached `cortex/lifecycle/reconcile-dashboard-docs-and-observability-requirements/events.log`. The feature's log ends at the `phase_transition` written *before* the review dispatched.

The visible symptom appears in a different tool, hours later: `cortex-morning-review-advance-lifecycle` returns `missing-review`, whose documented meaning is "the feature was expected to be reviewed overnight but wasn't". That sent this session's operator to the conclusion that a passing feature had merged unreviewed, and PR #27 was held on that false basis.

**Mechanism, reproduced directly.** `_advance_review_complete` (`cortex_command/pipeline/review_dispatch.py`) passes `_current_phase()` as `advance()`'s `from_state`. These are two different detectors and they disagree. Against the real session artifacts:

```
_current_phase()  -> 'complete'
advance()         -> refused, gate-mismatch:
                     "detected phase 'review' does not match expected from_state 'complete'"
```

`_current_phase`'s own docstring claims passing the detected phase "makes the gate a tautology ... so `advance` records the arm's transition rather than refusing on a gate-mismatch". That claim is false, and the arm was written "Best-effort; envelope ignored", so the refusal left no trace anywhere.

**A hardcoded `from_state` is not the fix — it was tried and rejected.** Setting `from_state="review"` satisfies the real session's artifact set (+2 rows written, verified) but mismatches in the *opposite* direction on a synthetic feature dir, where `advance` detects `complete` and refuses `review`. That trades one silent refusal for another.

## Role

Make the review-verdict transition record reliably, by resolving why the two phase detectors disagree rather than by guessing a state that satisfies one corpus.

The open question is which directory each detector reads. `_current_phase` calls `detect_lifecycle_phase(feature_events_log.parent)` — the directory containing the log it was handed. `advance` re-detects internally, and the two results differ even when pointed at the same feature, which suggests `advance` resolves the feature directory from the slug against the project root rather than from `log_path`. If so, the arm and the gate are describing different trees and no `from_state` value can be correct in general.

Either make both detectors read the same location, or give this arm a sanctioned way to assert the transition it just performed — the refusal envelope itself names `cortex-lifecycle-event log` as the sanctioned override for out-of-band rows.

## Integration

`_advance_to_review` (the implement→review entry arm) uses the same pattern and happens to succeed today, because at that moment `review.md` does not yet exist. Whatever fix lands should cover both arms rather than only the failing one.

## Edges

- `advance` must stay best-effort: a refusal must never fail a run. Already covered by a test.
- Refusals are no longer silent (shipped, see below) — the warning names the feature and the log it failed to write. Do not remove that when fixing the gate; it is what makes the next instance diagnosable.
- ADR-0025 makes the `phase_transition→complete` row the events-first completion signal, and `metrics.py:extract_feature_metrics` reads completion off it. A feature whose row never lands is invisible to those metrics too, not just to morning review.
- The 374 Phase-4 fold forbids this module emitting transition rows itself (`tests/test_fold_completion.py` fails if `log_event` is reintroduced here), so the fix must go through `advance`, not around it.
- Non-goal: changing what `detect_lifecycle_phase` means for interactive lifecycles. This is about the overnight arms agreeing with the gate they call.

## Touch points

- `cortex_command/pipeline/review_dispatch.py:39-48` — `_current_phase`, and the docstring claiming the gate is a tautology
- `cortex_command/pipeline/review_dispatch.py` — `_advance_to_review`, `_advance_review_complete`, `_advance_or_warn`
- `cortex_command/lifecycle/advance.py` — the `from_state` gate and its own phase detection
- `cortex_command/common.py:detect_lifecycle_phase`
- `cortex_command/overnight/advance_lifecycle.py` — the `missing-review` reader that surfaces the symptom
- Evidence: `cortex/lifecycle/reconcile-dashboard-docs-and-observability-requirements/{events.log,review.md}`; `cortex_command/pipeline/tests/test_review_verdict_recording.py`