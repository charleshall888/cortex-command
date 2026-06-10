---
name: refine
description: Prepare a backlog item for overnight execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "prepare for overnight", "prepare feature for execution", or "run on a backlog item before overnight". Produces cortex/lifecycle/{slug}/research.md and cortex/lifecycle/{slug}/spec.md, then sets status:refined on the backlog item.
when_to_use: "Use when preparing a backlog item for overnight execution (\"spec this out\", \"tighten the requirements\", \"lock in the spec\"). Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement."
inputs:
  - "topic: string (required) — backlog item ID (numeric), slug (kebab-case), or title (quoted phrase); or ad-hoc topic name if no backlog item exists"
outputs:
  - "cortex/lifecycle/{slug}/research.md — implementation-level research artifact"
  - "cortex/lifecycle/{slug}/spec.md — approved specification ready for overnight planning"
  - "cortex/backlog/{item}.md — updated with complexity:, criticality:, status: refined, spec: path, areas:"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory exists"
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
- **Exit 3** — no match. Switch to Context B (ad-hoc topic) per `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §1 and treat the input as the topic name. When the input is prose rather than a valid kebab-case slug (`^[a-z0-9]+(-[a-z0-9]+)*$`), apply the prose-derivation prescription from `${CLAUDE_SKILL_DIR}/../lifecycle/SKILL.md` Step 1 before treating it as the topic name — derive a 3–6 word kebab-case slug for `{lifecycle-slug}`, announce it, and proceed. Do not ask the user to confirm the derived slug.
- **Exit 64** — usage error (e.g., empty or malformed input). Halt and surface the stderr usage diagnostic to the user. Do NOT fall through to disambiguation.
- **Exit 70** — internal software error (malformed frontmatter, missing backlog directory, or other IO failure). Halt and surface the stderr diagnostic to the user. Do NOT fall through to disambiguation.

## Step 2: Check State

Check for existing artifacts to determine the resume point:

```
if cortex/lifecycle/{lifecycle-slug}/spec.md exists AND cortex/lifecycle/{lifecycle-slug}/research.md exists:
    both artifacts exist — refine is complete. Announce completion and skip directly to Step 6 (Completion).
    Re-run is triggered only by an explicit user message (e.g., "re-run refine", "redo the spec").
    Do not prompt the user; do not offer a menu.
elif cortex/lifecycle/{lifecycle-slug}/spec.md exists AND cortex/lifecycle/{lifecycle-slug}/research.md does NOT exist:
    warn: "spec.md exists but research.md is missing — overnight requires both. Running research phase."
    resume = research phase (skip Clarify — intent was already established when spec was written)
elif cortex/lifecycle/{lifecycle-slug}/research.md exists at that exact path:
    resume = spec phase (research already done — sufficiency check applies at phase entry)
    # Files referenced by a backlog item's discovery_source or research frontmatter field are
    # background context only. They are not a substitute for cortex/lifecycle/{lifecycle-slug}/research.md,
    # regardless of their path.
else:
    resume = clarify phase (start from beginning)
```

When both artifacts exist and the user has explicitly requested a re-run via a follow-up message, re-running will overwrite the existing spec and reset `status` to `in_progress` until the new spec is approved. No CLI flag is required — the trigger is the user's explicit message.

After determining the resume point, invoke `cortex-refine emit-lifecycle-start --backlog-slug {backlog-filename-slug} --lifecycle-slug {lifecycle-slug}` (omit `--backlog-slug` for Context B) so `events.log` carries the seed `lifecycle_start` row before any other event is logged. The subcommand is idempotent — safe on resume.

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading within Clarify uses the shared tag-based loading protocol at `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md` (the citation chain is refine SKILL.md → lifecycle clarify.md → load-requirements.md).

If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview.

Key outputs from Clarify (record these for use in subsequent phases):
- Clarified intent statement
- Complexity: `simple | complex`
- Criticality: `low | medium | high | critical`
- Requirements alignment note
- Open questions for research (may be empty)

After complexity and criticality are determined, run the write-back immediately (Context A only):

```bash
cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}
```

If `cortex-update-item` fails, surface the error and wait for the user to resolve before continuing. Exit 2 indicates an ambiguous slug — present the candidate list on stderr to the user and ask them to re-invoke with a disambiguated slug.

## Step 4: Research Phase

### Sufficiency Check

If `cortex/lifecycle/{lifecycle-slug}/research.md` already exists, apply the Research Sufficiency Criteria defined in `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §6. Use the clarified intent statement and scope from Clarify as the benchmark.

**Path guard** (explicit rules for what satisfies the Sufficiency Check):

1. The check passes only for a file at the exact path `cortex/lifecycle/{lifecycle-slug}/research.md`.
2. Files referenced by a backlog item's `discovery_source` or `research` frontmatter field are background context for the Clarify phase — they are not a substitute for the lifecycle research artifact, regardless of their path.
3. When `cortex/lifecycle/{lifecycle-slug}/research.md` does not exist at that exact path, run Research Execution below.

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

`/cortex-core:research` writes its output to `cortex/lifecycle/{lifecycle-slug}/research.md`.

After `/cortex-core:research` returns, verify that `cortex/lifecycle/{lifecycle-slug}/research.md` exists and is non-empty. If the file is absent or empty, surface the error to the user and halt — do not proceed to the Research Exit Gate.

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

After writing `research.md`, update `cortex/lifecycle/{lifecycle-slug}/index.md`:
- If `"research"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"research"` to the artifacts inline array
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

### Research Exit Gate

Before transitioning to Step 5 (Spec), scan `research.md`'s `## Open Questions` section. An item is **resolved** if it contains an inline answer. An item is **deferred** if it is explicitly marked deferred with written rationale (e.g., "Deferred: will be resolved in Spec by asking the user"). A bare unannotated bullet is neither resolved nor deferred.

If any unresolved, non-deferred items exist: present them to the user and resolve or explicitly defer each one before proceeding to Spec. Do not transition to Spec with open, unaddressed questions.

If the `## Open Questions` section is absent from `research.md`, the gate passes.

## Step 5: Spec Phase

**Reconcile lifecycle state to the Clarify assessment first.** Standalone `/cortex-core:refine` seeds `events.log` with a `lifecycle_start` row at Step 2 — *before* Clarify runs (Step 3) — so the seed carries the backlog's pre-Clarify tier/criticality, not what Clarify assessed. At Spec-phase entry, reconcile the two so the §3a Orchestrator Review and §3b Critical Review tier/criticality reads (which live inside the delegated `specify.md` below) observe the Clarify values rather than the stale seed:

- **Context A** (the item has a backlog file): `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — sources the Clarify-determined tier/criticality from the backlog frontmatter Clarify wrote back, covering the `resume=spec` path where Step-3 Clarify is skipped this session.
- **Context B** (no backlog file): `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes the in-context Clarify values directly.

The subcommand is idempotent (state-based no-op guard) and monotonic (never downgrades), so it is safe on resume and safe to double-fire — and a no-op under `/cortex-core:lifecycle`, whose post-Clarify `lifecycle_start` already moved the reduced state. Mirrors the Step-2 `emit-lifecycle-start` seed-before-other-events discipline.

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow it (its full protocol) with these adaptations:

- **§1 (Load Context)**: Requirements context was loaded during Clarify (Step 3) and research.md was produced in Step 4. Re-read `cortex/lifecycle/{lifecycle-slug}/research.md` but skip redundant requirements loading.
- **§2a loop-back**: If the Research Confidence Check triggers a loop-back, re-enter Step 4 (Research Phase) with the Sufficiency Check bypass described there.
- **§3b tier detection**: Read the active tier by running `cortex-lifecycle-state --feature {lifecycle-slug} --field tier` (emits JSON applying the canonical rule that `lifecycle_start.tier` is superseded by the most recent `complexity_override.to`; defaults to `simple` when the key is absent). The caller (`/cortex-core:lifecycle`) may escalate the tier between Research and Spec — do not rely solely on the Clarify output. Because the reconcile-clarify step above ran at Spec entry, this read (and the §3a/§3b criticality read) observes the Clarify-assessed tier/criticality rather than the stale pre-Clarify seed for a standalone `/cortex-core:refine`, so the §3b critical-review gate fires for Clarify-assessed complex/high features instead of silently skipping. If the `cortex-lifecycle-state` output contains `"corrupted": true`, the events.log is corrupted and the gate input is unknowable — treat the feature as requiring review (run the §3b gate) rather than defaulting to `simple` and skipping.
- **§4 (User Approval) — Complexity/value gate**: After the spec is written, before showing the approval surface, check whether complexity is proportional to the value case. Fire this check if the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem requiring ongoing per-feature upkeep. This check fires regardless of whether critical-review ran. When the check fires, decide which alternative is the recommended option for this specific spec. Default to "Confirm current scope" (full scope) unless the spec's complexity materially exceeds the value case, in which case recommend the smallest downsize that preserves the primary outcome. Announce the recommendation with a one-sentence rationale citing the specific spec surface(s) driving the choice — phrased as "I recommend X because Y." — before any user-facing question. Call `AskUserQuestion` only when the recommendation is not full scope OR when confidence is low; otherwise fold the announcement into the existing approval surface (Approve / Request changes / Cancel) and proceed without an intervening pick-menu. When `AskUserQuestion` fires, the lead option's `label` ends with the literal suffix ` (Recommended)` (single leading space, capital R) and its `description` opens with the rationale. The lead label is `Confirm current scope (Recommended)` when recommending full scope, or the recommended downsize labeled `… (Recommended)` otherwise. Carry through the existing downsize alternatives where they naturally exist: "drop entirely" (value is achievable another way or too weak), "bugs-only" (strip the feature, keep only latent fix work the spec uncovered), "minimum viable" (identify one concrete scope cut). If an alternative doesn't naturally apply, say so.

  Worked example — gate fires on a spec introducing three new state surfaces of which two are deferrable. The orchestrator announces: "I recommend 'minimum viable' because the spec introduces three new state surfaces (worktree registry, lock file, runner pidfile) but the value case is satisfied by just the registry; the lock and pidfile can be added later if contention surfaces." Because the recommendation is not full scope, `AskUserQuestion` then fires with options `[{"label": "Minimum viable (Recommended)", "description": "Only the worktree registry — defers lock and pidfile to a follow-up."}, {"label": "Confirm current scope", "description": "All three state surfaces as specified."}, {"label": "Drop entirely", "description": "Value is achievable via $TMPDIR ad-hoc with no persistent state."}]`.
- **§5 (Transition)**: Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts. The `lifecycle_start` session-start sentinel emitted at Step 2 is a deliberate carve-out from this rule and is owned by refine.
- **`## Hard Gate`**: Applies — refine's spec phase has the same no-implementation-code rule. The Hard Gate's Thought/Reality table from `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` carries through, with one caveat: the row "I'll add this to Open Decisions since I'm not sure" interacts with refine's existing **§4 (User Approval) — Complexity/value gate** adaptation above (which already routes simple specs and "drop entirely" alternatives through an explicit user-presented surface) — when both fire, follow §4's surface flow rather than a separate Open Decisions deferral.

Do NOT set `status: refined` before user approval.

After user approval (specify.md §4), update `cortex/lifecycle/{lifecycle-slug}/index.md`:
- If `"spec"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"spec"` to the artifacts inline array
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

### Write-Back on Approval (Context A only)

After user approves the spec:

**Infer areas**: Identify which subsystem the feature primarily modifies. Canonical area names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`. Use the primary subsystem only — the one where most files change. If the feature spans 4+ subsystems with no clear primary, use `areas=[]`.

```bash
cortex-update-item {backlog-filename-slug} --status refined --spec cortex/lifecycle/{lifecycle-slug}/spec.md
```

```bash
cortex-update-item {backlog-filename-slug} --areas area1 area2
```

For empty areas: `cortex-update-item {backlog-filename-slug} --areas` (passing `--areas` with no values clears the list).

If either `cortex-update-item` call fails, surface the error and wait for the user to resolve. Do not proceed silently. Exit 2 indicates an ambiguous slug — present the candidate list on stderr to the user and ask them to re-invoke with a disambiguated slug.

## Step 6: Completion

Announce that `/cortex-core:refine` is complete. Summarize:
- Backlog item: `{backlog-filename-slug}`
- Lifecycle directory: `cortex/lifecycle/{lifecycle-slug}/`
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
