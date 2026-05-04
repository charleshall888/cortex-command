# Research: refine should load parent-epic context

> **Decision history.** Round 1 recommended inline epic-context loading at refine's Clarify phase. The user's "think critically" redirect surfaced an over-anchoring concern (premature closure on the epic's chosen approach, suppression of independent research). Round 2 reframed the design space to consider worker/auditor separation patterns and dispatched fresh research; an initial round-2 recommendation (F: add S7 epic-alignment item to refine's spec-phase `orchestrator-review.md`) was rejected by critical review because (a) `orchestrator-review.md` mandates main-context execution, defeating the worker/auditor separation F cited as motivation, and (b) `orchestrator-review.md`'s binary pass/flag verdict scheme has no workable disposition for deliberate-descope cases (taxonomy class C3, exemplified by ticket 064). The current recommendation (α) is to add an **"Epic alignment" angle to `/cortex-interactive:critical-review`'s auto-fire from `specify.md §3b`**. Critical-review actually dispatches fresh parallel agents (delivers the cited mechanism) and its per-objection Apply / Dismiss / Ask verdict scheme handles C3 cases naturally without rewrite churn.

## Research Questions

1. **Is there empirical evidence of epic-context drift in recently-refined tickets with `parent:` set?** → Expanded sample of 17 (round-1 7 + round-2 10) shows **3 commission-class drift cases** (064 deliberate descope, 105 mild bundled fix, 110 mild count creep), 1 borderline, **0 confirmed omission cases visible from artifacts alone** (omission is structurally under-detected by artifact-only audit — count is a measurement floor, not a true zero). All 3 commission cases would be visible to a fresh-context reviewer reading the spec + parent epic; the C3 case (064) requires a verdict scheme that supports "Dismiss with rationale" (which critical-review has, and orchestrator-review does not).

2. **What does refine currently load, and where is parent-epic context conspicuously absent?** → Refine loads: backlog item body via `cortex-resolve-backlog-item`; requirements files in Clarify; `discovery_source` and `research` frontmatter fields as background reference only `[plugins/cortex-interactive/skills/refine/SKILL.md:54-56]`; prior `lifecycle/{slug}/research.md` for the sufficiency check `[plugins/cortex-interactive/skills/refine/SKILL.md:84-96]`. Parent-epic context is **not loaded** anywhere in refine today, including the auto-fired critical-review at `specify.md §3b`.

3. **What content should the auditor see, and what's a defensible token cap?** → Critical-review's reviewer prompts already include a `## Project Context` block from `requirements/project.md` `[plugins/cortex-interactive/skills/critical-review/SKILL.md:14-22]`. The auditor extension extends that loader to also include an "Epic Context" sub-block when the child ticket has `parent:` set. Content shape, derived from the round-1 epic-body corpus survey: title + named context section if present (priority `## Context from discovery` → `## Context` → `## Framing (post-discovery)`), with first-paragraph fallback. Token cap: ≤500 tokens hard / 300 tokens soft warn. The corpus survey of 17 epics confirms every existing epic produces a packet under 500 tokens via this heuristic. Important: this content reaches **fresh reviewer agents only**, not refine's main worker — so the round-1 anchoring concern does not apply here.

4. **Where in refine's existing review infrastructure should the epic-alignment check fire?** → **`/cortex-interactive:critical-review`'s auto-fire from `specify.md §3b`** for complex-tier tickets. Critical-review dispatches 3–4 fresh parallel agents per derived angle `[plugins/cortex-interactive/skills/critical-review/SKILL.md:14-67]`; we add an "Epic alignment" angle to its angle-derivation hints when the child has `parent:` set. Fresh-context reviewers see artifact + project-context (now including extracted epic content) + the angle prompt. **Not** orchestrator-review (main-context execution defeats the cited mechanism). **Not** clarify-critic (drift hasn't happened yet at clarify time). **Not** a new dedicated skill (premature complexity per `requirements/project.md:19`).

5. **How should the auditor degrade when parent linkage is missing or malformed?** → Tiered: (a) child has no `parent:` → skip the Epic alignment angle silently, critical-review proceeds with its other derived angles; (b) `parent:` set but file missing → emit a warning in the project-context block ("parent epic <id> referenced but file missing"), skip the angle; (c) `parent:` resolves to a non-epic ticket → load it as "linked context" and run the angle anyway (still useful for alignment); (d) nested parent chain → load only direct parent. Hard-fail is unwarranted.

6. **Does this drift problem affect adjacent skills (`/cortex-interactive:lifecycle`, `/cortex-interactive:clarify`)?** → `/cortex-interactive:lifecycle` records `discovery_source` and `research` as background reference context but does not load `parent:`. There is no standalone `clarify` skill. The auditor pattern is naturally generalizable to lifecycle's plan-phase critical-review (also fresh-agent dispatch); should land in refine first, with expansion gated on observed need.

7. **Prior art for parent-context propagation and worker/auditor separation in agentic systems?** → Two-part finding (preserved from round 2):
   - **Worker/auditor split** is the battle-tested adversarial-review topology (Constitutional AI, actor-critic loops with 90%+ issue elimination in 3–5 rounds, Inspect AI's Solver/Scorer, Anthropic's subagent docs explicitly recommending "Use a subagent that does not see our previous discussion"). Reviewers see artifact + rubric; not worker scratchpad. Critical-review's parallel-agent dispatch is a direct match for this topology; orchestrator-review's main-context execution is not.
   - **Anchoring resistance** is documented as ineffective (`arxiv 2412.06593`): CoT and "ignore the anchor" instructions are largely ineffective at counteracting anchoring bias. This is *why* the worker/auditor split is preferred over inline framing instructions — the separation is structural, not prompt-level.
   - **Token-cost caveat** (`arxiv 2510.26585`): verification overhead is real. The auditor at critical-review's already-running parallel dispatch adds one extra angle per complex-tier refine, which is bounded marginal cost; if the angle's hit rate is low, dropping it is cheap.

## Codebase Analysis

**Refine's existing context-loading surface area** (preserved from round 1):

| Phase | What loads | How much | Citation |
|-------|-----------|----------|----------|
| Clarify | Backlog item frontmatter + body | Full | `[plugins/cortex-interactive/skills/refine/SKILL.md:26-32]` |
| Clarify | `requirements/*.md` | Area-relevant docs only | `[plugins/cortex-interactive/skills/refine/references/clarify.md:31-37]` |
| Clarify | `discovery_source`, `research` fields | Reference path only ("background context, not substitute for lifecycle artifact") | `[plugins/cortex-interactive/skills/refine/SKILL.md:54-56]` |
| Research | `lifecycle/{slug}/research.md` (sufficiency check) | Full doc, four-signal staleness check | `[plugins/cortex-interactive/skills/refine/SKILL.md:84-96]` |
| Spec | `lifecycle/{slug}/research.md` | Full | `[plugins/cortex-interactive/skills/refine/references/specify.md:8-9]` |
| Spec | `requirements/*.md` | Area-relevant docs only | `[plugins/cortex-interactive/skills/refine/references/specify.md:9]` |
| Spec (auto-critical-review for complex-tier) | Spec.md + Project Context block from requirements/project.md | Project Context overview ~250 words | `[plugins/cortex-interactive/skills/critical-review/SKILL.md:14-22]`, `[plugins/cortex-interactive/skills/refine/references/specify.md:148-153]` |

**Backlog data model — epic linkage**: Epic↔child relationship uses `parent: <numeric-id>` in child frontmatter; epics have `type: epic` and a "## Child tickets" body section. 39 child items with `parent:` set; 22 distinct parent IDs; **0 dangling parents**, **0 nested epics**.

**Existing review infrastructure — fresh-agent dispatch property**:

| Surface | Fires when | Reviews | Dispatches fresh agents? | Per-finding verdict states |
|---------|------------|---------|--------------------------|----------------------------|
| `critical-review` skill | User invoke; auto from `specify.md §3b` for complex-tier; post-plan-approval | Most relevant lifecycle artifact (`plan.md` → `spec.md` → `research.md`) | **Yes (3–4 parallel angles)** | **Apply / Dismiss / Ask** per objection |
| Refine `orchestrator-review.md` | Between phase artifact write and user presentation; skip rule = `criticality:low AND tier:simple` | Phase artifact in main conversation context | No (review itself is in-context; fix dispatch uses fresh agents) | Pass / Flag (binary) |
| Refine `clarify-critic.md` | Post-§3 confidence assessment, always runs | Confidence assessment + raw source material | Yes (one fresh agent) | Apply / Dismiss / Ask per finding |

**Drift mode taxonomy** (preserved from round 2):

| Category | Description | Auditor catches? | Inline-load prevents? | Examples |
|---|---|---|---|---|
| **C1 Scope-list arithmetic creep** | Spec touches N items; epic/ticket said M < N | Yes (text counts mismatch) | Partial | 110 (4→7), 105 (1 script → all `bin/cortex-*`) |
| **C2 Bundled adjacent fix** | Spec adds an unrelated-but-nearby cleanup | Yes (clause exists in spec) | No | 105 (symlink retrofit), 108 (shared helper) |
| **C3 Deliberate descope** | Spec narrows below epic's primary deliverable | Yes (explicit "deferred" language) — but verdict scheme matters | **No** — intentional authoring move; loader cannot prevent | 064 |
| **O1 Premature closure on epic-chosen approach** | Spec adopts epic's option without re-deliberating; alternative absent | **No** — invisible | **No (worsens)** — loading epic re-asserts choice | None directly observed; theoretical |
| **O2 Inherited framing without re-justification** | Spec opens with epic's frame and inherits assumptions | **No** — invisible | **No (worsens)** — strengthens framing inheritance | 091 (round-1 noted) |

**Critical disposition note for C3 (064-class)**: critical-review's per-objection Apply / Dismiss / Ask verdict scheme means an "Epic alignment" objection raised against a deliberate-descope spec gets dismissed by the operator with rationale ("This is intentional descope — epic deliverable deferred per maintainer cost/benefit override"). No rewrite churn, no escalation. This is the structural advantage critical-review has over orchestrator-review for this class of finding.

**Cheapest viable design** (the recommendation): Add an `"Epic alignment"` angle to `/cortex-interactive:critical-review`'s angle-derivation hints when the child ticket has `parent:` set. Extend critical-review's project-context loader to include an "Epic Context" sub-block extracted from the parent epic via the round-1 heuristic (priority `## Context from discovery` → `## Context` → `## Framing (post-discovery)` → first paragraph; ≤500 tokens). Reviewers receive: spec.md + project-context (with epic context) + angle prompt. They do not see refine's main agent scratchpad — the worker/auditor separation is structural.

## Web & Documentation Research

**Worker/auditor separation patterns** (preserved from round 2):

- **Constitutional AI** (`arxiv 2212.08073`, Bai et al. 2022): critic sees artifact + ~10–20 principles, not worker deliberation.
- **Reflexion** (`arxiv 2303.11366`): exception — reviewer sees trajectory + reward, achieving +22% AlfWorld and +11% HumanEval gains because failure is process-level.
- **Inspect AI** (UK AISI): `Solver` and `Scorer` are decoupled; scorer typically sees output + rubric.
- **Actor-critic loops** ([Understanding Data: Actor-Critic Adversarial Coding](https://understandingdata.com/posts/actor-critic-adversarial-coding/)): empirical claim of **3–5 critique rounds eliminate 90%+ of issues** before human review.
- **Anthropic's subagent docs** ([code.claude.com/docs/en/sub-agents](https://code.claude.com/docs/en/sub-agents)): explicitly recommends fresh-context subagents for unbiased analysis — "Use a subagent that does not see our previous discussion."

**Anchoring bias evidence** (preserved from round 2):

- `arxiv 2412.06593` (Nguyen & Lyu): anchors significantly bias LLM judgments; **CoT and "ignore the anchor" instructions are largely ineffective**; effects amplify when the anchor is attributed to an "expert."
- Implication: structural separation (fresh-agent dispatch) is preferred over prompt-level mitigation (e.g., "this is alignment context only, do not substitute for research"). The α recommendation respects this: epic context reaches reviewers, not the worker.

**Token-cost evidence** (preserved from round 2):

- `arxiv 2510.26585`: MetaGPT's 2048 task spent 72% of tokens on verification. Critical-review's auto-fire is already complex-tier-only, so the extra "Epic alignment" angle adds one parallel agent per complex-tier refine — bounded marginal cost.

## Domain & Prior Art

The clean worker/auditor split — fresh auditor sees artifact + rubric, not worker scratchpad — is the production-default adversarial-review topology with concrete published gains (Reflexion +22% / +11%, actor-critic 90%+ issue elimination in 3–5 rounds). It dominates inline-context loading when the failure mode is artifact-checkable and where anchoring is the live risk. Critical-review's parallel fresh-agent dispatch is the cortex-command surface that instantiates this topology directly.

The auditor pattern's **structural blind spots** remain: it cannot catch O1 (premature closure on epic-chosen approach) or O2 (inherited framing) because those are process-level failures invisible from artifact text. **No artifact-only audit can catch these** — including round-1's inline-load proposal, which would have actively worsened them per the anchoring-bias evidence. The honest answer to the user's originally-reported O1/O2 concern is: round 2's main contribution is **rejecting round-1's inline-load** (declining to make O1/O2 worse). The α recommendation adds a separate, narrower contribution: catching commission-class drift via fresh-context audit. These are two distinct moves; the recommendation does not claim α "fixes" the O1/O2 concern.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| **α: Critical-review angle (recommended)** — add "Epic alignment" angle to `/cortex-interactive:critical-review`'s angle-derivation hints when child has `parent:` set; extend project-context loader to include extracted epic content (≤500 tokens via round-1 heuristic); reuses fresh-agent dispatch + Apply/Dismiss/Ask verdict scheme | S | Low — actually delivers worker/auditor separation; C3 cases dismissed with rationale (no churn). Coverage limited to complex-tier auto-fire (matches risk profile — all 3 observed drift cases were complex-tier). | Modify `plugins/cortex-interactive/skills/critical-review/SKILL.md` to add angle hint when `parent:` present + extend project-context loader; no other changes |
| **F: Spec orchestrator-review S7 (REJECTED — round 2 critical review)** — add S7 to refine's `orchestrator-review.md` checklist | S | High — orchestrator-review mandates main-context execution (`orchestrator-review.md:35`), so reviewer is the same conversation that authored the spec. Loading parent epic into that context re-creates the round-1 anchoring contamination at a new gate. Binary pass/flag + full-rewrite fix-dispatch + 2-cycle cap has no workable disposition for C3 cases (064) — either rewrites the spec away from intentional descope or escalates unnecessarily. | None |
| **β: Redesign F with fresh subagent** | S–M | Grafts fresh-agent dispatch onto a surface explicitly designed against it; still has C3 disposition problem unless verdict scheme is also extended. α achieves the same outcome with less structural change. | None |
| **γ: Hybrid α + F-as-self-review** | M | Two implementation sites; redundant for complex-tier; F-as-self-review framing doesn't add value when α is running. | None |
| **A1: Round-1 full inline load (REJECTED)** | S | Anchoring-bias evidence shows framing-mitigation instructions are largely ineffective (`arxiv 2412.06593`); risks worsening O1/O2 omission-class drift | None |
| **A2: Minimal inline load (REJECTED)** | S | Reduced over-anchoring surface but same anchoring-bias problem at smaller scale | None |
| **C: Full epic body inline (REJECTED)** | S | Maximally contaminates main agent | None |
| **D: Recursive parent-walker (REJECTED)** | M | Solves no current problem (0 nested epics) | None |
| **E: Do nothing** | trivial | Leaves observed commission-drift unaddressed; round-1 reversal already addresses the user's reported O1/O2 concern via negative action | None |
| **δ: Drop α, ship round-2 reversal only** | trivial | Defensible alternative to α: the user's redirect was about O1/O2; the round-2 rejection of inline-load already addresses that concern via negative action; commission drift is a separate problem that didn't motivate the discovery | None |

## Decision Records

### DR-1: Recommended approach is "Epic alignment" angle in critical-review's auto-fire

- **Context**: Round 1 recommended inline epic-context loading (rejected: anchoring bias). Round-2 initial recommendation was an orchestrator-review S7 item (rejected: `orchestrator-review.md`'s main-context execution defeats fresh-reviewer separation; binary verdict scheme has no workable C3 disposition). Critical-review is the cortex-command surface that actually instantiates the worker/auditor topology cited as load-bearing — fresh parallel agents per angle, per-objection Apply / Dismiss / Ask verdict scheme.
- **Options considered**: α (recommended), F (rejected), β (rejected), γ (rejected), A1/A2/C/D (rejected from round 1), E/δ (defensible no-op alternatives).
- **Recommendation**: **α**. Add an `"Epic alignment"` angle to `/cortex-interactive:critical-review`'s angle-derivation step, conditionally injected when the child ticket has `parent:` set in its frontmatter. Extend critical-review's project-context loader to also include an "Epic Context" sub-block extracted from the parent epic body (priority: `## Context from discovery` → `## Context` → `## Framing (post-discovery)` → first paragraph fallback; ≤500 tokens hard / 300 tokens soft warn — round-1 corpus survey confirms all 17 existing epics produce a packet under 500 tokens). The angle's prompt instructs the reviewer to flag scope mismatches between spec and parent-epic intent; per critical-review's verdict scheme, the orchestrator (in main context) then disposes of each finding as Apply / Dismiss / Ask — operator-overridable for C3 deliberate-descope cases without rewrite churn.
- **Trade-offs**: Coverage is limited to complex-tier auto-fire (`specify.md §3b`). Of the 3 observed drift cases, all were complex-tier (some via override) — the empirical floor matches risk profile. Low-criticality / simple-tier parent-linked tickets bypass the audit; the population audit found 0 such tickets in the sampled epics, so the gap is empirically small. **Honest scope statement**: α addresses *commission-class* drift (visible scope mismatches). It does **not** address the user's originally-reported *omission-class* concern (premature closure, inherited framing) — those are process-level failures invisible from artifact text, and no auditor pattern catches them. The user's concern is addressed by round 2's *negative action*: rejecting round-1's inline-load, which would have worsened O1/O2 via anchoring per `arxiv 2412.06593`. α is a separate, narrower improvement.

### DR-2: Auditor placement — critical-review at spec-time (complex-tier auto-fire)

- **Context**: Critical-review auto-fires from `specify.md §3b` post-orchestrator-review for complex-tier specs. By that point, scope decisions are crystallized in spec text and the parallel fresh-agent dispatch can evaluate scope vs epic intent.
- **Options considered**: critical-review at spec-time (recommended); critical-review at plan-time; critical-review at research-time; clarify-critic; new dedicated skill.
- **Recommendation**: **critical-review at spec-time**, the existing `specify.md §3b` auto-fire path. Plan-time is too late (scope-vs-epic mismatch should be caught before planning starts). Research-time has no spec to check yet. Clarify-critic precedes scope decisions. New skill is premature complexity.
- **Trade-offs**: Auto-fire is gated on complex-tier per `specify.md §3b`; non-complex specs don't run critical-review at all. This is acceptable given (a) the observed drift sample's complex-tier concentration, (b) the operator can manually invoke `/cortex-interactive:critical-review` on any artifact, and (c) widening the auto-fire trigger is a separate scope question.

### DR-3: Failure-mode degradation — silent skip when no parent, warn when dangling

- **Context**: Audit shows 0 dangling parents and 0 nested epics today. Defensive degradation is cheap.
- **Options considered**: Hard-fail; warn-but-proceed; silently skip.
- **Recommendation**: Tiered: (a) child has no `parent:` → skip the Epic alignment angle silently, critical-review proceeds with other angles; (b) `parent:` set but file missing → emit warning into project-context block, skip the angle; (c) `parent:` resolves to a non-epic ticket → load it as "linked context" and run the angle anyway; (d) nested parent chain → load only direct parent.
- **Trade-offs**: Same shape as round 1; permissive matches actual field usage.

### DR-4: Implementation site — modify critical-review skill

- **Context**: α's implementation surface is `/cortex-interactive:critical-review`'s angle-derivation step and project-context loader. No new bin script needed (the project-context block is constructed inline in critical-review's flow). No SKILL.md-to-bin parity wiring.
- **Options considered**: New bin script (round-1 path, obsolete); modify `critical-review/SKILL.md` directly; modify both.
- **Recommendation**: **Modify `plugins/cortex-interactive/skills/critical-review/SKILL.md`** Step 2a (project-context loader) to additionally read parent epic content when invoked from a refine context where the resolved backlog item has `parent:` set, extract via the round-1 heuristic, append as an "Epic Context" sub-block. Modify Step 2b (angle derivation) to surface "Epic alignment" as a hint angle in the menu when an Epic Context sub-block is present. The reviewer prompt template for that angle instructs: "Flag scope mismatches between the spec and the parent epic's intent. C3 (deliberate descope with explicit justification) is a valid pattern — flag it as a B-class finding with class rationale, not as A-class fix-invalidating, so the orchestrator can dismiss with operator rationale."
- **Trade-offs**: Critical-review currently doesn't have a refine-aware context loader (it loads `requirements/project.md` only). Extending it to also load a parent epic adds one more lookup. The angle is conditionally derived — fires only when the child has `parent:`. Marginal token cost: +1 parallel reviewer angle on parent-linked complex-tier specs.

### DR-5: Rejected alternatives — preserved with rationale

- **F (round-2 initial recommendation)**: rejected because `orchestrator-review.md`'s main-context execution defeats the fresh-reviewer property the recommendation cited as motivation, and its binary pass/flag + full-rewrite fix-dispatch has no workable disposition for C3 deliberate-descope cases. The α recommendation moves to critical-review specifically because critical-review delivers both: fresh-agent dispatch and Apply/Dismiss/Ask per-objection verdicts.
- **A1, A2, C, D (round-1 inline-load family)**: rejected per round-2 anchoring-bias evidence. CoT and "ignore the anchor" framing instructions are largely ineffective (`arxiv 2412.06593`); inline loading risks worsening O1/O2 omission-class drift.
- **β (redesign F with fresh subagent)**: rejected because critical-review already provides exactly this, without grafting fresh-agent dispatch onto a reference doc designed against it.
- **γ (hybrid α + F-as-self-review)**: rejected as redundant; F-as-self-review adds no value when α already runs.
- **δ (drop α, ship round-2 reversal only)**: defensible alternative — would mean treating round 2's main contribution as "reject round-1's inline-load" with no proactive change to refine. Not chosen because (a) commission-class drift is real and observed (3 cases in sample), (b) α's implementation cost is low and reuses existing infrastructure, (c) the C3 disposition problem that killed F doesn't apply to α.

**What's preserved from round 1**: the corpus survey of 17 epics and the extraction heuristic (now powering the project-context Epic Context sub-block, not an inline worker load). The `parent:` data-model audit (39 children, 22 epics, 0 dangling, 0 nested). The failure-mode degradation tiering (DR-3).

**What's discarded**: round-1's inline-load mechanism. The 500-token cap is preserved in α as the budget for the project-context Epic Context sub-block — not as an anti-flooding ceiling on the worker.

## Open Questions

- **Should the Epic alignment angle hint be hardcoded into critical-review's angle menu, or surfaced via project-context injection?** Two reasonable shapes: (a) hardcoded conditional in the angle-derivation step ("if Epic Context block present, include 'Epic alignment' as a hint"), (b) the project-context block itself names the suggested angle. (a) is simpler; (b) is more decoupled. **Deferred: implementation-time decision; both produce equivalent reviewer behavior.**
- **Should critical-review's auto-fire also widen beyond complex-tier when `parent:` is set?** Today, auto-fire is gated on `tier=complex` per `specify.md §3b`. If observed parent-linked drift escapes this gate (e.g., simple-tier specs that drift from epic intent), widening the trigger is the natural fix. Population audit found 0 simple-tier parent-linked drift cases in the sample, so the gap is empirically small. **Deferred: revisit if downstream audit surfaces simple-tier drift.**
- **The omission-class concern (O1, O2) remains structurally uncatchable by α.** The user's originally-reported "over-anchoring → premature closure" failure mode is process-level, invisible from artifact text. No auditor pattern can catch it from spec + epic alone. Round 2's response to the user's redirect is: **(a) reject round-1's inline-load** (which would have worsened it), and **(b) ship α** (a separate, narrower improvement for commission-class drift). The omission concern is **not addressed by α**; revisit only if (i) cortex-command grows process-level instrumentation (e.g., events.log of considered-then-rejected alternatives), or (ii) a future user redirect or retro entry surfaces O1/O2 as load-bearing for a specific failure case. **Deferred: no proactive trigger; revisit on signal.**
