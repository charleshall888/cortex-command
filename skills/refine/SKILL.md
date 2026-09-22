---
name: refine
description: Take a backlog item from idea to approved spec via Clarify → Research → Spec. Stops at spec; build takes it from there. Also preps for overnight.
argument-hint: "<topic>"
---

# Refine

Clarify → Research → Spec. Ends at `status: refined` with a linked spec, ready for `/cortex-core:build`. Between phases, announce and continue without asking. Stop to ask only at the `<!-- pause: -->` markers here and in the references.

<!-- pause: refine-empty-topic-prompt question -->
Topic: $ARGUMENTS. Empty → ask for one first.

## 1. Start

```bash
cortex-refine start <input>
```

Use the fields it returns as they are. Keep `backend`, `lifecycle_slug`, and `backlog_filename_slug` for the whole run — every write-back needs them.

- `ready` → continue. `needs-slug` (Context B: no matching item) → make a short kebab slug, announce it, re-run with `--lifecycle-slug`. Exit 2 → several items match; the candidates are on stderr, let the user pick. Exit 70 → report the error and stop.
- `epic_research` / `epic_spec` set → read them as background, show any `warning`, add a `## Epic Reference` link section to `research.md` and a preamble note to `spec.md`. Never copy epic content in — it covers every child ticket.
- `resume`: `complete` → announce and skip to §5. Re-run only if the user asks; that overwrites the spec and resets `status: in_progress`. `research` → a spec exists without research: warn that overnight needs both, skip Clarify, run Research. `spec` → resume at Spec. `clarify` → start there.

## 2. Clarify

Follow `${CLAUDE_SKILL_DIR}/references/clarify.md`; carry its §5 outputs forward.

Write complexity and criticality back right away (Context A only). Every backlog write here uses this **3-arm routing** on `backend`: `cortex-backlog` → `cortex-update-item {backlog-filename-slug} --complexity {value} --criticality {value}`; `none` → skip and say so in one line; external → try per `backlog.instructions`, and show the values if it fails. Exit 2 → the ambiguous-slug rule in `${CLAUDE_SKILL_DIR}/../build/references/backlog-writeback.md`.

**Stop at `simple`** — no lifecycle needed. Say so and hand back to direct implementation (dev rule 4). Continue only at `moderate` or `complex`.

## 3. Research

Follow `${CLAUDE_SKILL_DIR}/references/research-phase.md`. Then re-check the tier against Clarify's rubric. Only if it changed: `cortex-lifecycle-event complexity-override --feature <feature> --from <old> --to <new> --reason "{tag}: <one line>"`. The reason points to the argument in `research.md`; the tag is optional, one of `reversibility:` / `exposure:` / `consequence:` / `other:`.

## 4. Spec

Reconcile first. The lifecycle state still holds pre-Clarify defaults, and specify.md §3b's critical-review check reads the reconciled values:

```bash
# Context A — reads values from backlog frontmatter
cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --backlog-slug {backlog-filename-slug} --criticality-reason "{tag}: {why}" --tier-reason "{tag}: {why}"
# Context B — passes Clarify's computed values
cortex-refine reconcile-clarify --backend {resolved} --lifecycle-slug {lifecycle-slug} --complexity {value} --criticality {value} --criticality-reason "{tag}: {why}" --tier-reason "{tag}: {why}"
```

The `--*-reason` flags are optional one-liners reusing Clarify's reasoning. Omit them rather than use placeholders.

Then follow `${CLAUDE_SKILL_DIR}/references/specify.md` in full; its orchestrator-review path is `${CLAUDE_SKILL_DIR}/../build/references/orchestrator-review.md`.

The spec-approve verb does the approval write-back itself (same 3-arm routing). Pass it `--backend {resolved}`, `--backlog-file {backlog-filename-slug}` (`""` in Context B), `--spec-path cortex/lifecycle/{lifecycle-slug}/spec.md`, `--no-emit-transition` (refine stops at spec), and areas: `--areas a b` to set, `--clear-areas` to empty, omit to keep. Areas name the main subsystem changed (standard names: `overnight-runner`, `backlog`, `skills`, `lifecycle`, `hooks`, `report`, `tests`, `docs`); 4+ with no main one → clear.

## 5. Finish

```bash
cortex-lifecycle-stage-artifacts --phase refine --feature {lifecycle-slug} --commit-subject "Refine {feature}: research and spec"
```

Use `Refine {feature}: cancelled at spec approval` when `spec.md` is absent. `config_disabled` → show `message`. `nothing_staged` → nothing to do. `staged` → the verb committed; show `commit.sha`, or on `failed` show `commit.message` and stop.

Announce the item, lifecycle directory, artifacts, fields written (`complexity`, `criticality`, `status: refined`, `spec`, `areas`), and that `/cortex-core:build {lifecycle-slug}` is next.
