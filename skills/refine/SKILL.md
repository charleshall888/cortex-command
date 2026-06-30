---
name: refine
description: Prepare a backlog item for execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "prepare for overnight", "prepare feature for execution", or "run on a backlog item before overnight". Produces cortex/lifecycle/{slug}/research.md and cortex/lifecycle/{slug}/spec.md, then sets status:refined on the backlog item.
when_to_use: "Use when preparing a backlog item for execution (\"spec this out\", \"tighten the requirements\", \"lock in the spec\"). Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement."
inputs:
  - "topic: string (required) — backlog item ID (numeric), slug (kebab-case), or title (quoted phrase); or ad-hoc topic name if no backlog item exists"
outputs:
  - "cortex/lifecycle/{slug}/research.md — implementation-level research artifact"
  - "cortex/lifecycle/{slug}/spec.md — approved specification ready for planning"
  - "cortex/backlog/{item}.md — updated with complexity:, criticality:, status: refined, spec: path, areas:"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory exists"
argument-hint: "<topic>"
---

# /cortex-core:refine

Prepares a single backlog item for execution. Runs three phases in sequence: **Clarify** (intent gate and requirements alignment), **Research** (implementation-level exploration), and **Spec** (structured requirements interview). When complete, the backlog item has `status: refined` and a linked spec, ready to be planned and executed.

Topic: $ARGUMENTS (backlog item slug, title, or description). If empty, prompt user before proceeding.

## Step 1: Resolve Input

Determine the feature topic from the invocation argument.

Run:

```bash
cortex-resolve-backlog-item <input>
```

Where `<input>` is the `$ARGUMENTS` value (backlog item ID, slug, or title phrase). If `$ARGUMENTS` is empty, prompt the user for input before invoking the script.

Act on the result: a unique match prints JSON (`filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`) — use it directly, don't re-derive the slugs. An ambiguous match prints candidates on stderr — present them and let the user pick. No match means there's no backlog item: treat the input as an ad-hoc topic (Context B, per `${CLAUDE_SKILL_DIR}/references/clarify.md` §1); if it's prose rather than a kebab slug, derive a short kebab `{lifecycle-slug}`, announce it, and proceed without asking to confirm. On any hard error, surface the resolver's message and halt.

## Step 2: Check State

Determine the resume point with the read-only resume-point verb — it classifies the state from the lifecycle artifacts (`is_file()` over `spec.md`/`research.md`) and prints `{"resume":...,"spec_exists":...,"research_exists":...}`:

```bash
cortex-refine resume-point --lifecycle-slug {lifecycle-slug}
```

Branch on the returned `resume` value (`clarify | research | spec | complete`) and apply the judgment guard the CLI cannot encode:

- **`complete`** — both artifacts exist; refine is complete. Announce completion and skip directly to Step 6 (Completion). Do not prompt the user; do not offer a menu. Re-run is triggered only by an explicit user message (e.g., "re-run refine", "redo the spec"); a re-run overwrites the existing spec and resets `status` to `in_progress` until the new spec is approved.
- **`research`** — spec.md exists but research.md is missing. Warn that overnight requires both, then run the Research phase. Skip Clarify — intent was already established when the spec was written.
- **`spec`** — research.md exists without a spec; resume at the Spec phase, where the Research Sufficiency Check (`${CLAUDE_SKILL_DIR}/references/clarify.md` §6) applies at phase entry.
- **`clarify`** — neither artifact exists; start from the beginning at the Clarify phase.

**Resolve the backlog backend once** with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0). Carry the resolved value through the rest of refine — it keys the seed, write-back, and reconcile routing below, and it gates the §3b critical-review decision.

After determining the resume point, seed the `lifecycle_start` row so `events.log` carries it before any other event is logged. The subcommand is idempotent — safe on resume. One unconditional call, passing the resolved backend:

```bash
cortex-refine emit-lifecycle-start --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}
```

Omit `--backlog-slug` for Context B (no backlog item). You do **not** branch on the backend to decide whether to pass the slug: pass it whenever a local backlog item exists, and the verb's `--backend` guard structurally drops it (and emits a diagnostic) on any non-`cortex-backlog` backend, so no stale local file is read. The `cortex-backlog` arm stays byte-identical to today.

**Seed→reconcile→gate ordering invariant**: keep the seed → reconcile → §3b read ordering intact so the §3b read observes the ratcheted (not seed-default) tier — critical on non-`cortex-backlog` backends, where the gate would otherwise skip silently at `tier = simple`. Full rationale in `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md` under "Seed → reconcile → gate ordering".

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading within Clarify uses the shared tag-based loading protocol at `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`.

Key outputs from Clarify (record these for use in subsequent phases):
- Clarified intent statement
- Complexity: `simple | complex`
- Criticality: `low | medium | high | critical`
- Requirements alignment note
- Open questions for research (may be empty)

After complexity and criticality are determined, run the write-back immediately (Context A only) — gated on the backend resolved in Step 2. On `cortex-backlog`, run:

```bash
cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}
```

On `none`, skip with a one-line advisory that write-back is disabled for this repo. On any other (external) backend, apply the equivalent complexity/criticality update best-effort on the configured tracker per `backlog.instructions`; if it can't complete, surface the composed values. Under every backend the critical-review gate still gets fed correctly — Step 5's `reconcile-clarify` carries Clarify's computed tier/criticality forward regardless.

If `cortex-update-item` fails, surface the error and wait for the user to resolve before continuing. On exit 2, apply the canonical ambiguous-slug handling in backlog-writeback.md (loaded at lifecycle Step 2).

## Step 4: Research Phase

### Sufficiency Check

If `cortex/lifecycle/{lifecycle-slug}/research.md` already exists, apply the Research Sufficiency Criteria defined in `${CLAUDE_SKILL_DIR}/references/clarify.md` §6. Use the clarified intent statement and scope from Clarify as the benchmark.

**Path guard** (explicit rules for what satisfies the Sufficiency Check):

1. The check passes only for a file at the exact path `cortex/lifecycle/{lifecycle-slug}/research.md`.
2. Files referenced by a backlog item's `discovery_source` or `research` frontmatter field are background context for the Clarify phase — they are not a substitute for the lifecycle research artifact, regardless of their path.
3. When `cortex/lifecycle/{lifecycle-slug}/research.md` does not exist at that exact path, run Research Execution below.

- **Sufficient**: Announce that existing research is sufficient, state which sufficiency signals were checked, and skip to Spec (Step 5).
- **Insufficient**: State which signal(s) triggered insufficiency, then proceed to run new research.

**Bypass case — loop-back from §2a confidence check**: If Research is being re-entered because `specify.md`'s §2a confidence check flagged gaps during the structured interview, skip the Sufficiency Check entirely and re-run Research from scratch. Treat `research.md` as invalidated and overwrite it.

### Research Execution

Delegate to `/cortex-core:research`:

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

**Research scope anchor**: The clarified intent from Step 3 is the scope anchor for research — not the original ticket body; the ticket body provides context but the clarified intent defines what research must cover.

**Alternative exploration**: When a backlog item contains implementation suggestions AND the feature is complex-tier or high/critical criticality, research must explicitly explore at least one alternative approach alongside the ticket's suggestion, within the `/cortex-core:research` call. For simple-tier or low/medium-criticality features, alternative exploration is encouraged but not required. Validating the ticket's suggested approach is a correct outcome — the requirement is to explore alternatives, not to reject the suggestion.

`/cortex-core:research` writes its output to `cortex/lifecycle/{lifecycle-slug}/research.md`.

After `/cortex-core:research` returns, verify that `cortex/lifecycle/{lifecycle-slug}/research.md` exists and is non-empty. If the file is absent or empty, surface the error to the user and halt — do not proceed to the Research Exit Gate.

### Alignment-Considerations Propagation

After clarify-critic returns and dispositions are applied (see Step 3), collect every finding with `origin: "alignment"` whose disposition is **Apply** (or whose Ask was resolved to Apply via the §4 Q&A flow). Findings dispositioned as **Dismiss** are not propagated. Format the surviving alignment findings as a newline-delimited bullet list:

```
- consideration text one
- consideration text two
```

Each consideration must be a one-sentence paraphrase of the underlying alignment finding. Strip or paraphrase away any embedded `=` or `"` characters so the value remains a well-formed argument string.

Pass the assembled list as `research-considerations="..."` to the `/cortex-core:research` invocation. This argument fires only when at least one Apply'd alignment finding exists. If clarify-critic returned no alignment findings, or every alignment finding was Dismissed, omit the `research-considerations` argument entirely from the research dispatch.

After writing `research.md`, register the `"research"` artifact in `cortex/lifecycle/{lifecycle-slug}/index.md` per the canonical artifact-registration recipe in backlog-writeback.md (loaded at lifecycle Step 2).

### Research Exit Gate

Before transitioning to Step 5 (Spec), scan `research.md`'s `## Open Questions` section. An item is **resolved** if it contains an inline answer. An item is **deferred** if it is explicitly marked deferred with written rationale (e.g., "Deferred: will be resolved in Spec by asking the user"). A bare unannotated bullet is neither resolved nor deferred.

If any unresolved, non-deferred items exist: present them to the user and resolve or explicitly defer each one before proceeding to Spec. Do not transition to Spec with open, unaddressed questions.

If the `## Open Questions` section is absent from `research.md`, the gate passes.

## Step 5: Spec Phase

**Reconcile lifecycle state to the Clarify assessment first** — the `lifecycle_start` seed carries pre-Clarify tier/criticality; reconcile so the §3a/§3b reads observe the Clarify-assessed values. One unconditional call, passing the backend resolved in Step 2 as `--backend {resolved}`; the remaining flags follow the item-existence context (the verb's `--backend` guard owns the non-local slug-drop, so you no longer branch on the backend here):

- **Context A** (a local backlog item exists): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources tier/criticality from backlog frontmatter on the local arm (unchanged from today); on a non-local backend the guard drops the slug structurally.
- **Context B** (no backlog item): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes **Clarify's computed** `{value}` tier/criticality as explicit flags. On a non-local backend this is the live path: it ratchets the lifecycle state up from the seed defaults so the critical-review gate stays correctly fed (the seed→reconcile→§3b ordering invariant from Step 2). Pass Clarify's computed values here — not the seed defaults and not literals.

Idempotent — safe on resume; no-op under `/cortex-core:lifecycle`.

Read `${CLAUDE_SKILL_DIR}/references/specify.md` and follow it (its full protocol) with these adaptations:

- **§1 (Load Context)**: Requirements context was loaded during Clarify (Step 3) and research.md was produced in Step 4. Re-read `cortex/lifecycle/{lifecycle-slug}/research.md` but skip redundant requirements loading.
- **§2a loop-back**: If the Research Confidence Check triggers a loop-back, re-enter Step 4 (Research Phase) with the Sufficiency Check bypass described there.
- **§3b tier detection**: Run `cortex-lifecycle-state --feature {lifecycle-slug} --field tier`. The caller (`/cortex-core:lifecycle`) may escalate the tier between Research and Spec — do not rely solely on the Clarify output. If the output contains `"corrupted": true`, treat the feature as requiring review (run the §3b gate) rather than defaulting to `simple` and skipping. See `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md` for the full behavior matrix.
- **§4 (User Approval) — Complexity/value gate**: After the spec is written, before showing the approval surface, check whether complexity is proportional to the value case. Fire this check if the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem requiring ongoing per-feature upkeep. This check fires regardless of whether critical-review ran. When the check fires, decide which alternative is the recommended option for this specific spec. Default to "Confirm current scope" (full scope) unless the spec's complexity materially exceeds the value case, in which case recommend the smallest downsize that preserves the primary outcome. Announce the recommendation with a one-sentence rationale citing the specific spec surface(s) driving the choice — phrased as "I recommend X because Y." — before any user-facing question. Call `AskUserQuestion` only when the recommendation is not full scope OR when confidence is low; otherwise fold the announcement into the existing approval surface (Approve / Request changes / Cancel) and proceed without an intervening pick-menu. When `AskUserQuestion` fires, the lead option's `label` ends with the literal suffix ` (Recommended)` (single leading space, capital R) and its `description` opens with the rationale. The lead label is `Confirm current scope (Recommended)` when recommending full scope, or the recommended downsize labeled `… (Recommended)` otherwise. Carry through the existing downsize alternatives where they naturally apply — "drop entirely" (value is weak or achievable another way), "bugs-only" (keep only latent fixes the spec uncovered), "minimum viable" (one concrete scope cut) — and say so when one doesn't apply.
- **§5 (Transition)**: Skip the `phase_transition` event emission — /cortex-core:refine does not log `phase_transition` events; the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts. The `lifecycle_start` sentinel emitted at Step 2 is exempt from this rule.
- **`## Hard Gate`**: Applies; when the Open-Decisions row and the §4 gate both fire, §4's surface flow wins.

Do NOT set `status: refined` before user approval.

After user approval (specify.md §4), register the `"spec"` artifact in `cortex/lifecycle/{lifecycle-slug}/index.md` per the canonical artifact-registration recipe in backlog-writeback.md (the same canonical recipe as the `"research"` registration above).

### Write-Back on Approval (Context A only)

After user approves the spec:

**Infer areas**: Identify which subsystem the feature primarily modifies. Canonical area names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`. Use the primary subsystem only — the one where most files change. If the feature spans 4+ subsystems with no clear primary, use `areas=[]`.

Gate these status/spec/areas write-backs on the backend resolved in Step 2. On `cortex-backlog`, run:

```bash
cortex-update-item {backlog-filename-slug} --status refined --spec cortex/lifecycle/{lifecycle-slug}/spec.md
```

```bash
cortex-update-item {backlog-filename-slug} --areas area1 area2
```

For empty areas: `cortex-update-item {backlog-filename-slug} --areas` (passing `--areas` with no values clears the list).

On `none`, skip these write-backs with a one-line advisory that backlog write-back is disabled for this repo. On any other (external) backend, make the equivalent status/areas update best-effort on the configured tracker per `backlog.instructions`, surfacing the composed values if it cannot be completed.

Handle failures as in Step 3.

## Step 6: Completion

Announce that `/cortex-core:refine` is complete. Summarize:
- Backlog item: `{backlog-filename-slug}`
- Lifecycle directory: `cortex/lifecycle/{lifecycle-slug}/`
- Artifacts produced: research.md, spec.md
- Backlog fields written: `complexity`, `criticality`, `status: refined`, `spec`, `areas`

## Constraints

| Thought | Reality |
|---------|---------|
| "I should generate a plan" | Refine stops at spec; overnight auto-generates plans. |
| "I should set status:refined as soon as research is done" | Set only after user approves the spec (Step 5). |
| "I should use the lifecycle-slug as the cortex-update-item argument" | cortex-update-item takes the backlog-filename-slug (e.g., 119-create-refine-skill), not the lifecycle-slug. |
| "If cortex-update-item fails I can skip it and continue" | Surface and resolve; silent skips corrupt backlog state. |
