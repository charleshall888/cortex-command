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

Prepares a single backlog item for execution through three phases: **Clarify** (intent gate + requirements alignment), **Research** (implementation-level exploration), **Spec** (structured requirements interview). On completion: `status: refined`, linked spec, ready to plan.

Topic: $ARGUMENTS (backlog item slug, title, or description). If empty, prompt the user first.

## Step 1: Resolve Input

```bash
cortex-resolve-backlog-item <input>
```

Unique match → JSON (`filename`, `backlog_filename_slug`, `title`, `lifecycle_slug`); use it directly, don't re-derive the slugs. Ambiguous → candidates on stderr; let the user pick. No match → ad-hoc Context B (per `${CLAUDE_SKILL_DIR}/references/clarify.md` §1); if prose rather than a kebab slug, derive a short kebab `{lifecycle-slug}`, announce it, proceed without confirming. Hard error → surface the resolver's message and halt.

## Step 2: Check State

Resolve the resume point (read-only):

```bash
cortex-refine resume-point --lifecycle-slug {lifecycle-slug}
```

Branch on the returned `resume` (`clarify | research | spec | complete`) — judgment the CLI can't encode:

- **`complete`** — both artifacts exist; announce, skip to Step 6, no prompt. Re-run only on explicit request ("re-run refine", "redo the spec") — overwrites the spec, resets `status: in_progress` until re-approved.
- **`research`** — spec.md exists, research.md missing. Warn overnight needs both, run Research, skip Clarify (intent was set when the spec was written).
- **`spec`** — research.md exists, no spec; resume at Spec, where the Research Sufficiency Check (`clarify.md` §6) applies at entry.
- **`clarify`** — neither exists; start at Clarify.

**Resolve the backlog backend once** with `cortex-read-backlog-backend` (no args) and carry it through refine — it keys the seed, write-back, reconcile routing, and gates the §3b decision.

Then seed the `lifecycle_start` row so it precedes every other event (idempotent, safe on resume — one unconditional call passing the backend):

```bash
cortex-refine emit-lifecycle-start --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}
```

Omit `--backlog-slug` for Context B, otherwise always pass it — the verb's `--backend` guard, not this call site, owns the non-local slug-drop.

**Tier ratchet ordering invariant**: keep the seed → reconcile → §3b-read ordering so the §3b read observes the **tier ratchet**'s output, not the seed default. Rationale and the tier-ratchet definition: `${CLAUDE_SKILL_DIR}/references/seed-reconcile-gate-ordering.md`.

## Step 3: Clarify Phase

Read `${CLAUDE_SKILL_DIR}/references/clarify.md` and follow its full protocol (§2–§7). Requirements loading uses the shared protocol at `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`. Carry its §5 outputs forward into later phases.

Once complexity and criticality are set, run the write-back immediately (Context A only), gated on the Step-2 backend — the canonical **backend-gated write-back routing**, the 3-arm shape Step 5's Write-Back also uses (each site supplies its own fields):

- **`cortex-backlog`** → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
- **`none`** → skip with a one-line advisory that write-back is disabled for this repo.
- **external** → apply the equivalent complexity/criticality update best-effort per `backlog.instructions`; surface the values if it can't complete.

Every backend still feeds the critical-review gate — Step 5's `reconcile-clarify` carries Clarify's tier/criticality forward regardless. On `cortex-update-item` failure, surface and wait; on exit 2, apply backlog-writeback.md's ambiguous-slug handling.

## Step 4: Research Phase

Read `${CLAUDE_SKILL_DIR}/references/research-phase.md` and follow it — sufficiency check, alignment-considerations propagation, research dispatch, and exit gate.

## Step 5: Spec Phase

**Reconcile lifecycle state to the Clarify assessment first** — the `lifecycle_start` seed carries pre-Clarify tier/criticality; reconcile so §3a/§3b observe the Clarify-assessed values. One unconditional call passing `--backend {resolved}`; remaining flags follow item-existence context (per Step 2's `--backend` guard):

- **Context A** (local item): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources tier/criticality from backlog frontmatter.
- **Context B** (no item): `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes **Clarify's computed** values. On a non-local backend this is the **tier ratchet** (Step 2's ordering invariant) that keeps the critical-review gate fed.

Idempotent — safe on resume; no-op under `/cortex-core:lifecycle`.

Read `${CLAUDE_SKILL_DIR}/references/specify.md` and follow its full protocol — the refine-context notes are inlined there at §1 (skip redundant requirements loading), §3b (trust the state read; `corrupted: true` runs the gate), §4 (complexity/value gate), and §5 (skip the `phase_transition` emission). Its §3a/§3b gates and criticality matrix reference "the propagated `<target>` path"; standalone refine has no lifecycle manifest, so resolve them here: orchestrator-review → `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`, critical-review-gate → `${CLAUDE_SKILL_DIR}/../lifecycle/references/critical-review-gate.md`, criticality-matrix → `${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md`.

Do NOT set `status: refined` before approval. After approval (specify.md §4), register the spec artifact: `cortex-lifecycle-register-artifact --feature {lifecycle-slug} --artifact spec`.

### Write-Back on Approval (Context A only)

**Infer areas**: name the primary subsystem modified (canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`) — the one where most files change. Spanning 4+ with no clear primary → `areas=[]`.

Route these status/spec/areas write-backs through Step 3's canonical backend-gated write-back routing (the 3-arm shape), this site's fields. On `cortex-backlog`:

```bash
cortex-update-item {backlog-filename-slug} --status refined --spec cortex/lifecycle/{lifecycle-slug}/spec.md
cortex-update-item {backlog-filename-slug} --areas area1 area2
```

Empty areas: `cortex-update-item {backlog-filename-slug} --areas` (passing `--areas` with no values clears the list). The `none`/external arms and failure handling match Step 3.

## Step 6: Completion

Announce refine is complete: the item (`{backlog-filename-slug}`), the lifecycle directory (`cortex/lifecycle/{lifecycle-slug}/`), the artifacts produced (research.md, spec.md), and the backlog fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`).

## Constraints

| Thought | Reality |
|---------|---------|
| "Use the lifecycle-slug as the cortex-update-item argument" | cortex-update-item takes the backlog-filename-slug (e.g. 119-create-refine-skill), not the lifecycle-slug. |
| "Use the lifecycle-slug as the cortex-load-parent-epic argument" | cortex-load-parent-epic takes the backlog-filename-slug too — the lifecycle-slug returns `not found`. |
