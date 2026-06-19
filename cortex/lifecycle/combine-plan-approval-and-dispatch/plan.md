# Plan: combine-plan-approval-and-dispatch

## Overview
Merge the Plan §4 approval surface and the Implement §1 branch picker into one
`AskUserQuestion`, carrying the operator's branch choice forward on a new
`dispatch_choice` field of the `plan_approved` event and consuming it
line-position-last in Implement. The consumed choice **substitutes for the
picker's result** and flows through Implement's existing post-selection routing
(all guards intact), gated on `main`/`master`. The branch-option *decision logic*
is extracted once into a shared reference; each phase keeps its own
`AskUserQuestion` call and `cortex-lifecycle-branch-mode` marker in-body so the
parity test stays green.
**Architectural Pattern**: event-driven
<!-- Carry-forward channel is an event field (dispatch_choice on plan_approved) produced at Plan, consumed at Implement. Field optional/N-A for non-critical tier; included for clarity. -->

## Outline

### Phase 1: Shared branch-picker extraction (tasks: 1, 2)
**Goal**: Lift the branch-option decision-logic prose into a shared reference;
implement.md consults it while keeping its call site + marker in-body. No
behavior change.
**Checkpoint**: `branch-picker.md` exists with no `AskUserQuestion` literal;
implement.md references it; parity test still green.

### Phase 2: Carry-forward mechanism + merged surface (tasks: 3, 4, 5)
**Goal**: Add the line-position-last `dispatch_choice` resolver (helper + CLI +
reinstall + test) and rewrite plan.md §4 as the merged surface that records the
choice and pauses on "wait".
**Checkpoint**: `cortex-lifecycle-dispatch-choice --feature <fixture>` runs from
PATH and the unit test is green; plan.md §4 emits `plan_approved{dispatch_choice}`
and the "wait" path emits `feature_paused`.

### Phase 3: Implement consumes the recorded choice (task: 6)
**Goal**: implement.md §1, gated on main/master, consumes a valid recorded branch
mode by auto-selecting the picker result (identical routing + guards) and falls
back to the picker for the three absent-field shapes.
**Checkpoint**: implement.md §1 prose routes on `cortex-lifecycle-dispatch-choice`
and threads the consumed value into the existing selection routing.

### Phase 4: Governance parity (tasks: 7, 8, 9, 10, 11, 12)
**Goal**: SKILL.md inventory + manifest + §4 prose, events-registry row, the
follow-up ticket, ADR-0012, docs, and the full gate sweep (incl. mirror staging)
land green.
**Checkpoint**: parity test, events-registry gate, parity gate, `just test`, and
the staged dual-source mirror all pass; ADR-0012 and the follow-up backlog item
exist.

## Tasks

### Task 1: Create shared branch-picker decision-logic reference
- **Files**: `skills/lifecycle/references/branch-picker.md`
- **What**: Extract the branch-option-assembly *decision logic* from implement.md
  §1 (the `cortex-lifecycle-picker-decision` / `should_fire_picker` routing on the
  closed reason set; the uncommitted-changes-guard demotion rule; the runtime-probe
  3-way menu-disposition rule) into a new shared reference. Describe the logic
  generically so both Plan §4 and Implement §1 can consult it.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Source prose is implement.md §1 (Branch-mode dispatch preflight,
  Uncommitted-changes guard, Runtime probe). The reference must NOT contain the
  literal token `AskUserQuestion` and must NOT itself invoke
  `cortex-lifecycle-branch-mode` — those stay in each consuming phase body (parity
  constraints, R7). This reference needs a **Reference-path propagation manifest
  entry** in SKILL.md (Task 7) — that is the load-bearing path-propagation manifest
  at SKILL.md:140 (SP001/SP002 per ADR-0009), which is a DIFFERENT structure from
  the Kept-pauses inventory; it gets no inventory entry (no `AskUserQuestion`).
  Mirror auto-regenerates into `plugins/cortex-core/skills/lifecycle/references/`.
- **Verification**: `test -f skills/lifecycle/references/branch-picker.md && [ "$(grep -c 'AskUserQuestion' skills/lifecycle/references/branch-picker.md)" = 0 ]` — pass if file exists and count = 0.
- **Status**: [x] done

### Task 2: Refactor implement.md §1 to consult the shared reference (no behavior change)
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Replace the inlined branch-option-assembly decision prose in §1 with a
  reference to branch-picker.md, while keeping in-body: the `AskUserQuestion` call
  site, the `cortex-lifecycle-branch-mode` invocation (the conditional-pause
  marker), and the dispatch-by-selection routing. Behavior unchanged — the picker
  still fires exactly as before.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The marker regex the parity test requires is
  `read_branch_mode|lifecycle_config|cortex-lifecycle-branch-mode` within ±35
  lines of the §1 `AskUserQuestion` site (`tests/test_lifecycle_kept_pauses_parity.py`
  lines 42, 197–214). Keep the `cortex-lifecycle-branch-mode .` call adjacent to
  the picker. Do not yet add consumer logic (Task 6).
- **Verification**: `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0 — pass if exit 0.
- **Status**: [x] done

### Task 3: Add the dispatch_choice resolver (helper + console-script) and reinstall
- **Files**: `cortex_command/lifecycle_implement.py`, `cortex_command/lifecycle/dispatch_choice_cli.py`, `pyproject.toml`
- **What**: Add `read_dispatch_choice(events_path)` to `lifecycle_implement.py`
  returning the **line-position-last** `plan_approved` event's `dispatch_choice`
  value, or `None` when there is no `plan_approved` event or the latest one lacks
  the field (update the module docstring's "exactly two public symbols" note to
  admit the new export). Add a `cortex-lifecycle-dispatch-choice --feature <slug>`
  console-script (new `dispatch_choice_cli.py`) — resolution mirrors
  `cortex_command/lifecycle/state_cli.py` (`--feature` arg, CWD-relative
  `cortex/lifecycle/{feature}/events.log`), **not** `branch_mode_cli.py`'s
  positional path; the consumption is gated on main/master (Task 6) so the read
  always runs in the main-repo CWD. Register the `[project.scripts]` entry in
  `pyproject.toml`, then **reinstall so the console-script materializes on PATH**
  (`uv tool install --reinstall .` or `pip install -e .` for the dev env — a new
  `[project.scripts]` entry is NOT on PATH until reinstall; the runtime PATH copy
  lives in the uv-tool env, confirmed via `cortex-lifecycle-branch-mode`'s shebang).
- **Depends on**: none
- **Complexity**: complex
- **Context**: Mirror `state_cli.py` structure (argparse, `_telemetry.log_invocation`,
  `main(argv)`, events path at `state_cli.py:146`). Line-order convention: iterate
  `events_content.splitlines()`, keep the LAST `plan_approved` match — same
  convention as `cortex_command/common.py:265` (line order, never ts-sort).
  Console-script name parallels `cortex-lifecycle-state =
  "cortex_command.lifecycle.state_cli:main"`.
- **Verification**: `python3 -c "from cortex_command.lifecycle_implement import read_dispatch_choice"` exits 0 AND, after reinstall, `cortex-lifecycle-dispatch-choice --feature combine-plan-approval-and-dispatch` exits 0 (prints empty or a value) — pass if both exit 0.
- **Status**: [x] done

### Task 4: Unit-test the resolver (line-position-last + three-way fallback)
- **Files**: `tests/test_dispatch_choice_resolver.py`
- **What**: Test `read_dispatch_choice` against synthetic events.log fixtures:
  (a) single `plan_approved{dispatch_choice:"worktree-interactive"}` → that value;
  (b) two `plan_approved` rows (rework cycle) with different `dispatch_choice` →
  the line-position-last one; (c) `plan_approved` with no `dispatch_choice` →
  `None`; (d) no `plan_approved` event (only `phase_transition from:plan`
  sentinel) → `None`; (e) `dispatch_choice:"wait"` → `"wait"`. Plus a subprocess
  smoke asserting `cortex-lifecycle-dispatch-choice --feature <fixture>` exits 0.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Use `tmp_path` fixtures writing JSONL; import `read_dispatch_choice`
  from `cortex_command.lifecycle_implement`. Mirror existing lifecycle reducer
  test fixture style.
- **Verification**: `python3 -m pytest tests/test_dispatch_choice_resolver.py -q` exits 0 — pass if exit 0.
- **Status**: [x] done

### Task 5: Rewrite plan.md §4 as the merged approval surface
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Replace §4 (and §5 transition) so the approval surface is a single
  `AskUserQuestion` whose `options` are the adaptive branch modes (assembled per
  branch-picker.md) + "Approve plan but wait to implement" (≤4 options; "Other" is
  the auto-appended escape outside the cap). Selecting a branch mode emits
  `plan_approved` with `dispatch_choice ∈ {trunk, worktree-interactive,
  feature-branch}`, then `phase_transition plan→implement`, then auto-advances.
  "Wait" emits `plan_approved{dispatch_choice:"wait"}` then `feature_paused`, then
  halts; for backlog-linked (Context A) features, warn at wait-time that overnight
  may still execute the item. "Other" free-text → orchestrator routes cancel-intent
  to `lifecycle_cancelled`+halt, else Request-changes (revise loop). On each
  revision round, re-assemble and re-present the merged surface. Keep plan.md's own
  `cortex-lifecycle-branch-mode` invocation in-body for the assembly.
- **Depends on**: [1, 3]
- **Complexity**: complex
- **Context**: Current §4 is plan.md ~lines 265–289 (`Approve | Request changes |
  Cancel`; emits `plan_approved` then `phase_transition` then auto-advances). The
  `dispatch_choice` vocabulary mirrors `_VALID_BRANCH_MODES` minus `prompt`. The
  `feature_paused` JSON shape: `{"ts":..., "event":"feature_paused", "feature":...}`
  (a known significant event, `common.py:295`). Reference branch-picker.md via the
  body-resolved absolute path (manifest entry, Task 7). Skill prose only — no code
  bodies.
- **Verification**: `for t in dispatch_choice feature_paused trunk worktree-interactive feature-branch; do grep -q "$t" skills/lifecycle/references/plan.md || { echo "missing $t"; exit 1; }; done` exits 0; plus Interactive/session-dependent review of the surface logic (gated by Task 7 parity + Task 12 `just test`) — pass if the grep loop exits 0.
- **Status**: [x] done

### Task 6: Add consumer logic to implement.md §1 (substitute for picker result)
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: At the start of §1's branch-selection step — and **only when the
  current branch is `main`/`master`** (the existing picker gate; off-main resumed
  sessions skip both per the current line-90 behavior) — read the recorded choice
  via `cortex-lifecycle-dispatch-choice --feature {slug}`. If the value is a valid
  branch mode, **treat it exactly as if the operator had selected that option in
  the picker** and run the identical post-selection routing (do NOT jump past the
  guards):
  - `trunk` → the "Implement on current branch" path → §2;
  - `worktree-interactive` → the "Implement on feature branch with worktree" path →
    **record entry mode `selected`**, run §1 Step A (overnight-active rejection) and
    Step B (interactive-lock acquisition), then §1a;
  - `feature-branch` → the "Create feature branch" inline path (the existing
    "create and check out `feature/{lifecycle-slug}`" prose) → §2.
  If the value is `wait`, empty, or the CLI reports no recorded choice (absent field
  / no `plan_approved` / sentinel path), fall through to the existing fallback
  picker (now sourced from branch-picker.md, Task 2).
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: §1a (Interactive Worktree Creation) runs in entry modes `selected`
  vs `suppressed` and Step v branches on that marker — the consumed worktree path
  MUST be `selected` (it auto-enters via `EnterWorktree` per ADR-0008), NOT
  `suppressed` (cd-shim, de-authorized). The overnight-active + interactive-lock
  guards are §1 Step A/B (gated on selection), NOT inside §1a — routing the
  consumed worktree choice through the selection path is what preserves them.
  There is **no `### 1b.` heading** (verified — only §1/§1a exist); feature-branch
  creation is the inline prose at the current implement.md ~line 88, reachable via
  §2 — route there, not to a phantom "§1b". Gating on main/master keeps the
  resolver read in the main-repo CWD (the worktree carries its own events.log).
- **Verification**: `grep -q 'cortex-lifecycle-dispatch-choice' skills/lifecycle/references/implement.md && grep -q 'main/master\|on `main`' skills/lifecycle/references/implement.md` exits 0 — pass if exit 0.
- **Status**: [x] done

### Task 7: Update SKILL.md inventory, manifest, and §4 description
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Three distinct edits: (a) **Kept-pauses inventory** (SKILL.md:180) —
  re-anchor the `plan.md` plan-approval entry to its post-edit `AskUserQuestion`
  line and reword for the merged surface, keeping it an **unconditional** pause
  (do NOT tag it "conditional pause", even though plan.md keeps a
  `cortex-lifecycle-branch-mode` invocation in-body — plan approval always fires);
  re-anchor the `implement.md` entry, keep its "conditional pause" tag + marker
  note. (b) **Reference-path propagation manifest** (SKILL.md:140) — add a
  `branch-picker.md` entry (distinct structure from the inventory). (c) Update the
  Phase-Transition prose describing the Plan §4 surface as "Approve / Request
  changes / Cancel" to describe the merged surface.
- **Depends on**: [5, 6]
- **Complexity**: complex
- **Context**: Parity test checks every `AskUserQuestion` site → entry AND every
  entry → site within ±35 lines, plus the conditional-pause marker ONLY for entries
  tagged "conditional pause". Verify the post-edit line numbers of the
  `AskUserQuestion` mentions in plan.md (Task 5) and implement.md (Task 6) before
  writing anchors; re-anchor until the test is green. The manifest entry follows the
  existing format at SKILL.md:144–152 (`- **branch-picker** (consulted in Plan §4
  and Implement §1) → ${CLAUDE_SKILL_DIR}/references/branch-picker.md`).
- **Verification**: `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0 — pass if exit 0.
- **Status**: [x] done

### Task 8: Update the events-registry plan_approved row
- **Files**: `bin/.events-registry.md`
- **What**: Update the `plan_approved` row (~line 21) description to note the new
  `dispatch_choice` field and its closed value set. No new event type / row.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: The gate is `cortex-check-events-registry` (`just check-events-registry`,
  pre-commit Phase 1.8) — not `cortex-check-parity`. The gate scans skill prose for
  emitted event *names*; a description-only row edit satisfies it. Preserve the
  markdown table column structure.
- **Verification**: `just check-events-registry` exits 0 — pass if exit 0.
- **Status**: [x] done

### Task 9: File the follow-up ticket for overnight-honors-pause
- **Files**: `cortex/backlog/` (one new `NNN-*.md` item)
- **What**: Create a backlog item capturing the deferred work: make the overnight
  runner skip a feature whose lifecycle last-significant-event is `feature_paused`
  (so a "wait" genuinely blocks overnight), grounded in the verified `filter_ready`
  no-plan.md-requirement gap.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Use the backlog tooling (`/cortex-core:backlog new` or the backlog
  CLI). Body must reference the overnight `filter_ready`
  (`cortex_command/overnight/backlog.py`) / `feature_paused` interaction so spec
  R12's grep acceptance resolves.
- **Verification**: `ls cortex/backlog/ | grep -Ei 'overnight.*pause|pause.*overnight|wait.*overnight|honor.*pause'` returns ≥1 file — pass if a matching backlog file exists.
- **Status**: [x] done

### Task 10: Create ADR-0012 from the spec's Proposed ADR
- **Files**: `cortex/adr/0012-merged-plan-approval-and-dispatch-selection.md`
- **What**: Promote the spec's `## Proposed ADR` body (the
  `0012-merged-plan-approval-and-dispatch-selection` context/decision/trade-off)
  into a committed ADR file, following the repo ADR format and the three-criteria
  gate (the spec's Phase 4 lists "the ADR land together").
- **Depends on**: none
- **Complexity**: simple
- **Context**: Repo pattern: spec Proposed ADRs are committed via an explicit task
  (cf. ADR-0005, ADR-0009). Follow `cortex/adr/README.md` format and the existing
  ADR files (e.g. `cortex/adr/0008-*.md`, which this one complements). No lifecycle
  gate auto-creates the file.
- **Verification**: `test -f cortex/adr/0012-merged-plan-approval-and-dispatch-selection.md && grep -qi 'dispatch_choice' cortex/adr/0012-merged-plan-approval-and-dispatch-selection.md` — pass if exit 0.
- **Status**: [x] done

### Task 11: Reconcile docs/interactive-phases.md
- **Files**: `docs/interactive-phases.md`
- **What**: Review the Plan-phase approval description (the "plan approval
  required" / request-changes prose) and update it to reflect the merged surface
  (branch modes + wait imply approval; request-changes/cancel via "Other"). If the
  existing prose remains accurate (generic), make the minimal clarifying edit and
  note in the commit that docs were reviewed.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: `docs/interactive-phases.md` is the one doc describing the Plan
  approval gate (lines ~54, ~72). Keep edits minimal and accurate; do not
  over-document skill internals (docs ownership conventions).
- **Verification**: Interactive/session-dependent: review confirms the Plan-approval description matches the merged surface (no command can assert doc-prose correctness).
- **Status**: [x] done

### Task 12: Full gate sweep + mirror regen + staging check
- **Files**: (validation; `plugins/cortex-core/**` mirror regenerated by build)
- **What**: Regenerate the dual-source mirror (`just build-plugin`), stage the
  regenerated mirror, then run the full local gate set and resolve any fallout:
  parity test, events-registry gate, SKILL-to-bin parity, and `just test`. Confirm
  the canonical `skills/`/`bin/` edits and their `plugins/cortex-core/` mirrors are
  staged together (the drift pre-commit hook rejects a stale mirror).
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
- **Complexity**: simple
- **Context**: Run `just build-plugin` before the final commit (memory: on main,
  regen mirror with the canonical-edit commit). After `git add` of canonical +
  mirror, `git status --porcelain plugins/cortex-core/` should show no UNSTAGED
  mirror changes. The new resolver ships as `[project.scripts]`, not `bin/cortex-*`,
  so W003 should not fire — confirm with `cortex-check-parity`.
- **Verification**: `just test` exits 0 AND `python3 -m pytest tests/test_lifecycle_kept_pauses_parity.py -q` exits 0 AND `just check-events-registry` exits 0 AND `git status --porcelain plugins/cortex-core/ | grep -c '^ M' ` = 0 (no unstaged mirror drift) — pass if all hold.
- **Status**: [x] done

## Risks
- **Parity-anchor drift**: Tasks 5/6 change line counts in plan.md/implement.md;
  Task 7 re-anchors against *post-edit* numbers. Mitigated by the parity test as
  Task 7's verification (iterate to green) and by keeping the plan.md entry
  unconditional (no spurious marker match).
- **Console-script PATH staleness**: a `[project.scripts]` entry is not on PATH
  until reinstall (the runtime copy is in the uv-tool env). Task 3 mandates the
  reinstall and a subprocess acceptance check so the consumer's runtime command is
  actually exercised, not just imported.
- **Editable-install / sequential dispatch**: Task 3 edits the editable-installed
  `cortex_command` package — the Implement phase MUST use **sequential** dispatch
  (not worktree) so verification runs against the working tree, not a stale worktree
  copy (repo dispatch-mode constraint).
- **Consumed worktree path must use entry mode `selected`**: routing the consumed
  `worktree-interactive` choice as `suppressed` would skip `EnterWorktree`/ADR-0008
  authorization and emit a wrong diagnostic. Task 6 pins it to `selected` through
  the §1 Step A/B selection path.
- **"Other" classification is model judgment**: routing free-text to cancel vs
  request-changes is orchestrator interpretation (prose), acceptable per "prescribe
  What not How"; flagged as a soft surface.

## Acceptance
The merged Plan §4 surface presents branch modes + "wait" in one `AskUserQuestion`
(selecting a branch mode implies approval and records `dispatch_choice`); "wait"
pauses the feature (`feature_paused` → `implement-paused`) and warns on Context-A
features; Implement §1 — gated on main/master — consumes the line-position-last
recorded choice by substituting it for the picker result and running the identical
post-selection routing (guards intact), falling back to the picker for the three
absent-field shapes; the resolver console-script runs from PATH; the parity test,
events-registry gate, SKILL-to-bin parity, and `just test` pass with the
dual-source mirror staged; and ADR-0012 plus a follow-up backlog item exist.
Observable end-state: `just test` exits 0 with all the above wired and the mirror
staged.
