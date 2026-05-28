# Research: Auto-consolidation pass in /discovery decompose phase (#268)

> **Headline finding (read first):** This ticket requests a detector-driven proactive consolidation pass before the R15 gate. The same problem space was researched, specced, and shipped 14 days ago as **#247 (`offer-consolidation-clusters-before-r15-gate`)**, whose decision record explicitly **rejected this exact approach** ("Reject A and B as currently framed. Adopt D, with optional E as a follow-up") and shipped the manual `consolidate-pieces` affordance instead — which #268 now proposes to keep "as a fallback." #268's sole motivating artifact (`cortex/research/palette-editor-design-surface/decomposed.md`) **does not exist on disk**. The research below is real and useful, but it converges on a direction question the user must resolve before any spec: see **## Open Questions**.

## Codebase Analysis

**Prior-art collision (decisive).** `cortex/lifecycle/offer-consolidation-clusters-before-r15-gate/` (#247, shipped, backlog status to confirm) enumerated five alternatives and resolved:
- **A** — separate pre-R15 `AskUserQuestion` pause with a detector → **rejected**.
- **B** — fold detection into R15 as a derived suggestion / new option → **rejected**.
- **C** — do nothing.
- **D** (chosen, shipped) — add `consolidate-pieces <N,M,...>` to R15's `_RESPONSE_VALUES`; **no detector, no event, no parity-test debt, no false-positive risk**; the user names the candidates.
- **E** (named follow-up) — tighten the upstream research-phase R3 "Why N pieces" falsification gate.

#268 ≡ #247's Alternative A. The "fallback" #268 wants to retain *is* the thing #247 shipped as the deliberate non-detector answer.

**Files that would change if #268 proceeds:**
- `skills/discovery/references/decompose.md` (178 lines) — primary surface. §3 "Consolidation Review" (lines 46–52), §5 "Create Backlog Tickets" + the R15 "Post-decompose batch-review gate" sub-section (lines 100–115). Insertion point for an auto-pass: after §2 body authoring / §4 grouping, before §5/R15.
- `skills/discovery/SKILL.md` (114 lines) — the R15 gate summary (line ~102) and the R3 "Why N pieces" gate (lines ~82, ~85).
- `cortex_command/discovery.py` — helper. Owns **only** event emission (`emit_checkpoint_response` → `approval_checkpoint_responded`, `checkpoint="decompose-commit"`); `_RESPONSE_VALUES` (incl. `consolidate-pieces`) and `_CHECKPOINT_VALUES` are closed frozensets. **No loop/state/bookkeeping** — all R15 loop semantics, renumbering, and merge mechanics live in decompose.md prose. So an auto-pass is primarily a SKILL.md/reference **prose** change; the helper changes only if a new event is wanted.
- Tests: `tests/test_decompose_rules.py` (section-placement), `tests/test_discovery_events.py` (if new event).

**Where the falsification gate actually lives (answers research Q4).** The ticket cites "research.md §6 / Architecture write protocol," but `research.md` §6 holds only the Architecture template (`### Pieces`, `### How they connect`) plus a **soft inline hint** (~line 116: "If the piece count grows large, consider merging pieces…"). The **hard `### Why N pieces` falsification gate (`piece_count > 5`) lives in `skills/discovery/SKILL.md` (~lines 82, 85)**, not research.md. The "research-phase R3" that decompose.md §3 refers to is this SKILL.md-resident gate. There is pre-existing naming drift between SKILL.md's gate vocabulary and the research.md §6 template.

**R15 `consolidate-pieces` machinery (answers research Q5).** Fully implemented in decompose.md prose (lines 109, 113): prose-merge of `## Why`/`## Role`/`## Integration`; union/dedup of `## Edges`/`## Touch points`; lowest-index survivor; contiguous renumber from 1; recorded under `## Consolidation Notes` in `decomposed.md` (distinct from `## Dropped Items`). An auto-pass would feed a *proposed selection* into this existing flow rather than reproduce it.

**Motivating artifact missing.** No `cortex/research/palette-editor-design-surface/` anywhere (no git history). The pattern *is* corroborated elsewhere: 2 `decomposed.md` files carry `## Consolidation Notes` (e.g. `swap-daytime-autonomous-for-worktree-interactive`, a real 9→5 manual consolidation).

## Web Research

The feature concept has solid prior-art grounding, with one load-bearing caution.

- **Agile story-splitting has an explicit "combine" inverse** tied to INVEST-Valuable: pieces that aren't independently valuable should be merged into the piece they serve ("task masquerading as story" → merge; horizontal/architectural splits and "too-thin splits" are named anti-patterns). Right-sizing is a ratio rule (6–10 per sprint), not an absolute.
- **The five coupling signals each map to a software metric ancestor:** shared touch-points → logical/change coupling (Gall et al.; CodeScene's >50%-coupling "merge or decouple" rule of thumb); shared responsibility → cohesion/LCOM/SRP; shared interface → CBO; value-together → INVEST-Valuable; dependency stub → "task masquerading as story."
- **Load-bearing caution — open-ended LLM self-critique is unreliable:** "high false-positive rates and missing nearly all true negatives" (arXiv 2512.24103); ~25% verdict-flip on hard cases for LLM judges (Rating Roulette, SAGE); anchoring/sycophancy on the model's own first cut. **What measurably works:** failure-mode-*structured* critique (hand the model the explicit signal checklist, not "is this over-split?") improved F1 only when given known failure modes (arXiv 2601.09905); evidence-grounded/hybrid judging vastly outperforms holistic (Agent-as-a-Judge, 0.3% vs 31% divergence from human).
- **HITL UX — the dominant failure is rubber-stamping/review-fatigue.** Remedy is aggressive pre-filtering (surface few, high-signal items), progressive disclosure, and **propose-not-auto / never auto-merge.**

## Requirements & Constraints

- **`project.md` Complexity:** "Must earn its place by solving a real problem now. When in doubt, simpler wins." Directly load-bearing here.
- **`project.md` Solution horizon:** if a follow-up is already planned, propose the durable version. #247 *already named E (tighten R3) as the planned follow-up* — so by the project's own rule, the durable direction is E, not a downstream detector papering over a weak upstream gate.
- **"Prescribe What and Why, not How":** specify decision-criteria + output-shape, not heuristic detection rules. A list of token-overlap rules is disfavored *How*; "propose consolidation when drafted pieces exhibit tight coupling [named signals], output a proposed selection + rationale" is the prescribed *What/Why*.
- **MUST-escalation:** soft positive-routing default; no new MUST without an evidence artifact.
- **Events:** the existing `approval_checkpoint_responded` (via its `checkpoint` field) already covers the gate — reuse = zero registry change. A new event needs a registry row + documented consumer.
- **Size cap:** 500 lines applies to SKILL.md only (`references/*.md` exempt); both have headroom.
- **Scope:** modifying the discovery decompose flow is **in-scope** (skills/workflow orchestration; discovery documented inline, no area doc). The drafted-body surface overlaps `skills/backlog-author/` + `bin/cortex-check-prescriptive-prose` (LEX-1) — a possible reuse point.
- **Parity coverage gap:** discovery has **no kept-pauses parity-test coverage** (unlike lifecycle/refine, covered by `tests/test_lifecycle_kept_pauses_parity.py`). Adding a conditional pause to discovery would be unguarded.

## Tradeoffs & Alternatives

Framed against #247's already-shipped baseline (the user already sees every body at R15 and can already invoke `consolidate-pieces` — so no option buys a *new* review opportunity, only a *better default*).

- **A — dedicated auto-pass step before R15 (the ticket's framing).** Adds a second consecutive user-blocking surface over the same bodies + likely a new event (discovery.py validator/test churn). Largest surface; risks encoding *How*. = #247's rejected A.
- **B — enrich R15 with an auto-suggested default `consolidate-pieces N,M` + rationale.** Reuses the existing response value + checkpoint (zero schema cost), single pause, smallest surface, best *What/Why* fit. The tradeoffs agent's recommendation. = #247's rejected B in substance. **Still needs a detector to compute the default** (see Adversarial).
- **C — research-time gate.** Structurally cannot see body-level signals (bodies don't exist yet); complements but can't replace a body-time check.
- **D — pure §2 self-check during drafting.** Cheapest; weak as primary because mid-stream self-judgment lacks the whole-batch view (the documented failure mode). Already effectively the status quo's spirit.
- **E — tighten the research-phase R3 falsification gate.** The named durable follow-up; preserves the "research owns the piece-set" invariant.

Tradeoffs-agent recommendation: **B (+ D backstop)**. The Adversarial review contests this — see below.

## Adversarial Review

- **#268 is a re-litigation of #247's deliberate rejection, on weaker evidence.** #247 evaluated A and B and rejected both on the record; its OQ1 resolution: "The n=1 corpus does not support investing in a detector (A or B)." Corpus: only ~23% of discoveries reach ≥6 pieces, and **exactly one** R15 invocation in project history has *ever* looped. #268's single piece of evidence (the palette-editor discovery) left **no artifact on disk** — unverifiable.
- **Alternative B does not escape #247's objections — it hides the oracle in a default.** A non-blank default requires a detector to decide *which* pieces to pre-select — exactly the detection oracle #247 rejected, now invisible. The "zero schema cost" win is real but irrelevant; #247's cost was *detector reliability* + the *multiple-consolidation-surface anti-pattern* (an auto-pass + §3 + R15 = **three** surfaces for one decision; the D backstop makes four).
- **A pre-filled default is strictly worse HITL than blank-slate R15 (anchoring/automation bias).** A blank R15 forces independent judgment; a pre-filled merge proposal invites *accepting the agent's judgment* — the rubber-stamping trap. The error is **asymmetric**: a false-negative (silent, user over-decomposes) is recoverable via downstream `/lifecycle`; a false-positive merge a tired user accepts prose-merges two separable pieces with no un-merge tooling. "Propose-not-auto" protects against silent merges, not against anchoring.
- **The §3 contradiction is load-bearing.** decompose.md §2/§3/Constraints encode a hard invariant: the piece-set is **frozen at decompose entry**; if bodies reveal coupling, "return to research rather than silently consolidating at decompose time" (§3) / "do not silently mutate the set at decompose time" (Constraints line 173). An in-place auto-consolidation pass **violates this invariant**. Resolving it in #268's favor means rewriting the discovery skill's core "research owns the piece-set" decision across §2, §3, and Constraints — a far larger change than #268's framing admits. #268's own References call §3 a "stance" to "work around."
- **The legitimate kernel points to E, not A/B.** The one true thing #268 names (strongest coupling signals aren't legible at research time because bodies don't exist yet) is exactly *why* #247 named E as the follow-up. The durable fix is to make research write touch-points-per-piece eagerly enough that R3 can test overlap — not a downstream detector re-deriving what a weak upstream gate missed (textbook stop-gap the project rejects).
- **Recommended:** wontfix #268 as written / redirect to E; before any spec, demand the missing motivating artifact; if A/B ships anyway, the §2/§3/Constraints invariant must be explicitly rewritten in the same PR, discovery must gain kept-pauses parity coverage, and the anchoring regression must be justified against real labeled data, not an n=0 anecdote.

## Open Questions

> **Direction RESOLVED (2026-05-28, user decision).** The user re-centered the problem: discovery over-splits, producing ~10 small tickets where ~3 larger ones were the right cut, and the cost is lifecycle ceremony per ticket (modern models handle larger tasks fine). Decisive structural fact confirmed against `decompose.md`: **ticket count = research-phase piece count** — §2 maps each `### Pieces` bullet 1:1 to a ticket, and §4 "Determine Grouping" only branches on the count (≥2 → epic + one child per piece); it does not group. So the count is locked at research time and decompose is a faithful transcription. This re-scopes the feature away from #268's framing (a detector scanning drafted bodies before R15 = #247's rejected Alternative A) to: **make decompose §4 actually group tightly-coupled pieces into a single ticket (M pieces → 1 ticket), using the research-phase Integration-shape and Seam-level-edges signals, before bodies are drafted.** This is the most direct lever on ticket count, lives at decompose, preserves research's fine-grained seam analysis, and avoids #268's after-the-fact-merge, anchoring, and §3-invariant problems (grouping pieces into ticket units before drafting is not "silently mutating the piece-set" — the analytical pieces are unchanged; only the ticket packaging coarsens, as an explicit, user-visible decision surfaced at the existing R15 gate).

Resolutions to the questions raised by research:

1. **Direction.** RESOLVED → group at decompose §4 (above). Not A, not B, not wontfix/E.
2. **Missing evidence.** No longer blocking — the §4-grouping fix is justified by the structural 1:1-transcription fact plus the user's stated recurring pain, not by the missing palette-editor anecdote.
3. **§3 invariant.** Bounded for spec: §4 grouping must be reconciled with §2's "each bullet becomes one ticket candidate" wording and §3's reactive return-to-research stance, but it does **not** reopen "research owns the piece-set" the way an after-the-fact body-merge would — grouping precedes body-drafting and changes packaging, not the analytical set. Spec must state this reconciliation explicitly.
4. **Parity coverage.** No longer blocking — §4 grouping adds no new conditional pause; the result is presented at the existing user-blocking R15 gate, so discovery's missing kept-pauses parity coverage is not on the critical path for this change.

> Carried into Spec: (i) reconcile §2/§3/§4 wording so grouping is explicit and not a "silent mutation"; (ii) specify §4 grouping as decision-criteria + output-shape (the coupling signals to weigh + the grouped-ticket result surfaced at R15), not heuristic rules (What/Why-not-How); (iii) the manual R15 `consolidate-pieces` affordance (#247, shipped) stays as the post-draft fallback for couplings only visible once bodies exist; (iv) decide whether the epic/child frontmatter and `decomposed.md` record need any shape change when a ticket wraps multiple pieces.
