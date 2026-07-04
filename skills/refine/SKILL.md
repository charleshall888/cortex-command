---
name: refine
description: Prepare a backlog item for execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "prepare for overnight", or "prepare feature for execution". Produces cortex/lifecycle/{slug}/research.md and cortex/lifecycle/{slug}/spec.md, then sets status:refined on the backlog item.
when_to_use: "Use when preparing a backlog item for execution (\"spec this out\"). Different from /cortex-core:lifecycle — refine produces spec only; lifecycle wraps refine and continues to plan/implement."
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

Prepares a single backlog item for execution through three phases: **Clarify** (intent gate + requirements alignment), **Research** (implementation-level exploration), **Spec** (structured requirements interview). On completion the item has `status: refined` and a linked spec, ready to plan and execute.

Topic: $ARGUMENTS (backlog item slug, title, or description). If empty, prompt the user first.

## Step 1: Resolve Input

```bash
cortex-resolve-backlog-item <input>
```

Act on the result: a unique match prints JSON (`filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`) — use it directly, don't re-derive the slugs. Ambiguous → candidates on stderr; present them and let the user pick. No match → treat the input as an ad-hoc topic (Context B, per `${CLAUDE_SKILL_DIR}/references/clarify.md` §1); if it's prose rather than a kebab slug, derive a short kebab `{lifecycle-slug}`, announce it, and proceed without confirming. Hard error → surface the resolver's message and halt.

## Step 2: Check State

Resolve the resume point (read-only):

```bash
cortex-refine resume-point --lifecycle-slug {lifecycle-slug}
```

Branch on the returned `resume` (`clarify | research | spec | complete`), applying the judgment the CLI can't encode:

- **`complete`** — both artifacts exist; announce and skip to Step 6. No prompt, no menu. Re-run only on an explicit user message ("re-run refine", "redo the spec"), which overwrites the spec and resets `status: in_progress` until the new spec is approved.
- **`research`** — spec.md exists, research.md missing. Warn that overnight needs both, then run Research; skip Clarify (intent was set when the spec was written).
- **`spec`** — research.md exists, no spec; resume at Spec, where the Research Sufficiency Check (`clarify.md` §6) applies at entry.
- **`clarify`** — neither exists; start at Clarify.

**Resolve the backlog backend once** with `cortex-read-backlog-backend` (argless; prints the backend, exits 0). Carry it through refine — it keys the seed, write-back, and reconcile routing, and gates the §3b decision.

Then seed the `lifecycle_start` row so `events.log` carries it before any other event (idempotent — safe on resume; one unconditional call passing the backend):

```bash
cortex-refine emit-lifecycle-start --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}
```

Omit `--backlog-slug` for Context B. Don't branch on the backend to decide whether to pass the slug — pass it whenever a local backlog item exists; the verb's `--backend` guard owns the non-local slug-drop (ADR-0019).

**Tier ratchet ordering invariant**: keep the seed → reconcile → §3b-read ordering so the §3b read observes the **tier ratchet**'s output, not the seed default. Rationale and the tier-ratchet definition: `${CLAUDE_SKILL_DIR}/references/seed-reconcile-gate-ordering.md`.

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading uses the shared protocol at `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`.

Record Clarify's outputs for later phases: clarified intent, complexity (`simple|complex`), criticality (`low|medium|high|critical`), requirements-alignment note, open questions for research (may be empty).

Once complexity and criticality are set, run the write-back immediately (Context A only), gated on the Step-2 backend. This is the canonical **backend-gated write-back routing** — the 3-arm shape Step 5's Write-Back also uses, each site supplying its own fields:

- **`cortex-backlog`** → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
- **`none`** → skip with a one-line advisory that write-back is disabled for this repo.
- **external** → apply the equivalent complexity/criticality update best-effort per `backlog.instructions`; surface the values if it can't complete.

Under every backend the critical-review gate is still fed — Step 5's `reconcile-clarify` carries Clarify's tier/criticality forward. On `cortex-update-item` failure, surface and wait; on exit 2, apply backlog-writeback.md's ambiguous-slug handling.

## Step 4: Research Phase

### Sufficiency Check

If `cortex/lifecycle/{lifecycle-slug}/research.md` exists, apply the Research Sufficiency Criteria (`clarify.md` §6) against Clarify's intent and scope. **Path guard**: only a file at that exact path counts — a backlog item's `discovery_source`/`research` field is Clarify background, never a substitute, whatever its path. Missing → run Research Execution.

- **Sufficient** → announce, state which signals were checked, skip to Spec.
- **Insufficient** → state the triggering signal(s), run new research.

**Bypass**: if Research is re-entered from specify.md's §2a confidence-check loop-back, skip the Sufficiency Check and re-run from scratch, overwriting `research.md`.

### Alignment-Considerations Propagation

After clarify-critic returns and dispositions are applied (Step 3), collect every `origin: "alignment"` finding dispositioned **Apply** (or Ask resolved to Apply via the §4 Q&A); Dismiss'd ones aren't propagated. **Only when** ≥1 Apply'd alignment finding exists, do one coupled step: **write** the surviving findings to `cortex/lifecycle/{lifecycle-slug}/research-considerations.md` (overwrite, never append) **and** carry `research-considerations-file=cortex/lifecycle/{lifecycle-slug}/research-considerations.md` on the research dispatch. The write and the argument are inseparable — the argument never rides without a same-run fresh write, so a stale prior-run file can't be read. No alignment findings, or all Dismissed → neither write nor argument.

The file is a newline-delimited bullet list, one one-sentence paraphrase per finding. Because it rides a file (not a parsed argument), the content may contain arbitrary characters (`=`, `"`) with no escaping.

### Research Execution

Delegate to `/cortex-core:research` (append `research-considerations-file=cortex/lifecycle/{lifecycle-slug}/research-considerations.md` only when the propagation write above fired):

```
/cortex-core:research topic="{clarified intent}" lifecycle-slug="{lifecycle-slug}" tier={tier} criticality={criticality}
```

The clarified intent (not the ticket body) is the research scope anchor — the ticket body is context, the clarified intent defines coverage. **Alternative exploration**: when a backlog item carries implementation suggestions AND the feature is complex-tier or high/critical, research must explore ≥1 alternative alongside the ticket's suggestion (encouraged but not required for simple-tier or low/medium). Validating the suggestion is a correct outcome — the requirement is to explore alternatives, not to reject the suggestion.

After research returns, verify `research.md` exists and is non-empty (else surface the error and halt). Then register the `"research"` artifact in `index.md` per backlog-writeback.md's canonical recipe.

### Research Exit Gate

Scan `research.md`'s `## Open Questions`: an item is **resolved** if it has an inline answer, **deferred** if explicitly marked deferred with written rationale; a bare unannotated bullet is neither. Any unresolved, non-deferred items → present them and resolve or explicitly defer each before Spec. An absent `## Open Questions` section → the gate passes.

## Step 5: Spec Phase

**Reconcile lifecycle state to the Clarify assessment first** — the `lifecycle_start` seed carries pre-Clarify tier/criticality; reconcile so the §3a/§3b reads observe the Clarify-assessed values. One unconditional call passing the Step-2 backend as `--backend {resolved}`; the remaining flags follow item-existence context (the `--backend` guard owns the non-local slug-drop):

- **Context A** (local item): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources tier/criticality from backlog frontmatter on the local arm.
- **Context B** (no item): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes **Clarify's computed** values. On a non-local backend this is the **tier ratchet** (Step 2's ordering invariant) that keeps the critical-review gate fed. Pass Clarify's computed values, not seed defaults or literals.

Idempotent — safe on resume; no-op under `/cortex-core:lifecycle`.

Read `${CLAUDE_SKILL_DIR}/references/specify.md` and follow it (its full protocol) with these adaptations:

- **§1 (Load Context)**: requirements were loaded in Clarify and research.md was produced in Step 4 — re-read `research.md` but skip redundant requirements loading.
- **§2a loop-back**: a Research Confidence Check loop-back re-enters Step 4 with the Sufficiency Check bypass.
- **§3b tier detection**: run `cortex-lifecycle-state --feature {lifecycle-slug} --field tier`. The caller (`/cortex-core:lifecycle`) may escalate tier between Research and Spec — don't rely solely on Clarify. `"corrupted": true` → treat as requiring review (run §3b) rather than defaulting to `simple` and skipping. Canonical rule + full matrix: `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md`.
- **§3a/§3b gate references**: specify.md consults two lifecycle-sibling gates via "the propagated `<target>` path". Standalone refine carries no lifecycle SKILL.md manifest, so resolve them here: orchestrator-review → `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`, critical-review-gate → `${CLAUDE_SKILL_DIR}/../lifecycle/references/critical-review-gate.md`. The "propagated `<target>` path" phrasing binds to these.
- **§4 (User Approval) — Complexity/value gate**: before the approval surface, gate the spec on complexity/value proportionality. Fire — regardless of whether critical-review ran — when the spec has any of: 3+ distinct new state surfaces, a new persistent data format or config section the user must maintain, or a subsystem needing ongoing per-feature upkeep. Default recommendation is full scope; when complexity materially exceeds the value case, recommend the smallest downsize preserving the primary outcome. State it rationale-first — "I recommend X because Y." citing the driving spec surface(s) — before any user-facing question. Call `AskUserQuestion` only when the recommendation isn't full scope OR confidence is low; otherwise fold the announcement into the approval surface (Approve / Request changes / Cancel) with no pick-menu. When it fires, the lead option's `label` ends with ` (Recommended)` (single leading space, capital R) and its `description` opens with the rationale — `Confirm current scope (Recommended)` for full scope, else the recommended downsize labeled `… (Recommended)`. Offer the applicable downsizes ("drop entirely", "bugs-only", "minimum viable") and say when one doesn't apply.
- **§5 (Transition)**: skip the `phase_transition` emission — refine doesn't log it; the caller (`/cortex-core:lifecycle`) owns phase-transition logging and commit-artifacts. The Step-2 `lifecycle_start` sentinel is exempt.
- **`## Hard Gate`**: applies; when the Open-Decisions row and the §4 gate both fire, §4's surface flow wins.

Do NOT set `status: refined` before approval. After approval (specify.md §4), register the `"spec"` artifact in `index.md` per backlog-writeback.md's canonical recipe.

### Write-Back on Approval (Context A only)

**Infer areas**: name the primary subsystem modified (canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`) — the one where most files change. Spanning 4+ with no clear primary → `areas=[]`.

Route these status/spec/areas write-backs through Step 3's 3-arm backend-gated routing, this site's fields. On `cortex-backlog`:

```bash
cortex-update-item {backlog-filename-slug} --status refined --spec cortex/lifecycle/{lifecycle-slug}/spec.md
cortex-update-item {backlog-filename-slug} --areas area1 area2
```

Empty areas: `cortex-update-item {backlog-filename-slug} --areas` (no values clears the list). The `none`/external arms and failure handling match Step 3.

## Step 6: Completion

Announce refine is complete, summarizing the item (`{backlog-filename-slug}`), the lifecycle directory (`cortex/lifecycle/{lifecycle-slug}/`), the artifacts produced (research.md, spec.md), and the backlog fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`).

## Constraints

| Thought | Reality |
|---------|---------|
| "Use the lifecycle-slug as the cortex-update-item argument" | cortex-update-item takes the backlog-filename-slug (e.g. 119-create-refine-skill), not the lifecycle-slug. |
