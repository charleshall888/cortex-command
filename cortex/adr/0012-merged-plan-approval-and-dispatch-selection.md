---
status: accepted
---

# Merged Plan approval and branch/dispatch selection

## Context

The lifecycle historically separated two operator pauses — Plan §4 (plan
approval: `Approve | Request changes | Cancel`) and Implement §1 (branch/dispatch
selection: current branch / feature branch with worktree / create feature
branch). On the happy path these fire back-to-back, and the plan-approval click
conveys nothing the branch-selection click does not already imply. Both were
tracked entries in the `skills/lifecycle/SKILL.md` "Kept user pauses" inventory
and the `tests/test_lifecycle_kept_pauses_parity.py` parity test.

State is event-sourced; `cortex-lifecycle-state` is read-only and there is no
generic writable per-feature state field, so any value carried from Plan to
Implement must be an event field. `AskUserQuestion` caps its `options` array at 4,
with an "Other" free-text escape auto-appended *outside* that cap.

## Decision

Merge the two pauses into a single Plan §4 `AskUserQuestion`. The branch/dispatch
modes become the approval options (selecting one implies approval; ≤4 `options`,
with "Other" outside the cap), plus an "Approve plan but wait to implement"
option that emits `plan_approved{dispatch_choice:"wait"}` + `feature_paused`
(→ phase `implement-paused`) and halts.

The choice is carried to Implement via a `dispatch_choice` field on the
`plan_approved` event, resolved **line-position-last** (matching the reducer
convention in `cortex_command/common.py`, which warns against timestamp-sorting).
Implement §1 — gated on `main`/`master` so the read runs in the main-repo CWD —
consumes a valid branch mode by **substituting it for the picker's result** and
running the identical post-selection routing (the overnight-active and
interactive-lock guards in §1 Step A/B, the `selected` entry mode for the worktree
path per ADR-0008, the feature-branch creation prose); it retains the picker as a
fallback for the three "no recorded branch mode" shapes (no `plan_approved`, a
`plan_approved` lacking the field, or `dispatch_choice:"wait"`), and also falls
back when the resolver console-script is not yet installed.

Request-changes and Cancel move from first-class buttons to the `AskUserQuestion`
"Other" free-text escape, because the 4-option cap and the operator's choice to
see all branch modes leave no primary slot for them.

The branch-option *decision logic* is extracted into a shared reference
(`skills/lifecycle/references/branch-picker.md`) consulted by both phases; each
phase keeps its own `AskUserQuestion` call and `cortex-lifecycle-branch-mode`
marker in-body so the parity test's site→entry and conditional-pause-marker
checks both hold.

## Trade-off

Removes one redundant prompt per feature and keeps full branch choice, at the cost
of demoting Request-changes/Cancel to free-text "Other" (a real
affordance/discoverability cost for the revise loop). One interaction with the
overnight runner was originally logged here as a limitation: its eligibility gate
keys on backlog status + research/spec presence and does not read `dispatch_choice`
or `feature_paused`, so a "wait"-deferred feature stays overnight-eligible. That
was deferred to follow-up #310, which was **closed won't-fix (2026-06-30)**:
"Approve plan but wait" is a soft session-boundary deferral, not a hold, and
overnight is a legitimate fresh-context pickup path that **reuses the
operator-approved `plan.md`** (it synthesizes only when `plan.md` is missing —
`cortex_command/overnight/prompts/orchestrator-round.md:210`), so picking up a
waited feature is the intended handoff, not an override. Dependency-style waits
are expressed via `blocked_by`. The interactive `feature_paused` → `implement-paused`
surface (statusline/dashboard visibility) is unaffected.
The merge couples two previously-independent pauses; reversing means re-splitting
the surface and removing the `dispatch_choice` field.

## Three-criteria gate clearance

- **Hard to reverse**: reversing re-splits the Plan §4 surface, removes the
  `dispatch_choice` field and its `read_dispatch_choice` resolver + console-script,
  re-inlines the branch-picker decision logic, and re-anchors the Kept-pauses
  inventory across plan.md/implement.md/SKILL.md.
- **Surprising without context**: a maintainer seeing plan approval pick branch
  modes — and Request-changes living in "Other" rather than as a button — would
  reasonably assume a regression. This ADR records the rationale (the 4-option cap
  and the operator's all-branch-modes preference) and the deliberate affordance
  trade-off.
- **Real trade-off**: the alternative (keep the two pauses, or demote branch modes
  instead of Request-changes/Cancel) is concrete; the chosen demotion of the
  off-ramps and the deferred overnight-honors-pause work are the accepted costs.

## Alternatives considered

- **Keep the two separate pauses (rejected)**: the status quo; rejected because it
  asks two redundant questions on the happy path, which is the problem this feature
  removes.
- **Keep Request-changes as a button, trim a branch mode (rejected by operator
  choice)**: drop the rarely-used/risky "create feature branch" from the merged
  surface to free a slot for Request-changes. Rejected because the operator chose
  to see all branch modes and accept Request-changes/Cancel via "Other".
- **Emit only `plan_approved` on "wait", no `feature_paused` (rejected)**: simpler,
  but the deferred state would be invisible to statusline/dashboard
  (`detect_lifecycle_phase` would report plain `implement`), misrepresenting a
  paused feature as active work. Rejected in favor of `feature_paused` →
  `implement-paused`.
- **Make overnight honor "wait" by blocking eligibility (deferred → rejected via
  #310)**: originally deferred to follow-up #310, which was closed won't-fix
  (2026-06-30). "Approve plan but wait" is a soft session-boundary deferral, and
  overnight legitimately picks up a waited feature reusing the operator-approved
  `plan.md` — so blocking overnight eligibility would break that handoff rather
  than protect it. Dependency-style waits use `blocked_by`. See
  `cortex/lifecycle/archive/overnight-runner-honors-a-lifecycle-wait/research.md`.

## Relation to ADR-0008

Complements [ADR-0008](0008-picker-selection-authorizes-enterworktree.md): the
consumed worktree-interactive choice routes through the `selected` entry mode (the
`EnterWorktree` authorization path), not the suppressed cd-shim path.
