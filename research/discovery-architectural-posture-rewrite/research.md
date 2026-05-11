# Research: discovery-architectural-posture-rewrite

Second-pass audit of `/cortex-core:discovery`. The prior session (`research/discovery-skill-audit/research.md`) ended with a recommendation to add gates — extract clarify-critic, add a §3.5 Critical Pass sub-phase, add an approval gate at decompose §4. The user rejected that direction as "more machinery atop more machinery" and reframed the desired posture: **"Discovery is all about a high-level epic creation with rough ideas of what parts need to come together for that to work. It needs to be a principal architect type of discovery that proves out the larger architecture of the epic and design and edge cases without getting too in the weeds."**

This artifact holds principal-architect as the user's intent and tests one operationalization of it through a walk-through against `research/vertical-planning/`, with prescriptive-prose semantics grounded empirically across 14 sampled discovery-sourced tickets.

> **Revision note 1 (post-critical-review)**: An initial draft of DR-1 introduced a defect-vs-novel binary annotation on each architectural piece that gated path:line permission, lexical-scan whitelisting, and bundling judgment. Critical review (9 A-class findings across 4 reviewer angles) identified the binary as a circular load-bearing pivot with no independent rubric, asymmetric failure modes (over-tagging defect inverts the lexical scan), unspecified scan-exempt section taxonomy, an uncalibrated lexical threshold, walk-through evidence covering only the naive variant of the rule (not the refined defect-vs-novel variant), no events.log instrumentation for any new gate, and a bundling-question riding on an approval gate the walk-through itself said misses vagueness-class signals. The revised DR-1 below collapses the binary, replaces the multi-section taxonomy with a single optional `Touch points` section, removes the threshold, demotes the semantic self-check to authoring-time positive-routing, instruments three named gates with events, and replaces the bundling-question with a piece-count heuristic at architecture-section authoring time.

> **Revision note 2 (post-devil's-advocate + refined-shape re-walks)**: Following ticket creation (#195), a devil's advocate pass surfaced four objections: relabel-risk in the Architecture section, an unexamined demote-decompose alternative, prose-fixing-prose fragility, and vendor-endorsement migration. Two of these survived honest re-examination. To address the prose-fragility concern — the load-bearing one — the spec-phase re-walk obligation was executed pre-implementation rather than deferred. Both required corpora were walked: vertical-planning (mixed-stream, ~9 pieces under refined shape) and repo-spring-cleaning (surface-anchored, ~3 pieces under refined shape). Both re-walks produced architecturally-correct tickets with one gate-caught leak each — the gate detected real prescription leaks when applied honestly. Re-walk findings folded into the artifact below as `## Refined-shape re-walks (spec-phase, executed pre-implementation)`. The demote-decompose alternative was added to Feasibility as Approach G and *initially cut with rationale* (requires major new refine capability; cross-ticket coherence moves to a worse layer); revision note 3 below reverses that cut. The vendor-endorsement migration concern was confirmed as real but lower-likelihood than the framing implied; the existing "dissolved" language softened to "migrated to a less likely surface" in the trim table. See DR-1 §"Refined shape" and §"Refined-shape re-walks."

> **Revision note 3 (direction change: DR-1 → DR-G)**: After committing DR-1 as #195 and adding the demote-decompose option to Feasibility as cut Approach G, critical re-examination of the cut rationale found it thin: the "requires major new refine capability" framing was wrong (a small new promote-piece workflow suffices, refine is unchanged), the "cross-ticket coherence moves to a worse layer" framing was wrong (coherence lives in the Architecture section under either shape, with better placement under DR-G), and the "XL scope" estimate was inflated (realistic shape is M-L). The honest cut motivation was sunk cost on #195 plus familiarity bias toward "discovery produces tickets" — neither survives the user's stated criterion of best-long-term-option-even-at-upfront-cost. The user's reframe of discovery's posture ("high-level epic creation with rough ideas of what parts need to come together") describes DR-G, not DR-1. Accordingly: #195 is retired with a superseded-by pointer; #196 is created framed as DR-G; the empirical re-walk evidence transfers (it validated the per-piece ticket-body shape, which is what promote-piece will produce). DR-1's components that survive under DR-G: clarify scope-envelope (unchanged), Architecture section (richer, becomes load-bearing artifact not summary), approval checkpoint (now gates the architecture, structurally stronger), events instrumentation (event types adjusted), section-partitioned prescriptive-prose check (relocates to promote-piece time). DR-1's components that don't survive: decompose §2 per-piece ticket derivation (removed), "Why N pieces" justification gate (no decompose-time pressure to constrain count). New under DR-G: promote-piece workflow (skill or CLI), Architecture-section-richness calibration (worked examples + anti-patterns at spec time). See Feasibility Approach G (cut rationale superseded by this note) and #196 ticket body.

## Research Questions

1. **Diagnosis + shape**: Tracing the over-decompose/undersized/prescriptive/pigeonhole failure mode through one real over-decomposed discovery, what protocol surfaces produce each pain? What architectural shape of fix addresses all four pains as a unified design, including where "spec phase is valuable" lands, what happens to R2-R5 + surface-pattern helper, and whether the intervention is discovery-side, refine-side, or both? → **Answered below**; shape is a coordinated discovery-side rewrite (clarify §6 scope envelope + research.md `## Architecture` section with piece-count justification + research→decompose approval checkpoint + decompose.md aggressive trim + uniform Role/Integration/Edges/Touch-points ticket template + a single lexical prescriptive-prose check that partitions on section, not on piece type + three named events). Refine-side strengthening deferred. See DR-1.

2. **Walk-through evidence**: Applied to `research/vertical-planning/`, does the proposed shape produce architecturally-richer + appropriately-sized + non-prescriptive tickets, or relabel the same problem? Where does it break at edges? → **Mixed, on the naive shape only.** Headcount comes down (8 vs 11 shipped vs 29 drafted). Pigeonhole pressure releases on architecturally-novel pieces. Mechanism creeps back in on pieces whose value sits at a specific surface; vagueness creeps in on pieces whose value is structural. Bundling pain migrates from decompose-time to architecture-section authoring (pieces 4/7 still over-bundled). Edges: zero-piece exit undefined; one-line-change work forces empty role+integration+edges narrative. **The walk-through tested the naive variant of the rule.** The refined shape (uniform template + Touch points + piece-count heuristic + instrumented gates) is unvalidated. See DR-1 §"Refined shape" and §"Spec-phase obligation."

3. **Prescriptive-prose semantic check**: What lexical/structural signals distinguish prescriptive prose (function/file/line/control-flow named at decompose time) from architectural prose (role/integration/seam/contract named)? Is the distinction gate-checkable? → **Yes, partially — the gate-checkable component is structural: path:line citations and quoted prose patches are permitted only inside an optional `Touch points` section, never in body sections (Role/Integration/Edges).** Section indices (`§3a`, `R2(b)`) treated identically to path:line: permitted in Touch points, not in body. Semantic question ("would this paragraph still be true if implementer chose a different file/function?") relocated to authoring-time positive-routing in decompose §2, not a post-hoc self-check. See DR-1 §"Prescriptive-prose check (refined)."

## Codebase Analysis

### Current discovery protocol surfaces producing each pain

**Over-decomposition source**: `skills/discovery/references/decompose.md:11-31` §2 "Identify Work Items" treats *research findings* as the unit of decomposition — "Analyze the research and break findings into discrete, independently implementable work items." When research surfaces six approaches × three streams × two risk profiles (the vertical-planning case), decompose mirrors that grid → 29 children. The protocol does not ask "what's the right *architectural* granularity for tickets" because granularity isn't a named axis. The user's working remediation ("think critically about value → drop a few + combine a few") operates at exactly this level — re-grouping mirrored findings into pieces — and is currently entirely informal.

**Undersized source**: same as above. R3 per-item ack flow at `skills/discovery/references/decompose.md:37-42` encourages preserving every item rather than consolidating; the R4 cap at `:35` only fires on flagged items, not on aggregate count. The protocol has no "is this ticket worth its own lifecycle run" check.

**Prescription source**: `skills/discovery/references/decompose.md:24` R2(a) Local grounding check actively *requires* a `[file:line]` citation in Value prose — which the prose-scan finding identified as the single strongest prescriptive marker (Signal 1). R2(b) at `:25` cross-checks the research-side premise via the same `[file:line]` citation pattern. The R2 stack pushes Value prose toward path:line mechanism. The surface-pattern helper at `:27` deprecates vendor-authority phrasings ("Anthropic recommends", "industry best practice") but does *not* deprecate concrete mechanism phrasings ("extract function X from file:N"). The result: tickets that survive R2-R5 are *more* prescriptive than tickets that fail it, because surviving requires path:line grounding.

**Pigeonhole source**: prescription is the proximate cause. The deeper cause is that decompose-time ticket bodies are written before refine has a chance to challenge the framing. By the time refine runs `skills/refine/references/clarify-critic.md:14-68` Parent Epic Alignment sub-rubric, the body already names the mechanism. The sub-rubric evaluates child clarified-intent vs parent epic stated-intent for *alignment* — it does not ask "is this child overly prescribed for an epic that should permit reframing?" See refine-side considered-and-deferred analysis below.

### Empirical prose-scan: signals that distinguish registers

The prose-scan agent reviewed 14 discovery-sourced tickets across three batches (`backlog/083-092`, `backlog/166-183`, `backlog/188-194`). Breakdown:

- **Strongly prescriptive** (6 tickets): `backlog/173`, `backlog/175`, `backlog/177`, `backlog/179`, `backlog/183`, plus mixed-leaning `backlog/166`. Typical body shape: file paths with line numbers, quoted prose patches, imperative mechanism verbs, schema-shape specifications, algorithmic procedures.
- **Mildly prescriptive** (2 tickets): `backlog/192`, `backlog/193`. File-granularity only; no line numbers; no quoted patches.
- **Architectural** (3 tickets): `backlog/190`, `backlog/191`, `backlog/194`. Role nouns + integration verbs; mechanism unfixed.
- **Mixed** (3 tickets, register varies by paragraph): `backlog/085`, `backlog/090`, `backlog/188`, `backlog/189`.

The `188-194` batch is materially more architectural than the `166-183` batch — recent improvements (notably the `decomposed.md:147` ban on prescriptive headers shipped via tickets #137/138/139) appear to have moved the needle. But strongly-prescriptive tickets still ship: `backlog/177` has no banned header yet contains five paragraphs of mechanism (quoted prose patches, line-number ranges, algorithm specs). The current lexical rule catches header names but not body prose; the user's pain is in the body.

**Per-ticket citation-count distribution was not measured.** The prose-scan recorded the prescriptive-vs-architectural classification and quoted representative passages, but did not enumerate path:line occurrences per ticket. The refined gate (DR-1 §"Prescriptive-prose check") therefore does not depend on a numeric threshold — it flags ANY path:line citation in body sections. This is intentionally stricter than the original draft's ≥3 threshold, which was uncalibrated.

**Concrete examples** (from the prose-scan):

- Strongly prescriptive: `backlog/173-fix-duplicated-block-bug-in-refine-skillmd-and-5-stale-skill-references.md:36`: *"`skills/refine/SKILL.md` lines 117–136 and 138–157: identical 'Alignment-Considerations Propagation' sections. Delete one copy."*
- Strongly prescriptive: `backlog/177-trim-verbose-lifecycle-skill-content-implementmd-1a-planmd-1b-and-skill-gate-compression.md:53`: *"Collapse Gate 1 prose to ~3-line: 'Auto-escalate `simple` → `complex` if research.md has ≥2 `## Open Questions` bullets at end of research phase...'"*
- Architectural: `backlog/190-promote-lifecycle-state-out-of-events-log-full-reads.md:26`: *"This is wrong-layer storage: write-once-or-rarely state, read many times, currently buried in append-only logs and prose artifacts."*

The semantic distinction the user is reaching for is real, observable in the corpus, and admits a structural gate. Lexical part catches signal 1 (path:line) and signal 4 (quoted prose patch) by section — body sections flag, Touch points permits. No threshold; no semantic post-hoc check.

### Walk-through against `research/vertical-planning/`

The walk-through agent applied a **naive candidate** (decompose §2 rewrite to "name architectural pieces, no mechanism") to vertical-planning's research and compared the would-be output to the actual `decomposed.md`. **The walk-through did not test the refined shape below.** Key findings on the naive candidate:

- **Headcount**: 8 architectural-piece tickets vs 11 manually-consolidated tickets vs 29 originally drafted. The fix gets closer to the user's stated "reasonably sized" target than the shipped 11, primarily by merging Stream-A's three risk-flavored tickets into one piece.
- **Information loss on consolidation**: Stream-A's manual split (byte-identical / superset / predicate-test) preserved risk-profile information that the architectural-piece framing erases. Under the refined shape (DR-1) the lost information can be preserved by naming the surfaces in a `Touch points` section — risk flavors that anchor on specific files/contracts are nameable without making the ticket prescriptive.
- **Mechanism leaks on surface-anchored pieces**: pieces 2 (in-skill trim + duplicated-block bug), 5 (Architectural Pattern field + Scope Boundaries removal), and 6 (P9/S7 gates + `## Outline`) could not be described without naming the specific defect / field name / naming convention. The naive "no mechanism anywhere" rule was unsurvivable on these pieces. **This was the load-bearing failure of the naive operationalization.** The refined shape addresses this not by binary annotation (the initial-draft response, rejected at critical review for circularity) but by permitting path:line citations only inside an optional `Touch points` section that any piece may include.
- **Novel pieces drift to vagueness**: piece 6 ("introduce phase structure, gated by orchestrator") was unactionable as written. Refine reading it has too much room. Vague-mush risk is real and is not directly addressed by the refined shape; the spec-phase re-walk obligation exists in part to test whether Role/Integration/Edges authoring guidance produces concrete novel-piece bodies or vague ones.
- **Bundling pain migrates**: piece 4 (5 hygiene items) and piece 7 (4 test classes) over-bundled because the piece-naming step chose a coarse axis. The refined shape addresses this not at the approval checkpoint (which the walk-through showed catches counts but not vagueness) but at architecture-section authoring time: when pieces > 5, the agent must include a "Why N pieces" justification per piece explaining what makes each distinct.
- **Edge failures**: (i) single-piece research → decompose.md unconditionally creates an epic; needs explicit "≤1 piece → no epic" branch. (ii) zero-piece research ("just edit X") → no exit defined; agents will manufacture pieces. (iii) true S-sized one-line work → role+integration+edges narrative is vacuous, becomes ceremony in a different costume. Refined shape addresses (i) and (ii) via §4 explicit branches; (iii) is partially addressed by the `Touch points` section accommodating a one-line "the change lives at X" reference without forcing narrative.

The walk-through verdict on the **naive candidate** was: "**works partially**. Headcount comes down. Pigeonhole pressure releases on architecturally novel pieces. Mechanism creeps back on known-defect pieces; vagueness creeps in on novel pieces. The 'no mechanism' rule isn't survivable literally."

The refined shape is the response. It was re-walked pre-implementation; see next subsection.

### Refined-shape re-walks (spec-phase, executed pre-implementation)

Following a devil's advocate pass that surfaced prose-fixing-prose as the load-bearing fragility, the spec-phase re-walk obligation was executed before implementation rather than deferred. Both required corpora were walked under the refined shape (uniform Role/Integration/Edges/Touch-points template, section-partitioned gate, piece-count justification when N > 5, single-question approval gate).

#### Vertical-planning re-walk (mixed-stream corpus, refined shape)

- **Pieces produced**: 9 (vs 11 shipped, 29 originally drafted). Role-named (reference-integrity restorer, cross-skill canonicalizer, skill-content trimmer, skill-meta uplift, conditional-content extractor, artifact-template normalizer, skill-design test bed, vertical-planning surface, deterministic complexity router).
- **Section-partitioned gate**: 1 leak caught. Ticket 8 (vertical-planning surface) leaked a path:line into Edges; the gate flagged it correctly; remediation was a one-line edit moving the citation to Touch points.
- **Pain pass/fail**: over-decompose PASS (9 vs 11 manual / 29 drafted); undersized PASS (Touch points preserves detail on surface-anchored pieces without inflating body); prescription PASS with one caught leak; pigeonhole PASS (Ticket 8 leaves refine room to reframe DR-1's measure-first option vs naive adoption).
- **Failure modes surfaced**:
  1. **"Why N pieces" can rationalize bundling rather than constrain it.** The justification exercise produced defensible distinguishers without falsifying the count. Authors writing under prompt-pressure produce 9 plausible-looking justifications; the gate has no falsification mechanism.
  2. **Gate is honor-system unless implemented as code.** The path:line leak in Ticket 8 was caught only because the walk-through author was honest. A motivated author could leave it; a real lexical scanner (script) would catch it deterministically.
  3. **Touch points became a richness valve on the most surface-anchored piece (Ticket 8).** Body sections were real but thinner; the load-bearing parser-line-range, P9/S7 specifics, and exact template section names lived in Touch points.
  4. **Vague-mush partially still present on novel pieces.** Ticket 4 (skill-meta uplift "improve discoverability") and Ticket 7 (test bed "add regression guards") have role-true but role-generic body sections. Touch points patched this for 7 but barely for 4.
  5. **Single-question approval gate strains at 9 pieces.** Gate optimized for 3–5 pieces; at higher counts the "approve all / revise all / drop all" instrument is coarse.

#### Repo-spring-cleaning re-walk (surface-anchored corpus, refined shape)

- **Pieces produced**: 3 (vs 3 shipped, 7 originally drafted). Role-named (installer-facing surface rewrite, orphan-implementation retirement, lifecycle/research archive sweep). Exact parity with shipped consolidation.
- **Section-partitioned gate**: 1 leak caught. Ticket 2 (orphan retirement) leaked `justfile:326-327` into Edges; the gate flagged it correctly.
- **Pain pass/fail**: over-decompose PASS (parity with shipped); undersized PASS; prescription PARTIAL FAIL (1/3 needs reframe — the surface-anchored corpus stresses the body-section discipline more than mixed-stream); pigeonhole PASS with improvement (Role-level "no live consumer + zero drift" leaves implementers more room than a hardcoded delete-list).
- **Failure modes surfaced specific to surface-anchored corpora**:
  1. **Body sections become token-inefficient.** 60–80% of substance lives in Touch points; body sections carry framing-tax (audience claim, sequencing contract, spec/code coupling) but not content. The gate's structural value per token drops on surface-anchored corpora.
  2. **Bundling within a role can happen unchallenged when count ≤ 5.** Ticket 1 (installer-facing surface) bundles six legitimately-distinct content classes inside one role; the role description ("what installer sees first") accepts them; "Why N pieces" doesn't fire because count is 3. The role-level framing is permissive enough that bundling happens without the gate firing — correct on this corpus, but unchecked on others where bundling might be a mistake.
  3. **Information loss vs prescriptive shipped tickets is unknown without reading shipped body content.** Likely-net: parity for what-to-do, mild loss on why-this-sequencing-matters unless authors lean harder on Integration. Acceptable.
  4. **Touch points becomes the gate's blind spot.** The prescription-check operates on body sections only; on surface-anchored corpora Touch points is where everything load-bearing lives. Quoted-prose-patch over-volume in Touch points is not currently checked.

#### Synthesis across both re-walks

**The refined shape works on both corpus types.** Both produced architecturally-correct tickets at appropriate headcount. The gate caught real leaks on both walks when applied honestly. The shape is materially better than the naive variant — the binary annotation that critical review cut was the right cut.

**The weakest components are now visible**:

- **"Why N pieces" rationalizes rather than constrains** — needs a falsification framing in the protocol prose ("attempt to merge each piece with its neighbor; record what specifically blocks the merge" rather than "explain why each is distinct"). Spec-phase task.
- **The lexical scanner must be implemented as code, not relied on as prose discipline** — otherwise the gate is honor-system. Spec-phase task: ship a small script (e.g., `bin/cortex-check-prescriptive-prose`) that scans ticket bodies for the forbidden patterns and reports flags.
- **Touch points has no over-quotation check** — quoted prose patches in Touch points are currently permitted freely. Consider a follow-up: cap quoted-content in Touch points at N lines per entry, or flag entries that quote >50% of the cited surface. Not blocking; surface for follow-up audit.
- **Single-question approval gate strains at high piece counts** — when N > 7 or so, the gate's coarse "approve/revise/drop" instrument may need per-piece sub-questions. Not blocking; observe in practice and revise if needed.

**The demote-decompose alternative (devil's advocate Objection 2) is a real cut option but properly cut for scope.** See Feasibility table Approach G.

### Refine-side considered and deferred

`skills/refine/references/clarify-critic.md:14-68` Parent Epic Alignment sub-rubric is the only existing place where prescriptive child tickets get challenged against epic intent at refine time. The sub-rubric currently evaluates child-intent-vs-epic-intent alignment with rubric (a)/(b)/(c) at `:68` — it does not check for over-prescription. Adding an over-prescription check would mean adding a new dimension or sub-rubric to a sub-rubric, which sits inside a critic dispatch that has a soft cap of ≤5 dimensions at `:221`.

Strengthening refine-side has two structural issues:

1. **Catches the symptom downstream**: by the time refine runs, the decompose-time ticket body already names mechanism. The agent picking up the ticket has already absorbed the prescribed mental model.
2. **Per-ticket scope**: refine runs per child. The cross-ticket coherence failure ("these 15 tickets are really 5 pieces") is invisible to refine. The user's pain has a cross-ticket component that refine-side cannot reach.

Refine-side strengthening could be a complementary safety net for the *individual* over-prescription pain that the discovery-side fix misses on novel pieces (where refine could press "is this ticket actually too vague to act on?"). But it is not load-bearing for the primary failure mode (cross-ticket over-decomposition + decompose-time mechanism prescription). Deferred to follow-up; if discovery-side fix leaves residual pain on novel pieces specifically (the walk-through's vague-mush failure mode), refine-side strengthening becomes the obvious next ticket.

### Existing surface to trim

Per `requirements/project.md` workflow-trimming bias: prefer removing existing surface to adding new surface. Candidates for removal under the refined fix:

| Surface | Disposition | Rationale |
|---------|-------------|-----------|
| `decompose.md` R2(a) local grounding (`:24`) | **Remove** | R2(a) requires path:line in Value prose — the strongest prescriptive marker per the prose scan. Net negative under principal-architect framing. |
| `decompose.md` R2(b) research-premise check (`:25`) | **Remove** | Same premise as R2(a); pushes Value toward concrete mechanism. |
| `decompose.md` E9 ad-hoc fallback (`:26`) | **Remove** | Inherited from R2; dies with R2. |
| `decompose.md` surface-pattern helper (`:27`) | **Remove** | Vendor-endorsement was a real prior failure mode but the principal-architect frame migrates it to a less likely surface (architectural-piece body sections have no Value-prose shape where "Anthropic recommends" naturally attaches). Caveat surfaced by devil's advocate: Touch points is a prose surface where vendor-endorsement *could* still appear if an author writes "Anthropic recommends X" there — semantically out-of-place but not gate-flagged. Acceptable trade per the user's stated pain priorities (mechanism prescription > vendor-endorsement); revisit if the unlikely failure mode shows up empirically. |
| `decompose.md` R3 per-item ack flow (`:37-42`) | **Remove** | Quotes a Value string verbatim; under the new framing tickets don't have a structured Value field for this to operate on. Prior session's empirical finding (0/13 sampled tickets have structured Value) confirms the flow has no string to quote in practice. |
| `decompose.md` R4 cap (`:35`) | **Remove** | Cap exists to halt cascading R2 flags; no R2, no cap need. |
| `decompose.md` R5 flag propagation (`:70`) | **Remove** | Propagates R2 flags through consolidation; no R2 flags, nothing to propagate. E10 invariant dies with R5. |
| `decompose.md` R7 event types specific to flagging (`:46-52`) | **Replace, do not just remove** | Original draft removed R7 with no replacement. Critical review (Reviewer 4 A-class finding) identified this as breaking the CLAUDE.md MUST-escalation evidence path. Refined shape replaces R7's three flag-events with three new gate-events: `architecture_section_written`, `approval_checkpoint_responded`, `prescriptive_check_run`. See DR-1 §"Events instrumentation." |
| `decompose.md` §3(a)/(b) consolidation (`:54-70`) | **Keep** | Empirically validated by prior-session sampling. Same-file overlap and no-standalone-value prerequisite are the real consolidation drivers. |
| `decompose.md` §4 grouping (`:72-83`) | **Keep, augment** | Add explicit "single-piece → no epic" branch; add "zero-piece → fold-into-#N or no-tickets" exit. |
| `decompose.md` §5 ticket creation (`:84-96`) | **Keep** | Unaffected. |
| `decompose.md` §6 decomposed.md artifact (`:98-126`) | **Keep** | Audit trail. |
| `decompose.md:147` lexical prescriptive-headers ban | **Replace** | Necessary but insufficient — prose-scan confirms agents violate the spirit without violating the letter. Replace with section-partitioned lexical check (path:line and section indices permitted only in optional `Touch points` section). |

Net effect on rule count: existing ~17 rules → ~7 rules (§3(a), §3(b), §4 with two new branches, §5-§9 unchanged, new §2 architectural-piece consumption rule, section-partitioned prescriptive-prose check, three event emissions). The protocol gets meaningfully shorter, not longer.

## Web & Documentation Research

Skipped. The topic is purely internal to this project's skill surface; no external library/API research applies. The brief explicitly disallows spikes/measurement and frames the load-bearing test as a codebase walk-through.

## Domain & Prior Art

Skipped. The discovery skill's posture is project-specific; broader "story splitting" prior art (INVEST, eight canonical splits) was reviewed in the prior session and contributed to the previously-cut V-gate proposal; the principal-architect framing is closer to "vertical-slicing review" but does not need additional prior-art grounding beyond what was established in `research/discovery-skill-audit/research.md`.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **B. Defer refine-side strengthening (DR-2 deferred)** | — | Low — the discovery-side rewrite carries the load under either A or G. If novel-piece vague-mush persists after G lands, refine-side becomes the next ticket. Reversible deferral. | G's outcome. |
| **C. Status quo (do nothing)** | — | High — user pain documented; prior session's recommendation already rejected. | — |
| **D. Naive principal-architect §2 rewrite alone (prior recommendation, pre-revision)** | S | High — walk-through showed it fails on surface-anchored pieces, novel pieces, edge cases. **Not recommended.** | N/A. |
| **E. Defect-vs-novel binary annotation (initial-draft DR-1, cut at critical review)** | M | High — circular rubric, asymmetric failure modes, lexical scan inverts on mis-annotation. **Cut wholesale.** | N/A. |
| **F. Add gates without trimming (alternative read of prior session)** | M | High — compounds cumulative skip risk per CLAUDE.md; user has explicitly rejected "more machinery." **Not recommended.** | N/A. |
| **G. Demote decompose-time ticket creation; pieces promoted on demand via new workflow** (RECOMMENDED — supersedes A per revision note 3) | M–L | Medium. Architecture section richness must be sufficient to drive useful ticket creation at promotion time — calibration via worked examples is a spec-phase task. New promote-piece skill (or CLI) is net-new surface (~50–100 lines of skill prose plus a small helper). Backlog visibility for unfragmented pieces lives in the research artifact rather than the backlog index — acceptable trade given the alternative (stale piece-tickets accumulating) is the failure mode this approach exists to address. Initial cut rationale ("requires major new refine capability", "cross-ticket coherence moves to worse layer", "XL scope") was wrong — refine is unchanged; coherence lives in the Architecture section under either shape with better placement here; realistic scope is M–L. | Architecture-section richness calibration (one worked example per piece-shape category, anti-patterns list); promote-piece workflow design (slash command vs CLI). |
| **A. Coordinated discovery-side rewrite (DR-1, INITIAL recommendation — superseded by G per revision note 3)** | M | Initial recommendation. Refined-shape re-walks confirmed it works empirically. Cut motivation per revision note 3: structurally less aligned with user's stated framing than G; "Why N pieces" gate is the weakest component of either design and exists to manage pressure that G doesn't create; backlog calcification under per-piece-ticket model makes future transition to G more expensive over time. The empirical work isn't wasted — the per-piece ticket-body shape DR-1 validated is what promote-piece produces under G. | N/A — superseded. |

## Decision Records

### DR-1: Coordinated discovery-side rewrite (refined principal-architect operationalization)

#### Refined shape (post-revision)

Critical review surfaced 9 A-class findings on the initial draft's defect-vs-novel binary, lexical-gate thresholds and section taxonomy, walk-through coverage, and missing instrumentation. The refined shape below addresses each. **The refined shape itself has not been re-walked; spec phase must do so.**

One coordinated change across `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`, and `skills/discovery/references/decompose.md`. Six components, tightly coupled — split risks half-landed state worse than the status quo (acknowledged: this raises the cost of partial revisions discovered at implementation time).

**Component 1: Clarify §6 scope envelope**

Add a "Scope envelope" output to `skills/discovery/references/clarify.md` §6. Two short bullet lists (2–3 bullets each): "In scope" and "Out of scope / Non-goals." Optional — when topic is well-bounded already, the agent may write "No envelope needed (topic naturally bounded)." Where the user's "Clarify needs to be stronger initially" intuition lands. Small addition; not a new phase.

**Component 2: Research.md `## Architecture` section with piece-count justification**

Add `## Architecture` to the research artifact template at `skills/discovery/references/research.md` §6, between Codebase Analysis and Web & Documentation Research. Three required sub-sections plus one conditional:

- **Pieces** — one bullet per structural element of the proposed change, named by role. No `defect`/`novel` annotation — uniform treatment.
- **Integration shape** — how pieces connect, at the same level of abstraction. Names contracts and data flows between pieces, not file relationships.
- **Seam-level edges** — what breaks at piece boundaries. One bullet per edge.
- **Why N pieces** (CONDITIONAL: required only when piece count > 5) — one short justification per piece explaining what makes it distinct from the others, particularly distinguishing it from any adjacent piece that might be a candidate for merging. This is the cross-ticket-coherence check moved from the approval gate (where the walk-through showed it weak) to the architecture-section authoring step (where the bundling decision is actually being made).

Authoring guidance in the template: "Aim for the level of abstraction the user would use describing the change to a peer in conversation. Pieces should be visible to someone outside the codebase, not requiring file/function knowledge to parse." Empty `## Architecture` is permitted and meaningful — it signals the change has no architectural surface and decompose should exit via the zero-piece branch.

**Component 3: Research→decompose approval checkpoint (single question)**

Between research §6b critical-review and decompose §1, add a single `AskUserQuestion` presenting the Architecture section. **One question**: "Are these the right pieces?" — options: Approve / Revise pieces / Drop topic.

The original draft's second question ("Are any pieces overbundled?") is removed. The walk-through identified that approval-style checkpoints catch counting failures but not vagueness/judgment failures; bundling is a vagueness/judgment failure, so it's not addressed by adding a checkpoint question. Bundling-catch moves upstream to Component 2's "Why N pieces" justification (when count > 5, the agent must structurally justify each piece; the user reviewing the Architecture section sees those justifications and can press on any).

Soft positive-routing form per CLAUDE.md.

**Component 4: Decompose.md aggressive trim + §2 rewrite + uniform ticket template**

Remove R2(a), R2(b), E9, surface-pattern helper, R3 per-item ack, R4 cap, R5 flag propagation, E10 invariant, R7 flag event types (lines `:24-27, 33-52, 70` of current decompose.md). Keep §3(a)/(b) consolidation, §4 grouping (augmented), §5 ticket creation, §6 decomposed.md, §7-9.

Rewrite §2 "Identify Work Items" to consume the approved Architecture section: "Each piece in the Architecture section becomes one ticket. Ticket title names the piece by role."

**Uniform ticket body template** (every ticket, no exceptions for piece type):
- **Role** (1–2 sentences from the piece bullet) — what role this piece plays
- **Integration** — which other pieces/surfaces this touches, named at role level
- **Edges** — seam-level edge cases this piece must handle
- **Touch points** (OPTIONAL) — path:line references and section indices for surfaces the implementer will need to find. This section is the *only* place in the body where `path:line`, `§3a`, `R2(b)` style citations are permitted. When the change anchors on specific known surfaces, name them here. When the change is structural with no fixed surface, omit.

**Authoring-time positive routing** (replaces the original draft's post-hoc semantic self-check, which critical review identified as delegating detection to the author who already wrote the prescriptive prose): the rewritten §2 instructs the author at body-writing time: "When writing each Role/Integration/Edges paragraph, ask: *would this paragraph still be true if the implementer chose a different file, function, or algorithm that satisfied the same role and contract?* If no — the paragraph names mechanism. Either move the load-bearing surface reference to the `Touch points` section, or rewrite the paragraph at role level. This is a thinking-cue during authoring, not a post-hoc gate."

**Component 5: Section-partitioned prescriptive-prose check**

Replace `decompose.md:147` (lexical prescriptive-headers ban) with a structural check that runs after §5 ticket creation, before §8 commit:

**The rule (single, simple)**:
- In ticket-body sections (`Role`, `Integration`, `Edges`): no `path:line` citations, no section indices (`§3a`, `R2(b)`, `## Foo` references to specific section locations), no quoted prose patches (fenced code block ≥2 lines or multi-line italicized quoted text).
- In the optional `Touch points` section: `path:line`, section indices, and brief quoted excerpts are permitted freely.
- Any violation in body sections flags the ticket. No threshold; section partition is the gate.

The previous draft's defect-vs-novel binary, ≥3 threshold, and "Constraints / Touch points / Research hooks" multi-section taxonomy are removed. The gate now partitions on one canonical optional section name (`Touch points`) and applies the same rule to all tickets.

**Meta-surface ticket handling**: tickets that modify skill prose itself (this artifact's own DR-1 produces such tickets) write surface citations to `Touch points`, not to body sections. The rule applies uniformly — the section index for a skill-protocol rule is a path-equivalent reference and lives in Touch points like any other.

Soft positive-routing form: "Before committing, run the prescriptive-prose check on each ticket body…" — not MUST. Per CLAUDE.md policy.

**Component 6: Events instrumentation**

Three new events emitted by decompose, replacing R7's removed flag events:

```jsonl
{"schema_version": 2, "ts": "<ISO 8601>", "event": "architecture_section_written", "topic": "<slug>", "piece_count": <int>, "has_why_n_justification": <bool>, "status": "ok|empty|skipped"}
{"schema_version": 2, "ts": "<ISO 8601>", "event": "approval_checkpoint_responded", "topic": "<slug>", "response": "approve|revise|drop", "revision_round": <int>}
{"schema_version": 2, "ts": "<ISO 8601>", "event": "prescriptive_check_run", "topic": "<slug>", "tickets_checked": <int>, "flagged_count": <int>, "flag_locations": [{"ticket": "<id>", "section": "<Role|Integration|Edges>", "signal": "path_line|section_index|quoted_patch"}]}
```

Events write to `research/{topic}/events.log` (consistent with existing event-emitting surfaces). The instrumentation enables CLAUDE.md MUST-escalation policy compliance: skip behavior on the three new soft surfaces is now countable. If a gate is later observed to be routinely skipped under representative cases, the F-row evidence supports an effort=high → MUST escalation case.

**§4 grouping augmentation**: explicit branches for the edge cases:
- "If Architecture has zero pieces, decompose exits with one of: (a) `fold-into-#N` verdict — body explains why the change folds into an existing backlog item; (b) `no-tickets` verdict — body explains why no backlog change is needed. No tickets created in either case. decomposed.md still written as audit trail."
- "If Architecture has exactly one piece, decompose creates one ticket, no epic. The piece becomes the single ticket directly."

#### Why this beats the naive principal-architect §2 rewrite (walk-through evidence) AND the initial-draft defect-vs-novel binary (critical-review evidence)

- **Mechanism leak on surface-anchored pieces**: addressed by the uniform `Touch points` section. Any piece may name surfaces there without flagging the body. No binary annotation, no circular rubric, no asymmetric failure modes.
- **Novel vague mush**: partially addressed by required Role + Integration + Edges structure (Edges is a positive constraint that forces the author to identify what breaks). Authoring-time positive routing reminds the author at body-writing time. Remainder is unmitigated — the spec-phase re-walk will be the first empirical signal of whether novel pieces drift vague under the refined shape, and refine-side DR-2 is the fallback if so.
- **Bundling migration**: addressed at Component 2 (architecture-section authoring) via piece-count justification when N > 5. The decision-point is where the decision is made, not at a downstream checkpoint.
- **Edge cases**: single-piece, zero-piece, and one-line work all have explicit §4 branches or template handling.
- **Spec-phase intuition**: lands at Component 3's approval checkpoint, not as a new artifact.
- **Critical-review findings addressed**:
  - Defect-vs-novel rubric circularity → binary removed; uniform template.
  - Lexical scan inversion on mis-annotation → no annotation to mis-apply; section partition.
  - Undefined Constraints/Touch-points/Research-hooks → single canonical section `Touch points`.
  - Uncalibrated ≥3 threshold → no threshold; any path:line in body = flag.
  - Semantic self-check delegating to same author → demoted to authoring-time positive routing.
  - Meta-surface caveat breaks on skill tickets → section indices treated as path:line; allowed only in Touch points.
  - No events.log instrumentation → three named events.
  - Approval-checkpoint Q2 (bundling) relies on weak gate → Q2 removed; bundling-catch moved to architecture-section authoring.

#### Trade-offs (revised gate-count accounting)

**Honest gate accounting**: the refined shape introduces three distinct soft surfaces, each fired at a different actor:

1. **Research-phase author**: must write `## Architecture` section with piece-count justification when N > 5 (Component 2).
2. **User**: must respond to approval checkpoint (Component 3).
3. **Decompose-phase author**: must run prescriptive-prose check before commit (Component 5).

This is three independent gates, not one clustered gate. Cumulative skip exposure under soft routing is `(1-p)^n` at the gate level. Going from R2-R5's one clustered gate (one decision skip propagates through R2(a) → R2(b) → R3 → R4 → R5 → R7) to three independent gates is an increase in independent skip surfaces.

**Why this is acceptable**:
- The three gates fire at *different actors*, not in sequence by one agent. A user-prompt skip and a decompose-author skip don't compose the way two-decisions-by-one-agent compose: the user's choice is not a continuation of the agent's mental state.
- Events.log instrumentation (Component 6) makes skip behavior countable. If any gate is observed to be routinely skipped, the F-row evidence supports MUST-escalation per CLAUDE.md.
- The textual rule-count drops (~17 rules → ~7 rules), reducing cognitive load on agents reading the skill prose.

**Other trade-offs**:
- Single large coordinated change vs incremental landings. The change is reversible; partial-landing cost is the cost of one revision PR if implementation discovers a component needs revision.
- Refined shape is unvalidated by re-walk. Spec phase MUST re-walk against vertical-planning plus one alternative corpus before implementation lands. See §"Spec-phase obligation" below.
- Risk-profile information loss on consolidated pieces. Addressed by `Touch points` accommodating surface citations on any piece.

#### Spec-phase obligation

The refined shape (Components 1-6) is a hypothesis informed by walk-through findings against the *naive* shape — not validated by re-walk. **Before implementation, the spec phase must run a second walk-through**:

1. Apply Components 1-6 to `research/vertical-planning/research.md` again — this time the refined shape, not the naive one. Produce the would-be Architecture section, the piece-count justification (if > 5), the ticket bodies with Role/Integration/Edges/Touch-points. Confirm: (i) headcount lands at user's stated target, (ii) `Touch points` accommodates the surface-anchored pieces 2/5/6 without flagging the body, (iii) Edges sections on novel pieces are concrete rather than vague.
2. Apply Components 1-6 to one alternative corpus — `research/repo-spring-cleaning/` (hygiene-heavy, likely all-surface-anchored pieces) OR `research/opus-4-7-harness-adaptation/` (policy-heavy, possibly all-novel pieces). The alternative corpus stress-tests the refined shape on a structurally-different research artifact than vertical-planning's mixed-stream case.
3. If either re-walk surfaces a failure mode not addressed by Components 1-6, revise the implementation ticket before landing.

The re-walk is the load-bearing empirical step; without it, DR-1 ships on n=1 walk-through evidence of a shape it isn't shipping.

#### Why discovery-side and not refine-side

Walk-through showed cross-ticket coherence failures (over-decomposition + over-bundling) are invisible to refine. Refine-side strengthening is a per-ticket downstream filter; the load-bearing fix has to be at decompose. Refine-side complementary check deferred to DR-2.

#### Why coordinated, not split into separate tickets

Trimming decompose.md without adding the `## Architecture` section leaves §2 with nothing to consume. Adding `## Architecture` without trimming R2-R5 preserves the rules that push toward path:line mechanism. The approval checkpoint without the Architecture section has nothing meaningful to approve. The components only ship coherent as a single change. Acknowledged trade-off: partial-revision cost rises (a single component needing revision blocks the others); mitigated by the spec-phase re-walk surfacing such revisions before implementation lands.

### DR-2 (deferred): Refine-side clarify-critic over-prescription check

- **Context**: Refine's clarify-critic Parent Epic Alignment sub-rubric at `skills/refine/references/clarify-critic.md:14-68` could be extended with an over-prescription check ("is this child ticket overly prescribed for an epic that should permit reframing?"). This would catch residual prescription pain on novel pieces that the discovery-side fix misses.

- **Recommendation**: **Defer**. The walk-through shows discovery-side fix is load-bearing; cross-ticket coherence pain (the primary failure mode) is invisible to refine. If, after DR-1 lands and the spec-phase re-walk completes, the user reports residual per-ticket over-prescription pain on novel pieces specifically, file a follow-up ticket to extend the alignment sub-rubric. Soft cap at `:221` permits one more dimension if needed.

- **Trade-offs**: shipping both DR-1 and DR-2 simultaneously would add a refine-side gate when the discovery-side fix may already dissolve the pain. Deferral is reversible and information-cheap — DR-2 becomes obvious if needed.

## Open Questions

**Resolved by pre-implementation re-walks (no longer open):**

- ~~Spec-phase re-walk corpus choice~~ — RESOLVED: both required corpora (vertical-planning + repo-spring-cleaning) walked pre-implementation; evidence folded into Codebase Analysis §"Refined-shape re-walks."
- ~~Will the refined shape actually produce architecturally-richer tickets than the naive shape on real corpora?~~ — RESOLVED: yes on both corpus types tested; gate caught real leaks; pain pass on three of four dimensions across both walks.

**Open — for implementation-phase spec.md to resolve:**

- **Lexical scanner as code, not prose discipline**: re-walks showed the gate is honor-system without a real scanner. Implementation must ship a small script (suggested: `bin/cortex-check-prescriptive-prose`) that scans ticket body sections for path:line, section indices, and quoted-prose-patches, reporting flags. Without this the gate is unenforced.
- **"Why N pieces" falsification framing**: re-walks showed the current "explain why each is distinct" prompt produces rationalization rather than constraint. Implementation should reframe the prompt to attempt-merge: "for each adjacent pair of pieces, attempt to merge them and record what specifically blocks the merge. If nothing blocks, merge." This converts the gate from defensive to falsificationist.
- **Architecture-section authoring guidance volume**: re-walks confirmed agents need concrete scaffolding to stay role-level. Implementation should ship one worked example per piece-shape category (surface-anchored, structural-novel) plus a 2–3 bullet anti-patterns list.
- **Piece-count threshold for "Why N pieces"**: set at >5 in current draft. Vertical-planning re-walk produced 9 pieces (justifications fired and were defensible-but-rationalizing). Repo-spring-cleaning re-walk produced 3 pieces (didn't fire; bundling within a role went unchecked but was correct here). Implementation may tune the threshold downward (>3 or >4) to make the justification fire more often, or pair the lower threshold with the falsification framing above.
- **Approval-checkpoint UX at high piece counts**: re-walk surfaced that the single-question gate strains when N > 7. Implementation may add per-piece sub-questions when count exceeds a threshold; verify by observation post-implementation.

**Surfaced for follow-up (not blocking #195 implementation):**

- **Touch-points over-quotation check**: re-walks showed Touch points becomes the gate's blind spot on surface-anchored corpora. Consider a follow-up audit checking Touch-points entries for quoted-content volume (e.g., flag entries quoting >N lines or >50% of the cited surface). Not blocking; surface as a follow-up ticket if Touch points proves to be a prescription-leak valve in practice.
- **Refine-side strengthening (DR-2)**: re-walks showed mild vague-mush persists on novel pieces (vertical-planning Tickets 4 and 7). If empirical post-#195 implementation confirms this, DR-2's refine-side over-prescription check becomes obvious.
