# Research: grill-me-with-docs-learnings

## Headline Finding

The single highest-leverage adoption from Pocock's `/grill-with-docs` is **not** the glossary artifact, as a first pass of this research initially concluded. Critical-review surfaced that the jargon density used to justify a glossary (15+ procedural-scaffolding terms in 184 lines of `skills/lifecycle/references/specify.md` — `C1/C2/C3 signals`, `Sufficiency Check`, `loop-back`, `A→B downgrade rubric`, `confidence_check event`, etc.) is more directly diagnostic of the over-prescriptive authoring that CLAUDE.md's "prescribe What and Why, not How" principle and epic #82's post-Opus-4.7 harness adaptation are already attacking. Adding a glossary first would make the wrong terms cheaper to keep, working against work-in-flight. Per CLAUDE.md's Solution-Horizon principle, the durable sequence is **audit-then-(maybe-)glossary**, not glossary-then-audit. Concretely the recommendation tiers as: **(Tier 1, ship now)** — adopt the cadence/posture pieces from grill-with-docs that are translation-cheap (one-at-a-time grilling, code-vs-claim cross-reference moved from pre-write to during-interview, scenario stress-tests) into `/requirements-gather` and `lifecycle/specify`; seed 3 ADRs from existing CLAUDE.md prose so a `docs/adr/` directory exists with real content from day one. **(Tier 2, research)** — an authoring-discipline audit of `specify.md`, `lifecycle/SKILL.md`, and `critical-review/SKILL.md` asking which invented procedural nouns can collapse to plain prose under What/Why-not-How. **(Tier 3, conditional)** — introduce a glossary IFF Tier 2 finds a residual irreducible vocabulary large enough to justify the artifact. The interrupt-driven half of grill-with-docs (challenge-against-glossary, fuzzy-language sharpening) is held back to a separate evidence-gathering exercise per MUST-escalation policy.

## Research Questions

1. **Failure-mode coverage** → **Partially covered.** `/requirements-gather` has codebase-trumps-interview and recommend-before-asking [`skills/requirements-gather/SKILL.md:24-33`]. `lifecycle/specify` has a Verification check, Research cross-check, and Open-Decision Resolution that surface code-vs-claim contradictions [`skills/lifecycle/references/specify.md:74-90`]. `/critical-review` runs adversarial reviewers on plan/spec/research artifacts [`skills/critical-review/SKILL.md:18`]. The gaps Pocock targets that we don't address: **(a)** no project-wide canonical glossary (the *condition* whose justification is now the Tier-2 audit's job); **(b)** no inline (mid-interview) artifact updates — our spec writes happen at end of interview; **(c)** no fuzzy-language sharpening posture (interrupt-driven; held back per Tier-1 scope).
2. **Net-new patterns** → Three categories: **(a) Cadence/posture only** (Tier 1) — relentless one-at-a-time grilling [`grill-with-docs/SKILL.md:9`], scenario stress-tests, repositioning Verification check from pre-write to during-interview. **(b) Interrupt-driven behaviors** (held) — challenge-against-glossary, fuzzy-language sharpening; these require evidence per CLAUDE.md MUST-escalation policy before being claimed translatable to soft positive-routing prose. **(c) Composition** — Pocock's `/triage` invokes `/grill-with-docs` as a sub-step [`triage/SKILL.md:18`]; we already do this with `/critical-review` invoked by `/refine` Step 5 [`skills/refine/SKILL.md:147`].
3. **Glossary feasibility** → **Conditional.** The raw term-count justifies the artifact mechanically; what doesn't is the assumption that the term-count is fixed. Most of the inventoried terms (`C1/C2/C3 signals`, `loop-back`, `Sufficiency Check`, `A→B downgrade rubric`) are invented procedural nouns, not borrowed-from-a-domain vocabulary. Tier 2's audit asks "how many can collapse to plain prose under What/Why-not-How?" before committing to amortize them via glossary. If residual vocabulary > some threshold (Tier-2 sets it), Tier-3 introduces the glossary at `cortex/requirements/glossary.md`.
4. **ADR gap analysis** → **Real gap, seed now.** `cortex/requirements/project.md` Architectural Constraints captures shipped strategic constraints [`cortex/requirements/project.md:25-32`]. Lifecycle `spec.md` captures per-feature decisions. **Missing**: a project-wide, sequentially-numbered, durable record of decisions not tied to a single feature lifecycle. Three concrete candidates whose rationale already exists in CLAUDE.md prose: file-based state over database, wheel+plugins distribution model, MUST-escalation requires effort=high evidence. Pocock's ADR-FORMAT permits single-paragraph bodies, so seeding cost is trivial. Migration is a non-blocker — Architectural Constraints stay where they are; ADRs are forward-going. **Premise-unverified**: I did not check `docs/policies.md` for current ADR-shaped content [`premise-unverified: not-searched`].
5. **Authoring-style compatibility** → **Cadence-only is viable; interrupt-driven is unproven.** Pocock's imperative-tense `<what-to-do>` blocks translate cleanly to soft positive-routing for cadence behaviors that encode passive preconditions (e.g., "the interview proceeds one question at a time" satisfies "Q_n is the gate to Q_{n+1}"). They do **not** translate cleanly for spontaneous-injection behaviors (challenge-against-glossary, fuzzy-language sharpening, real-time code contradiction surfacing) — these require the agent to mid-turn detect a condition and break its conversational flow. Per CLAUDE.md MUST-escalation policy, a soft-routing translation cannot be classified as "viable" without effort=high (and possibly xhigh) dispatch evidence on a representative case. Tier 1 ships cadence-only; the interrupt-driven half is a separate research item.
6. **Leverage ranking** → **Tier 1 (ship now)**: ADR seed-now (3 ADRs, ~20 minutes of work each) + cadence/posture refresh in `/requirements-gather` and `lifecycle/specify` §2 (one-at-a-time, scenario stress-tests, code-vs-claim during-interview). **Tier 2 (research)**: authoring-discipline audit (own discovery / refine cycle). **Tier 3 (conditional on Tier 2)**: glossary artifact + glossary-aware behaviors. **Held**: interrupt-driven behaviors pending effort=high evidence. **Not recommended**: standalone `/grill` skill — duplicates `/critical-review` and `/refine` Spec.

## Codebase Analysis

### What we already absorbed from Pocock's earlier patterns

- **Recommend-before-asking** is canonical in `/requirements-gather`: every question carries a `**Recommended answer:**` line [`skills/requirements-gather/SKILL.md:27-29`].
- **Codebase-trumps-interview** is canonical in `/requirements-gather`: "Before drafting a question, decide whether the answer is recoverable from code … reserve interview questions for intent, priorities, scope boundaries, and non-functional bars" [`skills/requirements-gather/SKILL.md:24-25`].
- **Lazy artifact creation** is canonical: Q&A block held in conversation context until `/requirements-write` synthesizes [`skills/requirements-gather/SKILL.md:31-33`].
- The frontmatter explicitly attributes these to Pocock [`skills/requirements-gather/SKILL.md:3`].

### Failure modes our existing surfaces partially address

- **Code-vs-claim contradictions**: `lifecycle/specify` §2b Verification check [`skills/lifecycle/references/specify.md:74-83`] mandates that any spec claim about code be verified against actual code. Four sub-checks: git command syntax, function behavior, file paths, state ownership. This covers Pocock's "cross-reference with code" partially — but only at the *end* of the interview (pre-write), not actively during. Tier-1 work moves this posture into the interview.
- **Research-cross-check**: `lifecycle/specify` §2b re-reads `research.md` to catch silent omissions [`skills/lifecycle/references/specify.md:84`].
- **Confidence-check loop-back**: `lifecycle/specify` §2a flags when interview answers invalidate research (C1/C2/C3 signals) and loops back to Research [`skills/lifecycle/references/specify.md:38-71`]. Note: the C1/C2/C3 naming convention is itself a Tier-2 audit candidate.
- **Adversarial review**: `/critical-review` dispatches 3-4 parallel reviewers on distinct angles [`skills/critical-review/SKILL.md:51-61`].

### Failure modes our surfaces do NOT address (and our response)

- **Terminology drift across sessions**: Tier-2 audit asks "how much of this is invented terminology that should be removed vs. genuinely-irreducible vocabulary that should be glossary'd?" Held until Tier 2 completes. `NOT_FOUND(query="glossary|ubiquitous-language|CONTEXT.md", scope="cortex/requirements/**/*.md skills/**/*.md")` — the only references to a glossary concept are in `skills/requirements-gather/SKILL.md` (where `mattpocock` is named).
- **Inline (mid-interview) artifact updates**: Out of scope for Tier 1 (no glossary artifact yet) and held pending interrupt-driven evidence work.
- **Active fuzzy-language sharpening**: Held — interrupt-driven behavior requires evidence per MUST-escalation policy.
- **Project-wide durable decision log**: Tier-1 ADR seed-now addresses this. Three seeds from existing prose; no migration blocker. `NOT_FOUND(query="docs/adr|adr/", scope=".")`.

### Jargon density evidence (re-interpreted)

Sample read of `skills/lifecycle/references/specify.md` introduces 15+ project-specific terms in 184 lines: Sufficiency Check, loop-back, C1/C2/C3 signals, confidence_check event, current_cycle, Verification check, Research cross-check, Open Decision Resolution, A→B downgrade rubric (cross-ref), READ_OK sentinel (cross-ref), Specify Phase, Hard Gate, phase_transition event, lifecycle_cancelled event, complexity-value gate. Sample read of `skills/critical-review/SKILL.md` adds: artifact_sha256 / sentinel-first verification gate / Phase 1 / Phase 2 / record-exclusion / residue write / A-class / B-class / through-lines / tensions / concerns. CLAUDE.md adds OQ3, OQ6, MUST-escalation, F-row, soft positive-routing, dispatch effort=high/xhigh, dual-source enforcement, parity gate, two-mode gate. **Re-interpreted verdict**: this density is the *input* to the Tier-2 audit, not the *justification* for the Tier-3 glossary. The audit asks "of these 30+ terms, how many are invented procedural scaffolding that the What/Why-not-How principle would shrink?" Only the residual count justifies the glossary artifact.

## Web & Documentation Research

### `/grill-with-docs` canonical behavior (verbatim from `mattpocock/skills`)

- **One question at a time, recommend then wait** [`grill-with-docs/SKILL.md:7-9`]: "Interview me relentlessly … For each question, provide your recommended answer. Ask the questions one at a time, waiting for feedback on each question before continuing." (Tier 1.)
- **Code over interview** [`grill-with-docs/SKILL.md:11`]: "If a question can be answered by exploring the codebase, explore the codebase instead." (We already adopted this.)
- **Lazy file creation** [`grill-with-docs/SKILL.md:38`]: "Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved." (We already adopted lazy artifact creation.)
- **Challenge against the glossary** [`grill-with-docs/SKILL.md:44-46`]: "When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately." (Held — interrupt-driven; requires evidence per MUST-escalation.)
- **Sharpen fuzzy language** [`grill-with-docs/SKILL.md:48-50`]: "When the user uses vague or overloaded terms, propose a precise canonical term." (Held — interrupt-driven.)
- **Discuss concrete scenarios** [`grill-with-docs/SKILL.md:52-54`]: "stress-test … with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts." (Tier 1 — fits comfortably into spec interview as a non-interrupt-driven posture: "for each requirement, invent one edge-case scenario before asking acceptance criteria.")
- **Cross-reference with code** [`grill-with-docs/SKILL.md:56-58`]: "If you find a contradiction, surface it." (Tier 1 — moved from pre-write to during-interview as a passive posture: "as you ask each requirement, also cite the code path that would be modified.")
- **Update CONTEXT.md inline** [`grill-with-docs/SKILL.md:60-64`]: (Out of scope for Tier 1; revisited in Tier 3 if glossary lands.)
- **ADR three-criteria emission gate** [`grill-with-docs/SKILL.md:68-78`]: "Only offer to create an ADR when all three are true: 1. Hard to reverse 2. Surprising without context 3. The result of a real trade-off." (Tier 1 — adopted as the seed-criteria for the 3 ADR-seeds and as the emission rule for new ADRs.)

### `CONTEXT-FORMAT.md` (the glossary file format, deferred to Tier 3)

- Structure: `## Language` (bolded term + 1-sentence definition + `_Avoid_:` aliases), `## Relationships` (cardinality bullets), `## Example dialogue` (dev/expert exchange), `## Flagged ambiguities` (term-X-meant-both-Y-and-Z resolutions).
- Rules: opinionated (pick one term, list aliases-to-avoid); tight definitions (one sentence, what-it-IS not what-it-does); only project-specific concepts (general programming concepts excluded). The "only project-specific" rule is itself why Tier 2 must precede Tier 3 — most invented procedural nouns are not project-specific in the domain sense; they're authoring-implementation details.
- Multi-context support: `CONTEXT-MAP.md` at root pointing at per-context `CONTEXT.md` files. Likely overkill for Cortex.

### `ADR-FORMAT.md` (Tier 1)

- Path: `docs/adr/0001-slug.md`, sequentially numbered.
- Body: 1-3 sentences. "An ADR can be a single paragraph. The value is in recording *that* a decision was made and *why* — not in filling out sections."
- Optional sections: Status frontmatter, Considered Options, Consequences — included only when adding genuine value.
- Three-criteria gate is the discipline; without it the directory accumulates noise.
- **The single-paragraph permission is what makes seed-now feasible** — three seeds from CLAUDE.md prose require only synthesis-and-attribution, not new analysis.

### `/grill-me` (the productivity-bucket simpler form)

- Total skill body is ~3 sentences [`productivity/grill-me/SKILL.md`]: relentless one-at-a-time interview, walk decision tree, recommend-before-asking, code-over-interview. No artifacts. Used for non-code contexts. Cited here as evidence that Pocock's full-body skill is unusually short — Cortex's authoring discipline should aspire to the same compactness, which is itself a Tier-2 input.

### Composition pattern (`/triage` invokes `/grill-with-docs`)

- `/triage` Step 4 [`engineering/triage/SKILL.md:104-106`]: "Grill (if needed). If the issue needs fleshing out, run a `/grill-with-docs` session." Demonstrates that grill is intended as a callable sub-skill. Our parallel: `/refine` Step 5 invokes `/critical-review` after spec is drafted [`skills/refine/SKILL.md:147`]; `lifecycle/specify` §3b invokes `/critical-review` for complex tier [`skills/lifecycle/references/specify.md:147-151`].

### `/to-prd` (synthesize-only sibling)

- "Do NOT interview the user — just synthesize what you already know." [`engineering/to-prd/SKILL.md:7`]
- Explicit input: "Use the project's domain glossary vocabulary throughout the PRD, and respect any ADRs in the area you're touching" [`engineering/to-prd/SKILL.md:13`]. Confirms Pocock treats glossary + ADRs as **shared context for downstream skills** — a key consumer signal for Tier-3 glossary IF it lands.

## Domain & Prior Art

### Eric Evans / DDD "Ubiquitous Language"

Pocock's `CONTEXT.md` is the engineering-skills version of Evans' Ubiquitous Language pattern from *Domain-Driven Design*. The `_Avoid_:` line (aliases to drop) is a Pocock addition; the `## Flagged ambiguities` section maps to DDD's "linguistic friction signals." `CONTEXT-MAP.md` corresponds to DDD's Bounded Context Map [`premise-unverified: not-searched` — claim is from general DDD knowledge, not a verified citation]. **Note**: DDD's Ubiquitous Language assumes a real domain whose vocabulary the team is collaboratively learning. Cortex's "domain" is its own internal authoring patterns — a meaningfully different shape, which reinforces the audit-first posture.

### ADRs (Michael Nygard, ~2011)

Nygard's original ADR proposal was structured (Status / Context / Decision / Consequences). Pocock's deliberate stripping ("an ADR can be a single paragraph") is a meaningful divergence — he optimizes for low write-friction so the discipline survives, at the cost of structural consistency. This trade-off matches our own "ship faster, not be a project" quality bar in `cortex/requirements/project.md:23` and is the operational precondition that makes Tier-1 ADR seed-now feasible.

### Comparison with our discovery's `## Decision Records` block

`skills/discovery/references/research.md:165-172` already prescribes a `## Decision Records` block with `DR-N` items containing Context / Options considered / Recommendation / Trade-offs. This is closer to Nygard's full structure than Pocock's stripped form. The Cortex DR block is **scoped to a single research artifact** — it captures decisions made *during* discovery research, not durable project-wide decisions. ADRs (Tier 1) are complementary, not redundant.

### The "agent reads cold context" phenomenon (re-examined)

Pocock motivates the glossary on token-efficiency grounds: "agents are usually dropped into a project and asked to figure out the jargon as they go. So they use 20 words where 1 will do." Our first-pass research applied this directly to Cortex. Critical-review's reframe: in Cortex, the cold-context cost is not solely from genuinely-irreducible domain terms — it's largely from *invented* procedural nouns that the authoring-discipline audit would shrink. A glossary added before that audit *legitimizes* the cold-context tax rather than reducing it. Pocock's own glossary at `mattpocock/skills/CONTEXT.md` is 1364 bytes precisely because the underlying skill discipline is already tight.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **A. Tier-1 cadence/posture refresh** in `/requirements-gather` + `lifecycle/specify` (one-at-a-time, scenario stress-tests, code-vs-claim during-interview) | S | Prose churn in two SKILL.md files. Soft-positive-routing translation must avoid new MUSTs (CLAUDE.md MUST-escalation policy). Limited to behaviors with passive-precondition encoding — interrupt-driven behaviors held back. | None |
| **B. Tier-1 ADR seed-now** at `docs/adr/` + 3 seed ADRs synthesized from existing CLAUDE.md prose | S | Per Pocock single-paragraph format. Seeds: file-based state, wheel+plugins distribution, MUST-escalation evidence rule. ADR emission rule (three-criteria gate) added to `lifecycle/specify` §2b. | None — Architecture retired migration; seeds are synthesis-and-attribution only |
| **C. Tier-2 authoring-discipline audit** (own discovery topic) | M | Question: which invented procedural nouns in `specify.md`/`lifecycle/SKILL.md`/`critical-review/SKILL.md` collapse to plain prose under What/Why-not-How? Output: residual irreducible vocabulary count + glossary-or-not recommendation. Risk: audit may surface that some procedural names are load-bearing for safety (e.g., the `record-exclusion` subcommand contract); audit must distinguish naming from contract. | Tier 1 shipped (so Tier 2 can pattern-match the cadence-uplift edits as guidance) |
| **D. Tier-3 conditional glossary** at `cortex/requirements/glossary.md` + glossary-aware reads | M (conditional) | Only fires if Tier 2 finds residual irreducible vocabulary > N. Then write strategy (inline-vs-deferred) re-opens — DR-2 is vacated for now. | Tier 2 complete with positive recommendation |
| **E. Held: interrupt-driven behaviors** (challenge-against-glossary, fuzzy-language sharpening) | unknown | Per CLAUDE.md MUST-escalation policy: requires effort=high (and xhigh) dispatch evidence on a representative case before being classified translatable. Separate research item. | An evidence-gathering exercise (not yet scoped) |
| **F. New `/grill` skill** | M | Duplicates `/critical-review` (artifact stress-test) and `/refine` Spec phase (interview-style requirements gathering). High risk of confusing the routing surface in `/cortex-core:dev`. | Not recommended (DR-4) |

## Architecture

### Pieces

- **Cadence/posture uplift (Tier 1)** — Edits to `skills/requirements-gather/SKILL.md` and `skills/lifecycle/references/specify.md` (§2) adding (a) explicit one-question-at-a-time gating prose, (b) scenario-stress-test prompts ("for each requirement, invent one edge-case before asking acceptance criteria"), (c) repositioning the existing Verification check (`lifecycle/specify` §2b) as a *during-interview* posture, not just a pre-write gate. All translations stay in soft-positive-routing form — no new MUSTs, no interrupt-driven assertions.
- **ADR mechanism + 3 seeds (Tier 1)** — New `docs/adr/` directory + a one-paragraph policy doc at `docs/adr/README.md` capturing the three-criteria emission gate (hard-to-reverse + surprising-without-context + result-of-real-trade-off). Three initial ADRs synthesized from existing CLAUDE.md prose: `0001-file-based-state-no-database.md`, `0002-cli-wheel-plus-plugin-distribution.md`, `0003-must-escalation-requires-effort-high-evidence.md`. `lifecycle/specify` §2b Open Decision Resolution gains a fourth resolution path: "if the decision matches the three criteria, propose an ADR alongside the spec." Migration: Architectural Constraints in `project.md` stay where they are — they describe *shipped* strategic constraints; ADRs are forward-going per-decision records.
- **Authoring-discipline audit (Tier 2, own discovery)** — Separate discovery topic. Audits invented procedural nouns in `specify.md`, `lifecycle/SKILL.md`, `critical-review/SKILL.md` (and any skill flagged by Tier-1 work). Asks: "which collapse to plain prose under What/Why-not-How? Which are contract names where renaming would break code (e.g., `record-exclusion`, `READ_OK` sentinel)? Which are operational names mid-stream that prose would lose?" Output: a residual irreducible vocabulary count and a glossary-or-not recommendation.
- **Glossary artifact (Tier 3, conditional)** — Only emerges if Tier 2 returns positive. Format adapted from Pocock's `CONTEXT-FORMAT.md`. Deferred to its own discovery if it fires.

### Integration shape

- **Cadence/posture uplift** is purely behavioral — no shared contract with other pieces beyond "the interview proceeds one question at a time."
- **ADR mechanism** is read by future feature work referencing prior decisions and by `lifecycle/specify` §2b's emission rule. Written by `lifecycle/specify` when an Open Decision matches the three-criteria gate, OR ad-hoc by humans, OR by the seed-now Tier-1 work.
- **Authoring-discipline audit** is its own discovery output — produces a recommendation, possibly a backlog of skill rewrites, and a Tier-3 fire/no-fire decision. Does not directly modify the artifacts shipped by Tier 1.
- **Glossary artifact (conditional)** would integrate with `skills/lifecycle/references/load-requirements.md` (loading) and `skills/critical-review/SKILL.md:34-41` (reviewer-prompt context block) — but only if Tier 3 fires.

### Seam-level edges

- **Cadence/posture uplift** boundaries land on `skills/requirements-gather/SKILL.md` and `skills/lifecycle/references/specify.md` (§2 interview body). No new files; in-place edits.
- **ADR mechanism** boundary lands on a new `docs/adr/` directory + a one-paragraph `docs/adr/README.md`. Consumers: `skills/lifecycle/references/specify.md` §2b emission rule and `skills/refine/SKILL.md` Step 5 (which runs the Open Decision check via the specify reference).
- **Authoring-discipline audit** boundary is the Tier-2 discovery topic itself; deliverable is a research artifact + (optionally) a backlog of skill rewrites.
- **Conditional glossary** boundary is hypothetical until Tier 2 fires.

(`piece_count = 4`, ≤ 5 — the falsification-framed `### Why N pieces` gate does not fire.)

## Decision Records

### DR-1: Glossary artifact — DEFER pending Tier-2 audit

- **Context**: First-pass research recommended a `cortex/requirements/glossary.md` for v1 based on observed jargon density. Critical-review surfaced that the cited jargon is largely *invented procedural nouns* that CLAUDE.md's "What and Why, not How" principle and epic #82's harness adaptation are actively trying to shrink. Adding a glossary first would make those terms cheaper to keep, working against work-in-flight.
- **Options considered**:
  1. Ship glossary v1 immediately (first-pass recommendation).
  2. Audit-then-glossary (Tier 2 first; Tier 3 conditional).
  3. Drop glossary entirely.
- **Recommendation**: Option 2 (audit-then-glossary). Per CLAUDE.md Solution-Horizon, when a follow-up is foreseen (the migration audit explicitly named in this discovery's first-pass), propose the durable version. The durable version is the audit; the glossary is conditional on its outcome.
- **Trade-offs**: Loses Tier-1 amortization of cold-context cost for genuinely-irreducible vocabulary. Mitigation: that cost is largely composed of invented terms anyway — Tier 2 is expected to substantially reduce it before glossary is even on the table. Cost of audit (M effort) is real but earned: the alternative is shipping a stop-gap that Solution-Horizon explicitly rejects.

### DR-2: Glossary write strategy — VACATED

- **Context**: Originally addressed inline-vs-deferred-write for new glossary terms. With glossary deferred to Tier 3, this question is no longer live.
- **Recommendation**: Vacated. Re-opens IFF Tier 2 returns a positive glossary recommendation.

### DR-3: ADR mechanism — SEED NOW (3 ADRs)

- **Context**: First-pass research recommended deferring ADRs entirely. Critical-review surfaced that (a) the deferral rationale ("migration is non-trivial") is invalidated by this artifact's own Architecture section retiring migration as a blocker; (b) commit messages and archived spec.md files are *not* a working substitute for an indexed, sequentially-numbered decision log (lacking index, sequential numbering, and decision-tagging convention they cannot deliver Pocock's "stop the next engineer from fixing something deliberate" protection); (c) Pocock's single-paragraph format permits trivial seeding from existing prose.
- **Options considered**:
  1. Defer ADRs (first-pass).
  2. Open `docs/adr/` empty with a policy doc, no seeds.
  3. Seed-now: open `docs/adr/` with 3 ADRs synthesized from existing CLAUDE.md prose + the three-criteria emission gate added to `lifecycle/specify` §2b.
- **Recommendation**: Option 3 (seed-now). Three concrete seeds whose rationale already exists: `0001-file-based-state-no-database.md` (CLAUDE.md project.md Architectural Constraints + project.md:27), `0002-cli-wheel-plus-plugin-distribution.md` (CLAUDE.md Distribution + project.md:7), `0003-must-escalation-requires-effort-high-evidence.md` (CLAUDE.md MUST-escalation policy). Per Pocock single-paragraph format, each seed is ~5 lines.
- **Trade-offs**: A directory exists from day one that some reviewers may scan-and-question. Mitigation: the three seeds are real ADRs (single-paragraph format permits this), not placeholders — the directory is born content-bearing. The forward-going emission rule means future Open Decisions matching three-criteria add ADRs without backfill.

### DR-4: New `/grill` skill — STAND (no)

- **Context**: Pocock has both `/grill-me` (productivity) and `/grill-with-docs` (engineering). Should we add a parallel?
- **Options considered**:
  1. New `/cortex-core:grill` skill.
  2. Fold the grill posture into existing skills (`/critical-review`, `lifecycle/specify` §2).
  3. Reference doc only.
- **Recommendation**: Option 2. We already have two surfaces: `/critical-review` runs adversarial reviewers on artifacts, `lifecycle/specify` §2 runs interview-style requirements gathering. Tier-1 cadence/posture uplift lands inside those existing skills. Adding `/grill` would dilute the routing surface in `/cortex-core:dev`.
- **Trade-offs**: Loses the user-facing affordance of "I just want to be grilled on this idea." Mitigation: that affordance is `/cortex-core:critical-review` invoked directly on a draft artifact.

### DR-5 (NEW): Authoring-style translation — cadence YES, interrupt-driven HELD

- **Context**: First-pass research claimed grill-with-docs's behaviors are "viable with translation" to soft positive-routing prose. Critical-review surfaced that the worked example (cadence: "one at a time" → "Q_n is the gate to Q_{n+1}") generalizes only to passive-precondition behaviors. Net-new behaviors that require the agent to mid-turn detect a condition and break flow (challenge-against-glossary, fuzzy-language sharpening, real-time code contradiction surfacing) are interrupt-driven and have no equivalent passive-precondition form.
- **Options considered**:
  1. Translate everything to soft-routing as first-pass recommended.
  2. Cadence-only translation; hold interrupt-driven behaviors pending evidence.
  3. Re-imperativize interrupt-driven behaviors (would require new MUSTs).
- **Recommendation**: Option 2. Cadence behaviors translate cleanly; interrupt-driven behaviors require effort=high (and possibly xhigh) dispatch evidence on a representative case before classification per CLAUDE.md MUST-escalation policy. Tier-1 ships only translation-cheap behaviors. Interrupt-driven behaviors become a separate evidence-gathering item (Approach E in the Feasibility table).
- **Trade-offs**: Loses ~half the grill-with-docs behavior set in Tier 1. Acceptable per MUST-escalation policy: cannot claim "viable" without evidence. The held behaviors are not abandoned — they're queued behind a documented evidence prerequisite.

## Open Questions

- For Tier 1 cadence uplift: should the one-at-a-time gating be encoded as skill control flow (structurally enforced) or as soft-routing prose (per CLAUDE.md "structural separation over prose-only enforcement for sequential gates")? **Deferred to Tier 1 spec** — depends on the existing `lifecycle/specify` §2 control-flow shape.
- For Tier-1 ADR seeds: where does `docs/adr/README.md`'s policy text come from — synthesized inline or extracted from this research artifact? **Deferred to Tier 1 spec.**
- Tier-2 audit scope: does the audit cover `discovery/SKILL.md` and `discovery/references/*.md` (which contain their own procedural nouns: `R1`/`R2`/`R3`/`R4` checklist items, `READ_OK` sentinel, etc.)? **Deferred to Tier 2 discovery scoping.**
- Held interrupt-driven behaviors: what's the right evidence-gathering venue — a /pipeline run, a /critical-review against a draft skill that uses imperative form, or a dedicated discovery? **Deferred — separate research item.**
