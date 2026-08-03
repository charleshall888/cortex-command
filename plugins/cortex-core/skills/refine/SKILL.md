---
name: refine
description: Prepare a backlog item for execution by running it through Clarify → Research → Spec. Use when user says "/cortex-core:refine", "refine backlog item", "spec this out", or "prepare for overnight". Produces cortex/lifecycle/{slug}/research.md and spec.md, then sets status:refined on the backlog item.
when_to_use: "Use to take a ticket from idea to approved spec. Different from /cortex-core:build — refine produces research and spec and stops; build takes them through plan, implement, review, and complete. /cortex-core:dev routes to whichever the ticket's status calls for."
argument-hint: "<topic>"
---

# /cortex-core:refine

Three phases — **Clarify** (intent gate + requirements alignment), **Research** (implementation-level exploration), **Spec** (structured requirements interview). On completion: `status: refined`, linked spec, ready for `/cortex-core:build`.

Phase boundaries **auto-advance** — announce and continue, no confirmation. `<!-- pause: -->` markers, here and in the references, are the only sanctioned asks; a prior "report" or "summarize" instruction sets text cadence, not a boundary gate.

<!-- pause: refine-empty-topic-prompt question -->
Topic: $ARGUMENTS. If empty, prompt the user first.

## Step 1: Start

```bash
cortex-refine start <input>
```

One call resolves the item, reads the backlog backend, existence-checks epic context, classifies the resume point, idempotently seeds `lifecycle_start`, records the session marker, and creates `index.md`. Use its fields directly; don't re-derive them.

- **`state: ready`** — proceed. Carry `backend`, `lifecycle_slug`, and `backlog_filename_slug` through the whole run: they key the write-backs, reconcile routing, and the §3b gate.
- **`state: needs-slug`** — Context B (no matching item). Derive a short kebab slug from the input, announce it, and re-run with `--lifecycle-slug`; no confirmation needed.
- **Exit 2** — ambiguous reference; candidates are on stderr, let the user pick.
- **Exit 70** — surface and halt.

**Epic context.** `epic_research` (and `epic_spec` alongside it) are already existence-checked; relay any `warning` verbatim. **Do not copy epic content into lifecycle files** — epic research spans all tickets, so copying bleeds cross-ticket context into this one. Read it as background before Clarify, announce it, and add a `## Epic Reference` section to `research.md` plus a preamble note to `spec.md` linking the path. An epic research path never substitutes for this ticket's own `research.md`.

**Resume** branches on `resume` — judgment the CLI can't encode:

- **`complete`** — both artifacts exist; announce and skip to Step 6. Re-run only on explicit request; that overwrites the spec and resets `status: in_progress` until re-approved.
- **`research`** — spec exists without research. Warn that overnight needs both, run Research, skip Clarify (intent was set when the spec was written).
- **`spec`** — research exists; resume at Spec, where the Research Sufficiency Check applies at entry.
- **`clarify`** — neither exists; start at Clarify.

**Ordering invariant: seed → reconcile → §3b tier read.** On a non-local backend (or Context B) the seed carries the canonical `simple`/`medium` defaults, and the critical-review gate would skip silently at `tier = simple`. The gate stays alive only because Step 5's `reconcile-clarify` ratchets state up from Clarify's *computed* values before specify.md §3b reads it. The local `cortex-backlog` arm is immune either way — its `--backlog-slug` re-sources from backlog frontmatter.

## Step 2: Clarify

Follow `${CLAUDE_SKILL_DIR}/references/clarify.md`. Carry its §5 outputs forward into later phases.

Once complexity and criticality are set, write them back immediately (Context A only), gated on Step 1's backend — the canonical **backend-gated write-back routing**, the 3-arm shape every backend-gated write in this skill uses:

- **`cortex-backlog`** → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`
- **`none`** → skip with a one-line advisory
- **external** → apply the equivalent update best-effort per `backlog.instructions`; surface the values if it can't complete

Every backend still feeds the critical-review gate — Step 4's `reconcile-clarify` carries the values forward regardless. On failure, surface and wait; on exit 2, apply the ambiguous-slug rule in `${CLAUDE_SKILL_DIR}/../build/references/backlog-writeback.md`.

**Stop at `simple`.** If Clarify lands on `simple`, this work does not need a lifecycle: say so, hand back to direct implementation (dev Step 1.4), and stop — no research, no spec. Continue below only at `moderate` or `complex`.

## Step 3: Research

Follow `${CLAUDE_SKILL_DIR}/references/research-phase.md`. At the Research → Specify transition, run the complexity-escalation gate:

```bash
cortex-complexity-escalator <feature> --gate research_open_questions
```

**Advisory — it writes nothing.** Output means the unresolved-question count is unusually high; empty means it isn't. Either way *you* re-assess the tier now, with the research in hand, against Step 2's rubric. Only if your assessment changed, record it: `cortex-lifecycle-event complexity-override --feature <feature> --from <old> --to <new>` (either direction). Non-zero exit → surface stderr and halt.

## Step 4: Spec

**Reconcile first** — the seed carries pre-Clarify values, so reconcile before §3a/§3b observe them. One unconditional, idempotent call:

- **Context A**: `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug}` — re-sources from backlog frontmatter.
- **Context B**: `cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value}` — passes Clarify's computed values (the tier ratchet named in Step 1).

Then read `${CLAUDE_SKILL_DIR}/references/specify.md` and follow it in full, resolving its propagated target: orchestrator-review → `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

Do NOT set `status: refined` before approval. After approval, register the artifact with `cortex-lifecycle-register-artifact --feature {lifecycle-slug} --artifact spec`, then run the second escalation gate — same contract as Step 3:

```bash
cortex-complexity-escalator <feature> --gate specify_open_decisions
```

**Write-back on approval (Context A)** is performed *by the spec-approve verb* in-process, backend-gated exactly as Step 2's 3-arm routing is, and composed with the approval emissions — this step supplies the args, it does not call `cortex-update-item` itself. Hand the verb `--backend {resolved}`, `--backlog-file {backlog-filename-slug}` (`""` in Context B), `--spec-path cortex/lifecycle/{lifecycle-slug}/spec.md`, and areas: `--areas a b` to set, `--clear-areas` for the empty case, omit to leave them untouched (preserve-on-omit). Pass `--no-emit-transition` — refine stops at `spec.md`.

**Infer areas** by naming the primary subsystem modified — the one where most files change (canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`). Spanning 4+ with no clear primary → clear the field.

## Step 5: Completion

```bash
cortex-lifecycle-stage-artifacts --phase refine --feature {lifecycle-slug}
```

The verb reads `commit-artifacts` itself. Act on `signal`: `config_disabled` → relay its `message` and skip the commit; `nothing_staged` → exit silently; `staged` → commit. A non-zero exit is a staging failure — halt rather than commit a partial set. Commit subject from the staged set: `Refine {feature}: research and spec`, or `Refine {feature}: cancelled at spec approval` when `spec.md` is absent. If `/cortex-core:commit` exits non-zero, surface the error and halt — the uncommitted transition row waits until the operator resolves it and re-invokes.

Announce: the item, the lifecycle directory, the artifacts produced, the fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`), and that `/cortex-core:build {lifecycle-slug}` is the next step.
