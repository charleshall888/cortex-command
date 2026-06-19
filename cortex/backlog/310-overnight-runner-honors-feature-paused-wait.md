---
schema_version: "1"
uuid: 19f98a8d-928e-41e3-bd36-7cd5150ca0a0
title: Overnight runner honors a lifecycle "wait"/feature_paused instead of re-executing it
status: backlog
priority: medium
type: feature
created: 2026-06-19
updated: 2026-06-19
areas: ['overnight-runner']
---
**Why:** The interactive lifecycle now offers "Approve plan but wait to implement" (the `combine-plan-approval-and-dispatch` feature), which emits `plan_approved{dispatch_choice:"wait"}` plus `feature_paused` and halts so the operator can defer implementation. But overnight eligibility is blind to that signal: `filter_ready` in `cortex_command/overnight/backlog.py` admits a feature on backlog status (`backlog`/`ready`/`in_progress`/`implementing`/`refined`) plus `research.md` + `spec.md` presence, and explicitly does **not** require `plan.md` — it reads neither `dispatch_choice` nor the lifecycle `feature_paused` event. So a backlog-linked feature the operator deliberately set to "wait" stays overnight-eligible, and the next overnight run will plan and execute it, silently overriding the operator's deferral — precisely for the autonomous-overnight features the project most depends on. For now the interactive surface mitigates with a wait-time warning, but the deferral is not actually enforced.

**Role:** Make a lifecycle that is in the "wait"/paused state observed and respected by the overnight eligibility path, so an operator's "Approve plan but wait" genuinely holds until they resume — closing the gap between the interactive defer affordance and the overnight executor.

**Integration:**
- The overnight eligibility decision (`filter_ready` and its caller) should treat a feature whose lifecycle last-significant-event is `feature_paused` as not-ready, so it is skipped rather than executed.
- Decide and document how a paused feature is resumed for overnight (operator un-pause vs. a later `phase_transition`), keeping the signal consistent with how `detect_lifecycle_phase` already derives the `-paused` suffix.
- Relate to `combine-plan-approval-and-dispatch` (ADR-0012), which introduced the "wait" affordance and recorded this as a deliberate, deferred limitation.

**Edges:**
- The "wait" state lives in the per-feature lifecycle `events.log`, while overnight eligibility currently keys on backlog frontmatter status — the two surfaces must be reconciled without coupling overnight to interactive-only state in a brittle way.
- `feature_paused` is also an overnight-events-log concept (dashboard consumers); take care that an interactive-lifecycle `feature_paused` is interpreted correctly and does not collide with the overnight pause semantics.
- Non-goal: changing the interactive merged-approval surface itself; this is purely the overnight executor's side of honoring the pause.
