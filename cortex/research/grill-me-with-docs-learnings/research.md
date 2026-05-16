# Research: grill-me-with-docs-learnings

## Headline Finding

Pocock's `/grill-with-docs` (the YouTube source) introduces a small set of patterns that compose into a coherent **progressive-disclosure system** for the project's existing requirements/lifecycle structure. Adopt three of them now and one with a clearly-named caveat:

1. **Better requirements interview cadence** — one question at a time, recommend an answer before asking, code-vs-claim cross-reference moved from end-of-interview to during-interview, per-requirement scenario stress-test. Lands as in-place edits to `skills/requirements-gather/SKILL.md` and `skills/lifecycle/references/specify.md` §2. Soft-positive-routing only.

2. **Project glossary** at `cortex/requirements/glossary.md`, with Pocock's `CONTEXT-FORMAT.md` discipline applied per-entry: tight one-sentence definitions, opinionated naming with `_Avoid_:` aliases, only project-specific concepts (general programming words excluded). Following Pocock's producer-consumer separation: written inline by the cadence-uplifted interview surfaces (`/cortex-core:requirements` and `/cortex-core:lifecycle` Spec phase) when terms resolve; read by all other skills that load requirements. The act of writing tight definitions IS the audit — terms that can't survive Pocock's discipline get cut from skills entirely (replaced with plain prose) instead of admitted to the glossary.

3. **ADR system** at `docs/adr/` as the progressive-disclosure layer for `cortex/requirements/project.md` and area docs (`pipeline.md`, `multi-agent.md`, `observability.md`, `remote-access.md`). Today the requirements files carry the *rules* but not the *why* — the why is implied or scattered across commit messages and archived spec.md files. ADRs (one paragraph each, Pocock's three-criteria emission gate) make the why grep-able as one searchable log. Three seeds from existing CLAUDE.md prose so the directory is born content-bearing. Consumer-rule prose (use ADR vocabulary, flag conflicts) lives in `docs/adr/README.md` rather than in maintained indices per area doc — Pocock's `domain.md` template equivalent.

4. **Held with named caveat** — Pocock's interrupt-driven behaviors (challenge-against-glossary mid-sentence, propose-canonical-term when user is vague, surface code contradictions in real time). These are written as imperatives that conflict with CLAUDE.md's MUST-escalation policy; we don't yet have evidence that softer phrasing produces the same behavior. Held pending an evidence-gathering exercise.

The whole system makes the existing layered requirements/area structure cohere instead of fragment: `project.md` keeps the rule, `glossary.md` defines the words, ADRs carry the why, area docs carry operational detail. Each layer answers exactly one question. Two discipline rules prevent drift: no-content-duplication-across-layers and ADR status frontmatter. Maintenance follows Pocock's posture: lazy file creation, one producer surface (the cadence-uplifted interview) writes; all consumers have a vocabulary-or-signal prose rule.

## Research Questions

1. **Failure-mode coverage** → **Partially covered.** `/requirements-gather` has codebase-trumps-interview and recommend-before-asking [`skills/requirements-gather/SKILL.md:24-33`]. `lifecycle/specify` has a Verification check, Research cross-check, and Open-Decision Resolution that surface code-vs-claim contradictions [`skills/lifecycle/references/specify.md:74-90`]. `/critical-review` runs adversarial reviewers on plan/spec/research artifacts [`skills/critical-review/SKILL.md:18`]. Gaps Pocock's grill-with-docs targets that we don't address: (a) no shared vocabulary artifact (Pocock: `CONTEXT.md`); (b) no inline (mid-interview) artifact updates; (c) no fuzzy-language sharpening (interrupt-driven, held); (d) no progressive-disclosure layer for the *why* behind Architectural Constraints (Pocock: ADRs).
2. **Net-new patterns** → **(a) Cadence/posture** (Tier 1) — relentless one-at-a-time grilling [`grill-with-docs/SKILL.md:9`], scenario stress-tests, repositioning Verification check to during-interview. **(b) Artifacts** (Tier 1) — glossary at `cortex/requirements/glossary.md`, ADRs at `docs/adr/000N-*.md`. **(c) Interrupt-driven behaviors** (held) — challenge-against-glossary, fuzzy-language sharpening; require evidence per CLAUDE.md MUST-escalation policy. **(d) Composition** — Pocock's `/triage` invokes `/grill-with-docs` as a sub-step [`triage/SKILL.md:18`]; we already do this with `/critical-review` invoked by `/refine` Step 5 [`skills/refine/SKILL.md:147`].
3. **Glossary feasibility** → **Yes, with format-discipline-as-audit.** First-pass research recommended a glossary based on raw jargon density. Critical-review pushed back that the density is largely invented procedural nouns that should be cut, not catalogued. User judgment correctly held both truths: cataloging genuine vocabulary AND cutting invented scaffolding are compatible goals. The synthesis: apply Pocock's `CONTEXT-FORMAT.md` rules per-entry as the discipline gate. Terms that fit the format (one-sentence definition, what-it-IS-not-what-it-does, project-specific not general-programming) become entries; terms that can't fit get cut from their source skills (replaced with plain prose). The glossary file's discipline IS the audit — no separate audit project needed.
4. **ADR gap analysis** → **Real gap; ADRs land as the progressive-disclosure layer.** `cortex/requirements/project.md` Architectural Constraints captures shipped rules in one-line form (e.g., "File-based state: Lifecycle, backlog, pipeline, sessions in plain files. No database." [`cortex/requirements/project.md:27`]) with the *why* compressed out by the 1200-token budget [`skills/requirements-write/SKILL.md`]. The why is currently scattered across commit messages and archived `cortex/lifecycle/<feature>/spec.md` files — durable in the bit-rot sense but not searchable as a decision log. ADRs (Pocock's single-paragraph format permits trivial seeding) fill this layer. Three seeds whose rationale already exists in CLAUDE.md prose: file-based state over database, wheel+plugins distribution, MUST-escalation requires effort=high evidence. **Premise-unverified**: I did not check `docs/policies.md` for current ADR-shaped content [`premise-unverified: not-searched`].
5. **Authoring-style compatibility** → **Cadence-only is viable; interrupt-driven is unproven.** Pocock's imperative-tense `<what-to-do>` blocks translate cleanly to soft positive-routing for cadence behaviors that encode passive preconditions. They do **not** translate cleanly for spontaneous-injection behaviors (challenge-against-glossary, fuzzy-language sharpening, real-time code contradiction surfacing) — these require the agent to mid-turn detect a condition and break its conversational flow. Per CLAUDE.md MUST-escalation policy, a soft-routing translation cannot be classified as "viable" without effort=high (and possibly xhigh) dispatch evidence on a representative case. Tier 1 ships cadence-only; the interrupt-driven half is queued behind documented evidence prerequisites.
6. **Leverage ranking** → **Tier 1 (ship now)**: cadence/posture refresh in two skills + glossary at `cortex/requirements/glossary.md` (format-disciplined, inline-write at both interview surfaces) + ADR mechanism at `docs/adr/` with 3 seed ADRs from existing prose and consumer-rule prose in the policy doc. **Held**: interrupt-driven behaviors pending effort=high evidence. **Not recommended**: standalone `/grill` skill (DR-4); maintained per-area "Related ADRs" indices (Pocock's `domain.md` consumer-rule posture is the simpler equivalent).

## Codebase Analysis

### What we already absorbed from Pocock's earlier patterns

- **Recommend-before-asking** is canonical in `/requirements-gather`: every question carries a `**Recommended answer:**` line [`skills/requirements-gather/SKILL.md:27-29`].
- **Codebase-trumps-interview** is canonical in `/requirements-gather`: "Before drafting a question, decide whether the answer is recoverable from code … reserve interview questions for intent, priorities, scope boundaries, and non-functional bars" [`skills/requirements-gather/SKILL.md:24-25`].
- **Lazy artifact creation** is canonical: Q&A block held in conversation context until `/requirements-write` synthesizes [`skills/requirements-gather/SKILL.md:31-33`].
- The frontmatter explicitly attributes these to Pocock [`skills/requirements-gather/SKILL.md:3`].

### Existing requirements/area structure (the layered system Tier 1 plugs into)

- `cortex/requirements/project.md` — top-level rules at 1200-token cap [`skills/requirements-write/SKILL.md:36`]. Sections: Overview, Philosophy of Work, Architectural Constraints, Quality Attributes, Project Boundaries (In/Out/Deferred), Conditional Loading (trigger-phrase → area-doc map), Optional.
- `cortex/requirements/{area}.md` — operational specs for one subsystem, no token cap. Areas observed: `multi-agent.md`, `observability.md`, `pipeline.md`, `remote-access.md`.
- Conditional loading via tag-based protocol at `skills/lifecycle/references/load-requirements.md` — area docs load only when triggered by skills that match their tags.
- The 1200-token budget on `project.md` actively forces the *why* to be compressed out of Architectural Constraints. This is the gap ADRs fill: the rule stays terse and always-loaded; the rationale moves to a paragraph in `docs/adr/000N-*.md`, loaded on-demand.

### Failure modes our existing surfaces partially address

- **Code-vs-claim contradictions**: `lifecycle/specify` §2b Verification check [`skills/lifecycle/references/specify.md:74-83`] mandates that any spec claim about code be verified against actual code. Four sub-checks: git command syntax, function behavior, file paths, state ownership. This covers Pocock's "cross-reference with code" partially — but only at the *end* of the interview (pre-write), not actively during. Tier-1 work moves this posture into the interview.
- **Research-cross-check**: `lifecycle/specify` §2b re-reads `research.md` to catch silent omissions [`skills/lifecycle/references/specify.md:84`].
- **Adversarial review**: `/critical-review` dispatches 3-4 parallel reviewers on distinct angles [`skills/critical-review/SKILL.md:51-61`].

### Failure modes our surfaces do NOT address (and Tier-1 response)

- **Terminology drift across sessions**: addressed by Tier-1 glossary, with format-discipline-as-audit per RQ-3.
- **Project-wide durable decision log**: addressed by Tier-1 ADR seed-now per RQ-4. `NOT_FOUND(query="docs/adr|adr/", scope=".")`.
- **Inline (mid-interview) artifact updates** for the glossary specifically: scoped to a separate evidence question — Pocock writes inline; we have a "lazy-artifact-creation" tradition. Resolution proposed in DR-2 below.
- **Active fuzzy-language sharpening** and other interrupt-driven behaviors: held per DR-5.

### Jargon density evidence (re-interpreted)

Sample read of `skills/lifecycle/references/specify.md` introduces 15+ project-specific terms in 184 lines: Sufficiency Check, loop-back, C1/C2/C3 signals, confidence_check event, current_cycle, Verification check, Research cross-check, Open Decision Resolution, A→B downgrade rubric (cross-ref), READ_OK sentinel (cross-ref), Specify Phase, Hard Gate, phase_transition event, lifecycle_cancelled event, complexity-value gate. Sample read of `skills/critical-review/SKILL.md` adds: artifact_sha256 / sentinel-first verification gate / Phase 1 / Phase 2 / record-exclusion / residue write / A-class / B-class / through-lines / tensions / concerns. CLAUDE.md adds OQ3, OQ6, MUST-escalation, F-row, soft positive-routing, dispatch effort=high/xhigh, dual-source enforcement, parity gate, two-mode gate. **Re-interpreted role**: this density is the *input* to the glossary's per-entry discipline check. Per Pocock's `CONTEXT-FORMAT.md` rules, each candidate term is classified as: (a) **Contract** (subagent sentinel like `READ_OK`, CLI subcommand like `record-exclusion`, event name like `phase_transition`) — keep as contract; document at definition site, glossary entry optional. (b) **Compressing reference** (used 5+ times across files) — glossary entry with tight definition. (c) **Author scaffolding** (used 1-2 times, no contract) — cut from skill, replaced with plain prose; no glossary entry. (d) **Genuinely-domain term** — glossary entry, cross-referenced from area docs.

## Web & Documentation Research

### `/grill-with-docs` canonical behavior (verbatim from `mattpocock/skills`)

- **One question at a time, recommend then wait** [`grill-with-docs/SKILL.md:7-9`]: "Interview me relentlessly … For each question, provide your recommended answer. Ask the questions one at a time, waiting for feedback on each question before continuing." (Tier 1.)
- **Code over interview** [`grill-with-docs/SKILL.md:11`]: "If a question can be answered by exploring the codebase, explore the codebase instead." (Already adopted.)
- **Lazy file creation** [`grill-with-docs/SKILL.md:38`]: "Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved." (Already adopted as a pattern; applied to glossary in DR-2.)
- **Challenge against the glossary** [`grill-with-docs/SKILL.md:44-46`]: "When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately." (Held — interrupt-driven; requires evidence per MUST-escalation per DR-5.)
- **Sharpen fuzzy language** [`grill-with-docs/SKILL.md:48-50`]: "When the user uses vague or overloaded terms, propose a precise canonical term." (Held — interrupt-driven.)
- **Discuss concrete scenarios** [`grill-with-docs/SKILL.md:52-54`]: (Tier 1 — fits as a non-interrupt-driven posture: "for each requirement, invent one edge-case scenario before asking acceptance criteria.")
- **Cross-reference with code** [`grill-with-docs/SKILL.md:56-58`]: (Tier 1 — moved from pre-write to during-interview as a passive posture: "as you ask each requirement, also cite the code path that would be modified.")
- **Update CONTEXT.md inline** [`grill-with-docs/SKILL.md:60-64`]: (DR-2 below — recommendation: hybrid Option 3.)
- **ADR three-criteria emission gate** [`grill-with-docs/SKILL.md:68-78`]: "Only offer to create an ADR when all three are true: 1. Hard to reverse 2. Surprising without context 3. The result of a real trade-off." (Tier 1 — adopted as the seed-criteria for the 3 ADR-seeds and as the emission rule for new ADRs.)

### `CONTEXT-FORMAT.md` discipline rules (the audit, embedded in the format)

- **"Be opinionated."** When multiple words exist for the same concept, pick the best one and list the others as aliases to avoid.
- **"Flag conflicts explicitly."** If a term is used ambiguously, call it out in "Flagged ambiguities" with a clear resolution.
- **"Keep definitions tight."** One sentence max. Define what it IS, not what it does.
- **"Show relationships."** Use bold term names and express cardinality where obvious.
- **"Only include terms specific to this project's context."** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this context, or a general programming concept? Only the former belongs.
- **"Group terms under subheadings"** when natural clusters emerge.
- **"Write an example dialogue."** A conversation that demonstrates how the terms interact naturally.

These rules — particularly the "tight definition" + "project-specific only" rules — function as a per-entry audit gate. A term that can't survive them is scaffolding, not vocabulary.

### `ADR-FORMAT.md` (Tier 1)

- Path: `docs/adr/0001-slug.md`, sequentially numbered.
- Body: 1-3 sentences. "An ADR can be a single paragraph. The value is in recording *that* a decision was made and *why* — not in filling out sections."
- Optional sections: Status frontmatter (`proposed | accepted | deprecated | superseded by ADR-NNNN`), Considered Options, Consequences — included only when adding genuine value.
- Three-criteria gate is the discipline; without it the directory accumulates noise.
- Pocock's stripping (vs. Nygard's heavier original ADR template) optimizes for low write-friction so the discipline survives. Aligns with `cortex/requirements/project.md:23`'s "ship faster, not be a project" quality bar.

### Multi-context support and Cortex's choice

Pocock supports `CONTEXT-MAP.md` at root for multi-context repos pointing at per-context `CONTEXT.md` and per-context `docs/adr/`. Cortex doesn't have bounded contexts in the DDD sense — its "areas" (pipeline, multi-agent, observability, remote-access) are aspects of one workflow toolkit that share concepts (lifecycle, dispatch, sandbox) across each other. **Recommendation**: flat `docs/adr/` with `area:` and `status:` frontmatter; single `cortex/requirements/glossary.md` with optional H3 grouping by area for navigation. Per-area folders would create artificial boundaries you'd then constantly cross.

### `/grill-me` (the productivity-bucket simpler form)

Total skill body is ~3 sentences [`productivity/grill-me/SKILL.md`]: relentless one-at-a-time interview, walk decision tree, recommend-before-asking, code-over-interview. No artifacts. Used for non-code contexts. Cited here as evidence that Pocock's full-body skill is unusually short — the Tier-1 cadence/posture edits should aspire to similar compactness.

### Composition pattern

`/triage` Step 4 [`engineering/triage/SKILL.md:104-106`]: "Grill (if needed). If the issue needs fleshing out, run a `/grill-with-docs` session." Demonstrates that grill is intended as a callable sub-skill. Our parallel: `/refine` Step 5 invokes `/critical-review` after spec is drafted [`skills/refine/SKILL.md:147`]; `lifecycle/specify` §3b invokes `/critical-review` for complex tier [`skills/lifecycle/references/specify.md:147-151`].

### `/to-prd` (synthesize-only sibling, key consumer signal)

"Do NOT interview the user — just synthesize what you already know." [`engineering/to-prd/SKILL.md:7`]. Explicit input: "Use the project's domain glossary vocabulary throughout the PRD, and respect any ADRs in the area you're touching" [`engineering/to-prd/SKILL.md:13`]. Confirms Pocock treats glossary + ADRs as **shared context for downstream skills**. Our parallel consumer is `lifecycle/specify` reading `research.md` and area requirements.

## Domain & Prior Art

### Eric Evans / DDD "Ubiquitous Language"

Pocock's `CONTEXT.md` is the engineering-skills version of Evans' Ubiquitous Language pattern. The `_Avoid_:` line (aliases to drop) is a Pocock addition; the `## Flagged ambiguities` section maps to DDD's "linguistic friction signals" [`premise-unverified: not-searched` — claim is from general DDD knowledge, not a verified citation]. Cortex's "domain" is its own internal authoring patterns rather than an external problem domain — the Ubiquitous Language analogy holds, but the vocabulary is meta (talking about how the agent works) rather than first-order.

### ADRs (Michael Nygard, ~2011)

Nygard's original ADR proposal was structured (Status / Context / Decision / Consequences). Pocock's deliberate stripping ("an ADR can be a single paragraph") is a meaningful divergence — he optimizes for low write-friction so the discipline survives, at the cost of structural consistency. This trade-off matches our own "ship faster, not be a project" quality bar in `cortex/requirements/project.md:23`.

### Comparison with our discovery's `## Decision Records` block

`skills/discovery/references/research.md:165-172` already prescribes a `## Decision Records` block with `DR-N` items containing Context / Options considered / Recommendation / Trade-offs. This is closer to Nygard's full structure than Pocock's stripped form. The Cortex DR block is **scoped to a single research artifact** — it captures decisions made *during* discovery research, not durable project-wide decisions. ADRs (Tier 1) are complementary, not redundant.

### The "agent reads cold context" phenomenon

Pocock motivates the glossary on token-efficiency grounds: "agents are usually dropped into a project and asked to figure out the jargon as they go. So they use 20 words where 1 will do." For Cortex, the cold-context cost is amplified by routine subagent dispatch (`/critical-review` reviewers, parallel research agents, overnight runner sessions). A short shared glossary amortizes cheaply across cold reads. This benefit is **independent** of any authoring-discipline concerns — the glossary is valuable because it reduces re-learning per session, not just because it documents irreducible vocabulary.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Cadence/posture refresh** in `/requirements-gather` + `lifecycle/specify` (one-at-a-time, scenario stress-tests, code-vs-claim during-interview) | S | Prose churn in two SKILL.md files. Soft-positive-routing translation must avoid new MUSTs (CLAUDE.md MUST-escalation policy). Limited to behaviors with passive-precondition encoding — interrupt-driven behaviors held in Approach E. | None |
| **B. Glossary at `cortex/requirements/glossary.md`** with Pocock's CONTEXT-FORMAT discipline applied per-entry, inline-write rule at both interview surfaces | M | Per-entry discipline must be enforced — without it the glossary fills with author-scaffolding terms that should have been cut from skills. Mitigation: per-entry classifier prose in the cadence-uplifted interview prompts. Conditional loading via tag-based protocol at `skills/lifecycle/references/load-requirements.md` needs a small extension (always-load sentinel OR a global-context tag). Consumer-rule prose in `lifecycle/specify` and `critical-review` ("use vocabulary or signal a gap"). | Decision on how to wire into load-requirements.md |
| **C. ADR mechanism + 3 seeds** at `docs/adr/` + `docs/adr/README.md` policy doc with consumer-rule prose | S | 3 seeds synthesized from existing CLAUDE.md prose (file-based state; wheel+plugins distribution; MUST-escalation evidence rule). Status + area frontmatter required from day one. ADR emission rule (three-criteria gate) added to `lifecycle/specify` §2b. Discoverability across area docs handled by consumer-rule prose ("grep area: frontmatter") rather than maintained per-area indices, per Pocock's `domain.md` posture. | None — Architecture retired migration; seeds are synthesis-and-attribution only |
| **D. Held: interrupt-driven behaviors** (challenge-against-glossary, fuzzy-language sharpening) | unknown | Per CLAUDE.md MUST-escalation policy: requires effort=high (and xhigh) dispatch evidence on a representative case before being classified translatable. Separate evidence-gathering item (DR-5). | An evidence-gathering exercise (not yet scoped) |
| **E. New `/grill` skill** | M | Duplicates `/critical-review` (artifact stress-test) and `/refine` Spec phase (interview-style requirements gathering). High risk of confusing the routing surface in `/cortex-core:dev`. | Not recommended (DR-4) |

## Architecture

The Tier-1 system is a **layered progressive-disclosure stack** built on top of the existing requirements/area structure. Each layer answers exactly one question:

| Layer | What it answers | Loaded when |
|-------|----------------|-------------|
| `cortex/requirements/project.md` | What's the rule? | Always |
| `cortex/requirements/glossary.md` | What does this word mean? | Always (small) |
| `docs/adr/000N-*.md` | Why was this decision made? | On-demand (linked from project.md / area docs / specs) |
| `cortex/requirements/{area}.md` | How does this subsystem work? | Conditionally, by tag |

### Pieces

- **Cadence/posture uplift (Tier 1)** — Edits to `skills/requirements-gather/SKILL.md` and `skills/lifecycle/references/specify.md` (§2): explicit one-question-at-a-time gating, per-requirement scenario stress-test prompts, repositioning the existing Verification check (`lifecycle/specify` §2b) from pre-write gate to during-interview posture. All translations stay in soft-positive-routing form — no new MUSTs, no interrupt-driven assertions.
- **Glossary (Tier 1)** — New file at `cortex/requirements/glossary.md` following Pocock's `CONTEXT-FORMAT.md` structure (`## Language` with bolded terms + tight definitions + `_Avoid_:` aliases, `## Relationships` cardinality bullets, `## Example dialogue`, `## Flagged ambiguities`). Per-entry discipline applied via four-bucket classifier (Contract / Compressing reference / Author scaffolding / Genuinely-domain term) — author scaffolding gets cut from source skills instead of catalogued. Inline-write rule applied at both interview surfaces (`/cortex-core:requirements` and `/cortex-core:lifecycle` Spec phase via `/cortex-core:refine`). Lazy file creation on first term. Consumer-rule prose lands in `lifecycle/specify` and `critical-review` reviewer-prompt context: "use glossary vocabulary; if a concept you need isn't there yet, that's a signal." Conditional-loading wiring through `skills/lifecycle/references/load-requirements.md` extended with always-load (or global-tag) for glossary specifically.
- **ADR mechanism + 3 seeds (Tier 1)** — New `docs/adr/` directory + `docs/adr/README.md` policy doc capturing the three-criteria emission gate (hard-to-reverse + surprising-without-context + result-of-real-trade-off), the status frontmatter convention (`status: proposed | accepted | deprecated | superseded by ADR-NNNN`), the area frontmatter convention (`area: project | pipeline | multi-agent | observability | remote-access | skills`), the no-content-duplication-across-layers discipline rule, and consumer-rule prose for skills consuming the ADR log (analogous to Pocock's `domain.md` template — "use ADR vocabulary; flag conflicts explicitly"). Three initial ADRs synthesized from existing CLAUDE.md prose: `0001-file-based-state-no-database.md` (frontmatter `area: project, status: accepted`), `0002-cli-wheel-plus-plugin-distribution.md` (`area: project, status: accepted`), `0003-must-escalation-requires-effort-high-evidence.md` (`area: skills, status: accepted`). `lifecycle/specify` §2b Open Decision Resolution gains a fourth resolution path: "if the decision matches the three criteria, propose an ADR alongside the spec."

### Integration shape

- **Cadence/posture uplift** is purely behavioral — no shared contract beyond "interview proceeds one question at a time."
- **Glossary** is read by every skill that loads requirements via the tag-based protocol, plus by `/critical-review`'s Step 2a Project Context block [`skills/critical-review/SKILL.md:34-41`]. It is *written* inline at both producer surfaces (the cadence-uplifted requirements and spec interviews) when terms resolve. Lazy file creation on first term. No deferred-write path; no separate glossary-update Q&A item type — the producer-consumer separation is the simplification.
- **ADR mechanism** is read by `lifecycle/specify` §2b (when an Open Decision matches three-criteria, suggest an ADR), and by future feature work referencing prior decisions. Written by `lifecycle/specify`, ad-hoc by skill authors, or by the Tier-1 seed-now pass. Discoverability across the four-layer system relies on consumer-rule prose in `docs/adr/README.md` ("use ADR vocabulary; flag conflicts; grep `area:` frontmatter for area-scoped decisions") rather than on hand-maintained per-area indices — Pocock's posture per the `domain.md` seed template.

### Seam-level edges

- **Cadence/posture uplift** boundary lands on `skills/requirements-gather/SKILL.md` and `skills/lifecycle/references/specify.md` (§2 interview body). No new files; in-place edits.
- **Glossary** boundary lands on a new `cortex/requirements/glossary.md` (sibling of `project.md` and area docs). Loading wiring lands on `skills/lifecycle/references/load-requirements.md`. Inline-write rule lands inside the cadence-uplifted interview prose in `requirements-gather` and `lifecycle/specify` §2. Reviewer-prompt context block lands on `skills/critical-review/SKILL.md:34-41`.
- **ADR mechanism** boundary lands on a new `docs/adr/` directory + `docs/adr/README.md`. Consumers: `skills/lifecycle/references/specify.md` §2b emission rule and `skills/refine/SKILL.md` Step 5.

(`piece_count = 3`, ≤ 5 — falsification-framed `### Why N pieces` gate does not fire.)

## Decision Records

### DR-1: Glossary location and scope

- **Context**: Where does the project glossary live, and does it cover the whole project or per-area?
- **Options considered**:
  1. Single `cortex/requirements/glossary.md` (sibling of `project.md`).
  2. Per-area `cortex/requirements/{area}-glossary.md` files plus a root pointer.
  3. `CONTEXT.md` at repo root (Pocock's convention for single-context).
  4. Embed glossary in `project.md`'s `## Optional` section.
- **Recommendation**: Option 1 (single `cortex/requirements/glossary.md`). Reasons: (a) Cortex doesn't have bounded contexts in the DDD sense — areas share concepts, so per-area splits would create artificial boundaries; (b) `CONTEXT.md` at root would conflict with Cortex's convention of keeping tool-managed artifacts under `cortex/`; (c) `project.md` is at the 1200-token cap [`skills/requirements-write/SKILL.md`] — embedding glossary terms would push it over.
- **Trade-offs**: Single file means the glossary grows monotonically; if it gets large (>50 terms after Pocock-discipline filtering), introducing H3 area-grouping subheadings is the natural progression. Acceptable risk.

### DR-2: Glossary write timing — inline only, both interview surfaces

- **Context**: Pocock's `/grill-with-docs` writes to `CONTEXT.md` *as terms resolve*. Earlier iterations of this DR proposed a hybrid (deferred during ad-hoc interviews + inline during glossary-focused sessions). Investigation of how Matt actually handles maintenance (`setup-matt-pocock-skills/SKILL.md`, `domain.md` template, `improve-codebase-architecture/SKILL.md`) showed the simpler model: one producer (the interview skill itself), inline write always, lazy file creation, consumer-rule prose in other skills.
- **Options considered**:
  1. Inline-write only, both interview surfaces (`/cortex-core:requirements` and `/cortex-core:lifecycle` Spec phase, inheriting via `/cortex-core:refine`).
  2. Deferred-write: interview surfaces glossary updates as Q&A items; `/requirements-write` commits at end.
  3. Hybrid: deferred during ad-hoc; inline during glossary-focused sessions.
- **Recommendation**: Option 1 (inline-only, both surfaces). Reasons: (a) abandon-mid-interview safety that drove the deferred path doesn't apply to glossary the same way as spec/PRD drafts — a captured term is value even if the surrounding interview is abandoned (glossary grows monotonically); (b) producer-consumer separation matches Matt's model and removes the implementation surface of two write paths; (c) Cortex has two interview surfaces (project-scope requirements + per-feature spec), so the producer behavior lives in both, not because we're deviating from Matt but because we're applying his "interview is the producer" pattern to our skill catalog.
- **Trade-offs**: Two skills carry the inline-write capability vs Matt's one. Acceptable because both skills already share the cadence/posture uplift from #222; adding the glossary-write inline-rule to both is a small additional posture.

### DR-3: ADR mechanism — seed-now, flat directory, area frontmatter

- **Context**: ADRs serve as the progressive-disclosure layer for the *why* behind project.md and area-doc constraints. Where do they live, and do we open the directory empty or with seeds?
- **Options considered**:
  1. Defer ADRs entirely.
  2. Open `docs/adr/` empty with a policy doc, no seeds.
  3. Seed-now flat: open `docs/adr/` with 3 ADRs synthesized from existing CLAUDE.md prose, area carried in frontmatter.
  4. Seed-now per-area folders: `docs/adr/pipeline/`, `docs/adr/multi-agent/`, etc.
- **Recommendation**: Option 3 (seed-now flat with `area:` frontmatter). Reasons: (a) Pocock's single-paragraph format permits trivial seeding from existing prose; (b) Cortex areas aren't bounded contexts — they share concepts, so per-area folders would create boundaries to constantly cross; (c) flat + area frontmatter keeps decisions browsable as one log with filtering when wanted; (d) opening empty signals an unfinished feature; opening with real seeds delivers value from day one. Three seeds whose rationale already exists in CLAUDE.md prose: `0001-file-based-state-no-database.md` (CLAUDE.md `project.md:27`), `0002-cli-wheel-plus-plugin-distribution.md` (CLAUDE.md Distribution + `project.md:7`), `0003-must-escalation-requires-effort-high-evidence.md` (CLAUDE.md MUST-escalation policy section).
- **Trade-offs**: Flat directory may need re-organization if total ADR count grows past ~50. At that point Pocock's `CONTEXT-MAP.md` analogue (an `docs/adr/INDEX.md` grouped by area) is the natural extension. Acceptable for v1.

### DR-4: New `/grill` skill — STAND (no)

- **Context**: Pocock has both `/grill-me` and `/grill-with-docs`. Should we add a parallel?
- **Options considered**:
  1. New `/cortex-core:grill` skill.
  2. Fold the grill posture into existing skills (`/critical-review`, `lifecycle/specify` §2).
  3. Reference doc only.
- **Recommendation**: Option 2. We already have two surfaces: `/critical-review` runs adversarial reviewers on artifacts, `lifecycle/specify` §2 runs interview-style requirements gathering. Tier-1 cadence/posture uplift lands inside those existing skills. Adding `/grill` would dilute the routing surface in `/cortex-core:dev`.
- **Trade-offs**: Loses the user-facing affordance of "I just want to be grilled on this idea." Mitigation: that affordance is `/cortex-core:critical-review` invoked directly on a draft artifact.

### DR-5: Authoring-style translation — cadence YES, interrupt-driven HELD

- **Context**: Pocock's grill-with-docs uses imperative `<what-to-do>` blocks. Some translate cleanly to soft positive-routing prose (cadence: "one at a time" → "Q_n is the gate to Q_{n+1}"). Others — challenge-against-glossary, fuzzy-language sharpening, real-time code contradiction surfacing — are interrupt-driven mid-turn injections that require the agent to spontaneously break flow when it detects a condition.
- **Options considered**:
  1. Translate everything to soft positive-routing.
  2. Cadence-only translation; hold interrupt-driven behaviors pending evidence.
  3. Re-imperativize interrupt-driven behaviors (would require new MUSTs per CLAUDE.md MUST-escalation policy).
- **Recommendation**: Option 2. Per CLAUDE.md MUST-escalation policy, classifying a soft-routing translation as "viable" requires effort=high (and possibly xhigh) dispatch evidence on a representative case. Tier 1 ships only translation-cheap cadence behaviors. Interrupt-driven behaviors become a separate evidence-gathering item (Approach E in the Feasibility table).
- **Trade-offs**: Loses ~half the grill-with-docs behavior set in Tier 1. Acceptable per MUST-escalation policy; the held behaviors are not abandoned but queued behind documented evidence prerequisites.

### DR-6: Discipline rules in `docs/adr/README.md` (no-duplication, status, area)

- **Context**: A four-layer system (project.md / glossary / ADRs / area docs) without discipline rules drifts toward content duplication and fragmentation.
- **Recommendation**: `docs/adr/README.md` codifies three discipline rules from day one:
  1. **No content duplication across layers.** `project.md` is normative (the rule), ADR is historical (the why), glossary is terminological (what the word means). Any sentence appearing in two layers means one is wrong.
  2. **ADRs carry status frontmatter** from day one (`status: proposed | accepted | deprecated | superseded by ADR-NNNN`). Without status, ADRs from 2026 confuse readers in 2027 when decisions have been reversed.
  3. **ADRs carry `area:` frontmatter** matching the area-doc taxonomy (`project`, `pipeline`, `multi-agent`, `observability`, `remote-access`, `skills`, or new areas as added). The corresponding area doc's "Related ADRs" index MUST be updated when the ADR is accepted.
- **Trade-offs**: Three rules to remember. Mitigation: small enough to hold in head; emission rule in `lifecycle/specify` §2b can prompt the author to fill frontmatter at write time.

## Open Questions

- For Tier 1 cadence uplift: should the one-at-a-time gating be encoded as skill control flow (structurally enforced) or as soft-routing prose (per CLAUDE.md "structural separation over prose-only enforcement for sequential gates")? **Deferred to Tier 1 spec** — depends on the existing `lifecycle/specify` §2 control-flow shape.
- For glossary loading: the always-load sentinel vs global-context tag choice in `skills/lifecycle/references/load-requirements.md` requires file-level investigation of the tag mechanism. **Deferred to Tier 1 spec.**
- For the per-entry classifier (Contract / Compressing reference / Author scaffolding / Genuinely-domain term): does the classification get encoded as automated check (e.g., a script that scans skill diffs for new capitalized tokens) or as a soft authoring guideline? **Deferred to Tier 1 spec.**
- Tangential surfaced during this discovery: (a) discovery's R4 gate template fights comprehension (lapses into procedural jargon); (b) `/critical-review` Step 4 doesn't have a slot for "user already disagreed with this objection." **File as separate backlog tickets** alongside Tier-1 work — they're real but tangential to grill-with-docs adoption.
- Held interrupt-driven behaviors: what's the right evidence-gathering venue — a /pipeline run, a /critical-review against a draft skill that uses imperative form, or a dedicated discovery? **Deferred — separate research item.**
