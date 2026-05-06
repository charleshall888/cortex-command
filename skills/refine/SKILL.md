---
name: refine
description: Prepare a backlog item for overnight execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "prepare for overnight", "prepare feature for execution", or "run on a backlog item before overnight". Produces lifecycle/{slug}/research.md and lifecycle/{slug}/spec.md, then sets status:refined on the backlog item.
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

# /cortex-core:refine

Prepares a single backlog item for overnight execution. Runs three phases in sequence: **Clarify** (intent gate and requirements alignment), **Research** (implementation-level exploration), and **Spec** (structured requirements interview). When complete, the backlog item has `status: refined` and a linked spec, and the overnight runner can plan and execute it without further human input.

Topic: $ARGUMENTS (backlog item slug, title, or description). If empty, prompt user before proceeding.

## Step 1: Resolve Input

Determine the feature topic from the invocation argument.

Run:

```bash
cortex-resolve-backlog-item <input>
```

Where `<input>` is the `$ARGUMENTS` value (backlog item ID, slug, or title phrase). If `$ARGUMENTS` is empty, prompt the user for input before invoking the script.

Branch on the exit code:

- **Exit 0** — unambiguous match. Parse stdout JSON; the object contains exactly four fields: `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`. Use these directly in Step 2 and subsequent phases. Do not re-derive slugs from scratch.
- **Exit 2** — ambiguous match. Read the `<filename>\t<title>` candidate lines from stderr. Present them to the user and ask them to select one. Re-invoke `cortex-resolve-backlog-item` with the chosen filename slug, or treat the user's selection directly as the resolved item.
- **Exit 3** — no match. Switch to Context B (ad-hoc topic) per `references/clarify.md` §1 and treat the input as the topic name.
- **Exit 64** — usage error (e.g., empty or malformed input). Halt and surface the stderr usage diagnostic to the user. Do NOT fall through to disambiguation.
- **Exit 70** — internal software error (malformed frontmatter, missing backlog directory, or other IO failure). Halt and surface the stderr diagnostic to the user. Do NOT fall through to disambiguation.

## Step 2: Check State

Check for existing artifacts to determine the resume point:

```
if lifecycle/{lifecycle-slug}/spec.md exists AND lifecycle/{lifecycle-slug}/research.md exists:
    offer to re-run or exit (both artifacts present — spec is complete)
elif lifecycle/{lifecycle-slug}/spec.md exists AND lifecycle/{lifecycle-slug}/research.md does NOT exist:
    warn: "spec.md exists but research.md is missing — overnight requires both. Running research phase."
    resume = research phase (skip Clarify — intent was already established when spec was written)
elif lifecycle/{lifecycle-slug}/research.md exists at that exact path:
    resume = spec phase (research already done — sufficiency check applies at phase entry)
    # Files referenced by a backlog item's discovery_source or research frontmatter field are
    # background context only. They are not a substitute for lifecycle/{lifecycle-slug}/research.md,
    # regardless of their path.
else:
    resume = clarify phase (start from beginning)
```

If both artifacts exist and the user chooses to re-run, re-running will overwrite the existing spec and reset `status` to `in_progress` until the new spec is approved.

## Step 3: Clarify Phase

Read `references/clarify.md` and follow its full protocol (§2–§7).

Key outputs from Clarify (record these for use in subsequent phases):
- Clarified intent statement
- Complexity: `simple | complex`
- Criticality: `low | medium | high | critical`
- Requirements alignment note
- Open questions for research (may be empty)

After complexity and criticality are determined, run the write-back immediately (Context A only):

```bash
cortex-update-item {backlog-filename-slug} complexity={value} criticality={value}
```

If `cortex-update-item` fails, surface the error and wait for the user to resolve before continuing.

## Step 4: Research Phase

### Sufficiency Check

If `lifecycle/{lifecycle-slug}/research.md` already exists, apply the Research Sufficiency Criteria defined in `references/clarify.md` §6. Use the clarified intent statement and scope from Clarify as the benchmark.

**Path guard** (explicit rules for what satisfies the Sufficiency Check):

1. The check passes only for a file at the exact path `lifecycle/{lifecycle-slug}/research.md`.
2. Files referenced by a backlog item's `discovery_source` or `research` frontmatter field are background context for the Clarify phase — they are not a substitute for the lifecycle research artifact, regardless of their path.
3. When `lifecycle/{lifecycle-slug}/research.md` does not exist at that exact path, run Research Execution below.

- **Sufficient**: Announce that existing research is sufficient, state which sufficiency signals were checked, and skip to Spec (Step 5).
- **Insufficient**: State which signal(s) triggered insufficiency, then proceed to run new research.

**Bypass case — loop-back from §2a confidence check**: If Research is being re-entered because `specify.md`'s §2a confidence check flagged gaps during the structured interview, skip the Sufficiency Check entirely and re-run Research from scratch. The confidence check is the authoritative signal that the existing `research.md` is insufficient for the spec being written — the Sufficiency Check would likely declare it sufficient (since it just ran) and return to Spec, defeating the loop-back. Treat `research.md` as invalidated and overwrite it.

### Research Execution

Delegate to `/cortex-core:research`:

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

Where `{clarified intent}` is the output from Step 3 Clarify, `{lifecycle-slug}` is the slug computed in Step 1, and `{tier}` / `{criticality}` are the values confirmed during Step 3 Clarify.

**Research scope anchor**: The clarified intent from Step 3 is the scope anchor for research — not the original ticket body. The ticket body provides context, but the clarified intent defines what research must cover.

**Alternative exploration**: When a backlog item contains implementation suggestions (e.g., a "Proposed Fix" section, "one approach might be..." language, or specific technical recommendations) AND the feature is complex-tier or high/critical criticality, research must explicitly explore at least one alternative approach alongside the ticket's suggestion. This exploration happens within the `/cortex-core:research` call — not as a separate competing agent. For simple-tier or low/medium-criticality features, alternative exploration is encouraged but not required. If research ultimately validates the ticket's suggested approach, that is a correct outcome — the requirement is to explore alternatives, not to reject the suggestion.

`/cortex-core:research` writes its output to `lifecycle/{lifecycle-slug}/research.md`.

After `/cortex-core:research` returns, verify that `lifecycle/{lifecycle-slug}/research.md` exists and is non-empty. If the file is absent or empty, surface the error to the user and halt — do not proceed to the Research Exit Gate.

### Alignment-Considerations Propagation

After clarify-critic returns and dispositions are applied (see Step 3), collect every finding with `origin: "alignment"` whose disposition is **Apply** (or whose Ask was resolved to Apply via the §4 Q&A flow). Findings dispositioned as **Dismiss** are not propagated. Format the surviving alignment findings as a newline-delimited bullet list:

```
- consideration text one
- consideration text two
```

Each consideration must be a one-sentence paraphrase of the underlying alignment finding. Strip or paraphrase away any embedded `=` or `"` characters so the value remains a well-formed argument string.

Pass the assembled list as `research-considerations="..."` to the `/cortex-core:research` invocation:

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality} research-considerations="
- consideration text one
- consideration text two"
```

This argument fires only when at least one Apply'd alignment finding exists. If clarify-critic returned no alignment findings, or every alignment finding was Dismissed, omit the `research-considerations` argument entirely from the research dispatch.

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

Read `references/specify.md` and follow its full protocol (§1–§4) with these adaptations:

- **§1 (Load Context)**: Requirements context was loaded during Clarify (Step 3) and research.md was produced in Step 4. Re-read `lifecycle/{lifecycle-slug}/research.md` but skip redundant requirements loading.
- **§2a loop-back**: If the Research Confidence Check triggers a loop-back, re-enter Step 4 (Research Phase) with the Sufficiency Check bypass described there.
- **§3b tier detection**: Read `lifecycle/{lifecycle-slug}/events.log` for the most recent `lifecycle_start` or `complexity_override` event to determine the active tier. The caller (`/cortex-core:lifecycle`) may escalate the tier between Research and Spec — do not rely solely on the Clarify output.
- **§4 (User Approval) — Complexity/value gate**: After the spec is written, before showing the approval surface, check whether complexity is proportional to the value case. Fire this check if the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem requiring ongoing per-feature upkeep. This check fires regardless of whether critical-review ran. If the check fires, do NOT proceed to the approval question in the same turn — instead present: (1) a one-sentence value case for the primary outcome, (2) a one-sentence complexity cost, and (3) 2–3 concrete alternatives. Where they naturally exist for this ticket, offer: "drop entirely" (value is achievable another way or too weak), "bugs-only" (strip the feature, keep only latent fix work the spec uncovered), "minimum viable" (identify one concrete scope cut). If an alternative doesn't naturally apply, say so. Wait for the user's response before showing the approval surface.
- **§5 (Transition)**: Skip — /cortex-core:refine does not log phase transitions. The caller handles transition events if applicable.

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
cortex-update-item {backlog-filename-slug} status=refined spec=lifecycle/{lifecycle-slug}/spec.md
```

```bash
cortex-update-item {backlog-filename-slug} "areas=[area1,area2]"
```

For empty areas: `cortex-update-item {backlog-filename-slug} "areas=[]"`. The quoted string preserves the list format through shell argument parsing.

Keep these as two separate sequential `cortex-update-item` calls — do not combine them into one invocation to avoid argument-parsing ambiguity with list values.

If either `cortex-update-item` call fails, surface the error and wait for the user to resolve. Do not proceed silently.

## Step 6: Completion

Announce that `/cortex-core:refine` is complete. Summarize:
- Backlog item: `{backlog-filename-slug}`
- Lifecycle directory: `lifecycle/{lifecycle-slug}/`
- Artifacts produced: research.md, spec.md
- Backlog fields written: `complexity`, `criticality`, `status: refined`, `spec`, `areas`

The feature is now ready for overnight execution. The overnight runner will auto-generate a plan from the spec and execute it without further input.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should generate a plan" | /cortex-core:refine stops at spec. Overnight auto-generates plans from specs. |
| "I should set status:refined as soon as research is done" | status:refined is set only after the user approves the spec (Step 5). |
| "I should use the lifecycle-slug as the cortex-update-item argument" | cortex-update-item takes the backlog-filename-slug (e.g., 119-create-refine-skill), not the lifecycle-slug. |
| "If cortex-update-item fails I can skip it and continue" | Write-back failures must be surfaced and resolved before proceeding. Silent skips corrupt backlog state. |
| "I should do a deep requirements interview during Clarify" | Clarify asks ≤5 targeted questions. The deep interview is Spec's job (Step 5). |
