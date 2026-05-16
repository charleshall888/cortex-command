---
schema_version: "1"
uuid: 4ff7b08e-d4fa-4ae0-a012-b515ef41164b
title: "Discovery output density — investigate author-centric prose at gate"
status: ready
priority: medium
type: needs-discovery
created: 2026-05-16
updated: 2026-05-16
tags: [discovery, skills, agent-output, prose-density, ux]
complexity: complex
criticality: high
session_id: null
lifecycle_phase: null
lifecycle_slug: null
discovery_source: cortex/lifecycle/archive/redesign-discovery-output-presentation/research.md
---

# Discovery output density — investigate author-centric prose at gate

## What the user noticed

> "When [`/discovery`] outputs the whole pieces and architecture section, it is very complicated and unnecessarily hard to understand. We need to get creative and go back to the drawing board on how to best present the findings and proposed structure, VALUE, the 'why' and all behind the discovery."

And later, when pushed for specifics:

> "When I see that giant block of text, it feels like it is just throwing out a bunch of technical terms and using a ton of words to say not very much. It is a slog to read. I want to see the most important information in a readable way and be presented with the information I care to know about and should answer on as the ultimate orchestrator."

The complaint is at the research→decompose approval gate of `/cortex-core:discovery`. The gate currently displays `## Headline Finding` followed by the full `## Architecture` section (Pieces / Integration shape / Seam-level edges / optionally Why-N-pieces).

## Don't read this as a small fix

A prior lifecycle, [`improve-discovery-gate-presentation`](../lifecycle/archive/improve-discovery-gate-presentation/), shipped 2026-05-12. It added `## Headline Finding` as the gate's first content section, with the authoring directive "One paragraph. State the verdict and the one or two key findings supporting it." That fix didn't land. Production Headline Findings post-fix:

| Artifact | Headline Finding word count |
|---|---|
| `cortex/research/cursor-skill-port/research.md` | 171 |
| `cortex/research/grill-me-with-docs-learnings/research.md` | 296 |
| `cortex/research/windows-support/research.md` | 317 |
| `cortex/research/interactive-overnight-mode/research.md` | 402 |

A "one paragraph" directive yielded 171-402 word paragraphs. The mechanism — tightening prose discipline via an authoring directive — didn't bind.

## What an exploratory investigation already found

A previous attempt at this work (the now-archived [`redesign-discovery-output-presentation`](../lifecycle/archive/redesign-discovery-output-presentation/) lifecycle) ran four parallel reader-perspective agents over three real discovery outputs (`cursor-skill-port`, `windows-support`, `interactive-overnight-mode`). The four agents converged on three patterns, with one quantification.

**Forward references to undefined vocabulary.** `OQ7` cited ~8 times before the Open Questions section defines it. `DR-6`, `Q1`, `Architecture B` appear in front-matter blocking decisions before any are defined. Rubric labels (`A-zero-change` / `B-content-only` / `C-behavioral-degradation`) used as if known, with the rubric itself implicit. `W6 empirical validation` shows up before the W-numbering scheme is introduced. Coined compounds presented as known patterns ("Poetry + psutil hybrid," "sentinel-+-JSON-envelope marshaling").

**Headlines that argue with themselves.** Same claim restated 3-4 times in one paragraph with negations and qualifications mid-flight. `cursor-skill-port`: "per-release cost is bounded but non-zero" appears four times. `interactive-overnight-mode`: a positive recommendation followed by "B does NOT preserve sandbox-settings-per-spawn," "B does NOT extend process-group watchdog protection" — three negations of the just-stated positive claim, all in the headline paragraph. The Headline is litigating, not summarizing.

**Author-process narration treated as content.** "Why N pieces subsection skipped per template R3 — fires only when piece_count > 5." "Decomposition history: original was 7 pieces, walked back per template rule R1 across three iterations." "(piece_count = 3; honest decomposition omits the converter/publish split that earlier drafts presented separately…)" The author's working notes about how the artifact was constructed surface into the final artifact as if they were part of the result.

**Compression test.** A plain-words rewrite of six dense passages from the three artifacts (the Headline Finding plus the densest `### Pieces` bullet from each) compressed at an average **~2.5×** with **no decision content lost** and **all honest caveats preserved**. The compression came entirely from stripping name-drops, line-number citations without anchors, `DR-N`/`OQ-N`/`§N` cross-references, and restated invariants. The full rewrites are in `cortex/lifecycle/archive/redesign-discovery-output-presentation/research.md` if you want the worked examples.

## The pattern they share

All three patterns are the same shape: **the artifacts are written for the author**. The author has the cross-reference index in working memory — `DR-6` is fine to reference because the author knows what it is. The reader doesn't. Every undefined acronym, every "see Q7," every walked-back narration, every line-number citation without a one-line gloss is the author surfacing their own construction notes as deliverable content.

Look at the current template's HTML-comment authoring directives at `skills/discovery/references/research.md`:
- `## Architecture` section asks for "named contract surfaces" / "Role / Integration / Edges" vocabulary.
- `### Why N pieces` subsection asks for the falsification-gate's merge history.
- The template asks for `DR-N` decision records, `RQ-N` research questions, `OQ-N` open questions — a numbered cross-reference scheme.

The template asks for the author's working memory. The model dutifully delivers it.

## What did NOT turn out to be the lever

The archived lifecycle tried to fix this at the gate — restructure presentation, add a new `## Decision Surface` section with five short labeled fields, suppress `## Architecture` body at gate display. Critical review caught two problems:

1. The "structured sub-fields" mechanism is still prose discipline relabeled. Markdown bullets don't cap content length; the same drift class that produced 171-402 word Headline Findings against "one paragraph" could recur at the sub-field level. Subdividing one drift-prone slot into five identically-governed slots may *increase* aggregate drift, not constrain it.
2. The user's complaint isn't about which markdown section appears at which moment. It's about how the system communicates broadly. Trying to redirect to a smaller display window doesn't fix the underlying density.

A devil's-advocate pass added: even the "suppress Architecture at gate" load-bearing change relies on the model executing a negative-routing prose instruction reliably ("do not show X"). That's exactly the class of fragile prose enforcement the project's CLAUDE.md MUST-escalation policy treats with skepticism.

## What's open for the next investigator

Don't start by speccing. The previous attempt rushed to a 16-requirement spec on round one and produced a wrong-framing artifact. The user explicitly asked for "go back to the drawing board" framing — an exploratory ask, not an implementation ask.

Some directions worth taking seriously, none of which are prescribed as the answer:

- **The template itself is what's producing the density.** The most obvious lever is trimming the template's authoring directives — drop the requirement for numbered cross-references (`DR-N` / `OQ-N`), drop the `### Why N pieces` merge-history narration, drop or rephrase the contract-name vocabulary. But: prose-only changes to the template are exactly the class of fix that didn't bind for the Headline Finding paragraph. If you go this direction, think about what would *bind* — runtime validation, lint, structural shape — not just "tighter words."
- **The decompose contract pulls in one direction; the orchestrator's reading at the gate pulls in another.** Decompose consumes `### Pieces` bullets 1:1 as ticket source material — it benefits from named contract surfaces and specific anchors. The gate-reading orchestrator doesn't. The current artifact serves both audiences with one set of content, badly. Whether to split (two artifacts, two audiences), suppress (one artifact, two views), or restructure (one artifact, one shared distillation) is open.
- **It might not be a discovery problem at all.** The same author-centric prose patterns probably show up in lifecycle research artifacts, plan artifacts, even spec artifacts. The narrow lever fixes discovery; the broader lever fixes "how skills tell agents to write." If the broader fix is feasible at reasonable scope, it's the durable shape per CLAUDE.md Solution Horizon.
- **The gate's user-blocking moment is where the density hurts most**, but the density exists in the artifact regardless of the gate. Fixing the gate without fixing the artifact preserves the slog for archival readers, the decompose-agent reader, and anyone resuming a lifecycle. Fixing the artifact without fixing the gate's instruction about *what to render* leaves a smaller pile that still gets dumped at the wrong moment.
- **There's an empirical handle.** The four-agent reader study took ~10 minutes and produced quotable evidence the user could engage with. Whatever direction the next investigation takes, periodically re-running a small reader-study against actual produced artifacts is cheap and resists drift back into author-favorable framings.

## Things to NOT do (lessons from the archived attempt)

- Don't rush to a spec. The archived lifecycle's spec was wrong-framed because the framing wasn't questioned hard enough. Stay in research / conversation longer than feels comfortable.
- Don't add more template sections without first asking whether existing sections should go. Additive fixes to a density problem compound it.
- Don't trust the "structural separation" framing for prose-rendered markdown surfaces. Markdown grammar is not structural in the load-bearing sense — bullets, sub-fields, and labels are all prose discipline at finer grain. If structural enforcement is needed, it's runtime validation or a lint, not heading levels.
- Don't write the redesign artifact densely. The archived attempt produced a 16-requirement spec densely written ABOUT density. The user explicitly called it out. The redesign should be readable on the same terms it asks of discovery outputs.

## Raw materials

- `cortex/lifecycle/archive/redesign-discovery-output-presentation/research.md` — the multi-angle research artifact, including the four-agent reader-study findings in summarized form.
- `cortex/lifecycle/archive/redesign-discovery-output-presentation/spec.md` — the wrong-framed spec, kept for reference (what not to do).
- `cortex/lifecycle/archive/redesign-discovery-output-presentation/events.log` — the full lifecycle history including the critical-review residue and the `feature_wontfix` terminal event with rationale.
- `cortex/lifecycle/archive/improve-discovery-gate-presentation/` — the prior fix (Phase 1) and its research, including the rationale for why that fix's mechanism class doesn't bind.
- `skills/discovery/references/research.md` — the current discovery research-artifact template (the surface the next investigation is most likely to want to change).
- `skills/discovery/SKILL.md:74` — the current gate prose for research→decompose, including the existing `## Headline Finding`-missing fallback that the redesign attempts shouldn't break.

## Suggested but-not-required first move

Run the reader-study yourself before forming a hypothesis. Pick 2-3 real `cortex/research/*/research.md` artifacts, send 3-4 parallel agents to read them from different perspectives (first-time cold reader, gate decision-maker, jargon hunter, plain-words rewriter), look at what comes back. The previous investigation's findings will probably reproduce, but you'll have your own evidence to ground decisions on instead of inheriting framings.
