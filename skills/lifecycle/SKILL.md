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

When `$ARGUMENTS` is non-empty, invoke `bin/cortex-resolve-backlog-item` once to find the matching backlog file. This single call replaces the previous pattern of independently re-scanning `cortex/backlog/[0-9]*-*{feature}*.md` in each of the four Step 2 sub-procedures (Backlog Status Check, Create index.md, Backlog Write-Back, Discovery Bootstrap). The four sub-procedures consume Step 1's resolver output — they do not re-scan the backlog directory.

```bash
bin/cortex-resolve-backlog-item {feature}
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

**Detect criticality**: After determining the phase, read criticality via `cortex-lifecycle-state --feature {feature} --field criticality` (emits JSON; defaults to `medium` when the key is absent or events.log is missing). Report the detected criticality alongside the detected phase when resuming.

**Detect complexity tier**: After determining the phase, read the active complexity tier via `cortex-lifecycle-state --feature {feature} --field tier` (emits JSON applying the canonical rule that `lifecycle_start.tier` is superseded by the most recent `complexity_override.to`; defaults to `simple` when the key is absent). Report the detected tier alongside the detected phase when resuming.

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

- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — Backlog Status Check, Create index.md (new lifecycle only), and Backlog Write-Back (Lifecycle Start)
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — Detect epic cortex/research/spec from backlog frontmatter and record paths for refine context injection (do not copy epic content)

Run them in this order: Backlog Status Check → Create index.md → Backlog Write-Back → Discovery Bootstrap.

## Step 3: Execute Current Phase

### /cortex-core:refine Delegation

The Clarify, Research, and Spec phases are delegated to `/cortex-core:refine`. This section determines whether delegation is needed and, if so, how to execute it.

**If `cortex/lifecycle/{feature}/spec.md` already exists AND `cortex/lifecycle/{feature}/research.md` also exists** (from a prior `/cortex-core:refine` run, or a resumed lifecycle): announce that early-phase delegation is skipped and proceed directly to the phase execution table below (Plan phase).

**If `cortex/lifecycle/{feature}/spec.md` exists but `cortex/lifecycle/{feature}/research.md` does not**: warn that the lifecycle is in an inconsistent state — spec exists without research, and overnight requires both. Delegate to `/cortex-core:refine` normally; `/cortex-core:refine`'s Step 2 will detect the missing research.md and route to the research phase.

**If `cortex/lifecycle/{feature}/spec.md` does not exist**: delegate to `/cortex-core:refine` as follows:

1. **Read `skills/refine/SKILL.md` verbatim.** Do not paraphrase or reconstruct `/cortex-core:refine`'s protocol from training context. The file read is mandatory — this ensures lifecycle stays in sync as `/cortex-core:refine` evolves.

2. **Epic context injection** (applies when `epic_research_path` was recorded in Discovery Bootstrap): follow the Epic Context Injection protocol in [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md).

3. **Determine the starting point for `/cortex-core:refine`:** follow the Refine Starting-Point Rules in [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md).

4. **Event logging during delegation**: lifecycle owns `cortex/lifecycle/{feature}/events.log`. Log these events as `/cortex-core:refine` completes each phase:

   - After the full Clarify phase completes (including §3a critic review and any Q&A) — **before Research begins** — log `lifecycle_start` (tier and criticality come from the post-critic, post-Q&A values in context):
     ```json
     {"ts": "<ISO 8601>", "event": "lifecycle_start", "feature": "<name>", "tier": "simple|complex", "criticality": "<level>"}
     ```
   - After each phase completes, log a `phase_transition` event:
     ```json
     {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "clarify", "to": "research"}
     {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "research", "to": "specify"}
     {"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "specify", "to": "plan"}
     ```

5. **Complexity escalation gates**: run the Research → Specify and Specify → Plan complexity-escalator gates per [complexity-escalation.md](${CLAUDE_SKILL_DIR}/references/complexity-escalation.md).

The Research and Spec phases are handled by the /cortex-core:refine delegation block above. The following phases run directly in the lifecycle context:

| Phase | Reference | Artifact Produced |
|-------|-----------|-------------------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `cortex/lifecycle/{feature}/plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source code + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `cortex/lifecycle/{feature}/review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the reference for the current phase. Do not preload other phases.

## Phase Transition

Proceed automatically — do not ask the user for confirmation at phase boundaries. Announce the transition and continue to the next phase. Between phases, include these minimum fields in the transition summary:

- **Decisions**: Key decisions made during this phase (or "None")
- **Scope delta**: Changes to scope, approach, or plan since last phase (or "None")
- **Blockers**: Active blockers, escalations, or deferred questions (or "None")
- **Next**: Next phase name and what it will do

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
- `skills/lifecycle/references/implement.md:22` — branch selection on main: trunk vs autonomous worktree vs feature branch.
- `skills/lifecycle/references/backlog-writeback.md:11` — backlog write-back complete-lifecycle prompt on a backlog item already marked complete.

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
- [discovery-bootstrap.md](${CLAUDE_SKILL_DIR}/references/discovery-bootstrap.md) — epic-research detection from backlog frontmatter, epic-context injection during refine
- [backlog-writeback.md](${CLAUDE_SKILL_DIR}/references/backlog-writeback.md) — backlog status check, index.md creation, and write-back to the originating backlog item
- [wontfix.md](${CLAUDE_SKILL_DIR}/references/wontfix.md) — three-step terminal-state workflow (`git mv` to `archive/` → emit `feature_wontfix` event → `cortex-update-item status=wontfix`) for operator-decided lifecycle termination
