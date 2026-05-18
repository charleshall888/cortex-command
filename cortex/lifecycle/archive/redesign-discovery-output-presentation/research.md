# Research: redesign-discovery-output-presentation

> Topic anchor: Redesign how the discovery skill presents research findings at the research→decompose approval gate so the orchestrator can quickly grasp value, motivation, and per-piece purpose without slogging through a dense jargon-heavy technical block. Scope (artifact template vs gate rendering layer) deliberately open at clarify-exit.

## Context: this is Phase 2

A prior lifecycle, `cortex/lifecycle/improve-discovery-gate-presentation/`, completed 2026-05-12 (per its events.log). It added `## Headline Finding` as the first content section the gate quotes, ahead of `## Architecture`. Phase 1's stated mechanism was a tighter authoring directive in the template (`skills/discovery/references/research.md:78-84`): *"One paragraph. State the verdict and the one or two key findings supporting it."*

The current user complaint — "giant block of text… throwing out technical terms… using a ton of words to say not very much… slog to read" — is the post-Phase-1 evidence that Phase 1 did not fully land the orchestrator-readability affordance. Phase 2's job is to identify why Phase 1 underperformed and choose a different mechanism, not to repeat Phase 1's pattern.

## Codebase Analysis

### Files in scope
- `skills/discovery/SKILL.md` — gate prose at `skills/discovery/SKILL.md:74` (the "Research → Decompose approval gate (spec R4)" section). Currently instructs the gate to quote `## Headline Finding` then `## Architecture` subsections verbatim. Currently 106/500 lines (size budget).
- `skills/discovery/references/research.md` — artifact template. `## Headline Finding` slot at lines 78-84; `## Architecture` template with `### Pieces` / `### Integration shape` / `### Seam-level edges` / conditional `### Why N pieces` at lines 117-176.
- `tests/test_discovery_gate_presentation.py` — pins verbatim marker phrases (`R1_HEADLINE_MARKER_PHRASE`, `R3_DROP_DUAL_USE_MARKER_PHRASE`) and asserts `## Headline Finding` precedes `## Architecture`. Updates needed in lockstep with any pinned-phrase change.

### Adjacent surfaces (touched only if scope expands)
- `skills/discovery/references/decompose.md:11-13` — consumes `### Pieces` bullets 1:1 as ticket candidates. **Load-bearing contract**: any redesign must preserve a flat bullet list consumable here.
- `cortex_command/discovery.py` — pure event-emission + path-resolution. No rendering layer. Emits `architecture_section_written` keyed on `piece_count` / `has_why_n_justification` (lines 277-303) and `approval_checkpoint_responded` (lines 369-396). Field changes would propagate to `bin/.events-registry.md`.
- `bin/cortex-check-prescriptive-prose` (LEX-1) — scans ticket-body sections `## Role/Integration/Edges/Touch points`, NOT research.md. Structurally independent of this redesign.
- `tests/test_lifecycle_kept_pauses_parity.py` — scope is `skills/lifecycle/` + `skills/refine/`. Discovery gate is **NOT** in the parity inventory. Free to change without parity impact.

### Empirical readability evidence (the disease)

Measured `## Headline Finding` word counts in 4 production post-Phase-1 artifacts (template asks for "one paragraph"):

| Artifact | Headline Finding word count | Architecture section length |
|---|---|---|
| `cortex/research/cursor-skill-port/research.md` | **171 words** | 31 lines, 3 pieces |
| `cortex/research/grill-me-with-docs-learnings/research.md` | **296 words** | 35 lines, 4 pieces |
| `cortex/research/windows-support/research.md` | **317 words** | 42 lines, 5 pieces |
| `cortex/research/interactive-overnight-mode/research.md` | **402 words** | 39 lines, 4 pieces |

Every real artifact violates "one paragraph" by 2-4×. The Phase-1 authoring-directive mechanism, identical in shape to Agent 4's H+F recommendation ("sharpen the directive"), did not bind in production.

Each `### Pieces` bullet in production is a **150-250-word dense engineering manifest** packed with file paths, contract names, and cross-section references (`OQ7`, `DR-5`). The `### Why N pieces` falsification gate, when it fires, narrates the author's past-tense merge reasoning — opaque to non-author readers at decision time.

### The audience-mismatch finding (the underlying disease)

`## Architecture` is **authored for the future decompose-agent reader** (a contract surface for ticket synthesis). It is **displayed at the gate to a different reader** (the human approver deciding approve/revise/drop). Same content; wrong audience. The user's complaint is fundamentally audience-mismatch — Phase 2's surface is *which audience does the gate serve*, not *how to write Architecture more readably*.

### Project prior art for decision-surface gates
- `skills/lifecycle/references/specify.md:155-168` — spec approval gate prescribes three explicit decision-relevant fields: `Produced` / `Value` / `Trade-offs`. Each field answers one decision question. Significantly more decision-readable than the discovery gate.
- `skills/lifecycle/references/plan.md:277-289` — plan approval gate uses similar `Produced` + `Trade-offs` + overview pattern.
- `skills/discovery/references/decompose.md:123-135` — decompose-commit batch-review gate renders per-ticket bodies under their final 4-header template (review-at-final-surface pattern).

**Pattern verdict**: lifecycle's spec/plan gates *prescribe specific decision-relevant fields*. Discovery gate is the outlier — it re-renders artifact subsections rather than decision-relevant surface. Aligning discovery to the project's existing prior art is a precedented move.

### No Python rendering layer exists

`cortex_command/discovery.py` is 686 lines of event-emission + path-resolution; zero rendering. The "gate rendering" is the orchestrator-model reading markdown subsection headings in the order named by SKILL.md prose and re-quoting them. This means **the gate prose itself IS the rendering layer** — it can instruct extraction-and-reshape against a verified structural source, not just verbatim quotation. (Agent 1 initially framed this as a binary "fabricate or add slot"; Agent 5's adversarial pass identified the third option.)

## Web Research

### Convergent prior art for decision-gate presentation

Across ADRs (Nygard), Amazon 6-pager, Shape Up pitch, Rust RFC, and Google design docs, the consistent pattern for approve/reject decision surfaces is:

- **Decision-first / BLUF / Pyramid Principle (SCQA)** — the answer/recommendation comes first; supporting context after. Empirically reduces follow-up questions and meeting time.
- **Problem always paired with solution** — Shape Up's most-cited failure mode is solution-first without problem framing.
- **Non-goals / no-gos are load-bearing**, not optional — they prevent reviewers from re-litigating closed scope.
- **Three-way decision (approve/reshape/drop)** — templates supporting only two-way ("ship it / kill it") miss the most common gate outcome (good direction, reshape these specifics).
- **Reviewer-need ≠ author-need** — PR template research: reviewers need *why* it changed and *impact*, not restated content. Directly maps to discovery: the orchestrator can see the decomposition; they need *why these pieces, in this shape, for this value*.

### Readability research findings
- **F-pattern scanning** (Nielsen, 1.5M instances, replicated): readers scan, not read. First horizontal sweep, second shorter sweep, then vertical scan down left edge.
- **Above-the-fold attention is ~84% greater than below-fold**; 57% of viewing time happens in the first viewport. For markdown/CLI, this maps to the first ~25-40 rendered lines carrying disproportionate weight.
- **Jargon paradox (Berrios 2025)**: jargon simultaneously *decreases comprehension* AND *increases credibility judgments*. Particularly dangerous at an approval gate — rubber-stamping risk where the reader confidently approves something they didn't fully grasp.
- **Decision fatigue**: unbounded gates with 20+ undifferentiated metrics/options freeze decision-making. The orchestrator needs prioritization signal, not raw findings.

### Visual / hybrid format insights
- **Tables beat prose for comparative/enumerated content** — strongly supported across cognitive-load literature. A per-piece table (Piece / Purpose / Value / Depends-on / Open question) lets the orchestrator skim before drilling in.
- **CLI/terminal markdown table rendering is inconsistent**. Claude Code renders tables in its chat UI; raw terminal output often doesn't. Practical constraint: tables work at the gate-display surface if narrow-column, degrade-gracefully patterns are used.
- **Mermaid/C4 diagrams** help for spatial/architectural decisions but fail for diagnostic/policy/rewrite topics — the discovery skill must handle all of these.

### Anti-patterns mapped to discovery's current state
- "Wall of text" — directly the user's complaint.
- "Bullet-point flattening" (Bezos critique) — bullets without narrative connective tissue hide relative importance and causality. The current Architecture's piece bullets are this anti-pattern.
- "Solution-first without problem" — the current Architecture goes straight to pieces without value/motivation framing.
- "Author-centric framing" — diff-restatement is wasted text. Current Architecture is author-centric (decompose-agent audience).
- "False precision" — detailed implementation specifics in research/discovery create the illusion the decision is more settled than it is. Fat-marker-sketch discipline is the antidote.

### Synthesis takeaway

A reader-grounded redesign uses BLUF + progressive disclosure: the first viewport answers *what was investigated, what's recommended, why it matters, what to approve/revise/drop*. The artifact owns the structured surface; the gate quotes it verbatim. Bullet-only summaries fail without narrative connective tissue. Tables are the highest-leverage format for the per-piece view.

## Requirements & Constraints

### Project-instruction constraints (CLAUDE.md)
- **"Prescribe What and Why, not How"** [`CLAUDE.md:64-70`]: adding new MANDATORY sections is permitted *if each names a decision/output-shape with intent* (What/Why). Adding step-by-step rendering procedure ("first emit a callout, then summarize…") violates the principle. Removing prescriptive procedural narration in favor of decision-criteria framing honors it.
- **MUST-escalation policy (post-Opus-4.7)** [`CLAUDE.md:72-81`]: new MUSTs require dispatch-evidence + documented `effort=high`/`xhigh` failure. Current discovery gate prose uses soft positive routing; redesign must preserve this style. *Sharpening an existing prose directive without dispatch-evidence repeats Phase 1's mechanism.*
- **Skill / phase authoring guidelines** [`CLAUDE.md:52-58`]: "Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction." **Strongest single constraint pointing toward structured fields over prose prescription.**
- **Solution horizon** [`CLAUDE.md:60-62`]: when a fix is foreseeably-redoable (because the same pattern has already been tried), choose the durable version. Phase 1 is now a known-needs-redoing patch; Phase 2 must not repeat its prose-discipline mechanism.

### Requirements alignment
- `cortex/requirements/project.md` does NOT specify research.md or Architecture-section shape. The current template is a contingent design choice, not a requirements-pinned constraint (except `### Pieces` cardinality for decompose).
- **Complexity must earn its place** [`project.md:19`]: simpler wins when in doubt. Argues against additive section sprawl.
- **Handoff readiness** [`project.md:13`]: artifacts must be self-contained and agent-verifiable from zero context. Argues for structured fields over prose discipline.

### Must-preserve contracts (load-bearing)
- `### Pieces` bullet-set cardinality — decompose consumes 1:1 as ticket candidates. Bullet shape may evolve (e.g., bullets can carry more structured sub-content) but the 1-bullet-per-piece relationship is fixed.
- Four-option gate set: `approve` / `revise` / `drop` / `promote-sub-topic`, with event emission via `cortex-discovery emit-checkpoint-response`. Closed-set.
- R13 re-run slug-collision semantics [`SKILL.md:51-60`].
- The `architecture_section_written` event payload contract (or registry update if changed).
- The gate's user-blocking nature (not "ceremonial" — protects approve/reshape/drop user-facing affordance).

### Tone policy [`docs/policies.md`]
Cortex ships no tone directive. Skill prose should specify content shape and decision criteria, not voice or framing tone. Avoid "present warmly" / "use empathetic framing" prescriptions.

### Boundary catalog
- **Must-preserve**: `### Pieces` cardinality, 4-option gate set, event emission, R13 semantics, LEX-1 scanner contract (only matters if ticket-body section names change — they shouldn't).
- **May-change**: Architecture subsection names (with propagation to decompose.md), `## Headline Finding` slot's shape, gate prose's quotation rules, new sections in research.md.
- **Encouraged-to-simplify**: prescriptive procedural narration → decision-criterion framing. Remove jargon-rich prose where simpler framing carries equal meaning.
- **Out-of-scope**: lifecycle skill changes, decompose-commit batch-review gate, LEX-1 scanner regex patterns.

## Tradeoffs & Alternatives

Eight alternatives were evaluated. Headline summary (full prose in Agent 4's analysis):

| # | Alternative | Implementation cost | Maintainability | Alignment | Verdict |
|---|---|---|---|---|---|
| A | Gate rendering only (preserve artifact) | Low | Medium (two surfaces drift) | Mixed — violates structural-separation | Weak — no codebase precedent for artifact/gate divergence |
| B | Template restructure preserving Pieces | Medium | High | Strong | Strong runner-up |
| C | Full redesign incl. Pieces shape | High | Low-Medium | Mixed | **Ruled out** — prior adversarial review concluded Pieces isn't the problem |
| D | Layered output (separate Gate Brief slot) | Medium | Low | Mixed | Weak — three summary registers excessive |
| E | Visual / diagram-forward | Medium | Low | Weak — fails universality | Ruled out — diagnostic/policy/rewrite topics fail |
| F | Decision-first prose (BLUF/Pyramid) | Low-Medium | High | Very strong | Strong primitive; pairs with H |
| G | Reduce prescription, add prose guidance | High net | Low | Mixed (tensions structural-separation) | Ruled out — loses falsification gate's structural check |
| H | Headline Finding promotion only | Very Low | Very High | Strongest on paper | **Ruled out by adversarial empirical evidence** — same mechanism as Phase 1 |

### The adversarial-review pivot

Agent 4 initially recommended **H+F** (sharpen Headline Finding's authoring directive to require BLUF/Pyramid shape). Agent 5's adversarial pass refuted this:

> H+F is empirically the same mechanism that produced 171-402-word Headline Finding sections in production after Phase 1's identical "tighter authoring directive" approach. The MUST-escalation policy plus the verified Phase 1 failure make "sharpen the existing slot's directive" the wrong move per CLAUDE.md.

### Modified recommendation: MA-1 + MA-2 (compound structural move)

**MA-1: Replace `## Headline Finding` paragraph slot with a structured `## Decision Surface` section** carrying named single-line sub-fields. Sketched shape:

```
## Decision Surface

- **Verdict**: <one sentence>
- **Pieces (N)**: one line per piece — `<piece name> — <why this piece exists, plain English>`
- **What you're approving**: <one sentence framing the scope of the approve action>
- **Reject if**: <one sentence falsifiability condition>
- **Trade-offs**: <one sentence on the chosen direction vs alternatives>
```

Each field has an obvious upper bound (one line / one sentence) that resists Phase-1-style prose drift. The fields are structurally separated (CLAUDE.md:55-57), not prose-only-enforced. The `Reject if` field is the falsifiability surface that neutralizes the jargon-paradox rubber-stamping risk.

**MA-2: Rewrite `skills/discovery/SKILL.md:74`'s gate prose to render the Decision Surface and a tabular extract from `### Pieces`** (columns: Role / Why / Risk), suppressing the rest of `## Architecture` at gate display. `## Architecture` remains authored in full for decompose-phase consumption — different audience, different surface. This is extract-and-reshape against a verified structural source — bounded transformation, not fabrication.

### Why MA-1+MA-2 over the alternatives
1. **Different mechanism from Phase 1** — Phase 1 was "add a slot, tighter prose directive." Phase 2 is "replace the slot's shape (prose → structured fields) AND restructure the gate's selection logic." Both legs change mechanism, breaking the Phase-1 loop.
2. **Honors structural-separation** (CLAUDE.md:55-57) — bounded per-field surface area, structurally enforceable via marker-phrase tests on field labels.
3. **Honors solution-horizon** (CLAUDE.md:60-62) — the durable shape rather than a known-needs-redoing patch.
4. **Architecture's audience problem solved** — gate sees a decision-surface view; decompose sees full Architecture. Same artifact, different display per consumer.
5. **Falsifiability built in** — the `Reject if` field forces engagement past confident headline prose, mitigating jargon-paradox risk.
6. **Decompose contract preserved** — `### Pieces` cardinality untouched; gate just selects a different view of it.

### Open scope question

The scope decision Clarify left open (artifact template vs gate rendering layer) **resolves to both, by necessity**. There is no Python rendering layer to redesign in isolation; the gate's "rendering" is SKILL.md prose plus the orchestrator-model reading markdown. The minimal-disruption path touches *both* layers because they are coupled in the current design.

If the user prefers minimum-viable, the fallback is **MA-2 alone** (rewrite gate prose to extract-and-reshape, leave artifact untouched). More reversible than H+F because it changes the mechanism (selection logic, not prose directive). H+F is the only option to actively recommend *against* — it has direct empirical evidence of prior failure.

## Adversarial Review

Agent 5's adversarial pass invalidated Agent 4's initial recommendation and surfaced the empirical Phase-1 failure data above. The summary findings are integrated throughout this artifact rather than siloed here. Key adversarial findings, beyond what Tradeoffs covers:

- **Render-time transformation was missed** (the third option beyond fabricate-vs-add-slot). Now central to MA-2.
- **Architecture's audience-mismatch is the disease** — not its authoring shape. Adding framing in front of Architecture treats the symptom (presentation density) while preserving the disease (wrong-audience content at the gate).
- **Per-piece table rendering at gate display is unverified**. Claude Code renders tables in its chat UI, but the gate's actual surface is the orchestrator-model relaying content to the user in conversation. The model often paraphrases tables into prose. Empirical verification needed before spec commits.
- **R13 re-run multiplies authoring cost** — `{topic}-N/research.md` artifacts pay any new framing cost again. Budget impact unaccounted for in agents 1-4.
- **MA-1's "single line per field" discipline still requires enforcement** — without word-count or structural checks, prose drift can re-emerge. Falsifiability mitigation: marker-phrase tests on field labels + line-count assertions in `tests/test_discovery_gate_presentation.py`.

## Open Questions

These need spec-phase resolution before implementation:

1. **Does `## Architecture` get displayed at the research→decompose gate at all under MA-2, or is it fully suppressed in favor of the Decision Surface + tabular Pieces extract?** Suppression is cleaner audience-wise but loses traceability for orchestrators who want to drill in. — *Deferred: spec phase to resolve via user input or critical-review.*

2. **Per-piece tabular format viability at the actual gate-delivery surface (orchestrator → user via conversation):** Will Claude Code render the table, or will the model paraphrase it into prose? Spec phase should require a brief empirical verification (emit one markdown table via the orchestrator in a real gate flow, observe rendering) before committing to the tabular format. — *Deferred: spec phase to add verification task.*

3. **Marker-phrase tests for MA-1's structured fields** (`Verdict`, `Pieces (N)`, `What you're approving`, `Reject if`, `Trade-offs`) — what marker phrases are pinned in `tests/test_discovery_gate_presentation.py`? Are line-count or word-count assertions added per field to enforce single-line discipline? — *Deferred: spec phase to specify the test contract.*

4. **Backward compatibility with existing artifacts under `cortex/research/*/research.md`** that have `## Headline Finding` but no `## Decision Surface`: does the gate fall back gracefully, or does Phase 2 ship a migration? Most existing artifacts pre-date Phase 2 and shouldn't be retroactively rewritten. — *Deferred: spec phase to define fallback behavior.*

5. **`### Why N pieces` falsification gate**: the current gate quotes it (when piece_count > 5) but it narrates author-facing past-tense merge reasoning. Under MA-2's "suppress rest of Architecture at gate display" rule, does Why-N still surface at the gate, or is it decompose-only too? — *Deferred: spec phase to decide.*

6. **Phase-3 risk**: if MA-1 also underperforms in production, what's the next escalation surface? Naming this now anchors the durable-fix lens. Candidates: word-count enforcement at write-time via discovery.py validator, dispatch-side evidence requirements before approval, two-step gates (direction check before Architecture authoring). — *Deferred: spec phase open-decision; flagged as Phase-3 contingency, not in scope for Phase 2.*

## Considerations Addressed

No `research-considerations` argument was passed to this research dispatch — clarify-critic surfaced no `origin: "alignment"` findings (Context B ad-hoc, no parent epic), so no considerations flow-through applied. This section is included for schema completeness and intentionally empty.
