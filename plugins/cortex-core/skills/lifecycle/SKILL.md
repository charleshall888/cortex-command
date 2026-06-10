---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/cortex-core:lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", "start a feature lifecycle", or wants to build a non-trivial feature with structured phases. Required before editing files in `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/`. Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` regenerate via pre-commit hook; edit canonical sources only.
when_to_use: "Use when starting a new feature (\"start a feature\", \"build this properly\") or any non-trivial change with structured phases. Different from /cortex-core:refine — refine stops at spec.md; lifecycle continues to plan/implement/review."
argument-hint: "<feature> [phase]"
inputs:
  - "feature: string (required) — kebab-case slug of the feature to develop or resume"
  - "phase: string (optional) — explicit phase to enter: research|specify|plan|implement|review|complete"
outputs:
  - "cortex/lifecycle/{{feature}}/ — directory containing phase artifacts: research.md, spec.md, plan.md, review.md, events.log"
preconditions:
  - "Run from project root"
  - "cortex/lifecycle/ directory must exist or will be created"
precondition_checks:
  - "test -d cortex/lifecycle"
---

# Feature Lifecycle

A file-based state machine that survives context loss. Enforces research-before-code, prose-before-implementation, and spec-before-build discipline.

## Contents

1. [Invocation](#invocation)
2. [Project Configuration](#project-configuration)
3. [Step 1: Identify the Feature](#step-1-identify-the-feature)
4. [Step 2: Check for Existing State](#step-2-check-for-existing-state)
5. [Step 3: Execute Current Phase](#step-3-execute-current-phase)
6. [Phase Transition](#phase-transition)
7. [Lifecycle Directory](#lifecycle-directory)
8. [Reference Files](#reference-files)

## Invocation

- `/cortex-core:lifecycle {{feature}}` — start new or resume existing feature
- `/cortex-core:lifecycle {{phase}}` — explicitly enter a phase for the active feature
- `/cortex-core:lifecycle resume {{feature}}` — resume a specific feature if multiple exist

## Project Configuration

If `cortex/lifecycle.config.md` exists at the project root, read it first. It contains project-specific overrides for complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Identify the Feature

Feature/phase from invocation: $ARGUMENTS. Parse: first word = feature name, second word (if present) = explicit phase override. If $ARGUMENTS is empty, fall through to the existing behavior (scan for incomplete lifecycle directories).

When `$ARGUMENTS` is non-empty but its first word is prose rather than a valid kebab-case slug (the valid-slug pattern is `^[a-z0-9]+(-[a-z0-9]+)*$`), derive a 3–6 word kebab-case slug that summarizes the prose's intent, announce the chosen slug as you create `cortex/lifecycle/{slug}/`, and use it as `{feature}` for the rest of Step 1 and Step 2. Do not ask the user to confirm the derived slug — proceed and let the user correct via re-invocation if needed. A derived slug that collides with an existing `cortex/lifecycle/{slug}/` directory is treated as a resume per Step 2's phase-detection routing, not silently disambiguated.

Determine the feature name from the invocation. Use lowercase-kebab-case for directory naming. When linked to a backlog item, use the canonical `slugify()` from `cortex_command.common`.

### Resolve the originating backlog file once

When `$ARGUMENTS` is non-empty, invoke `cortex-resolve-backlog-item` once to find the matching backlog file. This single call replaces the previous pattern of independently re-scanning `cortex/backlog/[0-9]*-*{feature}*.md` in each of the four Step 2 sub-procedures (Backlog Status Check, Create index.md, Backlog Write-Back, Discovery Bootstrap). The four sub-procedures consume Step 1's resolver output — they do not re-scan the backlog directory.

```bash
cortex-resolve-backlog-item {feature}
```

Route on the resolver's exit code:

- **exit code 0** — Unambiguous match. The resolver prints the resolved backlog filename on stdout (e.g. `cortex/backlog/193-lifecycle-and-hook-hygiene-one-offs.md`). Record this as the `{backlog-file}` Step 2 sub-procedures will consume. Also perform a single read of the file's YAML frontmatter at Step 1 entry and hold the parsed fields (`uuid`, `status`, `tags`, `discovery_source`, `research`, `spec`) in conversation memory for the four sub-procedures.
- **exit code 2** — Ambiguous match. The resolver prints candidate filenames on stderr. Present the candidates via `AskUserQuestion` and halt for user selection. Once selected, treat the chosen filename as the `{backlog-file}`.
- **exit code 3** — No match. The named feature has no backlog file. Step 2 sub-procedures each handle the no-backlog-file path independently (Backlog Status Check skips silently; Create index.md proceeds with null fields; Backlog Write-Back silent-skips; Discovery Bootstrap records no epic context).
- **exit code 64** — Usage error. Halt with the resolver's diagnostic; this indicates an invocation bug, not a feature-naming issue.
- **exit code 70** — Software/IO error. Halt with the resolver's diagnostic.

When `$ARGUMENTS` is empty, skip the resolver entirely — the existing incomplete-lifecycle-dirs scan path applies (see Step 2's empty-arguments fallback).

The single-resolve contract is prose discipline: Step 2's four sub-procedures (in `references/backlog-writeback.md` and `references/discovery-bootstrap.md`) reference Step 1's `{backlog-file}` and parsed frontmatter without re-scanning. If a long session causes the parsed frontmatter to drop from working memory, a single targeted re-Read of `{backlog-file}` is permitted at the phase boundary — but the four sub-procedures do not re-scan the backlog directory.

## Step 2: Check for Existing State

Scan for `cortex/lifecycle/{feature}/` at the project root.

### Artifact-Based Phase Detection

If no `cortex/lifecycle/{feature}/` directory exists, `phase = none` — start from the beginning. Otherwise, invoke the canonical detector and route on the returned `phase` field:

```bash
cortex-common detect-phase cortex/lifecycle/{feature}
```

The command emits a single JSON object on stdout, e.g. `{"phase":"implement","checked":2,"total":5,"cycle":1}`. Parse the `phase` field and route accordingly. The `checked`/`total` fields report plan-task progress; `cycle` reports the review-cycle number.

Reference table (one line per `phase` value):

| `phase`            | Semantic meaning                                                                                  |
|--------------------|---------------------------------------------------------------------------------------------------|
| `research`         | No artifacts yet — start the Research phase.                                                      |
| `specify`          | `research.md` exists; advance to the Specify phase.                                               |
| `plan`             | `spec.md` exists; advance to the Plan phase.                                                      |
| `implement`        | `plan.md` exists with at least one task unchecked; run/resume the Implement phase.                |
| `implement-rework` | `review.md` verdict is `CHANGES_REQUESTED`; re-enter Implement to address review feedback.        |
| `review`           | `plan.md` exists with all tasks checked; run the Review phase.                                    |
| `complete`         | `events.log` has a `feature_complete` event, or `review.md` verdict is `APPROVED` — feature done. |
| `escalated`        | `review.md` verdict is `REJECTED`; present reviewer analysis and ask the user for direction.      |

**Paused suffix**: when the detected phase ends in `-paused` (e.g. `implement-paused:3/5`, `review-paused`), strip the `-paused` portion for routing-table lookup above; display the full label including ` — paused` to the user. The `-paused` marker is set when `events.log`'s most recent significant event among `{phase_transition, feature_complete, feature_wontfix, feature_paused}` is `feature_paused`. A later `phase_transition` event resumes the feature and clears the marker. This rule survives future `-paused` variants without table updates.

**Detect criticality**: After determining the phase, run `cortex-lifecycle-state --feature {feature} --field criticality` (rules: [criticality-matrix.md §Reading lifecycle state](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md)). Report the detected criticality alongside the detected phase when resuming.

**Detect complexity tier**: After determining the phase, run `cortex-lifecycle-state --feature {feature} --field tier` (rules: [criticality-matrix.md §Reading lifecycle state](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md)). Report the detected tier alongside the detected phase when resuming.

**Register session**: After identifying the feature (whether new or existing), register this session by writing the session file:

```
echo $LIFECYCLE_SESSION_ID > cortex/lifecycle/{feature}/.session
```

If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase. Before presenting the offer, surface two staleness signals so the user can decide whether the existing artifacts are still trustworthy:

1. **Artifact age (mtime)**: report the modification time of `cortex/lifecycle/{feature}/spec.md` (and `plan.md` if present) via `os.path.getmtime` or `stat -c %Y`. Express the result as a relative age (e.g., "spec.md last modified 12 days ago").
2. **Commits since artifact (git log)**: run `git log --since="$(stat -c %Y cortex/lifecycle/{feature}/spec.md)" --oneline -- <files-mentioned-in-spec>` and report the count of commits touching files the spec names. A non-zero count suggests the spec's research assumptions may have drifted.

Surface both signals as terse lines (one each) above the continue/restart prompt. Do not block on either signal — they inform the user's choice; the offer still defaults to "continue".

### Backlog Status, index.md, Write-Back, and Discovery Bootstrap

These four sub-procedures all read or update the originating backlog item and (for new lifecycles) seed `index.md` and epic context. Read the reference for the protocol:

- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — Backlog Status Check and Backlog Write-Back (Lifecycle Start)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — Create index.md (new lifecycle only), detect epic cortex/research/spec from backlog frontmatter, and record paths for refine context injection (do not copy epic content). Read only when `phase = none` (new lifecycle) or `phase = research`.

Run them in this order: Backlog Status Check → Create index.md → Backlog Write-Back → Discovery Bootstrap.

### Auto-apply init drift refresh

Run `cortex-lifecycle-init-ensure` before advancing to Step 3. If the command exits non-zero, halt and surface its diagnostic to the user — do not proceed to phase execution. This wiring encodes the halt-on-non-zero contract structurally rather than as a prose instruction the model must interpret.

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

The Clarify, Research, and Spec phases are delegated to `/cortex-core:refine`. This section determines whether delegation is needed and, if so, how to execute it.

**If `cortex/lifecycle/{feature}/spec.md` already exists AND `cortex/lifecycle/{feature}/research.md` also exists** (from a prior `/cortex-core:refine` run, or a resumed lifecycle): announce that early-phase delegation is skipped and proceed directly to the phase execution table below (Plan phase).

**If `cortex/lifecycle/{feature}/spec.md` exists but `cortex/lifecycle/{feature}/research.md` does not**: warn that the lifecycle is in an inconsistent state — spec exists without research, and overnight requires both. Delegate to `/cortex-core:refine` normally; `/cortex-core:refine`'s Step 2 will detect the missing research.md and route to the research phase.

**If `cortex/lifecycle/{feature}/spec.md` does not exist**: read [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md) and follow it, substituting the body-resolved paths from the Reference-path propagation manifest below.

The Research and Spec phases are handled by the /cortex-core:refine delegation block above. The following phases run directly in the lifecycle context:

| Phase | Reference | Artifact Produced |
|-------|-----------|-------------------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `cortex/lifecycle/{feature}/plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source code + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `cortex/lifecycle/{feature}/review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the reference for the current phase. Do not preload other phases.

### Reference-path propagation (load-bearing)

A reference file cannot itself resolve `${CLAUDE_SKILL_DIR}` (the substitution happens only in this SKILL.md body), and a shell line inside a reference file gets no substitution pass at all — so a bare `skills/…` or `../` path written in a reference file resolves against CWD, which breaks off-repo. Resolve these targets here in the body (where `${CLAUDE_SKILL_DIR}` resolves) and carry the absolute paths into the phase. When you read the current-phase reference, substitute these body-resolved absolute paths wherever it directs you to one of these targets:

- **clarify-critic** (consulted in Clarify §3a) → `${CLAUDE_SKILL_DIR}/../refine/references/clarify-critic.md` (the critic protocol lives in the **refine** sibling skill; `${CLAUDE_SKILL_DIR}/../refine/…` resolves here, a bare `../` in the reference file does not).
- **overnight-check sidecar** (executed in Implement §1 Step A and §1a.ii) → `${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh` (lifecycle's OWN `references/` sibling). The Implement reference invokes it as `cat ${CLAUDE_SKILL_DIR}/references/_interactive_overnight_check.sh | bash -s -- "<message>" "<root>"` using this body-resolved absolute path — not a bare `skills/lifecycle/…` path, which resolves against CWD and breaks off-repo. Preserve the existing `bash -s --` message and root arguments verbatim.
- **load-requirements protocol** (consulted in Specify §1, Review §1, and Clarify §2) → `${CLAUDE_SKILL_DIR}/references/load-requirements.md` (lifecycle's OWN `references/` sibling; `${CLAUDE_SKILL_DIR}/references/…` resolves here, a bare `references/load-requirements.md` in the reference file resolves against CWD and breaks off-repo). Read this body-resolved absolute path for the shared tag-based requirements-loading protocol and follow it.
- **refine SKILL.md** (read verbatim in refine-delegation.md Step 1) → `${CLAUDE_SKILL_DIR}/../refine/SKILL.md` (the refine sibling skill; `${CLAUDE_SKILL_DIR}/../refine/…` resolves here). Substitute as `<REFINE_SKILL_MD>` in refine-delegation.md.
- **discovery-bootstrap** (read in refine-delegation.md Steps 2–3) → `${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md`. Substitute as `<DISCOVERY_BOOTSTRAP_MD>` in refine-delegation.md.
- **complexity-escalation** (run in refine-delegation.md Step 5) → `${CLAUDE_SKILL_DIR}/references/complexity-escalation.md`. Substitute as `<COMPLEXITY_ESCALATION_MD>` in refine-delegation.md.
- **post-refine-commit** (read in refine-delegation.md Step 6) → `${CLAUDE_SKILL_DIR}/references/post-refine-commit.md`. Substitute as `<POST_REFINE_COMMIT_MD>` in refine-delegation.md.
- **criticality-matrix** (§Reading lifecycle state rules cited by Detect criticality/tier in Step 2, and §Criticality Behavior Matrix cited at end of Phase Transition) → `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md`.
- **orchestrator-review** (read at Specify §3a and Plan §3a) → `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md`. Substitute this body-resolved absolute path wherever a phase reference says `read and follow references/orchestrator-review.md` — a bare relative path resolves against CWD and breaks off-repo.
- **critical-review-gate** (read at Specify §3b and Plan §3b on the skip branch) → `${CLAUDE_SKILL_DIR}/references/critical-review-gate.md`. Substitute this body-resolved absolute path wherever a phase reference says `read and follow the critical-review gate protocol` — a bare relative path resolves against CWD and breaks off-repo.

## Phase Transition

Proceed automatically — do not ask the user for confirmation at phase boundaries. Announce the transition and continue to the next phase. Between phases, include these minimum fields in the transition summary:

- **Decisions**: Key decisions made during this phase (or "None")
- **Scope delta**: Changes to scope, approach, or plan since last phase (or "None")
- **Blockers**: Active blockers, escalations, or deferred questions (or "None")
- **Next**: Next phase name and what it will do

**A phase boundary is a mechanical transition, not a synchronization point.** The boundary fires when the gate condition above is satisfied (e.g., `plan.md` exists with all tasks `[x]`), not when the user gives input — so there is nothing to "wait for" once the gate has fired. If an earlier user instruction in the session asked you to "report" or "summarize" (at the end, between phases, between tasks), that modulates text-emission cadence — emit the transition summary as plain text and continue. It is not authorization to call `AskUserQuestion`, which is a syntactically different operation (yielding control to the user) rather than a text emission. When a user genuinely wants synchronization at a boundary, they will state it explicitly ("pause after Implement and wait for me before Review"); without such an explicit request, the auto-advance fires.

`AskUserQuestion` at a phase boundary is authorized only by the Kept user pauses inventory below. The parity test `tests/test_lifecycle_kept_pauses_parity.py` keeps the inventory and the actual call sites in sync, catching file-level regressions — but it cannot catch runtime deviations. This paragraph is the runtime backstop.

### Per-phase completion rule

"Completing a phase artifact" is defined per-phase. A phase is complete (and auto-advance fires) only when its gate condition is satisfied:

- **Specify**: `spec.md` exists AND (`spec_approved` event in `events.log` OR a `phase_transition` event with `"from":"specify"` already exists as a migration sentinel for in-flight lifecycles authored before approval events existed).
- **Plan**: `plan.md` exists AND (`plan_approved` event in `events.log` OR a `phase_transition` event with `"from":"plan"` already exists as a migration sentinel).
- **Implement**: `plan.md` exists AND every task's `**Status**` line is `[x]` — no approval gate; the checkbox tally is the gate.
- **Review**: `review.md` exists AND a `review_verdict` event in `events.log` with `verdict: APPROVED` is present (auto-routes to Complete) OR the cycle-2 escalation condition is met (routes to `escalated`, which is a genuine user-blocking state).
- **Complete**: a `feature_complete` event is present in `events.log`.

Specify and Plan retain a single user-facing approval surface at §4 of their respective references (Approve / Request changes / Cancel) — the approval event is emitted on `Approve` and the lifecycle auto-advances from there. The other transitions emit `phase_transition` events without a pause.

### Kept user pauses

The following user-facing pauses are deliberate and remain in scope. Each entry names the file and the rough line anchor of the `AskUserQuestion` call site, plus a one-line rationale. The parity test at `tests/test_lifecycle_kept_pauses_parity.py` enforces that this inventory and the actual call sites stay in sync (±35-line tolerance).

- `skills/lifecycle/SKILL.md:60` — ambiguous backlog match needs operator disambiguation.
- `skills/lifecycle/references/clarify.md:57` — low-confidence clarify question batch surfaces unknowns the model cannot resolve alone.
- `skills/lifecycle/references/specify.md:36` — structured-interview gap-fill: model needs user input for unstated requirements.
- `skills/lifecycle/references/specify.md:67` — §2a cycle-2 confidence-check: user decides whether to loop back to research or proceed with gaps.
- `skills/lifecycle/references/specify.md:155` — spec approval surface (Approve / Request changes / Cancel). Substantive user decision.
- `skills/lifecycle/references/plan.md:277` — plan approval surface (Approve / Request changes / Cancel). Substantive user decision.
- `skills/lifecycle/references/implement.md:44` — conditional pause: branch selection on main (trunk vs feature-branch-with-worktree vs feature branch). Suppressed when `lifecycle.config.md::branch-mode` is set AND the working tree is clean AND no concurrent live interactive worktree exists for the feature slug.
- `skills/lifecycle/references/backlog-writeback.md:11` — backlog write-back complete-lifecycle prompt on a backlog item already marked complete.
- `skills/lifecycle/references/complete.md:73` — phase-exit pause: merge-wait pause inside the multi-step Complete phase; user re-invokes /cortex-core:lifecycle complete <slug> after merging on GitHub.
- `skills/refine/SKILL.md:166` — refine §4 complexity-value gate pick-menu — renders only when the orchestrator's recommendation diverges from full scope or confidence is low; otherwise the announcement folds into the regular approval surface.

If the user invokes `/cortex-core:lifecycle <phase>` to jump to a specific phase, honor the request but warn if prerequisite artifacts are missing (e.g., entering Plan without research.md).

For criticality override syntax and the criticality behavior matrix (which phases run, model selection, parallel-vs-single dispatch), see [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md).

## Lifecycle Directory

The `cortex/lifecycle/` directory handling is a per-project choice. Projects may:
- **Commit artifacts** as design history and institutional memory
- **Gitignore them** as ephemeral working state
- **Mix** — commit spec and plan, ignore research scratch work

There is no global enforcement. This is intentionally left to the project.

## Reference Files

Beyond the per-phase references in the table above, these references cover cross-cutting concerns. Load on demand:

- [concurrent-sessions.md](${CLAUDE_SKILL_DIR}/references/concurrent-sessions.md) — `.session` file convention, multi-feature concurrency, listing incomplete features
- [parallel-execution.md](${CLAUDE_SKILL_DIR}/references/parallel-execution.md) — running multiple features in parallel via `Agent(isolation: "worktree")`, worktree-inspection invariant
- [criticality-matrix.md](${CLAUDE_SKILL_DIR}/references/criticality-matrix.md) — criticality override event, behavior matrix across review/orchestrator/dispatch/model dimensions
- [complexity-escalation.md](${CLAUDE_SKILL_DIR}/references/complexity-escalation.md) — `cortex-complexity-escalator` gates at phase transitions
- [refine-delegation.md](${CLAUDE_SKILL_DIR}/references/refine-delegation.md) — delegation steps for the Clarify/Research/Specify phases (read when spec.md does not exist; uses body-resolved paths from the manifest above)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — index.md creation (new lifecycle only), epic-research detection from backlog frontmatter, epic-context injection during refine
- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — backlog status check and write-back to the originating backlog item
- [post-refine-commit.md](${CLAUDE_SKILL_DIR}/references/post-refine-commit.md) — canonical commit site for the refine→plan boundary
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — terminal-state workflow for operator-decided lifecycle termination
