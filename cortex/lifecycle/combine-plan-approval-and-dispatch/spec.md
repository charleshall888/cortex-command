# Specification: combine-plan-approval-and-dispatch

## Problem Statement

On the happy path, approving a plan on `main` costs the operator two
back-to-back prompts: Plan §4 (`Approve | Request changes | Cancel`) and then
Implement §1 (which branch/dispatch mode). The plan-approval click conveys no
information the branch-selection click doesn't already imply. This feature folds
the branch/dispatch selection into the plan-approval `AskUserQuestion`: each
branch option implies plan approval, plus an "approve but wait to implement"
option. It removes one redundant prompt per feature. Every disposition *path*
survives, but two of them change affordance: Request-changes and Cancel move
from first-class buttons to the `AskUserQuestion` "Other" free-text escape — a
deliberate trade-off accepted by the operator (Clarify §4) and recorded in the
Proposed ADR.

## Phases

- **Phase 1: Shared branch-picker extraction** — lift the branch-option
  *decision-logic prose* out of Implement §1 into a shared reference both phases
  consult, with no behavior change. The `AskUserQuestion` call site and the
  `cortex-lifecycle-branch-mode` marker invocation stay in each phase's body.
- **Phase 2: Merged plan-approval surface** — Plan §4 presents the merged menu,
  records the choice on `plan_approved`, and on "wait" emits `feature_paused`
  and halts.
- **Phase 3: Implement consumes the recorded choice** — Implement §1 consumes a
  recorded branch mode (skipping its picker) or falls back to the picker.
- **Phase 4: Governance parity** — Kept-pauses inventory, parity test,
  events-registry, SKILL.md prose, the follow-up ticket, and the ADR land
  together.

## Requirements

> **Priority (MoSCoW)**: R3–R12 are **Must-have** — the merged surface (R3–R5),
> the consumer side (R6), and governance parity (R7–R12) must all land together
> or the change ships a broken or test-failing state; there is no coherent
> partial ship. R1–R2 (shared-reference extraction) are **Should-have**: strongly
> preferred to avoid duplicating the decision-logic prose across `plan.md` and
> `implement.md` (a drift liability under the dual-source ethos), but the merge
> could technically function with the prose referenced from one phase. No
> requirement is nice-to-have. Won't-do is enumerated in Non-Requirements.

1. **Shared branch-picker reference**: The branch-option-assembly *decision logic*
   (branch-mode decision routing on `cortex-lifecycle-picker-decision` /
   `should_fire_picker`, the uncommitted-changes-guard rule, the runtime-probe
   degrade rule) is described in one shared reference file under
   `skills/lifecycle/references/` (e.g. `branch-picker.md`). The shared reference
   does **not** contain the literal token `AskUserQuestion` and does **not**
   itself invoke `cortex-lifecycle-branch-mode` — those stay in the consuming
   phase bodies (see R2, R7). Acceptance:
   `grep -l 'should_fire_picker' skills/lifecycle/references/branch-picker.md`
   returns the file AND `grep -c 'AskUserQuestion' skills/lifecycle/references/branch-picker.md`
   = 0. **Phase**: Shared branch-picker extraction.

2. **Both phases consult the shared reference, not inline copies**: After
   extraction, the decision-logic prose appears once (in the shared reference)
   and is referenced — not duplicated verbatim — by both `plan.md` §4 and
   `implement.md` §1. Each phase retains, in its own body, (a) its own
   `AskUserQuestion` call site and (b) the `cortex-lifecycle-branch-mode`
   invocation that the parity test's conditional-pause marker requires.
   Acceptance: Interactive/session-dependent — verified by review that the
   picker-decision/runtime-probe prose block exists once and both phases point
   to it while keeping their own call site + marker.
   **Phase**: Shared branch-picker extraction.

3. **Merged plan-approval surface**: `plan.md` §4 assembles a single
   `AskUserQuestion` whose `options` array is (a) the adaptive branch/dispatch
   modes from the shared reference, plus (b) "Approve plan but wait to
   implement". Selecting any branch mode implies plan approval. The worst-case
   `options` count is 3 branch modes + "wait" = **4**, which is the
   `AskUserQuestion` `options` cap; the always-present "Other" free-text escape
   is auto-appended by the platform **outside** the `options` array and does
   **not** consume one of the 4 slots, so the surface always renders.
   Request-changes and Cancel are handled via "Other": the orchestrator reads the
   free-text and routes a cancel-intent to Cancel (emit `lifecycle_cancelled`,
   halt) and any other text to Request-changes (revise loop). On each
   Request-changes revision round, Plan §4 **re-assembles and re-presents** the
   full merged surface (re-running the shared-reference assembly + uncommitted
   guard + runtime probe). Acceptance: Interactive/session-dependent —
   `plan.md` §4 prose instructs assembling the ≤4-option merged set + "wait",
   the "Other" routing, and the per-round re-presentation.
   **Phase**: Merged plan-approval surface.

4. **`plan_approved` records the choice**: On a branch-mode selection, `plan.md`
   §4 emits `plan_approved` carrying a `dispatch_choice` field whose value is one
   of `{trunk, worktree-interactive, feature-branch}` (mirroring
   `cortex_command/lifecycle_implement.py::_VALID_BRANCH_MODES`, minus `prompt`),
   then `phase_transition plan→implement`, then auto-advances. Acceptance:
   `grep -c 'dispatch_choice' skills/lifecycle/references/plan.md` ≥ 1.
   **Phase**: Merged plan-approval surface.

5. **"Wait to implement" halts, paused and visible**: Selecting "Approve plan but
   wait to implement" emits `plan_approved` with `dispatch_choice: "wait"`, then
   emits `feature_paused`, then halts — no auto-dispatch, no task execution this
   session. The `feature_paused` event makes the deferred state visible:
   `detect_lifecycle_phase` reports `implement-paused` (since `plan_approved` is
   present AND the last significant event is `feature_paused` —
   `cortex_command/common.py:301,308,353`), so statusline/dashboard show "paused"
   rather than active implementation. Re-invocation routes to `implement`
   (because `plan_approved` is present, the routing predicate
   `plan_approved OR plan_transitioned_out` is satisfied — `common.py:353`), where
   Implement fires its fallback picker (`dispatch_choice:"wait"` is not a branch
   mode — see R6). When the feature is backlog-linked (Context A), Plan §4 warns
   at "wait"-time that the overnight runner may still execute the item unless it
   is paused (see R12 and Non-Requirements). Acceptance:
   `grep -c 'feature_paused' skills/lifecycle/references/plan.md` ≥ 1.
   **Phase**: Merged plan-approval surface.

6. **Implement consumes the recorded choice (line-position-last, with explicit
   fallback)**: `implement.md` §1 reads the **line-position-last** `plan_approved`
   event from `events.log` — line order, not timestamp order, matching the
   reducer convention at `cortex_command/common.py:265` (≥2 `plan_approved` rows
   are possible across rework/re-approval cycles). It then routes on that row's
   `dispatch_choice`:
   - value ∈ `{trunk, worktree-interactive, feature-branch}` → Implement skips its
     own picker and routes directly to the matching path (current-branch §2 /
     worktree §1a / feature-branch §1b);
   - value is `"wait"`, OR the field is absent (legacy in-flight `plan_approved`
     with no `dispatch_choice`), OR there is no `plan_approved` event at all
     (reached `implement` via the `phase_transition from:plan` migration sentinel
     / legacy log / resumed or direct `/lifecycle implement` entry) → Implement
     runs the existing fallback picker (now sourced from the shared reference).

   The extraction mechanism (a small helper CLI mirroring
   `cortex-lifecycle-branch-mode`, or an inline read) is a Plan-phase decision,
   but it MUST implement the line-position-last + three-way-fallback contract
   above. Acceptance: a unit test asserts the resolver returns the
   line-position-last branch mode when present and falls back (empty / picker
   signal) for all three absent-field shapes —
   `python3 -m pytest <new test> -q` exits 0; plus
   `grep -c 'dispatch_choice' skills/lifecycle/references/implement.md` ≥ 1.
   **Phase**: Implement consumes the recorded choice.

7. **Kept-pauses inventory + parity test stay green (multi-site)**: The
   `skills/lifecycle/SKILL.md` "Kept user pauses" inventory is updated so (a) the
   `plan.md` plan-approval entry reflects the merged surface at its new line
   anchor, and (b) the `implement.md` branch-picker entry remains (now a
   fallback) with its `cortex-lifecycle-branch-mode` conditional-pause marker
   within ±35 lines of the `implement.md` `AskUserQuestion` site. Because the
   shared reference carries no `AskUserQuestion` literal (R1) and each phase keeps
   its own marker invocation in-body (R2), no new inventory entry is needed for
   `branch-picker.md` and the marker stays in window. The parity test enforces
   **both directions over every `AskUserQuestion` site** under `skills/lifecycle/`
   and `skills/refine/` — re-validate every site→entry and entry→site mapping,
   not just the two changed anchors. Acceptance:
   `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0.
   **Phase**: Governance parity.

8. **Events-registry coherence**: `plan_approved` gains a `dispatch_choice` field
   (no new event *type*), so no new registry row is required; the existing
   `plan_approved` row description in `bin/.events-registry.md:21` is updated to
   note the field. Acceptance: `just check-events-registry` (the
   `cortex-check-events-registry` gate wired at pre-commit Phase 1.8 — **not**
   `cortex-check-parity`, which lints `bin/cortex-*` scripts and does not parse
   the registry) exits 0. **Phase**: Governance parity.

9. **SKILL.md prose reconciled**: The `skills/lifecycle/SKILL.md` Phase-Transition
   text describing the Plan approval surface as "Approve / Request changes /
   Cancel" is updated to describe the merged surface (branch modes + wait;
   request-changes/cancel via "Other"). Acceptance: Interactive/session-dependent
   — review confirms the §4 description matches the new behavior.
   **Phase**: Governance parity.

10. **SKILL-to-bin parity for any new helper**: If R6's resolver is implemented as
    a new `bin/cortex-*` / console-script, it must wire through an in-scope
    reference (SKILL.md/reference/test) per the parity contract. Acceptance:
    `cortex-check-parity` exits 0 on the staged diff (W003 orphan check).
    **Phase**: Governance parity.

11. **Full test suite passes**: Acceptance: `just test` exits 0.
    **Phase**: Governance parity.

12. **Follow-up ticket filed for overnight-honors-pause**: A backlog item is
    created capturing the deferred work — make the overnight runner skip a
    feature whose lifecycle last-significant-event is `feature_paused` (so a
    "wait" genuinely blocks overnight). Acceptance: a `cortex/backlog/NNN-*.md`
    file exists whose body references the overnight `filter_ready` /
    `feature_paused` interaction. **Phase**: Governance parity.

## Non-Requirements

- Does **not** alter the overnight pipeline. The merged surface is
  interactive-only; `cortex_command/overnight/` never reaches `plan.md` §4's
  `AskUserQuestion` and does not consume `dispatch_choice`.
- Does **not**, in this feature, make the overnight runner honor a "wait".
  Verified limitation: overnight eligibility (`filter_ready`,
  `cortex_command/overnight/backlog.py`) gates on backlog status + research.md +
  spec.md and does **not** require plan.md, so a backlog-linked feature set to
  "wait" remains overnight-eligible and the next run would execute it. This
  feature mitigates with (a) a wait-time warning to the operator (R5) and (b) a
  follow-up ticket (R12); it does not block overnight. This is a known,
  documented limitation — not a claim of safety.
- Does **not** change the Specify §4 approval surface. Only Plan §4 is merged
  with Implement §1.
- Does **not** add a first-class "Cancel" or "Request changes" button to the
  merged surface; both route through "Other" per the operator's Clarify decision.

## Edge Cases

- **Not on `main`/`master`**: Implement §1 skips the picker today when already on
  a feature branch. At Plan §4 in that state, the merged surface offers no branch
  sub-choices — it reduces to `[Approve & implement (current branch), Approve but
  wait]` (+ auto "Other"). `dispatch_choice` records `trunk`.
- **`branch-mode: prompt`** (the all-modes-shown config): produces the maximal
  3-branch fan-out — the worst case for the option count — yielding exactly 4
  `options` (3 modes + wait). This is the cap-relevant maximal case.
- **`branch-mode` config suppresses the picker** (e.g. `branch-mode: trunk`,
  `worktree-interactive`, `feature-branch`): the branch sub-choices collapse to
  the configured mode; the merged surface is `[Approve & implement (<configured
  mode>), Approve but wait]`. "wait" is always present regardless of config.
- **Dirty working tree**: the uncommitted-changes guard still demotes (warns +
  strips "recommended" from) the stay-on-current-branch option in place — it adds
  no option, so the count is unchanged.
- **Worktree tooling absent** (`command -v cortex-worktree-create` exit 1): the
  worktree option is removed, leaving `[current branch, create feature branch,
  wait]` (3 options).
- **Resume after "wait"**: re-invoking lands in `implement-paused` →
  (paused-suffix stripped for routing) `implement`; `dispatch_choice` is `"wait"`
  → Implement fires the fallback picker, which re-runs the full preflight against
  current tree state. The once-approved plan stands; there is no separate plan
  re-confirmation gate (the merge intentionally folded the plan-approval into §4).
  If plan or tree drifted materially during the deferral, the operator re-engages
  through the fallback picker and may Cancel/re-plan.
- **Operator picks "Other" → cancel-intent**: emit `lifecycle_cancelled`, halt
  (no `plan_approved`). **"Other" → any other free-text**: treat as Request
  changes — revise loop; no `plan_approved` until a later branch-mode/"wait"
  selection.
- **Re-approval / rework loop**: intermediate revision rounds emit nothing; a
  review `CHANGES_REQUESTED` → re-plan → re-approve cycle legitimately emits a
  second `plan_approved`. The consumer (R6) reads the **line-position-last**
  `plan_approved`, so the most recent selection wins.

## Changes to Existing Behavior

- **MODIFIED**: `plan.md` §4 approval surface — was `Approve | Request changes |
  Cancel`; now the merged branch-modes + "wait" surface (≤4 `options`), with
  request-changes/cancel via "Other".
- **MODIFIED**: `plan_approved` event — now carries a `dispatch_choice` field.
- **ADDED**: `feature_paused` is emitted on the Plan §4 "wait" path (new emit
  site in the interactive lifecycle), yielding phase `implement-paused`.
- **MODIFIED**: `implement.md` §1 — picker becomes a fallback; the primary path
  consumes the line-position-last recorded `dispatch_choice`.
- **ADDED**: shared branch-picker decision-logic reference under
  `skills/lifecycle/references/`.
- **MODIFIED**: `SKILL.md` Kept-pauses inventory (plan.md entry rationale + line
  anchors; implement.md entry rationale) and the §4 approval-surface description.

## Technical Constraints

- State is event-sourced; `cortex-lifecycle-state` is read-only. Carry-forward
  must be an event field (`dispatch_choice` on `plan_approved`), resolved
  **line-position-last** (not ts-sorted — `common.py:265`).
- `detect_lifecycle_phase` reads `event_type` only; the new `dispatch_choice`
  field is backward-compatible for **phase detection**. The new *consumer* of the
  field is Implement §1 (a different reader), which must degrade gracefully for
  the three absent-field shapes (R6) — legacy `plan_approved` without the field,
  the migration-sentinel path with no `plan_approved`, and `dispatch_choice:"wait"`.
- The routing predicate for plan→implement is `plan_approved OR plan_transitioned_out`
  (`common.py:353`), not `plan_approved` alone.
- Overnight `filter_ready` does not require plan.md and ignores `dispatch_choice`
  — the basis for the R12 follow-up and the documented "wait" limitation.
- The parity test enforces both directions over every `AskUserQuestion` site
  within ±35 lines and requires the `cortex-lifecycle-branch-mode`/`read_branch_mode`
  marker near the implement.md conditional pause. The extraction (R1) keeps the
  literal and the marker in-body specifically to preserve both checks.
- `cortex-check-events-registry` (not `cortex-check-parity`) is the gate for the
  registry-row edit; both run at pre-commit.
- Critical-review (`tier=complex` ∧ `criticality=high`) runs before both spec and
  plan approval in this lifecycle.
- Dual-source mirror: `skills/`, `hooks/`, `bin/` canonical sources regenerate
  into `plugins/cortex-core/` via the pre-commit build; edit canonical only and
  commit canonical+mirror together (including the new `branch-picker.md`).

## Open Decisions

None — the overnight-scope question was resolved with the operator (minimal +
warn + follow-up ticket; see R5, R12, Non-Requirements). All other design
questions resolved in Clarify (surface layout) and Research/critical-review
(mechanism).

## Proposed ADR

### Proposed ADR: 0012-merged-plan-approval-and-dispatch-selection

**Context**: The lifecycle historically separated two operator pauses — Plan §4
(plan approval) and Implement §1 (branch/dispatch selection) — each a tracked
"Kept user pause". On the happy path these fire back-to-back, and the
plan-approval click implies nothing the branch selection doesn't.

**Decision**: Merge them into a single Plan §4 `AskUserQuestion`. The branch/
dispatch modes become the approval options (selecting one implies approval; ≤4
`options`, with "Other" auto-appended outside the cap), plus an "approve but wait
to implement" option that emits `plan_approved{dispatch_choice:"wait"}` +
`feature_paused` (→ `implement-paused`) and halts. The choice is carried to
Implement via the `dispatch_choice` field on `plan_approved`, resolved
line-position-last; Implement consumes a valid branch mode and skips its own
picker, retaining the picker as a fallback for the three absent-field shapes.
Request-changes and Cancel move from first-class buttons to the "Other"
free-text escape, because `AskUserQuestion` caps `options` at 4 and the operator
prioritized seeing all branch modes.

**Trade-off**: Removes one redundant prompt per feature and keeps full branch
choice, at the cost of demoting Request-changes/Cancel to free-text "Other"
(a real affordance/discoverability cost for the revise loop) and of a known
limitation — the overnight runner does not yet honor "wait" (deferred to a
follow-up ticket; mitigated by a wait-time warning). The merge couples two
previously-independent pauses; reversing means re-splitting the surface and
removing the `dispatch_choice` field. Recorded because a future maintainer
seeing plan-approval pick branch modes (and Request-changes living in "Other")
would otherwise lack the rationale. Complements ADR-0008 (picker-selection
authorizes `EnterWorktree`).
