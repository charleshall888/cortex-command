# Research: combine-plan-approval-and-dispatch

## Clarified Intent

Merge the two back-to-back user prompts on the happy path — the **Plan-phase
approval surface** (`skills/lifecycle/references/plan.md` §4: `Approve | Request
changes | Cancel`) and the **Implement-phase branch/dispatch selection**
(`skills/lifecycle/references/implement.md` §1: current branch / feature branch
with worktree / create feature branch) — into a **single `AskUserQuestion` at
plan approval**. Each option is an implementation/branch mode that implies plan
approval; one extra option is "approve plan but wait to implement". Request-changes
and Cancel move to the always-present `AskUserQuestion` "Other" free-text escape
(per operator decision in Clarify §4).

Complexity: **complex**. Criticality: **high** (shared workflow orchestration).

## Current Mechanics (grounded in source)

### Plan §4 approval (`plan.md:265–289`)
- `AskUserQuestion` with `Approve | Request changes | Cancel`.
- **Approve** → append `plan_approved` event → append `phase_transition`
  `plan→implement` → auto-advance to Implement.
- **Request changes** → revise loop (no `plan_approved` until final Approve).
- **Cancel** → `lifecycle_cancelled`, halt.
- §3a Orchestrator Review and §3b Critical Review run **before** §4. For this
  feature (complex + high) the §3b `critical-review` skill fires before approval.

### Implement §1 branch selection (`implement.md:11–90`)
The branch picker fires **only on `main`/`master`**, and only when not suppressed.
Its option set is assembled by a multi-stage preflight:
1. **Branch-mode decision**: `cortex-lifecycle-branch-mode .` (reads per-repo
   `lifecycle.config.md::branch-mode`) → `cortex-lifecycle-picker-decision . {slug} {mode}`.
   The decider is `cortex_command/lifecycle_implement.py::should_fire_picker`
   (closed reasons: `branch_mode_unset_or_invalid`, `branch_mode_prompt`,
   `dirty_tree`, `live_interactive_worktree_session`, `suppressed`). When
   `suppressed`, the picker is skipped and the configured mode is used directly.
2. **Uncommitted-changes guard**: `git status --porcelain` — demotes (warns +
   strips "recommended" from) the stay-on-current-branch option; never removes it.
3. **Runtime probe**: `command -v cortex-worktree-create` — exit 1 **removes** the
   worktree option (2-option menu); exit 0 keeps all three.
- After selection, execution-time machinery runs: §1a worktree creation
  (`cortex-worktree-create`, `EnterWorktree`, interactive-lock acquisition,
  overnight-active rejection) or §1b feature-branch creation.

### Phase detection (`cortex_command/common.py::detect_lifecycle_phase`, lines 255–372)
- Event-sourced. Step 3 (line 351): `plan.md` exists →
  - **NOT (`plan_approved` OR `plan_transitioned_out`)** → phase `plan` (stay).
  - all tasks `[x]` → `review`; else → `implement`.
- `paused` (line 301) = the **last significant event** (`phase_transition`,
  `feature_complete`, `feature_wontfix`, `feature_paused`) is `feature_paused`
  → non-terminal phases get a `-paused` suffix → `implement-paused`.

### State is read-only / event-sourced
- `cortex-lifecycle-state` (`state_cli.py`) is **read-only** — it reduces
  `events.log` to `{criticality, tier}`. There is **no generic writable
  per-feature state field**. Any carry-forward of the branch choice must be an
  **event** in `events.log`.

## Key Findings → Design Implications

1. **Carry-forward = an event field.** Record the selected branch mode as a
   field on the `plan_approved` event (e.g.
   `{"event":"plan_approved", ..., "dispatch_choice":"trunk|worktree-interactive|feature-branch|wait"}`).
   `detect_lifecycle_phase` reads `event_type` only (line 282) and ignores extra
   fields, so this is backward-compatible. `plan_approved` is registered in
   `bin/.events-registry.md:21`; **adding a field needs no new registry row**
   (only a new *event type* would). Atomic approval+choice matches the operator's
   "selecting an implementation option implies approval".

2. **Implement §1 keeps the picker as a fallback.** Implement §1 must read the
   latest `plan_approved.dispatch_choice`:
   - valid branch mode → **consume it, skip the picker**, route to §1a/§1b/§2.
   - `"wait"` or absent (resumed session / direct `/lifecycle implement` entry /
     legacy logs) → **run the existing picker**.
   So implement.md **retains an `AskUserQuestion` site** — the parity test still
   needs that inventory entry (and its `cortex-lifecycle-branch-mode` conditional-
   pause marker within ±35 lines).

3. **Avoid duplicating the option-assembly prose.** The branch-option assembly
   (branch-mode decision + uncommitted guard + runtime probe) is needed at BOTH
   plan §4 (to build the merged surface) and implement §1 (fallback). Extract it
   into a **shared reference** (e.g. `references/branch-picker.md`) consulted by
   both, rather than copy-pasting (drift risk; the project's dual-source/parity
   ethos).

4. **"wait" must emit `plan_approved`.** Because Step 3 of `detect_lifecycle_phase`
   returns phase `plan` when `plan_approved` is absent, the "wait" option must
   still emit `plan_approved` (with `dispatch_choice:"wait"`) so re-invocation
   routes to `implement`, not back into Plan. This also matches the operator's
   stated semantics ("approve plan but wait" → plan IS approved). On re-invoke,
   implement §1 sees `dispatch_choice:"wait"` (not a branch mode) → fires the
   normal picker.

5. **Overnight is unaffected.** The merged surface is interactive-only.
   The overnight pipeline (`cortex_command/overnight/`) auto-plans and executes
   under `--dangerously-skip-permissions` and never reaches plan.md §4's
   `AskUserQuestion`. No overnight code path consumes the new field.

6. **Parity-test obligations** (`tests/test_lifecycle_kept_pauses_parity.py`):
   - plan.md gains/changes a merged-approval `AskUserQuestion` → update the
     `plan.md:277` inventory entry (line + rationale).
   - implement.md keeps its picker `AskUserQuestion` → keep the `implement.md:44`
     entry; preserve the `cortex-lifecycle-branch-mode` marker within ±35 lines
     (it is tagged a "conditional pause").
   - Both directions of the parity test must stay green; re-anchor line numbers
     after edits land.

## Design Options to Resolve in Spec

- **A. "wait" event representation.**
  - (A1) `plan_approved{dispatch_choice:"wait"}` only — simplest; re-invoke →
    `implement` (plan_approved + tasks unchecked).
  - (A2) `plan_approved{dispatch_choice:"wait"}` + `feature_paused` — re-invoke →
    `implement-paused`, surfacing the deferred state to statusline/dashboard.
    Idiomatic but adds a second event. **Lean A2** for the clean "paused" signal.
- **B. Whether Plan §5 still emits `phase_transition plan→implement` on the
  "wait" path.** On a branch-mode selection: yes (advance). On "wait": optional —
  routing works via `plan_approved` alone. Decide alongside A.
- **C. Shared-reference extraction vs. inline.** Recommend extracting the option-
  assembly into `references/branch-picker.md` (Finding 3).

## Open Questions

All resolved during research — none deferred to the user:

- *How does a plan-time choice reach Implement?* → event field on `plan_approved`
  (Finding 1). **Resolved.**
- *Does adding a field break any reader?* → No; `detect_lifecycle_phase` reads
  `event_type` only; `dashboard/seed.py` only emits a sample `plan_approved`.
  **Resolved.**
- *Does "wait" risk re-entering Plan on resume?* → No, provided "wait" emits
  `plan_approved` (Finding 4). **Resolved.**
- *Is overnight affected?* → No (Finding 5). **Resolved.**

## Recommended Approach (for Spec/Plan)

1. Extract the branch-option-assembly preflight into a shared reference.
2. At plan §4, after §3a/§3b pass, assemble the merged surface = (adaptive branch
   options, via the shared reference) + "Approve but wait to implement". Selecting
   a branch option emits `plan_approved{dispatch_choice:<mode>}` +
   `phase_transition plan→implement` and auto-advances. "wait" emits
   `plan_approved{dispatch_choice:"wait"}` (+ `feature_paused` per A2) and halts.
   Request-changes / Cancel handled via "Other".
3. Implement §1 reads the latest `plan_approved.dispatch_choice`; consumes a valid
   branch mode (skipping the picker and running the right §1a/§1b path), else
   falls back to the existing picker.
4. Update the SKILL.md Kept-pauses inventory + the parity test in lockstep.

## Risks

- **Parity-test drift**: the ±35-line anchors and the conditional-pause marker
  are brittle to edits — must re-verify after each edit.
- **Two-picker drift**: plan §4 and implement §1 fallback must not diverge — the
  shared-reference extraction is the mitigation.
- **Dirty-tree timing**: branch-mode/dirty-tree state is sampled at plan-approval
  time; if the tree changes before re-invocation on the "wait" path, the
  implement-time picker re-samples (acceptable — the fallback path re-runs the
  full preflight).
