---
name: refine
description: Take a backlog item from idea to approved spec via Clarify → Research → Spec. Stops at spec; build takes it from there. Also preps for overnight.
argument-hint: "<topic>"
---

# Refine

Clarify (intent gate) → Research → Spec. Ends at `status: refined` with a linked spec, ready for `/cortex-core:build`. Phase boundaries auto-advance — announce and continue; `<!-- pause: -->` markers here and in the references are the only sanctioned asks.

<!-- pause: refine-empty-topic-prompt question -->
Topic: $ARGUMENTS. Empty → ask for one first.

## 1. Start

```bash
cortex-refine start <input>
```

Use its fields; don't re-derive them. Carry `backend`, `lifecycle_slug`, and `backlog_filename_slug` through the run — they key every write-back.

- `ready` → proceed. `needs-slug` (Context B: no matching item) → derive a short kebab slug, announce it, re-run with `--lifecycle-slug`. Exit 2 → ambiguous; candidates are on stderr, let the user pick. Exit 70 → surface and halt.
- `epic_research` / `epic_spec` set → read them as background, relay any `warning`, add a `## Epic Reference` link section to `research.md` and a preamble note to `spec.md`. Never copy epic content in — it spans every child ticket.
- `resume`: `complete` → announce and skip to §5 (re-run only on explicit request; that overwrites the spec and resets `status: in_progress`). `research` → a spec without research: warn overnight needs both, run Research, skip Clarify. `spec` → resume at Spec. `clarify` → start there.

## 2. Clarify

Follow `${CLAUDE_SKILL_DIR}/references/clarify.md`; carry its §5 outputs forward.

Write complexity and criticality back at once (Context A only), routed on `backend` — the **3-arm routing** every backend-gated write here uses: `cortex-backlog` → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`; `none` → skip with a one-line advisory; external → best-effort per `backlog.instructions`, surfacing the values if it fails. Exit 2 → the ambiguous-slug rule in `${CLAUDE_SKILL_DIR}/../build/references/backlog-writeback.md`.

**Stop at `simple`** — no lifecycle needed: say so, hand back to direct implementation (dev rule 4), stop. Continue only at `moderate` or `complex`.

## 3. Research

Follow `${CLAUDE_SKILL_DIR}/references/research-phase.md`. Then re-assess the tier against §2's rubric with the research in hand. Only if it changed: `cortex-lifecycle-event complexity-override --feature <feature> --from <old> --to <new> --reason "{tag}: <one line>"` — a pointer to the argument in `research.md`, led by an optional tag from `reversibility:` / `exposure:` / `consequence:` / `other:`.

## 4. Spec

Reconcile first — the seed carries pre-Clarify defaults and specify.md §3b's critical-review gate reads the ratcheted state:

```bash
# Context A — re-sources from backlog frontmatter
cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug} --criticality-reason "{tag}: {why}" --tier-reason "{tag}: {why}"
# Context B — passes Clarify's computed values
cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value} --criticality-reason "{tag}: {why}" --tier-reason "{tag}: {why}"
```

The `--*-reason` flags are optional one-liners reusing Clarify's stated reasoning; omit rather than fill with placeholders.

Then follow `${CLAUDE_SKILL_DIR}/references/specify.md` in full; its orchestrator-review path is `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

Approval write-back belongs to the spec-approve verb (in-process, same 3-arm routing). Hand it `--backend {resolved}`, `--backlog-file {backlog-filename-slug}` (`""` in Context B), `--spec-path cortex/lifecycle/{lifecycle-slug}/spec.md`, `--no-emit-transition` (refine stops at spec), and areas: `--areas a b` to set, `--clear-areas` to empty, omit to preserve. Areas name the primary subsystem modified (canonical: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`); 4+ with no primary → clear.

## 5. Finish

```bash
cortex-lifecycle-stage-artifacts --phase refine --feature {lifecycle-slug}
```

`config_disabled` → relay `message`, skip the commit. `nothing_staged` → nothing. `staged` → commit as `Refine {feature}: research and spec`, or `Refine {feature}: cancelled at spec approval` when `spec.md` is absent. Non-zero exit from staging or commit → surface and halt.

Announce the item, lifecycle directory, artifacts, fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`), and that `/cortex-core:build {lifecycle-slug}` is next.
