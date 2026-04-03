---
name: lifecycle
description: Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Use when user says "/lifecycle", "start a lifecycle", "lifecycle research/specify/plan/implement/review/complete", or wants to build a non-trivial feature with structured phases. Also triggers on "start a feature lifecycle" or "lifecycle <feature-name>". Required before editing any file in ~/.claude/skills/ or ~/.claude/hooks/ — skip only if the user explicitly says to.
argument-hint: "<feature> [phase]"
inputs:
  - "feature: string (required) — kebab-case slug of the feature to develop or resume"
  - "phase: string (optional) — explicit phase to enter: research|specify|plan|implement|review|complete"
outputs:
  - "lifecycle/{{feature}}/ — directory containing phase artifacts: research.md, spec.md, plan.md, review.md, events.log"
preconditions:
  - "Run from project root"
  - "lifecycle/ directory must exist or will be created"
precondition_checks:
  - "test -d lifecycle"
---

# Feature Lifecycle

A file-based state machine that survives context loss. Enforces research-before-code, prose-before-implementation, and spec-before-build discipline.

## Invocation

- `/lifecycle {{feature}}` — start new or resume existing feature
- `/lifecycle {{phase}}` — explicitly enter a phase for the active feature
- `/lifecycle resume {{feature}}` — resume a specific feature if multiple exist

## Project Configuration

If `lifecycle.config.md` exists at the project root, read it first. It contains project-specific overrides for complexity defaults, test commands, phase skipping, and review criteria.

## Step 1: Identify the Feature

Feature/phase from invocation: $ARGUMENTS. Parse: first word = feature name, second word (if present) = explicit phase override. If $ARGUMENTS is empty, fall through to the existing behavior (scan for incomplete lifecycle directories).

Determine the feature name from the invocation. Use lowercase-kebab-case for directory naming. When the lifecycle is linked to a backlog item, derive the directory name by slugifying the backlog item's full title: lowercase, strip non-alphanumeric characters except hyphens and spaces, collapse runs of spaces/hyphens to a single hyphen (e.g., backlog title "Build bash runner and orchestrator round loop" → `lifecycle/build-bash-runner-and-orchestrator-round-loop/`). This ensures the overnight selection module can discover the lifecycle artifacts automatically.

## Step 2: Check for Existing State

Scan for `lifecycle/{feature}/` at the project root. Determine the current phase by checking artifacts in reverse order:

```
if no lifecycle/{feature}/ directory exists:
    phase = none (start from beginning)
elif events.log contains a feature_complete event:
    phase = complete (feature is done)
elif review.md exists with APPROVED verdict:
    phase = complete (feature is done)
elif review.md exists with CHANGES_REQUESTED:
    phase = implement (re-entry for rework)
elif review.md exists with REJECTED:
    phase = escalated (present reviewer analysis, ask user for direction)
elif plan.md exists with all [x] checked:
    phase = review
elif plan.md exists:
    phase = implement (check [x] count for progress)
elif spec.md exists:
    phase = plan
elif research.md exists:
    phase = specify
else:
    phase = research
```

**Detect criticality**: After determining the phase, read criticality from `events.log`. Scan for the most recent event with a `criticality` field (either `lifecycle_start` or `criticality_override`). If no criticality field is found (pre-existing lifecycle), default to `medium`. Report the detected criticality alongside the detected phase when resuming.

**Detect complexity tier**: After determining the phase, read the active complexity tier from `events.log` in two steps: (1) read `tier` from the `lifecycle_start` event as the baseline; (2) scan for the most recent `complexity_override` event — if one exists, its `"to"` field supersedes the baseline tier. The result of step (2), if present, is the active tier for all subsequent phases. If no `lifecycle_start` event exists (pre-existing lifecycle), default to `simple`. Report the detected tier alongside the detected phase when resuming.

**Register session**: After identifying the feature (whether new or existing), register this session by writing the session file:

```
echo $LIFECYCLE_SESSION_ID > lifecycle/{feature}/.session
```

If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase.

### Backlog Status Check

Before creating any artifacts or performing write-back, check whether the originating backlog item has already been marked complete outside the lifecycle:

1. **Scan** for `backlog/[0-9]*-*{feature}*.md` — a matching backlog file for this feature.
2. **If no match is found**, or the matched file's YAML frontmatter `status` field is not `complete`: skip this section silently and fall through to "Create index.md" and subsequent sections as normal.
3. **If a match is found and `status: complete`**: present a prompt using `AskUserQuestion` with two options:
   - **"Close lifecycle"**
   - **"Continue from current phase"**

   If `AskUserQuestion` is unavailable (e.g., overnight batch context where no interactive prompt is possible), default to **Continue** — never auto-close.

4. **On "Continue"** (or if the check was skipped): fall through to "Create index.md" and "Backlog Write-Back" sections as normal. No further action from this section.

5. **On "Close lifecycle"**: the behavior depends on the current phase:

   - **If `phase != none`** (a `lifecycle/{feature}/` directory exists):
     1. Append the following NDJSON event to `lifecycle/{feature}/events.log` (one JSON object per line):
        ```json
        {"ts": "<ISO 8601>", "event": "feature_complete", "feature": "<name>"}
        ```
        Intentionally omit `tasks_total` and `rework_cycles` — `plan.md` may not exist on this path (the lifecycle may have been completed out-of-band before a plan was written). Do NOT add those fields with value 0.
     2. Run:
        ```bash
        update-item <slug> status=complete lifecycle_phase=complete session_id=null
        ```
        Where `<slug>` is the backlog filename stem (e.g., `1043-add-backlog-status-detection-to-lifecycle-resume`).
     3. **Exit immediately.** Do not proceed to "Create index.md", "Backlog Write-Back", "Discovery Bootstrap", or any subsequent Step 2 sections or later steps. The lifecycle is closed.

   - **If `phase = none`** (no `lifecycle/{feature}/` directory exists):
     1. **Exit immediately** without creating any lifecycle artifacts (no directory, no events.log, no index.md) and without calling `update-item`. The backlog item is already complete and no lifecycle artifacts need to exist.

### Create index.md (New Lifecycle Only)

When `phase = none` (no prior `lifecycle/{slug}/` directory exists), create `lifecycle/{slug}/index.md` as follows:

**Guard**: If `lifecycle/{slug}/index.md` already exists, skip this entire block — do not overwrite.

Scan `backlog/[0-9]*-*{slug}*.md` for a matching backlog item. If a match is found, read its frontmatter to populate the fields below. If no match is found, set null fields.

Write `lifecycle/{slug}/index.md` with all seven required frontmatter fields:

```yaml
---
feature: {lifecycle-slug}
parent_backlog_uuid: {uuid from backlog item, or null}
parent_backlog_id: {numeric ID prefix from backlog filename, or null}
artifacts: []
tags: {inline array from backlog item tags field, or []}
created: {today's date in ISO 8601, e.g. 2026-03-23}
updated: {today's date in ISO 8601}
---
```

If a matching backlog item was found, append the wikilink body:

```
# [[{NNN}-{backlog-slug}|{backlog title}]]

Feature lifecycle for [[{NNN}-{backlog-slug}]].
```

Where `{NNN}` is the zero-padded numeric prefix exactly as it appears in the backlog filename (e.g. `030`, `1048`), and `{backlog-slug}` is the filename without its `.md` extension and numeric prefix (e.g. `cf-tunnel-fallback-polish` from `030-cf-tunnel-fallback-polish.md`). Use the full filename stem (numeric prefix + slug) in the wikilink, e.g. `[[1048-lifecycle-feature-index|...]]`.

If no matching backlog item was found, omit the heading and body line entirely.

`artifacts: []` must always use inline YAML array notation — never block notation.

### Backlog Write-Back (Lifecycle Start)

After registering the session, attempt to write the lifecycle start back to the originating backlog item. Scan for a matching backlog file:

```
scan backlog/[0-9]*-*{feature}*.md for a matching file
```

If a match is found, run:

```bash
update-item <path> status=in_progress session_id=$LIFECYCLE_SESSION_ID lifecycle_phase=research
```

Where `<path>` is the slug-or-uuid of the matched backlog item (e.g., `045-my-feature`).

Additionally, when `phase = none` (new lifecycle only), also run the following write-back to record the lifecycle slug — this is separate from and in addition to the status write-back above:

```bash
update-item <path> lifecycle_slug={lifecycle-slug}
```

This `lifecycle_slug` write-back runs only when `phase = none`. The status write-back runs on all phases when a match is found.

If no backlog item is found, skip this step silently -- lifecycles can exist independently of the backlog.

### Discovery Bootstrap

When `phase = research` (no lifecycle directory exists yet), check whether discovery already produced epic-level artifacts for this feature:

```
scan backlog/[0-9]*-*{feature}*.md for a matching file
if match found:
    read frontmatter of first match
    if discovery_source field exists:
        epic_research_path = discovery_source field value
    elif research field exists:
        epic_research_path = research field value
    else:
        (no epic context — epic_research_path is unset)
    if epic_research_path is set:
        if epic_research_path file exists on disk:
            record epic_research_path
            if spec field also exists and spec file path exists on disk:
                record epic_spec_path = spec field value
        else:
            log warning: "epic research file {epic_research_path} not found on disk — no epic context available"
            epic_research_path = unset
```

**Do not copy epic content into lifecycle files.** Epic research covers all tickets in the epic — copying it wholesale bleeds cross-ticket context into this ticket's research and spec. Record the paths as reference context only; `/refine` will produce ticket-specific research.md and spec.md that reference the epic artifacts without reproducing them.

If `epic_research_path` was found, announce: "Found epic research at `{epic_research_path}` — will use as background reference during research. Running ticket-specific research and spec phases."

## Step 3: Execute Current Phase

### Epic Context Event Logging

If `epic_research_path` was found in Discovery Bootstrap above, log a `discovery_reference` event before delegating to `/refine`. This records that the lifecycle is scoped from a larger epic, without implying that any phases were skipped:

```json
{"ts": "<ISO 8601>", "event": "discovery_reference", "feature": "<name>", "epic_research": "<epic_research_path>", "epic_spec": "<epic_spec_path or null>"}
```

If no epic context was found, skip this section entirely.

### /refine Delegation

The Clarify, Research, and Spec phases are delegated to `/refine`. This section determines whether delegation is needed and, if so, how to execute it.

**If `lifecycle/{feature}/spec.md` already exists AND `lifecycle/{feature}/research.md` also exists** (from a prior `/refine` run, or a resumed lifecycle): announce that early-phase delegation is skipped and proceed directly to the phase execution table below (Plan phase).

**If `lifecycle/{feature}/spec.md` exists but `lifecycle/{feature}/research.md` does not**: warn that the lifecycle is in an inconsistent state — spec exists without research, and overnight requires both. Delegate to `/refine` normally; `/refine`'s Step 2 will detect the missing research.md and route to the research phase.

**If `lifecycle/{feature}/spec.md` does not exist**: delegate to `/refine` as follows:

1. **Read `skills/refine/SKILL.md` verbatim.** Do not paraphrase or reconstruct `/refine`'s protocol from training context. The file read is mandatory — this ensures lifecycle stays in sync as `/refine` evolves.

2. **Epic context injection** (applies when `epic_research_path` was recorded in Discovery Bootstrap): before starting Clarify, read the epic research file at `{epic_research_path}` (and `{epic_spec_path}` if present) as background context. This explains the broader epic scope and which concerns belong to adjacent tickets. Instruct `/refine` to:
   - Scope research and spec to THIS ticket's specific requirements only — do not reproduce content that belongs to other tickets in the epic
   - Include a `## Epic Reference` section near the top of `research.md` with a link to the epic research path and a one-sentence note on how the epic relates to this ticket
   - In `spec.md`, add a brief preamble note referencing the epic research path for broader context

3. **Determine the starting point for `/refine`:** follow `/refine`'s Step 2 (Check State) normally — it checks `lifecycle/{lifecycle-slug}/research.md` and `lifecycle/{lifecycle-slug}/spec.md` specifically. **Any file loaded from the backlog item's `discovery_source` or `research` frontmatter field does NOT satisfy this check** — it is background context only, regardless of path. `/refine` must still run its full Research phase to produce `lifecycle/{slug}/research.md`, even when epic research exists.

4. **Event logging during delegation**: lifecycle owns `lifecycle/{feature}/events.log`. Log these events as `/refine` completes each phase:

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

5. **Research → Specify complexity escalation check**: Immediately after research completes and **before** entering the Specify phase, check whether to escalate the complexity tier:

   a. Read the active tier from `lifecycle/{feature}/events.log` using the two-step detection in Step 2. If the active tier is already `complex`, skip this check entirely and proceed to Specify.
   b. Open `lifecycle/{feature}/research.md` and locate the `## Open Questions` section. Count the number of bullet items (`-` or `*` prefixed lines) directly under that heading. If the section is absent, the count is 0.
   c. If the count is ≥ 2, automatically escalate to Complex tier — append the following event to `lifecycle/{feature}/events.log`, announce the escalation briefly ("Escalating to Complex tier — research surfaced N open questions"), then proceed to Specify at Complex tier:
      ```json
      {"ts": "<ISO 8601>", "event": "complexity_override", "feature": "<name>", "from": "simple", "to": "complex"}
      ```

6. **Critical-review gate**: after the spec draft is written to `lifecycle/{feature}/spec.md` — and **before** presenting the spec to the user for approval — read the active tier from `lifecycle/{feature}/events.log` (applying any `complexity_override` event per Step 2).
   - If active tier = `complex`: invoke the `critical-review` skill on `lifecycle/{feature}/spec.md`. Incorporate or present findings alongside the spec, then present spec + critical-review output for user approval together.
   - If active tier = `simple`: skip the critical-review gate and present the spec for user approval directly.

7. **Specify → Plan complexity escalation check**: after the spec is approved by the user and **before** logging the `phase_transition` event from "specify" to "plan", check whether to auto-escalate the complexity tier:

   - Read the active tier from `lifecycle/{feature}/events.log` using the two-step detection in Step 2. If the active tier is already `complex`, skip this check entirely.
   - Otherwise, scan `lifecycle/{feature}/spec.md` for a `## Open Decisions` section. Count the number of bullet items (`-` or `*` lines) directly under that heading. If the section is absent or the count is fewer than 3, skip the check.
   - If the count is ≥ 3, automatically escalate to Complex tier — append the following event to `lifecycle/{feature}/events.log`, announce the escalation briefly ("Escalating to Complex tier — spec contains N open decisions"), then proceed to Plan at Complex tier:
     ```json
     {"ts": "<ISO 8601>", "event": "complexity_override", "feature": "<name>", "from": "simple", "to": "complex"}
     ```

The Research and Spec phases are handled by the /refine delegation block above. The following phases run directly in the lifecycle context:

| Phase | Reference | Artifact Produced |
|-------|-----------|-------------------|
| Plan | [plan.md](${CLAUDE_SKILL_DIR}/references/plan.md) | `lifecycle/{feature}/plan.md` |
| Implement | [implement.md](${CLAUDE_SKILL_DIR}/references/implement.md) | Source code + commits |
| Review | [review.md](${CLAUDE_SKILL_DIR}/references/review.md) | `lifecycle/{feature}/review.md` |
| Complete | [complete.md](${CLAUDE_SKILL_DIR}/references/complete.md) | Git workflow + summary |

Read **only** the reference for the current phase. Do not preload other phases.

## Phase Transition

After completing a phase artifact, announce the transition and proceed to the next phase automatically. Between phases, briefly summarize what was accomplished and what comes next.

If the user invokes `/lifecycle <phase>` to jump to a specific phase, honor the request but warn if prerequisite artifacts are missing (e.g., entering Plan without research.md).

## Criticality Override

The user can change criticality at any time by requesting it explicitly. When overriding, append a `criticality_override` event:

```json
{"ts": "<ISO 8601>", "event": "criticality_override", "feature": "<name>", "from": "<old>", "to": "<new>"}
```

The user's criticality setting is always final. No automated process (including future orchestrator additions) may override the user's choice.

## Complexity Override

Complexity tier may be escalated automatically at specific phase transitions if heuristics detect additional complexity. When the user accepts an escalation prompt, a `complexity_override` event is appended to `lifecycle/{feature}/events.log`:

```json
{"ts": "<ISO 8601>", "event": "complexity_override", "feature": "<name>", "from": "simple", "to": "complex"}
```

Escalation can occur at two points:

1. **Research → Specify transition**: If `lifecycle/{feature}/research.md` contains a `## Open Questions` section with ≥2 bullet items, automatically escalate to Complex tier and announce briefly.
2. **Specify → Plan transition**: If `lifecycle/{feature}/spec.md` contains a `## Open Decisions` section with ≥3 bullet items, automatically escalate to Complex tier and announce briefly.

In both cases:
- Escalation is automatic — no user confirmation required.
- Append the `complexity_override` event and proceed to the next phase at Complex tier.
- If the feature is already at Complex tier: skip the check entirely.

The `complexity_override` event changes the active complexity tier for all subsequent phases. State detection (Step 2, "Detect complexity tier") will recognize this event and apply its `"to"` field as the active tier for Plan, Implement, Review, and Complete phases.

## Criticality Behavior Matrix

| Criticality | Review phase (023) | Orchestrator review (024) | Scaled behaviors (025) | Model selection |
|-------------|-------------------|--------------------------|----------------------|----------------|
| low | Tier-based (skip for simple) | Skipped for simple; active for complex | Single research, single plan | Haiku explore, Sonnet build/review |
| medium | Tier-based (skip for simple) | Active at phase boundaries | Single research, single plan | Haiku explore, Sonnet build/review |
| high | Forced regardless of tier | Active at all phase boundaries | Single research, single plan | Sonnet explore, Opus build/review |
| critical | Forced regardless of tier | Active at all phase boundaries | Parallel research, competing plans | Sonnet explore/research/plan, Opus build/review |

All three tickets (023, 024, 025) are implemented. The Review phase column reflects tier-based skip logic, the Orchestrator review column reflects boundary-checking behavior, and the Scaled behaviors column reflects criticality-conditional dispatch in the research and plan reference files. The Model selection column reflects which models are used at each criticality level.

## Lifecycle Directory

The `lifecycle/` directory handling is a per-project choice. Projects may:
- **Commit artifacts** as design history and institutional memory
- **Gitignore them** as ephemeral working state
- **Mix** — commit spec and plan, ignore research scratch work

There is no global enforcement. This is intentionally left to the project.

## Concurrent Sessions

Multiple sessions can work on different features simultaneously. Each session is associated with one feature at a time via a `.session` file.

**Session-feature association**: When a session starts or resumes a feature, it writes its session ID to `lifecycle/{feature}/.session`:

```
echo $LIFECYCLE_SESSION_ID > lifecycle/{feature}/.session
```

`LIFECYCLE_SESSION_ID` is an environment variable set automatically by the SessionStart hook at the beginning of each session.

**`.session` files are ephemeral**: They are gitignored, cleaned up by the SessionEnd hook when the session exits, and overwritten when another session resumes the same feature. Do not commit them.

**Listing incomplete features**: If multiple incomplete `lifecycle/*/` directories exist and the user has not specified which to work on, list them and ask which to resume. Completed features (those with a `feature_complete` event in `events.log`, or `review.md` containing an APPROVED verdict) are ignored.

## Parallel Execution

When the user requests running multiple lifecycle features in parallel (e.g., "/lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` for each feature:

```
Agent(
  isolation: "worktree",
  prompt: "/lifecycle {feature}"
)
```

**Do not use `git worktree add` manually in sandboxed sessions.** This fails for two reasons:

1. **`.claude/` is sandbox-restricted at the Seatbelt OS level**: Any worktree target inside `.claude/` (e.g., `.claude/worktrees/{feature}`) will fail because git tries to write tracked `.claude/**` files into the new worktree. The restriction is broader than what `denyWithinAllow` explicitly shows.
2. **Orphaned branches**: `git worktree add` creates the branch *before* checking out files. A failed checkout leaves an orphaned branch that blocks the next attempt with "branch already exists". Clean up with `git branch -d <name>` before retrying.

The `Agent` tool's `isolation: "worktree"` handles all of this correctly — it creates the worktree outside the sandbox write path and auto-cleans if no changes are made. If manual worktree creation is ever needed, use `$TMPDIR` (not `.claude/`) as the target.

### Worktree Inspection Invariant

**Prohibited**: `cd <worktree-path> && git <cmd>` — this triggers a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") that is not bypassable by allow rules or sandbox config. It also fails general compound-command allow-rule matching.

**Correct pattern**: inspect worktree branches from the main repo CWD using remote-ref syntax:

```
git log HEAD..worktree/{task-name} --oneline
```

The task name is the `name` parameter passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}` (from `cortex-worktree-create.sh` line 30).

Hook `updatedPermissions` session injection: ruled out — `updatedPermissions` is exclusive to `PermissionRequest` hooks; `WorktreeCreate` command hooks use plain-text stdout only and cannot inject session allow rules. Fix is behavioral only: use `git log HEAD..worktree/{name}` from main CWD (never `cd <path> && git`).
