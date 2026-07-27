---
name: refine
description: Prepare a backlog item for execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "spec this out", or "prepare for overnight". Produces cortex/lifecycle/{slug}/research.md and spec.md, then sets status:refined on the backlog item.
when_to_use: "Use to take a ticket from idea to approved spec. Different from /cortex-core:build — refine produces research and spec and stops; build takes them through plan, implement, review, and complete. /cortex-core:dev routes to whichever the ticket's status calls for."
argument-hint: "<topic>"
---

# /cortex-core:refine

Three phases — **Clarify** (intent gate + requirements alignment), **Research** (implementation-level exploration), **Spec** (structured requirements interview). On completion: `status: refined`, linked spec, ready for `/cortex-core:build`.

<!-- pause: refine-empty-topic-prompt question -->
Topic: $ARGUMENTS. If empty, prompt the user first.

## Step 1: Resolve the item

```bash
cortex-resolve-backlog-item <input>
```

Unique match → use the returned `filename`, `backlog_filename_slug`, `title`, `lifecycle_slug` directly; don't re-derive the slugs. Ambiguous → candidates on stderr, let the user pick. No match → ad-hoc Context B; if the input is prose rather than a kebab slug, derive a short kebab `{lifecycle-slug}`, announce it, and proceed without confirming. Hard error → surface and halt.

**Epic context.** From the item's frontmatter take `discovery_source` (falling back to `research`) as the epic research path, recording it only if the file exists — warn and treat as unset otherwise; record `spec` as the epic spec path only alongside a recorded, existing research path. **Do not copy epic content into lifecycle files** — epic research spans all tickets, so copying bleeds cross-ticket context into this one. Read it as background before Clarify, announce it, and add a `## Epic Reference` section to `research.md` plus a preamble note to `spec.md` linking the path. A `discovery_source` pointing at epic research elsewhere never substitutes for this ticket's own `research.md`.

## Step 2: Resume point and seeding

```bash
cortex-refine resume-point --lifecycle-slug {lifecycle-slug}
```

Branch on `resume` — judgment the CLI can't encode:

- **`complete`** — both artifacts exist; announce and skip to Step 6. Re-run only on explicit request; that overwrites the spec and resets `status: in_progress` until re-approved.
- **`research`** — spec exists without research. Warn that overnight needs both, run Research, skip Clarify (intent was set when the spec was written).
- **`spec`** — research exists; resume at Spec, where the Research Sufficiency Check applies at entry.
- **`clarify`** — neither exists; start at Clarify.

Resolve the backend once with `cortex-read-backlog-backend` and carry it through — it keys the seed, the write-backs, reconcile routing, and the §3b gate. Then seed `lifecycle_start` so it precedes every other event (idempotent, safe on resume):

```bash
cortex-refine emit-lifecycle-start --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}
```

Omit `--backlog-slug` for Context B; otherwise always pass it — the verb's `--backend` guard owns the non-local slug-drop, not this call site.

**Ordering invariant: seed → reconcile → §3b tier read.** On a non-local backend (or Context B) the seed carries the canonical `simple`/`medium` defaults, and the critical-review gate would skip silently at `tier = simple`. The gate stays alive only because Step 5's `reconcile-clarify` ratchets state up from Clarify's *computed* values before specify.md §3b reads it. The local `cortex-backlog` arm is immune either way — its `--backlog-slug` re-sources from backlog frontmatter.

## Step 3: Clarify

Follow `${CLAUDE_SKILL_DIR}/references/clarify.md`. Carry its §5 outputs forward into later phases.

Once complexity and criticality are set, write them back immediately (Context A only), gated on the Step-2 backend — the canonical **backend-gated write-back routing**, the 3-arm shape every backend-gated write in this skill uses:

- **`cortex-backlog`** → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
- **`none`** → skip with a one-line advisory
- **external** → apply the equivalent update best-effort per `backlog.instructions`; surface the values if it can't complete

Every backend still feeds the critical-review gate — Step 5's `reconcile-clarify` carries the values forward regardless. On failure, surface and wait; on exit 2, apply the ambiguous-slug rule in `${CLAUDE_SKILL_DIR}/../build/references/backlog-writeback.md`.

## Step 4: Research

Follow `${CLAUDE_SKILL_DIR}/references/research-phase.md`. At the Research → Specify transition, run the complexity-escalation gate:

```bash
cortex-complexity-escalator <feature> --gate research_open_questions
```

Exit 0 with output → announce the escalation and proceed at Complex tier. Exit 0 empty → the gate didn't fire; proceed at the current tier. Non-zero → surface stderr and halt the transition until resolved.

## Step 5: Spec

**Reconcile first** — the seed carries pre-Clarify values, so reconcile before §3a/§3b observe them. One unconditional call:

- **Context A**: `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources from backlog frontmatter.
- **Context B**: `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes Clarify's computed values (the tier ratchet named in Step 2).

Idempotent; safe on resume.

Then read `${CLAUDE_SKILL_DIR}/references/specify.md` and follow it in full, resolving its propagated target: orchestrator-review → `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

Do NOT set `status: refined` before approval. After approval, register the artifact: `cortex-lifecycle-register-artifact --feature {lifecycle-slug} --artifact spec`, then run the second escalation gate — same contract as Step 4:

```bash
cortex-complexity-escalator <feature> --gate specify_open_decisions
```

**Write-back on approval (Context A)** is performed *by the spec-approve verb* in-process, backend-gated exactly as Step 3's 3-arm routing is, and composed with the approval emissions — this step supplies the args, it does not call `cortex-update-item` itself. Hand the verb `--backend {resolved}`, `--backlog-file {backlog-filename-slug}` (`""` in Context B), `--spec-path cortex/lifecycle/{lifecycle-slug}/spec.md`, and areas: `--areas a b` to set, `--clear-areas` for the empty case, omit to leave them untouched (preserve-on-omit). Pass `--no-emit-transition` — refine stops at `spec.md`.

**Infer areas** by naming the primary subsystem modified — the one where most files change (canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`). Spanning 4+ with no clear primary → clear the field.

## Step 6: Completion

Run `cortex-read-commit-artifacts`: `false` → skip the commit silently; `true` → `cortex-lifecycle-stage-artifacts --phase refine --feature {lifecycle-slug}`, then act on its `signal` (`nothing_staged` → exit silently; `staged` → commit). A non-zero verb exit is a staging failure — halt rather than commit a partial set. Commit subject from the staged set: `Refine {feature}: research and spec`, or `Refine {feature}: cancelled at spec approval` when `spec.md` is absent. If `/cortex-core:commit` exits non-zero, surface the error and halt — the uncommitted transition row waits until the operator resolves it and re-invokes.

Announce: the item, the lifecycle directory, the artifacts produced, the fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`), and that `/cortex-core:build {lifecycle-slug}` is the next step.

> `cortex-update-item` and `cortex-load-parent-epic` both take the **backlog-filename slug** (e.g. `119-create-refine-skill`), never the lifecycle slug — the lifecycle slug returns `not found`.
