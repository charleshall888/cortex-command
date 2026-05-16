# Research: add-project-glossary-at-cortex-requirements

## Epic Reference

This ticket sits under epic [[221-adopt-grill-with-docs-progressive-disclosure-system]]. The epic's full discovery — including Pocock's source patterns, decision records DR-1 through DR-6, and the feasibility assessment — lives at `cortex/research/grill-me-with-docs-learnings/research.md`. That research established *that* a project glossary at `cortex/requirements/glossary.md` is Tier-1 work; this ticket-specific research scopes *how* to implement it given the open spec-phase decisions (critical-review consumer surface, loading mechanism, classifier prose form, requirements-gather contract narrowing).

## Codebase Analysis

### Files that will change

**New file:**
- `cortex/requirements/glossary.md` — lazily created on first term resolved (does not exist until then). Sibling of `project.md`.

**Modified — producer skills (write inline):**
- `skills/requirements-gather/SKILL.md` (currently 72 lines) — needs (1) narrowed no-filesystem contract on line 33, (2) inline glossary-write rule, (3) per-entry classifier prose.
- `skills/lifecycle/references/specify.md` §2 (currently 191 lines; §2 spans roughly L11–L36 with interview "areas" L23–L34) — needs same inline-write rule + classifier prose, IF the proposal retains the dual-producer model (see Open Questions).

**Modified — loading mechanism:**
- `skills/lifecycle/references/load-requirements.md` (27 lines, 5-step protocol L7–L17) — needs always-load wiring. Today step 1 unconditionally loads `project.md` (L9); the natural slot for an always-load glossary sentinel sits between step 1 (project.md) and step 2 (tag extraction). The Matching Semantics block (L19–L23) and the "avoid over-loading" intent (L26–L27) constrain the alternative shapes (see Tradeoffs §b).

**Modified — consumer skills:**
- `skills/critical-review/SKILL.md` Step 2a (L33–L41) — per backlog L31 the reviewer-prompt context block would gain a glossary read. The deliberate-exemption notice on L41 ("Do not 'fix' this exemption by wiring tag-based loading into the dispatch path") is the live constraint distinguishing prose-only consumer rule from context-block injection.

**Indirect consumers (inherit automatically from any load-requirements.md extension):**
- `skills/lifecycle/references/clarify.md:33`, `specify.md:9`, `review.md:12`
- `skills/discovery/references/clarify.md:15`, `research.md:27`
- `skills/refine/SKILL.md:68` (cites the chain refine → lifecycle clarify → load-requirements)

**Tests that gate changes:**
- `tests/test_load_requirements_protocol.py` — hard-coded assertions: 5 protocol steps L91–L114, the `CONSUMER_REFS` tuple L38–L45 enumerating the six non-exempt consumers, the critical-review exemption anchor phrase L74–L88.
- `tests/test_skill_size_budget.py` — 500-line cap; current sizes (critical-review 115, requirements-gather 72, specify.md 191) have ample headroom.
- `tests/test_lifecycle_kept_pauses_parity.py` — LINE_TOLERANCE=35 on AskUserQuestion anchors in `specify.md`; inserting ~30-50 lines of new prose near §2 (line ~36) could shift anchors at `:67, 162, 168` outside tolerance.
- `tests/test_requirements_skill_e2e.py:86-101, 301-345` — e2e simulation does NOT currently write a glossary file; narrowing gather's contract would create simulation/runtime divergence.

### Relevant existing patterns

**Producer/consumer separation already canonical for requirements:**
- `skills/requirements-gather/SKILL.md:33` codifies the no-filesystem contract: "This sub-skill never touches the filesystem under `cortex/requirements/`. If the user abandons mid-interview, no partial file is left behind." Rationale is twofold — synthesis is `/requirements-write`'s job AND abandon-safety.
- `skills/requirements-write/SKILL.md:4` is currently "the only sub-skill that touches the filesystem" — this contract phrasing in `when_to_use` would also need narrowing if requirements-gather gains a glossary-only exception.
- `skills/requirements/SKILL.md:5` orchestrator's passive-artifact framing rests on a single producer — narrowing has wider contract-coherence cascade.

**Inline-checks pattern in specify.md §2:**
- §2b Verification check (L74–L83), Research cross-check (L82), Open Decision Resolution (L84–L90) all share the "silent on pass / surface only the failing item" shape — same template a glossary inline-write rule could adopt.

**Tag-protocol semantics:**
- `skills/lifecycle/references/load-requirements.md:9` step 1 is the only unconditional load today.
- L21–L23: whole-tag-matching rule; L25–L27 frames the protocol as "explicit, author-curated signal cross-referenced against an explicit, requirements-author-curated signal."
- An always-load sentinel for glossary fits as a "loaded for every consumer" axiom analogous to project.md.

**Critical-review's exemption is structural and parity-tested:**
- `skills/critical-review/SKILL.md:41` exemption text is parity-pinned via the literal anchor phrase "Requirements loading: deliberately exempt" in `tests/test_load_requirements_protocol.py:84`.
- The exemption's anchor-avoidance rationale: "broader project context (priorities, area-specific tags, decisions) would dilute that focus and anchor reviewers to existing reasoning."

**MUST-escalation policy for new classifier prose:**
- `CLAUDE.md:74-76`: soft positive-routing is default for new authoring; new MUSTs require effort=high failure evidence in events.log F-row OR transcript URL.
- Existing `/requirements-gather` decision-criteria prose (L21–L33) uses soft positive-routing throughout — clean precedent.

## Web Research

### Pocock's canonical CONTEXT.md system

Fetched verbatim from `mattpocock/skills` `main` branch (2026-05-13):

**Format rules (`grill-with-docs/CONTEXT-FORMAT.md`):**
- "Keep definitions tight. One sentence max. Define what it IS, not what it does."
- "Be opinionated. When multiple words exist for the same concept, pick the best one and list the others as aliases to avoid." — `_Avoid_: alias1, alias2` is the canonical syntax.
- "Only include terms specific to this project's context… Before adding a term, ask: is this a concept unique to this context, or a general programming concept? Only the former belongs."
- Required sections: `# Title`, opening 1–2 sentence description, `## Language`, `## Relationships`, `## Example dialogue`, `## Flagged ambiguities`.

**Inline-write cadence:**
- "When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen." — verbatim.
- Scope guard: "`CONTEXT.md` should be totally devoid of implementation details… It is a glossary and nothing else." — recently hardened (commit e74f0061, 2026-05-13).

**Producer-consumer model:**
- **Multiple producers ARE supported** — `grill-with-docs` AND `improve-codebase-architecture/SKILL.md` both write inline using "same discipline as `/grill-with-docs`". Coordination mechanism: a single canonical format spec (`CONTEXT-FORMAT.md`) referenced by each producer. **No locking, queueing, or ordering.** This directly validates the structural shape Cortex proposes — but see Adversarial §1 for the analogy's limits.
- **Consumers** (read-only): `to-prd`, `to-issues`, `diagnose`, `tdd`, in-progress `review`. Cadence: read eagerly at task start, proceed silently if missing, use prose-only references in consumer skill text and let always-in-context root file (CLAUDE.md/AGENTS.md) carry the resolution.

**Classifier shape:**
- **The four-bucket classifier (Contract / Compressing reference / Author scaffolding / Genuine domain) is a Cortex synthesis, NOT Pocock.** Pocock has only a binary "project-specific vs general programming" filter. Document this explicitly when adopting.

**Mid-interview abandon-safety:**
- **Pocock has none.** Search for "abandon", "atomic", "stale" — zero results. The inline-write directive is unqualified. Cortex would be extending past Pocock here.

**Glossary-ADR boundary:**
- Glossary captures *what something IS*; ADRs capture *why a decision was made* (three gating criteria: hard to reverse, surprising without context, real trade-off existed). Cross-references via inline links, never merged artifacts.

### DDD / Ubiquitous Language prior art

- **Eric Evans, DDD Reference (2015)**: the foundational source. "Use the model as the backbone of a language… Within a bounded context, use the same language in diagrams, writing, and especially speech."
- **Fowler, "Bounded Context"**: same term can mean different things in different contexts. **Direct prior-art analog to critical-review's exemption**: critical-review is a deliberately separate bounded context with adversarial vocabulary. DDD's resolution is the Context Map: explicit mappings between contexts with optional translation (Anti-Corruption Layer, Shared Kernel).

### Engineering glossaries in practice

- Kubernetes / Cargo Book / MDN: tight first-sentence definitions, explicit inclusion criteria, alphabetical ordering, **no automated drift detection** — all rely on community curation, versioned doc snapshots, or ownership-based editing.

### Sources

- [grill-with-docs/CONTEXT-FORMAT.md](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/CONTEXT-FORMAT.md)
- [grill-with-docs/SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md)
- [setup-matt-pocock-skills/domain.md](https://github.com/mattpocock/skills/blob/main/skills/engineering/setup-matt-pocock-skills/domain.md)
- [improve-codebase-architecture/SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/engineering/improve-codebase-architecture/SKILL.md)
- [Fowler — Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
- [DDD Reference (Evans, 2015 PDF)](https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf)
- [Kubernetes Glossary](https://kubernetes.io/docs/reference/glossary/) · [Cargo Book Glossary](https://doc.rust-lang.org/cargo/appendix/glossary.html) · [MDN Glossary template](https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Page_structures/Page_types/Glossary_page_template)

## Requirements & Constraints

**From `cortex/requirements/project.md`:**
- Philosophy of Work: "Complexity must earn its place by solving a real problem now. When in doubt, simpler wins." Handoff readiness: "spec has no open questions, criteria are agent-verifiable from zero context."
- Quality bar: "ROI matters — ship faster, not be a project."
- Conditional Loading section (L63-L68): 4 area docs currently tag-gated.

**Architectural constraints that apply:**
- File-based state — markdown glossary consistent.
- Per-repo sandbox registration — `cortex/requirements/` already in `allowWrite`.
- SKILL.md size cap 500 lines — ample headroom in all affected files.
- Skill-helper modules — does not apply; glossary is documentation, not dispatch.

**Events registry and parity:**
- `bin/.events-registry.md` already lists `clarify_critic`. No `glossary_*` events registered.
- `bin/.parity-exceptions.md` — no glossary-relevant scripts exempt.

**Policy constraints from CLAUDE.md:**
- **For decision (a) — reviewer-prompt context injection**: No CLAUDE.md policy forbids the shape. `skills/lifecycle/references/review.md:12` and `load-requirements.md` step 4 already establish the injection precedent ("Record the full list of loaded requirements files for injection into the reviewer prompt"). The only constraint is the critical-review-local exemption at SKILL.md:41.
- **For decision (b) — load protocol shape**: "Prescribe What and Why, not How" cautions against expanding procedural steps. "Prefer structural separation over prose-only enforcement for sequential gates" — but load-requirements.md is documentation-of-protocol, not a gate.
- **For decision (c) — classifier prose**: Soft positive-routing is the default. New MUST requires (a) evidence artifact (events.log F-row OR transcript URL) AND (b) effort=high (and xhigh if needed) failed-dispatch outcome. OQ3-eligible for format-conformance / correctness failures (classifier mis-admit is OQ3, not tone). Net: soft phrasing is the default; any MUST-class language requires evidence.
- **For decision (d) — requirements-gather contract**: "Solution horizon" applies — "Before suggesting a fix, ask whether you already know it will need to be redone." A narrow exception must argue the durable-version question: does it generalize, or does it stay narrow and risk accreting more exceptions? "Prescribe What and Why, not How" — the existing contract phrasing is What + Why; the exception should preserve that shape.

## Tradeoffs & Alternatives

### Decision (a) — critical-review consumer-surface shape

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A1** Prose-only consumer rule | One line in reviewer prompt: "use glossary vocabulary if it exists." Exemption notice unchanged. | Zero token cost; smallest diff; respects "deliberately exempt" directive verbatim. | Reviewers told to use vocabulary they haven't loaded — functionally near-no-op. |
| **A2** Context-block injection | Step 2a Project Context block reads glossary.md inline. Exemption explicitly carved for glossary only. | Reviewers actually have the vocabulary; matches existing project.md Overview pattern; auditable narrow exception. | Reverses an explicit "do not fix" directive; adds reviewer-prompt tokens; sets precedent that exemption can be carved. |
| **A3** Hybrid prose + on-demand fetch | "Use glossary vocabulary if it exists; you may Read glossary.md if you need a definition." | Tokens only spent when needed. | Soft-routing decision the reviewer must make mid-review; inconsistent application across angles. |

### Decision (b) — loading mechanism in load-requirements.md

| Option | Description | Pros | Cons |
|---|---|---|---|
| **B1** Always-load sentinel | Add bullet to step 1: "Always load `cortex/requirements/glossary.md` if it exists." | Single-line addition; mirrors project.md pattern. | Hard-codes glossary.md in protocol; future always-load docs need protocol edits. |
| **B2** Global-context tag | Magic `_always` tag auto-injected, or schema extension to `project.md` with a `## Global Context` section listing always-loaded files. | Preserves "author-curated signals" invariant if reframed as schema extension. Future always-load files use the same path. | Net new authoring pattern; either tag-side magic or schema-side new section needed. |
| **B3** Conditional always-load | Same as B1 with explicit lazy-file framing: "load if it exists; absent file is documented fallback." | Functionally identical to B1; aligns with lazy-creation contract. | Slips file-existence-based loading into a protocol whose existing fallback is "no tags is not an error" — a categorically new semantic. |

### Decision (c) — per-entry classifier prose

| Option | Description | Pros | Cons |
|---|---|---|---|
| **C1** Soft positive-routing prose | "Strong candidates for glossary entries are X; terms that fit Y belong as source-skill prose." No MUST. | Honors CLAUDE.md default; aligns with "Prescribe What and Why, not How." | Prose-only enforcement may drift; the *model* gets classification wrong inline under interview pressure (see Adversarial §2). |
| **C2** Structural gate (`bin/cortex-check-glossary-entry`) | Pre-commit script validates surface form (sentence count, `_Avoid_:` line presence). | Matches "prefer structural over prose-only enforcement." | Can only enforce surface form, not classification judgment; cost exceeds checkability ceiling; risks false confidence. |
| **C3** MUST language with effort=high evidence | Imperative MUST prose backed by F-row evidence per policy. | Strongest enforcement; durable across model versions. | Requires evidence not yet gathered; contradicts epic's own posture (interrupt-driven behaviors deferred on same grounds). |

### Decision (d) — requirements-gather contract narrowing

| Option | Description | Pros | Cons |
|---|---|---|---|
| **D1** Narrow with exception clause | "Never touches filesystem under `cortex/requirements/` except `glossary.md` on term resolve." | Minimal diff; named, audited, obvious. | Mixes negative rule with positive carve-out; future second exception compounds awkwardness. |
| **D2** Explicit positive grant | "Writes only to `cortex/requirements/glossary.md` (lazy file creation; per-term append). Does not touch project.md or area docs." | Positive framing matches producer-consumer model; enumerated writable set easy to verify. | Loses original "lazy artifact creation" framing — must retain it as separate sentence. |
| **D3** Tiny helper sub-skill (`/glossary-append`) | Move inline-write into a new helper that requirements-gather calls. | Strongest separation; original contract stays pure negative rule. | Disproportionate overhead for one-line append; widens routing surface. |

### Provisional recommendations (subject to Open Questions)

- **(a) A1 OR A2** — Adversarial §7 argues A2's narrowed injection (Language section only) preserves the exemption's actual rationale ("anchor reviewers to *existing reasoning*"). The Tradeoffs synthesis prefers A1 on directive-respect grounds. **Unresolved.**
- **(b) B1/B3 OR B2-as-schema-extension** — Tradeoffs prefers B3 for prose clarity; Adversarial §5 argues B3 introduces a categorically new "always-load if exists" semantic the protocol should not normalize, and reframes B2 as a `## Global Context` schema extension that preserves the author-curated-signal invariant. **Unresolved.**
- **(c) C1** — Soft positive-routing; Adversarial §2 questions whether the four-bucket Cortex classifier is the right discipline at all (Pocock uses binary). **C1 form OK; classifier scope unresolved.**
- **(d) D2** — Explicit positive grant; Adversarial §6 surfaces cascade points beyond Agent 1's enumeration. **Unresolved scope.**

## Adversarial Review

### 1. The dual-producer claim — Pocock analogy breaks at "different phase, same term, different verdict"

Pocock's two producers (`grill-with-docs` + `improve-codebase-architecture`) act at different operational moments (interview vs refactor) on disjoint term streams. Cortex's two producers are both interviews at different lifecycle phases on the **same vocabulary scope**. Three failure modes the proposal does not address:
- **Promote**: spec needs to extend a "compressing reference" entry to "genuine domain term" with `_Avoid_:` aliases. No prose tells the producer to extend vs replace.
- **Demote**: spec interview finds the term used only twice across the codebase. Cutting from a *spec* interview is a project-level mutation — has the spec producer earned that authority?
- **Conflict**: requirements at T1 defines a term; spec at T2 defines it differently. The monotonic-growth assumption (DR-2 at `research.md:179, 188`) treats this as impossible. **Required mitigation**: term-already-exists probe before write; on present-term, branch to "use existing verbatim or surface conflict to user before reclassifying."

### 2. Classifier judgment problem — C1 inherits C2's blind spot

The four-bucket classifier (Cortex synthesis, not Pocock) was load-bearing in *audit* context (deliberate, post-hoc). At *inline-write* time, the model is interviewing, not auditing. Specific failure modes:
- **False admit**: producer fails to grep the codebase, admits an Author scaffolding term as Compressing reference. Glossary fills with the noise the discipline was designed to remove. Structurally identical to the deprecated `ubiquitous-language` failure.
- **False cut**: term appears once in the current artifact because the rest of the project isn't read into context. Producer cuts a Genuine domain term from the source skill. Skill rewritten with verbose paraphrase — inverts the token-efficiency rationale.
- **False contract**: producer sees the term in a skill prompt, assumes contract-status, exempts from glossary entry. Term gets no documentation surface at all — orphaned.

The MUST-escalation policy gates MUST language by requiring effort=high evidence. The four-bucket classifier is prose-routing — sidesteps the gate — but is exactly the kind of judgment the gate was designed to evidence-gate. **Required mitigation**: either drop to Pocock's binary classifier for v1, OR defer inline-write entirely until evidence supports the four-bucket judgment under interview load. Do not ship C1+four-bucket-classifier without one of these positions.

### 3. Orphaned terms — abandon-safety gap is wider than surfaced

Every other persist-on-resolve pattern in Cortex is either write-once (events.log), commit-and-promote (lifecycle archive), or explicit rollback. The glossary's "always-persist-on-resolve" model has no analogue. Critical edge case missed: **interview-abandon when the term was introduced by a recommend-before-asking line, not by the user**. If the model writes glossary entries inline for terms it introduced in its own recommendations, those entries are pure model speculation if the user never confirmed — model-authored vocabulary persisted into project-level requirements with no human review. **Required mitigation**: a "term resolved" gate before write — user explicitly named the term OR explicitly confirmed a model-proposed term. Model-introduced terms with no confirmation do not trigger inline write.

### 4. Parity-test cascade — recommended path triggers more than one test

The Agent 1 enumeration was incomplete. The B3+A1 path triggers at least five parity surfaces:
1. `test_load_requirements_protocol.py:103` — `test_load_requirements_md_enumerates_five_protocol_steps()` iterates 1–6 and asserts numbered list. Adding step 6 breaks; restructuring step 1 may shift fallback prose regex anchors.
2. `test_load_requirements_protocol.py:84` — `test_critical_review_documents_deliberate_exemption()` asserts literal substring. A1 keeps the anchor — but the rationale prose at `:41` ("broader project context… would dilute that focus and anchor reviewers to existing reasoning") opens a contradiction if glossary is in fact broader project context. Either anchor stays and prose self-contradicts, or prose gets re-written and anchor risks accidental deletion.
3. `test_requirements_skill_e2e.py:301-345` — `_simulate_write()` does NOT write a glossary file. If gather narrows to write glossary inline, simulation diverges from runtime.
4. `test_lifecycle_kept_pauses_parity.py:25-27, 88` — LINE_TOLERANCE=35. Adding ~30-50 lines of new prose near `specify.md` §2 (line ~36) could shift later AskUserQuestion anchors at `:67, 162, 168` outside tolerance.
5. `bin/cortex-check-events-registry` — if any new event is introduced (e.g., `glossary_term_resolved`), registry row needed. Decision is forced: ship zero events (post-hoc audit impossible) OR ship any (registry cascade).

### 5. The "always-load if exists" anti-pattern — protocol semantics drift

The current protocol's five steps are about *tag-resolution mechanics* with one specific fallback semantic ("no tags is not an error"). B3 ("always load glossary.md if it exists") slips a *different* semantic into the same protocol — file-existence-based loading, no signals involved. Risk: once allowed, every future "important file" gets that treatment. The protocol's `## Why this protocol` section claims author-curated signals as the load-bearing design feature; B3 erodes exactly that. **Required mitigation**: prefer B2 reframed as schema extension — add a `## Global Context` section to `project.md` listing always-loaded files. Keeps signal-based architecture clean.

### 6. The requirements-write contract parity cascade

The exclusive-write claim at `requirements-write/SKILL.md:4` is the durable rationale for the orchestrator's three-tier architecture. Narrowing means two producers can write to `cortex/requirements/` — gather (for glossary) and write (for project.md/area.md). The orchestrator's passive-artifact framing (`skills/requirements/SKILL.md:5`) now has to distinguish artifacts gather may touch from those it may not. Cascade points beyond Agent 1's list:
- `skills/requirements/SKILL.md:21` `list` subcommand — does it enumerate glossary.md? If yes, scope column needed; if no, list silently hides part of the surface.
- `test_requirements_skill_e2e.py:60-68` AREA_TEMPLATE_H2S — glossary is a third template structure, never documented.
- `requirements-write/SKILL.md:36-46` Area template enumerates seven H2s; glossary's structure (Pocock's `## Language`, `## Relationships`, `## Example dialogue`, `## Flagged ambiguities`) is a fourth section taxonomy with no documented home.

**Required mitigation**: either (a) re-open DR-2's deferred-write rejection given this cascade — glossary entries flow through `/requirements-write`, preserving exclusive-write — OR (b) enumerate every contract-coherence point that needs updating before implementation begins.

### 7. Anchoring concerns for critical-review — the exemption's actual scope

The exemption's wording at `critical-review/SKILL.md:41` is precise: "broader project context (priorities, area-specific tags, decisions) would dilute that focus and anchor reviewers to **existing reasoning**." The load-bearing phrase is "existing reasoning," not "any project context." A glossary entry by Pocock's discipline is **definitional**, not reasoning — "one-sentence what-it-IS definitions." A1 conflates two anchoring risks:
- (a) Reviewers anchored to **arguments** used to construct the artifact (real load-bearing concern).
- (b) Reviewers anchored to **vocabulary** for naming the domain (actually-positive contribution — reviewers can challenge "the kept pause at line 47" precisely instead of paraphrasing).

The exemption was crafted against (a). A1's blanket exclusion trades zero (a)-risk reduction for (b)-precision loss. The synthesizer prompt DOES load glossary (operates on full project context), so A1 creates an asymmetry: reviewers reason in paraphrase, synthesizer reasons in terms — a translation seam where adversarial intent can be lost. **Recommended mitigation**: re-open A2 with one guardrail — inject the glossary's **Language section only** (IS-definitions and `_Avoid_:` aliases), not Relationships or Example dialogue (which could approach "existing reasoning"). Update the exemption anchor at `:41` to narrow its scope to "priorities and area-specific decisions, not vocabulary."

### 8. Hidden coupling: lifecycle/specify §2 vs requirements-gather — scope-mismatch

Three failure modes from placing identical inline-write rule in both producers:
- **Feature-local terms admitted to project glossary**: A feature lifecycle's `BQDatasetRef` resolved at spec time persists project-wide even after the lifecycle archives. Other features unnecessarily load the term.
- **Project-level terms re-defined at feature level**: spec interview "resolves" `phase_transition` differently inline — silently overwrites the project-canonical entry.
- **Concurrent writes across simultaneous lifecycles**: Two parallel overnight feature lifecycles both write inline to `glossary.md`. No `fcntl.flock`, no atomic-rename. The existing sandbox-write architecture has no concurrency primitive — `/requirements-write` operates one orchestrator invocation at a time. Inline-write at two surfaces under overnight parallel-dispatch breaks this implicit serialization.

DR-2's "producer-consumer separation matches Matt's model" rationale assumes Matt's model has the same concurrency profile. It does not — Pocock's `grill-with-docs` is synchronous, single-user. **Required mitigation options**:
- (a) Restrict glossary inline-write to `requirements-gather` only. Feature-spec surfaces candidate terms as Q&A items and defers to next requirements interview.
- (b) Add atomic-rename semantics via a CLI subcommand (`cortex-glossary append`); promotes glossary to a state-mutation surface with telemetry; events-registry row required.
- (c) Five-bucket classifier with feature-local-term bucket; structural restriction in `specify.md §2` says "do not write if feature-local."

## Open Questions

The Adversarial Review surfaced eight contradictions or gaps with Agent 4's recommendations. The Spec phase must resolve these before plan/implement:

1. **Term-already-exists protocol** — Inline-write rule needs a probe-before-write branch (use verbatim / surface conflict / reclassify). Currently unspecified. **Spec: define the branch behavior.**

2. **Classifier scope (binary vs four-bucket)** — Pocock uses a binary classifier (project-specific vs general programming); the four-bucket Cortex synthesis is unproven at inline-write cadence under interview pressure. **Spec: pick binary for v1 OR document the four-bucket classifier as a Cortex extension with effort=high evidence justifying its judgment shape.**

3. **Recommend-before-asking gate** — A model-introduced term from a recommend-before-asking line, never user-confirmed, currently triggers inline write. **Spec: require user-named or user-confirmed term before write.**

4. **Decision (a) re-opened** — A2 with Language-section-only injection may better honor the exemption's actual "existing reasoning" rationale than A1's blanket exclusion. **Spec: choose A1 vs A2-narrowed with explicit reasoning anchored on the exemption's wording.**

5. **Decision (b) re-opened** — B3's "always-load if exists" introduces a categorically new semantic vs the existing tag protocol's author-curated-signal model. B2 reframed as a `## Global Context` schema extension to `project.md` preserves the invariant. **Spec: pick B1/B3 (with explicit acceptance of the new protocol semantic) or B2-as-schema-extension.**

6. **Dual-producer scope-mismatch and concurrency** — Project-scope glossary writes from a feature-scope producer create scope-leak and parallel-overnight race conditions. **Spec: pick from (a) restrict inline-write to requirements-gather only, (b) atomic-rename via CLI subcommand, or (c) five-bucket classifier with feature-local-term filter.**

7. **Contract-coherence cascade** — Narrowing requirements-gather affects requirements-write's exclusive-write claim, the orchestrator's passive-artifact framing, the list subcommand's scope, e2e simulation, and the glossary template's documentation home. **Spec: either re-open DR-2's deferred-write rejection OR enumerate every coherence point with planned updates.**

8. **Parity test cascade** — At least five parity surfaces are affected. **Spec: enumerate each impacted test and its planned update in the touch-points list.**

## Considerations Addressed

This research was dispatched without `research-considerations`. No considerations to address.
