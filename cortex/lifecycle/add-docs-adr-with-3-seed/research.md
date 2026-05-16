# Research: Add docs/adr/ with policy doc + 3 seed ADRs + §2b emission rule

## Epic Reference

Parent epic: [[221-adopt-grill-with-docs-progressive-disclosure-system]] — see `cortex/research/grill-me-with-docs-learnings/research.md` for the full discovery analysis and DR-1 through DR-6 that arbitrated the ADR mechanism's shape against alternatives. This ticket is the third Tier-1 component of the four-layer progressive-disclosure stack: project.md / glossary / **ADRs (this ticket)** / area docs. Research below scopes to this ticket only — glossary and cadence/posture uplift are sibling tickets and out of scope here.

## Codebase Analysis

### Files that will change

- `docs/adr/README.md` (new) — policy doc: three-criteria emission gate, frontmatter conventions, no-duplication rule, consumer-rule prose.
- `docs/adr/0001-file-based-state-no-database.md` (new seed).
- `docs/adr/0002-cli-wheel-plus-plugin-distribution.md` (new seed).
- `docs/adr/0003-must-escalation-requires-effort-high-evidence.md` (new seed).
- `skills/lifecycle/references/specify.md` §2b (modified) — add ADR-proposal handling to Open Decision Resolution.
- **Likely additional touch points surfaced by adversarial review** (decide in spec):
  - `CLAUDE.md` and `cortex/requirements/project.md:7,27` — back-pointer edits replacing one-liners with `→ ADR-000N` references (Nygard/MADR canonical no-duplication pattern); OR a documented exception in `docs/adr/README.md` carving out "compressed rule vs paragraph rationale" as non-duplicative.
  - `bin/.events-registry.md` (only if the §2b path emits an event).

### Current §2b Open Decision Resolution shape (`skills/lifecycle/references/specify.md:84-90`)

Three ordered prose-only resolution paths, no events, no subprocess: (1) check `research.md`; (2) ask the user directly; (3) defer to `## Open Decisions`. Insertion point: after path 3 and before "Any item that IS deferred" — but the adversarial review (Adversarial #3) argues this is the wrong shape; see Open Questions.

### Existing `docs/` directory

- `docs/policies.md` — single tone/voice policy section. Not decision-shaped in the ADR sense.
- `docs/internals/auto-update.md` — implementation narrative (intent-vs-wired audit table).
- `docs/internals/mcp-contract.md:7-37` — contains "Schema versioning" and "Forever-public API" sections that ARE decision-shaped (decision + rationale + consequences + evolution log). This is a live counter-example to the no-duplication rule on day one (see Open Questions).
- No existing `docs/adr/` directory and no top-level `docs/` subdirectories beyond `internals/`.

### Existing requirements taxonomy (`cortex/requirements/`)

`project.md` + four area docs: `multi-agent.md`, `observability.md`, `pipeline.md`, `remote-access.md`. **No `skills.md` exists** — `project.md:46` explicitly: "Discovery and backlog are documented inline (no area docs)." This is the source of the area-enum orphan question (see Open Questions).

Decision-shaped Rationale prose was found in `multi-agent.md` (Seatbelt worktree-path constraint) and `pipeline.md` (repair-attempt cap, integration-branch persistence) — additional latent ADR candidates not in the seed set.

### Frontmatter conventions

YAML with inline arrays (e.g. `tags: [a, b, c]`); lowercase enum values; standard fields `schema_version`, `uuid`, `status`, `tags`, `created`, `updated`. Standalone scripts (`bin/cortex-resolve-backlog-item`) parse frontmatter via a self-contained `_parse_frontmatter()` helper — no shared `cortex_command` import (install-guard discipline). The `cortex-update-item` script mutates frontmatter on backlog items; could be reused for ADR status transitions if needed.

### Source prose for seed ADRs

- **0001 (file-based state)**: `cortex/requirements/project.md:27` and `CLAUDE.md:12` (cortex/ umbrella description).
- **0002 (CLI wheel + plugins)**: `CLAUDE.md` Distribution section (lines 20-22), `project.md:7`, `project.md:32` (CLI/plugin version contract).
- **0003 (MUST-escalation effort=high)**: `CLAUDE.md:72-80` (full MUST-escalation policy section).

## Web Research

### Pocock's canonical ADR-FORMAT.md (`mattpocock/skills`)

- Path: `docs/adr/0001-slug.md`, sequentially numbered, 4-digit prefix.
- Body: "1-3 sentences explaining context, the decision made, and reasoning. That's sufficient — the goal is recording *that* a decision happened and *why*."
- Optional sections (only when adding value): status frontmatter (`proposed | accepted | deprecated | superseded by ADR-NNNN`), Considered Options, Consequences.
- **Three-criteria gate (verbatim)**: (1) Hard to reverse, (2) Surprising without context, (3) Result of a real trade-off. All three required; skip the ADR if any one is missing.
- Pocock's own seed `0001-explicit-setup-pointer-only-for-hard-dependencies.md` ships with **NO frontmatter at all** — no status, no Considered Options, no Consequences. ~150 words of pure prose.

### Nygard 2011 → Pocock delta

Nygard: five mandatory sections (Title, Context, Decision, Status, Consequences); one-to-two pages per ADR. Pocock cuts to 1-3 sentences fusing Context/Decision/Consequences; status becomes optional frontmatter; Considered Options + Consequences optional. Status enum `{Proposed, Accepted, Deprecated, Superseded}` traces to Nygard — not a Pocock invention.

### Directory and discoverability patterns

- `docs/adr/` flat is the de-facto standard for single-context repos. Per-folder splits make sense only for DDD bounded contexts with code locality (not Cortex's aspect-shared model).
- Sequential numbering monotonic, never reused; renumbering is anti-pattern (breaks PR/commit references).
- Re-organization at scale (~50+ ADRs) typically adds a generated INDEX.md, not folder restructure.

### Consumer-rule patterns (Pocock)

No `domain.md` template equivalent — consumer rule is **distributed across SKILL.md files**, not centralized. The canonical phrase across four soft-dependency Pocock skills: *"ADRs in the area you're touching"* — designed for graceful degradation when `docs/adr/` is empty. Pocock's own `CLAUDE.md` contains NO consumer-rule prose.

### Adoption-pattern canon

Web evidence supports the **replace-with-back-pointer** pattern when seeding from existing prose: "REPLACE the original prose with a back-pointer to the ADR, not leave both in place." MADR's bootstrap `0000-use-markdown-architectural-decision-records.md` is a meta-ADR justifying the format itself — projects commonly seed with a meta-ADR plus 2-4 historical decisions.

### Area-enum-with-validation: no prior art

No published project found that validates ADR `area:` frontmatter against a separate governance-doc enum. Closest analog is structural per-folder separation. Free-form tag vocabulary is the dominant flat-pattern choice.

## Requirements & Constraints

### Project.md (`cortex/requirements/project.md`)

- **Architectural Constraints** (`:25-32`): file-based state (no database) — confirms ADRs as plain markdown; SKILL.md size cap 500 lines (does not bind ADRs but informs proportionality); CLI/plugin version contract pins forever-public-API behavior already documented in `docs/internals/mcp-contract.md`.
- **Project Boundaries** (`:42-62`): In Scope does NOT explicitly enumerate `docs/` — the backlog treats `docs/adr/` as appropriate by analogy, but this is an unargued anchor. The cortex/ umbrella (`:46`) is described as the tool-managed surface.
- **Philosophy of Work** (`:9-23`): "ship faster, not be a project" + "Complexity must earn its place" — both support Pocock's stripped one-paragraph ADR format over Nygard's heavier original.
- **Conditional Loading** (`:63-68`): four area-doc triggers (observability, pipeline, remote-access, multi-agent). No `skills` area doc; `project.md` itself is the project-area surface.

### CLAUDE.md

- **Design principle "prescribe What and Why, not How"** (lines 64-70): structural alignment with ADR purpose (record the *why*).
- **"Solution horizon"** (lines 60-62): ADRs are a durable mechanism, not a stop-gap.
- **Line 58**: "Prefer structural separation over prose-only enforcement for sequential gates. ... Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low." Directly bears on the three-criteria gate enforcement question — see Open Questions.
- **MUST-escalation policy** (lines 72-80): full source prose for seed ADR 0003.

### The 1200-token cap on project.md

**Unverified premise.** The cap is referenced in the backlog ("the existing project requirements doc cannot carry under its 1200-token cap") and in the epic research, but is NOT stated as an explicit architectural constraint in `cortex/requirements/project.md` itself. Current project.md is 76 lines — well under any plausible cap. If the cap is the load-bearing justification for the ADR layer, the spec should either (a) state the cap in project.md alongside the architectural constraints, or (b) drop the cap-justification from the role narrative.

### Existing decision-shaped content (no-duplication implications)

- `docs/internals/mcp-contract.md:7-37` — Schema versioning + Forever-public API decisions, ADR-shaped in everything but format.
- `cortex/requirements/multi-agent.md:77-78` — Seatbelt mandatory-deny rationale for worktree paths.
- `cortex/requirements/pipeline.md` — repair-attempt-cap and integration-branch-persistence rationale.
- `docs/policies.md` — tone/voice policy (the line "decision to NOT ship a tone directive (accepting the 4.7 regression)" arguably meets criterion 1 + 3).

These are **existing counter-examples to the no-duplication rule** that the policy doc will announce on day one. The B2 audit (sweep existing decision-shaped content into ADRs) was scoped out of this ticket; this leaves a known consistency hole — see Open Questions.

## Tradeoffs & Alternatives

Summarized from the per-cluster analysis (full reasoning in agent dispatch). The convergence on the ticket's design is contested by the adversarial review; treat the recommendations as **defaults to be ratified in spec**, not as locked.

| Cluster | Options | Recommendation | Adversarial pushback |
|---|---|---|---|
| **A. Location** | A1 `docs/adr/` (Pocock-conventional) · A2 `cortex/adr/` (cortex umbrella consistency) · A3 per-area folders · A4 inline in project.md | A1 (default) | A2 is locally more coherent — `cortex/requirements/` and `cortex/research/` already house the same class of artifact. Spec must explicitly choose. |
| **B. Seed scope** | B1 three seeds as specified · B2 three + sweep `docs/internals/` for existing decision content · B3 empty with policy only · B4 synthesize from spec.md history | B1 (default) | B2 is forced by the no-duplication-on-day-one consistency hole. If B2 is deferred, the policy doc must explicitly grandfather existing prose with a tracked sweep ticket. |
| **C. §2b emission integration** | C1 fourth peer path in resolution order · C2 §3a post-write critic check · C3 new §2c sub-step · C4 manual only | C1 (default) | The path shape is wrong — paths 1-3 resolve unresolved decisions; ADR proposal is about already-resolved decisions. Should be a post-condition step gated on three-criteria, not a peer. |
| **D. Three-criteria enforcement** | D1 prose-only · D2 author checklist in README · D3 pre-commit hook · D4 in-spec critic check | D1 (default) | D1 may contradict `CLAUDE.md:58` (prose-only only when deviation cost is low; the directory accumulating noise IS the stated deviation cost). Spec must either ship D3 OR explicitly defend the prose-only carve-out citing CLAUDE.md:58. |
| **E. Discoverability** | E1 consumer-rule prose only · E2 per-area "Related ADRs" index · E3 generated INDEX.md · E4 both prose + INDEX.md | E1 (default) | E1 is correct for v1. E3 is the deferred upgrade at ~50 ADRs per DR-3. E2 is explicitly rejected by both Pocock posture and epic #221 Out-of-Scope. |

Recommended starting position: **A1 + B1 + C1 (with adversarial reshape) + D1 (with carve-out defense) + E1**, with mitigations from the adversarial review folded into the policy doc.

## Adversarial Review

The convergent recommendation across agents 1-4 anchored on the ticket + epic research without re-litigating the choices. The following objections require explicit treatment in the spec:

1. **Location: cortex/adr/ deserves more weight than `docs/adr/`.** ADRs are the same class of artifact as `cortex/requirements/` and `cortex/research/` (durable authorial artifacts about the project). The web convention `docs/adr/` was picked without weighting the local umbrella convention. Spec must justify the choice rather than treat it as decided.

2. **Day-one duplication is real, not pedantic.** All three seeds are paragraph-expansions of one-liners that remain in `project.md` / `CLAUDE.md` after ADR creation. The no-duplication rule will be violated at introduction unless: (a) source one-liners get `→ ADR-000N` back-pointer replacement, OR (b) the policy doc carves an explicit "compressed rule vs paragraph rationale" exception. Neither is in the ticket scope as written.

3. **The §2b fourth path is mis-shaped.** Paths 1-3 are an ordered resolution strategy for *unresolved* decisions. ADR proposal is about *resolved* decisions that warrant recording. Inserting as peer #4 either reads as "if 1-3 failed, propose an ADR" (incoherent — there's no decision to ADR if unresolved) or overloads the structure. Correct shape: a post-condition check that runs after paths 1-3 land, gated on three-criteria.

4. **`area:` frontmatter is premature at 0 ADRs.** Pocock ships no frontmatter at all. At three ADRs, frontmatter buys nothing; at twenty it starts to. Worse, the `skills` area in the enum has no `cortex/requirements/skills.md` anchor — the consumer-rule "grep area frontmatter" has nowhere to cross-reference. Options: defer all frontmatter (Pocock-minimal), enforce area-enum-equals-requirements-docs (validation), or ship `skills.md` to anchor the area.

5. **Consumer-rule manual/automatic boundary is unspecified.** The ticket disclaims "automatic side-effect" but the consumer-rule prose tells skills they MUST "flag the conflict explicitly." Flagging IS an automatic side-effect. The policy doc must spell out: MUST automatic (read existing ADRs in touched area), MUST NOT automatic (create or mutate ADRs), SHOULD surface (ADR conflicts during §2b). Two implementations will diverge without this.

6. **The B2 deferred audit leaves a known counter-example on day one.** `docs/internals/mcp-contract.md:7-37` is ADR-shaped content. Any reviewer will point at it the moment the policy doc lands. Either widen seed set or explicitly grandfather and file a tracked sweep ticket.

7. **D1 contradicts `CLAUDE.md:58` without acknowledgment.** Prose-only is appropriate when deviation cost is low; ADR noise accumulation is the stated worry. Either ship a structural gate (D3-style) on day one OR have the policy doc cite CLAUDE.md:58 explicitly and argue why ADR creation's rarity + PR review visibility makes prose-only the right carve-out here.

8. **CLAUDE.md / project.md back-pointer edits missing from Touch points.** The canonical adoption pattern is to replace original prose with back-pointers. Without that, the no-duplication rule fails at introduction (see #2). Small edit, structurally significant — should be added to spec touch points.

9. **User-approval bypass mechanism for the §2b path is aspirational.** "Must not bypass" is stated; the mechanism is not. Required: ADR proposals MUST appear as a discrete `## Proposed ADR` section in spec.md (not buried), and §4 approval surface must call out ADR proposals as a separate consent item.

10. **Status enum conflation.** `superseded by ADR-NNNN` embeds data in an enum slot, breaking YAML validation. Conventional split: `status: superseded` + `superseded_by: 0007`. Also unspecified: who promotes `proposed → accepted` and at what gate?

11. **Three seeds teach one shape only** (constraint-with-rationale). None demonstrates a real trade-off with rejected alternatives — which is criterion #3 of the emission gate. A fourth seed exercising criterion #3 (e.g., the per-repo sandbox registration choice with its alternatives) would teach the full pattern.

12. **The 1200-token cap on project.md is the load-bearing justification for ADRs but is unverified** (see Requirements & Constraints). Either state the cap as an architectural constraint or rework the role narrative without it.

## Open Questions

**All eleven items below are explicitly deferred to Spec.** Rationale: each is a design tradeoff requiring user judgment between coherent alternatives that the spec's structured-interview phase is the correct surface for. Research cannot pre-empt these without overriding user judgment; clarify is the wrong gate because each requires the spec's per-requirement context to evaluate. The spec phase will surface each as a numbered interview item with a recommended-answer line.

1. **Location: `docs/adr/` vs `cortex/adr/`?** The ticket assumes `docs/adr/`. Adversarial argues `cortex/adr/` is locally coherent with `cortex/requirements/` and `cortex/research/`. Spec must pick with reasoning.

2. **No-duplication on day one: back-pointer edits to CLAUDE.md and project.md, OR a policy carve-out for "compressed rule + paragraph rationale"?** If neither, the rule is DOA. (Adversarial #2, #8.)

3. **§2b path shape: peer #4 in the resolution order, OR a post-condition step after paths 1-3?** Adversarial #3 argues post-condition is the correct shape. Affects both the §2b edit and the §4 user-approval surface.

4. **Frontmatter on day one: ship `status:` and `area:` from ADR-0001, OR defer to Pocock-minimal (no frontmatter)?** If shipped: how to ground the `skills` area (ship `skills.md` requirements doc? collapse to `project`? document as free-form tag vocabulary)? (Adversarial #4 — deferred from clarify Ask.)

5. **Consumer-rule MUST/MUST-NOT/SHOULD boundary** — exact prose to write in `docs/adr/README.md` for what skills automatically do vs manually do vs may surface. (Adversarial #5.)

6. **Grandfathered counter-examples in `docs/internals/mcp-contract.md` and area-doc Rationale sections** — explicit acknowledgment in policy doc + tracked sweep ticket, OR widen the seed set to include them now. (Adversarial #6.)

7. **Three-criteria gate enforcement: prose-only with cited carve-out from `CLAUDE.md:58`, OR a structural check on day one (PR-body checkbox, length cap, required `## Reasoning` block)?** (Adversarial #7.)

8. **User-approval non-bypass mechanism for ADR proposals: discrete `## Proposed ADR` section in spec.md + explicit consent item in §4 approval surface — confirm shape.** (Adversarial #9.)

9. **Status enum shape: `superseded by ADR-NNNN` as a value, OR `status: superseded` + separate `superseded_by:` field? Who promotes `proposed → accepted` and at what lifecycle gate?** (Adversarial #10.)

10. **Seed set composition: ship the three specified seeds, OR add a fourth seed demonstrating criterion #3 (real trade-off with rejected alternatives)?** (Adversarial #11.)

11. **The 1200-token cap on project.md: state it as an architectural constraint in project.md as part of this ticket, OR drop it from the ADR role narrative?** (Adversarial #12.)

## Considerations Addressed

- **Investigate whether docs/policies.md, docs/internals/auto-update.md, or docs/internals/mcp-contract.md already contain ADR-shaped decision content** — Addressed. `docs/policies.md` contains a tone/voice decision (borderline three-criteria). `docs/internals/auto-update.md` is implementation narrative (not decision-shaped). `docs/internals/mcp-contract.md:7-37` IS decision-shaped (Schema versioning, Forever-public API) and creates a day-one consistency hole captured as Open Question #6.

- **Map the existing skills/lifecycle/references/specify.md §2b control flow** — Addressed. Three ordered prose-only paths quoted in Codebase Analysis. The original "insert as peer #4" approach is contested by adversarial review (Open Question #3); the correct integration shape is a post-condition check, not a peer in the resolution order.

- **Include a `## Epic Reference` section linking to the discovery research** — Addressed (top of this file).

- **Surface for spec phase: the unresolved area-enum policy question** — Addressed as Open Question #4, expanded by the adversarial review to include the `skills` area orphan and the Pocock-minimal alternative.
