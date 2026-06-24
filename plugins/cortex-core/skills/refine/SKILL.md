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

Branch on the exit code:

- **Exit 0** — unambiguous match. Parse stdout JSON for `filename`, `backlog_filename_slug`, `title`, and `lifecycle_slug`; use these directly in Step 2 and subsequent phases. Do not re-derive slugs from scratch.
- **Exit 2** — ambiguous match. Read the `<filename>\t<title>` candidate lines from stderr. Present them to the user and ask them to select one. Re-invoke `cortex-resolve-backlog-item` with the chosen filename slug, or treat the user's selection directly as the resolved item.
- **Exit 3** — no match. Switch to Context B (ad-hoc topic) per `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §1 and treat the input as the topic name. When the input is prose rather than a valid kebab-case slug (`^[a-z0-9]+(-[a-z0-9]+)*$`), derive a 3–6 word kebab-case slug for `{lifecycle-slug}`, announce it, and proceed. Do not ask the user to confirm the derived slug.
- **Any other non-zero exit** (e.g., `64` usage error from empty/malformed input; `70` internal error from malformed frontmatter, missing backlog directory, or other IO failure) — halt, surface the stderr diagnostic to the user verbatim, and do NOT fall through to disambiguation.

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
else:
    resume = clarify phase (start from beginning)
```

Re-running overwrites the existing spec and resets `status` to `in_progress` until the new spec is approved. No CLI flag required.

**Resolve the backlog backend once** with `` `cortex-read-backlog-backend` `` (argless; it prints the resolved backend and exits 0). Carry the resolved value through the rest of refine — it keys the seed, write-back, and reconcile routing below. The default `cortex-backlog` arm is byte-identical to today; the non-local arm omits `--backlog-slug` and feeds Clarify's computed tier/criticality forward as explicit flags.

After determining the resume point, seed the `lifecycle_start` row so `events.log` carries it before any other event is logged. The subcommand is idempotent — safe on resume. Route on the resolved backend:

- **`cortex-backlog`** (the default arm) → invoke `cortex-refine emit-lifecycle-start --backlog-slug {backlog-filename-slug} --lifecycle-slug {lifecycle-slug}` (omit `--backlog-slug` for Context B). Unchanged from today.
- **any non-`cortex-backlog` backend** → invoke `cortex-refine emit-lifecycle-start --lifecycle-slug {lifecycle-slug}` (omit `--backlog-slug`), so `_read_backlog_frontmatter(None)` returns the seed defaults without reading or validating any local backlog file.

**Seed→reconcile→gate ordering invariant**: keep the seed → reconcile → §3b read ordering intact so the §3b read observes the ratcheted (not seed-default) tier — critical on non-`cortex-backlog` backends, where the gate would otherwise skip silently at `tier = simple`. Full rationale in `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md` under "Seed → reconcile → gate ordering".

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading within Clarify uses the shared tag-based loading protocol at `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`.

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

If `cortex/lifecycle/{lifecycle-slug}/research.md` already exists, apply the Research Sufficiency Criteria defined in `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md` §6. Use the clarified intent statement and scope from Clarify as the benchmark.

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

**Reconcile lifecycle state to the Clarify assessment first** — the `lifecycle_start` seed carries pre-Clarify tier/criticality; reconcile so the §3a/§3b reads observe the Clarify-assessed values. Key the form on the backend resolved in Step 2:

- **Context A** (a `cortex-backlog` item with a backlog file): `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources tier/criticality from backlog frontmatter (unchanged from today).
- **Context B** (no backlog file, OR any non-`cortex-backlog` backend): `cortex-refine reconcile-clarify --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — omits `--backlog-slug` (so no local file is read or validated) and passes **Clarify's computed** `{value}` tier/criticality as explicit flags. Under a non-local backend this is the live path: it ratchets the lifecycle state up from the seed defaults so the critical-review gate stays correctly fed (the seed→reconcile→§3b ordering invariant from Step 2). Pass Clarify's computed values here — not the seed defaults and not literals.

Idempotent — safe on resume; no-op under `/cortex-core:lifecycle`.

Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow it (its full protocol) with these adaptations:

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

### Overnight-candidate advisory (standalone `/refine` only)

This advisory runs only on the standalone `/refine` path. Detect that path with a concrete signal: standalone `/refine` never logs `phase_transition` events (it writes only `lifecycle_start` and `*_override` rows), whereas a run under `/cortex-core:lifecycle` already carries `phase_transition` rows from its phase boundaries — the early `clarify→research` and `research→specify` transitions are on disk before any spec exists. Check:

```bash
grep -c '"event": "phase_transition"' cortex/lifecycle/{lifecycle-slug}/events.log
```

- `0` → standalone: assess overnight-suitability and surface the advisory below when warranted.
- `≥ 1` → invoked under `/cortex-core:lifecycle`: stay silent (the user is building interactively and verifies throughout).

When standalone, assess whether the approved `spec.md` is a poor overnight candidate. Anchor on these mechanical signals, and cite each that is present:

- any acceptance criterion marked `Interactive/session-dependent`, and
- any unresolved item under the spec's `## Open Decisions`.

You may additionally cite judgment reasons when they apply: the work needs network or credentials the sandbox can't reach, it leans on human-visual or human-judgment verification, or its scope is exploratory/under-specified.

When one or more reasons apply, surface a brief advisory naming them — e.g., "Heads up — this looks like a poor overnight candidate because …" — so the operator can choose to run it interactively instead. When none apply, say nothing about overnight suitability; the advisory is silent on a good candidate.

## Constraints

| Thought | Reality |
|---------|---------|
| "I should generate a plan" | Refine stops at spec; overnight auto-generates plans. |
| "I should set status:refined as soon as research is done" | Set only after user approves the spec (Step 5). |
| "I should use the lifecycle-slug as the cortex-update-item argument" | cortex-update-item takes the backlog-filename-slug (e.g., 119-create-refine-skill), not the lifecycle-slug. |
| "If cortex-update-item fails I can skip it and continue" | Surface and resolve; silent skips corrupt backlog state. |
