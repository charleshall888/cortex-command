# Specification: Wire requirements drift check into lifecycle review

> Epic reference: [`research/requirements-audit/research.md`](../../../research/requirements-audit/research.md) — this ticket is scoped to making drift detection mandatory in the review phase. Requirements authoring, area doc creation, and skill path fixes are separate tickets.

## Problem Statement

The lifecycle review phase currently completes without any requirements check. A feature can be APPROVED with implementation behavior that was never captured in requirements docs, and the project has no mechanism to detect or log this drift. The forward risk is that every feature built through lifecycle has a chance to silently widen the gap between what requirements say the system does and what it actually does. The fix is to make requirements drift detection a mandatory, logged output of the review phase — not an advisory prompt — so that drift is either explicitly declared absent or explicitly documented and flagged for follow-up.

## Requirements

1. **Mandatory drift section**: The review artifact (`lifecycle/{slug}/review.md`) must include a `## Requirements Drift` section. This section is required — review.md without it is incomplete. The review phase protocol validates the section exists before logging `review_verdict`.

2. **Two-state structured format**: The drift section uses this exact fill-in template:
   ```
   ## Requirements Drift

   **State**: none | detected
   **Findings**:
   - (one bullet per drifted item, or "None" if state is none)
   **Update needed**: (path to requirements file that needs updating, or "None")
   ```
   - `none` — implementation matches stated requirements; no drift detected
   - `detected` — drift found; the `Findings` bullets describe what drifted; `Update needed` names the requirements file that requires a human update

   The reviewer is read-only and cannot mark drift as resolved. Whether or not drift was subsequently addressed is out of scope for the review artifact — this field is a point-in-time observation only.

3. **Verdict JSON extended**: The verdict JSON block gains a `requirements_drift` field using the same two values:
   ```json
   {"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
   ```
   Valid values: `"none"` or `"detected"`. This is the machine-readable channel for drift status. The `**State**:` field in the drift section and the verdict JSON field use the same two-value vocabulary — no mismatch.

4. **Replaces `## Requirements Compliance`**: The existing conditional `## Requirements Compliance` section is removed and replaced by the mandatory `## Requirements Drift` section. The new section covers both directions: (a) implementation violates existing requirements, and (b) implementation introduces behavior not reflected in any requirements doc.

5. **Drift does not influence verdict**: The verdict (APPROVED / CHANGES_REQUESTED / REJECTED) reflects spec compliance and code quality only. Requirements drift is an observation logged for human action. The reviewer prompt must explicitly state this. A feature with `detected` drift may still be APPROVED.

6. **Requirements doc loading (review phase §1, before reviewer dispatch)**: The existing freeform scan in review.md's §1 ("Scan `requirements/` for area docs relevant to this feature") is replaced by this structured tag-based loading step:
   - Read `lifecycle/{slug}/index.md` to get the `tags:` array
   - Read `requirements/project.md`'s Conditional Loading section
   - For each tag word, check whether any Conditional Loading phrase contains that word; collect matching area doc paths
   - Inject the resolved list of requirements files (project.md + matched area docs) explicitly into the reviewer prompt
   - If no area docs are matched or none exist, load project.md only; log this as a comment in the reviewer prompt ("no area docs matched for tags: [tags]; drift check covers project.md only")

7. **Reviewer is read-only**: The reviewer sub-task must not modify any requirements files. The log + flag only constraint is enforced via the reviewer prompt and by the existing read-only sub-task convention.

8. **Morning report surfaces drift**: `claude/overnight/report.py` gains a `_read_requirements_drift(feature)` helper (following `_read_verification_strategy()` pattern) that extracts the `**State**:` value and `**Findings**:` bullets from `review.md`. The helper returns `None` when `review.md` is absent and a dict `{"state": str, "findings": list[str]}` when found. The helper is called for all features where `lifecycle/{feature}/review.md` exists — not just features that completed to `merged` status — so that drift findings from interrupted sessions are surfaced.

9. **Overnight context: no stall**: Drift findings are written to review.md as normal and surfaced in the morning report. Detected drift never stalls the overnight session and does not hold merges.

## Non-Requirements

- No automated requirements file updates — this ticket explicitly excludes any logic that modifies `requirements/*.md` as part of the review
- No changes to earlier lifecycle phases (research, specify, plan, implement)
- No new file types — drift findings live in review.md, not in a separate drift.md artifact
- No changes to overnight runner merge logic — `detected` drift does not prevent merging
- No RTM (Requirements Traceability Matrix) generation — this is a point-in-time logged observation, not a structured traceability system
- No retroactive updates to existing review.md artifacts
- No changes to `claude/common.py` or the lifecycle state machine — enforcement is handled by the review phase protocol, not the Python parser

## Edge Cases

- **Area docs don't yet exist**: The `requirements/` directory currently contains only `project.md`. Drift check degrades gracefully to project.md-only with an explicit note in the reviewer prompt. This is the expected state at deployment; tag-to-doc matching improves automatically as area docs are added.
- **Feature has no tags**: If `lifecycle/{slug}/index.md` has an empty `tags:` array, the step loads project.md only and notes this in the reviewer prompt.
- **Reviewer context overflow / missing drift section**: Before logging `review_verdict`, the review phase protocol checks that `## Requirements Drift` exists in review.md. If absent (e.g., context-overflowed reviewer), the orchestrator re-dispatches the reviewer with explicit instruction to complete the drift section, or escalates if on retry limit.
- **Session interrupted after review.md written but before verdict processed**: Morning report's `_read_requirements_drift()` reads review.md for all features with it present — so drift findings are surfaced even for in-progress review phases.
- **Drift detected at CHANGES_REQUESTED cycle 2**: The reviewer logs drift in the drift section but issues CHANGES_REQUESTED only for spec failures. If the only finding is drift (no spec/code failures), the verdict is APPROVED with `requirements_drift: detected`. The cycle counter does not increment.
- **Tag-to-doc mapping fails to match**: If no tag words match any Conditional Loading phrase, the review loads project.md only. This is treated as a successful but narrow drift check, not an error — logged in the reviewer prompt for transparency.

## Technical Constraints

- The verdict JSON block (`{"verdict": ..., "cycle": ..., "issues": [...]}`) is machine-parsed by the lifecycle state machine. The new `"requirements_drift"` field is additive — existing parsers that don't read it continue to work. Enforcement of field presence is handled by the review phase protocol (pre-event validation in review.md), not by the Python state machine.
- The reviewer sub-task is dispatched as a focused read-only agent — it cannot log to `events.log` directly. Drift status propagates to the orchestrator via the review artifact (the `**State**:` field and the verdict JSON `"requirements_drift"` value). The orchestrator validates the drift section exists before logging the updated `review_verdict` event.
- Tag-to-doc mapping: tags are compared against Conditional Loading phrase words (case-insensitive substring match). Example: tag `pipeline` matches the phrase "Working on pipeline, overnight runner, conflict resolution..." → loads `requirements/pipeline.md`. A tag that matches no phrase loads no area doc for that tag.
- `_read_requirements_drift()` in `report.py` extracts the `**State**:` line value and the `**Findings**:` bullet list from the `## Requirements Drift` section. Returns `None` when the section is absent. Returns `{"state": "none"|"detected", "findings": list[str]}` when found. If the section exists but is malformed (no `**State**:` line), returns `{"state": "malformed", "findings": []}` — this is treated as a drift detection failure and surfaced in the morning report.
