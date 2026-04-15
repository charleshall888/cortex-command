---
name: refine
description: Prepare a backlog item for overnight execution by running it through Clarify → Research → Spec. Use when user says "/refine", "refine backlog item", "prepare for overnight", "prepare feature for execution", or "run on a backlog item before overnight". Produces lifecycle/{slug}/research.md and lifecycle/{slug}/spec.md, then sets status:refined on the backlog item.
inputs:
  - "topic: string (required) — backlog item ID (numeric), slug (kebab-case), or title (quoted phrase); or ad-hoc topic name if no backlog item exists"
outputs:
  - "lifecycle/{slug}/research.md — implementation-level research artifact"
  - "lifecycle/{slug}/spec.md — approved specification ready for overnight planning"
  - "backlog/{item}.md — updated with complexity:, criticality:, status: refined, spec: path, areas:"
preconditions:
  - "Run from project root"
  - "backlog/ directory exists"
argument-hint: "<topic>"
---

# /refine

Prepares a single backlog item for overnight execution. Runs three phases in sequence: **Clarify** (intent gate and requirements alignment), **Research** (implementation-level exploration), and **Spec** (structured requirements interview). When complete, the backlog item has `status: refined` and a linked spec, and the overnight runner can plan and execute it without further human input.

Topic: $ARGUMENTS (backlog item slug, title, or description). If empty, prompt user before proceeding.

## Step 1: Resolve Input

Determine the feature topic from the invocation argument.

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §1 (Resolve Input) and follow its protocol to identify the backlog item and input context (Context A — backlog item, or Context B — ad-hoc prompt).

Record:
- `backlog-filename-slug`: the backlog filename without `.md` (e.g., `119-create-refine-skill`) — used for `update_item.py` calls
- `item-title`: the `title:` field from the backlog item frontmatter — used to derive the lifecycle slug
- `lifecycle-slug`: derived from `item-title` using the canonical `slugify()` from `claude/common.py`: lowercase, convert underscores and slashes to spaces, strip remaining non-alphanumeric except hyphens/spaces, collapse runs of spaces/hyphens to single hyphen. Underscores become hyphens, not stripped (e.g., `session_panel` → `session-panel`, not `sessionpanel`). Leading/trailing hyphens are stripped.

Example: title `"Create /refine skill (Clarify → Research → Spec)"` → lifecycle-slug `create-refine-skill-clarify-research-spec`

These two slugs are often different. Do not conflate them.

## Step 2: Check State

Check for existing artifacts to determine the resume point:

```
if lifecycle/{lifecycle-slug}/spec.md exists AND lifecycle/{lifecycle-slug}/research.md exists:
    offer to re-run or exit (both artifacts present — spec is complete)
elif lifecycle/{lifecycle-slug}/spec.md exists AND lifecycle/{lifecycle-slug}/research.md does NOT exist:
    warn: "spec.md exists but research.md is missing — overnight requires both. Running research phase."
    resume = research phase (skip Clarify — intent was already established when spec was written)
elif lifecycle/{lifecycle-slug}/research.md exists:
    resume = spec phase (research already done — sufficiency check applies at phase entry)
    NOTE: Only lifecycle/{lifecycle-slug}/research.md satisfies this check. Any file loaded from
    a backlog item's discovery_source or research frontmatter field is background context only —
    it does NOT satisfy this check regardless of path.
else:
    resume = clarify phase (start from beginning)
```

If both artifacts exist and the user chooses to re-run, re-running will overwrite the existing spec and reset `status` to `in_progress` until the new spec is approved.

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` and follow its full protocol (§2–§7).

Key outputs from Clarify (record these for use in subsequent phases):
- Clarified intent statement
- Complexity: `simple | complex`
- Criticality: `low | medium | high | critical`
- Requirements alignment note
- Open questions for research (may be empty)

After complexity and criticality are determined, run the write-back immediately (Context A only):

```bash
update-item {backlog-filename-slug} complexity={value} criticality={value}
```

If `update-item` fails, surface the error and wait for the user to resolve before continuing.

## Step 4: Research Phase

### Sufficiency Check

If `lifecycle/{lifecycle-slug}/research.md` already exists, apply the Research Sufficiency Criteria defined in `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §6. Use the clarified intent statement and scope from Clarify as the benchmark.

**Path guard**: Only `lifecycle/{lifecycle-slug}/research.md` satisfies this check. Any file loaded from a backlog item's `discovery_source` or `research` frontmatter field is background context — it does NOT count as the lifecycle research artifact and does NOT satisfy this check, regardless of path. If `lifecycle/{lifecycle-slug}/research.md` does not exist, always run Research Execution below.

- **Sufficient**: Announce that existing research is sufficient, state which sufficiency signals were checked, and skip to Spec (Step 5).
- **Insufficient**: State which signal(s) triggered insufficiency, then proceed to run new research.

**Bypass case — loop-back from §2a confidence check**: If Research is being re-entered because `specify.md`'s §2a confidence check flagged gaps during the structured interview, skip the Sufficiency Check entirely and re-run Research from scratch. The confidence check is the authoritative signal that the existing `research.md` is insufficient for the spec being written — the Sufficiency Check would likely declare it sufficient (since it just ran) and return to Spec, defeating the loop-back. Treat `research.md` as invalidated and overwrite it.

### Research Execution

Delegate to `/research`:

```
/research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

Where `{clarified intent}` is the output from Step 3 Clarify, `{lifecycle-slug}` is the slug computed in Step 1, and `{tier}` / `{criticality}` are the values confirmed during Step 3 Clarify.

**Research scope anchor**: The clarified intent from Step 3 is the scope anchor for research — not the original ticket body. The ticket body provides context, but the clarified intent defines what research must cover.

**Alternative exploration**: When a backlog item contains implementation suggestions (e.g., a "Proposed Fix" section, "one approach might be..." language, or specific technical recommendations) AND the feature is complex-tier or high/critical criticality, research must explicitly explore at least one alternative approach alongside the ticket's suggestion. This exploration happens within the `/research` call — not as a separate competing agent. For simple-tier or low/medium-criticality features, alternative exploration is encouraged but not required. If research ultimately validates the ticket's suggested approach, that is a correct outcome — the requirement is to explore alternatives, not to reject the suggestion.

`/research` writes its output to `lifecycle/{lifecycle-slug}/research.md`.

After `/research` returns, verify that `lifecycle/{lifecycle-slug}/research.md` exists and is non-empty. If the file is absent or empty, surface the error to the user and halt — do not proceed to the Research Exit Gate.

After writing `research.md`, update `lifecycle/{lifecycle-slug}/index.md`:
- If `"research"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"research"` to the artifacts inline array
- Add wikilink: `- Research: [[{lifecycle-slug}/research|research.md]]`
  (where `{lifecycle-slug}` is the feature directory name, e.g. `add-lifecycle-feature-indexmd-for-obsidian-navigation`)
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

### Research Exit Gate

Before transitioning to Step 5 (Spec), scan `research.md`'s `## Open Questions` section. An item is **resolved** if it contains an inline answer. An item is **deferred** if it is explicitly marked deferred with written rationale (e.g., "Deferred: will be resolved in Spec by asking the user"). A bare unannotated bullet is neither resolved nor deferred.

If any unresolved, non-deferred items exist: present them to the user and resolve or explicitly defer each one before proceeding to Spec. Do not transition to Spec with open, unaddressed questions.

If the `## Open Questions` section is absent from `research.md`, the gate passes.

## Step 5: Spec Phase

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow its full protocol (§1–§4) with these adaptations:

- **§1 (Load Context)**: Requirements context was loaded during Clarify (Step 3) and research.md was produced in Step 4. Re-read `lifecycle/{lifecycle-slug}/research.md` but skip redundant requirements loading.
- **§2a loop-back**: If the Research Confidence Check triggers a loop-back, re-enter Step 4 (Research Phase) with the Sufficiency Check bypass described there.
- **§3b tier detection**: Read `lifecycle/{lifecycle-slug}/events.log` for the most recent `lifecycle_start` or `complexity_override` event to determine the active tier. The caller (`/lifecycle`) may escalate the tier between Research and Spec — do not rely solely on the Clarify output.
- **§4 (User Approval) — Complexity/value gate**: After the spec is written, before showing the approval surface, check whether complexity is proportional to the value case. Fire this check if the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem requiring ongoing per-feature upkeep. This check fires regardless of whether critical-review ran. If the check fires, do NOT proceed to the approval question in the same turn — instead present: (1) a one-sentence value case for the primary outcome, (2) a one-sentence complexity cost, and (3) 2–3 concrete alternatives. Where they naturally exist for this ticket, offer: "drop entirely" (value is achievable another way or too weak), "bugs-only" (strip the feature, keep only latent fix work the spec uncovered), "minimum viable" (identify one concrete scope cut). If an alternative doesn't naturally apply, say so. Wait for the user's response before showing the approval surface.
- **§5 (Transition)**: Skip — /refine does not log phase transitions. The caller handles transition events if applicable.

Do NOT set `status: refined` before user approval.

After user approval (specify.md §4), update `lifecycle/{lifecycle-slug}/index.md`:
- If `"spec"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"spec"` to the artifacts inline array
- Add wikilink: `- Spec: [[{lifecycle-slug}/spec|spec.md]]`
  (where `{lifecycle-slug}` is the feature directory name, e.g. `add-lifecycle-feature-indexmd-for-obsidian-navigation`)
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

### Write-Back on Approval (Context A only)

After user approves the spec:

**Infer areas**: Identify which subsystem the feature primarily modifies. Canonical area names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`. Use the primary subsystem only — the one where most files change. If the feature spans 4+ subsystems with no clear primary, use `areas=[]`.

```bash
update-item {backlog-filename-slug} status=refined spec=lifecycle/{lifecycle-slug}/spec.md
```

```bash
update-item {backlog-filename-slug} "areas=[area1,area2]"
```

For empty areas: `update-item {backlog-filename-slug} "areas=[]"`. The quoted string preserves the list format through shell argument parsing.

Keep these as two separate sequential `update-item` calls — do not combine them into one invocation to avoid argument-parsing ambiguity with list values.

If either `update-item` call fails, surface the error and wait for the user to resolve. Do not proceed silently.

## Step 6: Completion

Announce that `/refine` is complete. Summarize:
- Backlog item: `{backlog-filename-slug}`
- Lifecycle directory: `lifecycle/{lifecycle-slug}/`
- Artifacts produced: research.md, spec.md
- Backlog fields written: `complexity`, `criticality`, `status: refined`, `spec`, `areas`

The feature is now ready for overnight execution. The overnight runner will auto-generate a plan from the spec and execute it without further input.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should generate a plan" | /refine stops at spec. Overnight auto-generates plans from specs. |
| "I should set status:refined as soon as research is done" | status:refined is set only after the user approves the spec (Step 5). |
| "I should use the lifecycle-slug as the update_item.py argument" | update_item.py takes the backlog-filename-slug (e.g., 119-create-refine-skill), not the lifecycle-slug. |
| "If update_item.py fails I can skip it and continue" | Write-back failures must be surfaced and resolved before proceeding. Silent skips corrupt backlog state. |
| "I should do a deep requirements interview during Clarify" | Clarify asks ≤5 targeted questions. The deep interview is Spec's job (Step 5). |
