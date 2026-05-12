# Research: Improve /cortex-core:discovery gate presentation and add no-tickets terminus

## Codebase Analysis

### Current state of the Research→Decompose gate

The R4 gate is defined at `skills/discovery/SKILL.md:72-90`. It presents the Architecture section's four sub-sections (`### Pieces`, `### Integration shape`, `### Seam-level edges`, optionally `### Why N pieces`) and offers exactly four response options enforced as a closed set:

- `approve` — proceed to Decompose phase
- `revise` — scoped explicitly to the Architecture section per `SKILL.md:77` ("re-emit `### Pieces`, re-run `### Integration shape` and `### Seam-level edges`, re-run the `### Why N pieces` falsification gate if piece_count > 5")
- `drop` — abandon discovery; no `decomposed.md` produced; `research.md` stays as audit trail
- `promote-sub-topic` — file a `needs-discovery` ticket for a sub-topic and return to the gate

The gate's revise option is **structurally scoped to Architecture only**. There is no path to revise the rest of the research artifact at the gate.

### Findings location in the research artifact

Architecture is **not** the only content in research.md. The discovery research template (`skills/discovery/references/research.md:115-158`) places `## Architecture` between Feasibility Assessment and Decision Records. The user's friction-run artifact (`cortex/research/artifact-format-evaluation/research.md:5`) already has its **headline finding stated above the Architecture section** — line 5 reads: *"**Headline finding**: the current per-class mix (markdown for prose, JSON for state, JSONL for events) is consistent with Anthropic prescription..."* with Architecture beginning at line 116.

This is load-bearing for the spec: **findings are present in research.md, but the gate-presentation surface displays only Architecture.** The mechanism of friction is gate-presentation, not research.md template structure.

### The zero-piece path is gate-unreachable

`skills/discovery/references/decompose.md:77-89` defines a zero-piece branch:
- **Fold-into-#N**: research surfaced a finding that belongs on an existing ticket; record in `decomposed.md` under `## Fold-into`
- **No-tickets verdict**: research surfaced no actionable work; record verdict and rationale in `decomposed.md` under `## Verdict`

In both sub-cases `decomposed.md` is written as an audit trail with frontmatter `decomposition_verdict: zero-piece` for machine-readability.

**Critical structural finding**: the zero-piece branch lives **inside the decompose phase**, reachable only after the user approves the gate. The friction-run artifact's directory (`cortex/research/artifact-format-evaluation/`) contains `research.md` and `events.log` but **no `decomposed.md`** — the user's `drop` response (`events.log:1`) terminated discovery before decompose could write the zero-piece verdict. The honest no-tickets terminus exists structurally but the user cannot reach it without first approving an Architecture section they consider semantically inappropriate for the topic.

### Helper module surface (cortex_command/discovery.py)

The module (686 lines) exposes four subcommands invoked from skill prose:
- `resolve-events-log-path` (lines 151-195) — picks lifecycle-vs-research events.log target; honors `LIFECYCLE_SESSION_ID` env + `.session` file (EVT-1), R13 `-N` slug suffix, or plain `cortex/research/{topic}/events.log`
- `emit-architecture-written` (lines 369-396) — emits `architecture_section_written` event
- `emit-checkpoint-response` (lines 399-421) — emits `approval_checkpoint_responded` event
- `emit-prescriptive-check` (lines 424-448) — emits `prescriptive_check_run` event

The closed sets are enforced as Python `frozenset` literals:
- `_CHECKPOINT_VALUES = {"research-decompose", "decompose-commit"}` (line 264)
- `_RESPONSE_VALUES = {"approve", "revise", "drop", "promote-sub-topic", "approve-all", "revise-piece", "drop-piece"}` (lines 265-273)

Adding a new gate response value requires: updating `_RESPONSE_VALUES`, updating events-registry rows, and updating SKILL.md prose (which contains the literal `"event": "<name>"` strings the registry scanner relies on).

### Events registry

`bin/.events-registry.md` rows 112-114 register the three discovery events:
- `architecture_section_written` — producers in SKILL.md + references/research.md; consumers `tests/test_discovery_events.py (tests-only)`; category `audit-affordance`; target `per-feature-events-log | research-topic-events-log`
- `approval_checkpoint_responded` — same shape; producers in SKILL.md + references/decompose.md
- `prescriptive_check_run` — same shape; producer in references/decompose.md

All three are `gate-enforced` scan coverage (the prose contains literal `"event":` strings the static gate scans) and `audit-affordance` (no live runtime consumers; events exist for compliance audit + skip-rate monitoring per EVT-3 policy).

### Tests baseline (tests/test_discovery_module.py — 404 lines)

14 test functions covering:
- Path resolution: plain slug, R13 `-N` suffix, lifecycle env override, `.session-owner` chain, empty-env fallback (tests 1-5)
- Architecture write: validation, re_walk_attempt field (tests 6-7)
- Checkpoint response: response/checkpoint enum validation (test 8)
- Prescriptive check: nested flag_locations, malformed rejection (tests 9-10)
- Subcommand integration: emit-* uses resolve_events_log_path (test 11)
- CLI smoke: help, resolve, emit (tests 12-14)

**Coverage gaps relevant to this work**:
- No test for the `decompose-commit` checkpoint
- No test for R15 response options (`approve-all`, `revise-piece`, `drop-piece`)
- No structural test that the Architecture/Findings prose at the gate actually contains the required headers
- No discovery analog to `tests/test_lifecycle_kept_pauses_parity.py` (lifecycle's parity test for the kept-user-pauses inventory)

### Prior-work artifacts

- `cortex/lifecycle/reframe-discovery-to-principal-architect-posture/spec.md` — #195's 15 requirements R1-R15 (Architecture section authoring, falsification gate, R4 gate, uniform piece-shaped template, LEX-1 prescriptive-prose scanner, R15 decompose-commit batch-review gate)
- `cortex/research/discovery-architectural-posture-rewrite/research.md` — #195's source research; DR-1 (Architecture section) was preferred over DR-G (deferred ticket creation, i.e., #196's direction)
- `cortex/backlog/196-restructure-discovery-produce-architecture-not-tickets.md` — reverted "decompose-on-demand" direction (user explicitly wanted epic + tickets in same flow)

### Integration with lifecycle

`/cortex-core:lifecycle` consumes discovery via `discovery_source:` frontmatter on backlog tickets. Lifecycle's discovery-bootstrap (`skills/lifecycle/references/discovery-bootstrap.md`) reads `discovery_source` or `research:` field, records the epic research path, and injects it as background context during `/cortex-core:refine` Clarify. Epic content is **not copied** into the ticket lifecycle — only referenced. This contract must remain stable: any new artifact shape (e.g., a richer `decomposed.md` or a new `findings.md`) needs to either fit the existing `discovery_source` linkage or extend the linkage without breaking pre-existing consumers.

## Web Research

### Findings-first / verdict-first reporting templates

- **BLUF (Bottom Line Up Front)** — military communication standard; conclusion appears first, context and reasoning follow. Now widely adopted in technical writing. Direct parallel to "verdict + reasoning + actions" as a gate surface.
- **ADR / MADR templates** — include a "Decision Outcome" section that names the chosen option and rationale upfront. The compressed MADR form (context → options → outcome) maps cleanly onto verdict + reasoning + actions.
- **Consulting recommendation reports** — Executive Summary → Findings → Analysis → Recommendations & Actions is the canonical shape; recommendations are explicitly "one-liners anyone can easily remember."
- **Code review staged disclosure** (GitHub PR reviews, Claude Code Review, Copilot review) — surfaces a headline summary first, then mechanical change-list comments. Direct prior art for "verdict at the gate, decomposition below."
- **Pyramid Principle** (Barbara Minto, McKinsey consulting) — governing thought → key arguments → supporting data. Another variant of the same pattern.

### Terminal-state vocabulary for "completed without producing output"

Strong, repeated prior art across mature workflow systems:
- **GitHub** — `close as not planned` vs `close as completed`. Filterable via `reason:completed` / `reason:"not planned"`. Cleanest two-state model.
- **Jira resolutions** — Done / Won't Do / Cannot Reproduce. Terminal states distinguish action-taken vs no-action-needed vs unable-to-investigate.
- **Airflow** — DAG run succeeds if all leaf nodes are `success` OR `skipped`. `skipped` is explicitly non-failure ("completed without execution").
- **Temporal** — Completed / Canceled / Failed. `Canceled` is distinct from `Failed`. ContinueAsNew explicitly models "completed but transitioning."
- **RFC processes** (Bytecode Alliance, Fuchsia) — Accepted/Approved vs Rejected vs Abandoned/On-Hold/Withdrawn. Three-state minimum; "we investigated and concluded against" differs from "the author dropped this."

### CLI abandon-vs-complete naming

- **Git rebase**: `--continue` (proceed/complete) vs `--abort` (cancel/abandon, restore prior state)
- **CircleCI**: `circleci-agent step halt` for exit-without-failing (distinct from fail-exit)
- **Agent loops** (LangChain, Vercel AI SDK): "tool with no execute function" is a recognized termination pattern

Recurring axis: `abort/cancel/drop/kill` (destructive, prior-state restore) vs. `continue/accept/finalize/complete/done` (constructive, advances state). Strongly supports adding an `accept-findings`-style option distinct from `drop`.

### Decision-record vs architecture-record vocabulary fit

Field has converged on a precedent: many teams **relabeled** `architecture/` directories to `decisions/` deliberately, because "architecture" deters non-architectural decision-recording (vendor choices, planning, scheduling). Joel Parker Henderson's ADR repo, MADR docs, and Cognitect's original post all note this. Direct prior art for relabeling `## Architecture` toward a broader heading.

**"Verdict + reasoning + actions"** is not a named template shape in prior art. The attested equivalents are BLUF, ADR Decision Outcome, recommendation memo, Pyramid Principle. "Findings" leans investigative; "Verdict" leans decisive — both are attested in domain literature.

### Topic-shape branching: thin to nonexistent prior art

**Strong negative finding**: no clear precedent for tools that programmatically branch their output template by topic shape using a deterministic gate rule.
- Dual-track agile (discovery vs delivery) branches by **validation outcome**, not topic shape up-front
- Jira Product Discovery offers two post-discovery paths but the branch is decided **at the end by the human**, not by pre-classified topic shape
- E-learning branching scenarios use predetermined branches per learner choice, but this is interactive, not template-shape classification

Mature tools use **outcome-based** branching (let work happen, route at terminal state) rather than **shape-based up-front** classification. This is a meaningful signal that Option C (topic-shape branching) is unsupported by prior art and likely a non-starter on patterns grounds.

### Anti-patterns identified

1. **Over-narrow heading vocabulary** that fits one topic shape and forces awkward writing for others. Field consensus: broaden ("Architecture" → "Decisions" / "Findings").
2. **Single terminal state for both "done with output" and "done without output"** — every mature workflow tool surveyed (Airflow, Temporal, GitHub, Jira) explicitly separates these. Conflating them loses signal and forces users to invent workarounds.
3. **Up-front topic-shape classification with no escape hatch** — none of the surveyed tools do this.
4. **Burying the verdict** — staged-disclosure code-review tools (GitHub, Claude Code Review, Copilot) all surface a headline first because reviewers won't reliably read past mechanical change-lists.

## Requirements & Constraints

### Workflow trimming / complexity must earn its place

Source: `cortex/requirements/project.md`. Quoted: *"Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."* and *"Workflow trimming: Workflows that have not earned their place are removed wholesale rather than deprecated in stages."*

**Implication**: any new gate option, relocated section, or phase variant must demonstrate why simpler alternatives fail. A new gate option with single-attested utility (one friction run) is on shaky ground without a path to validate recurrence.

### Skill-helper modules

Source: `cortex/requirements/project.md`. When dispatch ceremony is load-bearing enough that a weakly-grounded LLM would skip steps, ceremony may be collapsed into atomic subcommands at `cortex_command/<skill>.py`. Helper subcommands must fuse validation + mutation + telemetry. New event types must register in `bin/.events-registry.md` even when SKILL.md does not contain the literal `"event": "<name>"` string.

**Implication**: `cortex_command/discovery.py` already exists and is the right home for any new gate-response validation and event emission. New events must register.

### Two-mode gate pattern (events-registry static gate)

Source: `cortex/requirements/project.md`. Pre-commit gates pair `--staged` (referential schema check) with `--audit` (time-based or repo-wide). Fail-closed-vs-fail-open is per-gate; events-registry fails closed.

**Implication**: any new event added by this work must register or pre-commit fails closed. No new gate infrastructure needed.

### Design principle: prescribe What and Why, not How

Source: `CLAUDE.md`. *"Resist prescribing step-by-step method (the How). Capable models (Opus 4.7 and later) determine method themselves given clear decision criteria and intent."*

**Implication**: new gate prose should describe decisions (verdict, exit, approval) and intent ("surface findings at the gate"), not order-of-operations narration. Procedural narration is brittle.

### User-facing affordance preservation

Source: `CLAUDE.md`. *"Before classifying a phase boundary or gate as ceremonial, identify the user-facing affordance that boundary protects."* Kept-pauses inventory lives in `skills/lifecycle/SKILL.md` and is parity-tested at `tests/test_lifecycle_kept_pauses_parity.py`.

**Implication**: any change that touches the gate's option set must map current affordances (Architecture review, approve/revise loop, drop, promote-sub-topic) to the proposed surface. Affordances dropped need explicit reasoning. **There is no discovery analog of the kept-pauses parity test today** — this is invisible scope if the work changes the gate option set.

### MUST-escalation policy (post-Opus 4.7)

Source: `CLAUDE.md`. Default to soft positive-routing. New MUST/CRITICAL/REQUIRED escalation requires events.log F-row evidence + a prior `effort=high` dispatch demonstrating soft form failure.

**Implication**: new gate prose should use soft positive-routing. If a dispatch test shows soft form fails to route correctly, escalate with cited evidence. Untested soft prose is also fragile — the spec must call out whether dispatch verification is in scope.

### Structural separation over prose-only enforcement

Source: `CLAUDE.md`. *"Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction."*

**Implication**: encoding the new exit as a closed-set response value in `_RESPONSE_VALUES` is the right pattern; encoding it only in prose ("at the gate, also offer X") is fragile.

### SKILL.md size cap (500 lines)

`skills/discovery/SKILL.md` is currently 107 lines — no constraint here. Complex gate logic naturally lives in `references/`.

## Tradeoffs & Alternatives

Eight candidate approaches evaluated. The adversarial review collapsed two pairs (F & G are mechanism-identical; B is dominated by other options), so the operative option set is six. Each option is described with the same elements: mechanism, files affected, additive-vs-replacing classification, complexity, maintenance cost, risk.

### Option A — Add `## Findings` section to research.md template

**Mechanism**: at research-phase write time, the agent authors a new `## Findings` section (verdict + key findings with WHY + recommended actions + honest gaps). Lead the gate prose with this section instead of `## Architecture`.

**Files**: `skills/discovery/references/research.md` (template), `skills/discovery/SKILL.md` (gate prose), `skills/discovery/references/decompose.md` (note Architecture-as-input only).

**Classification**: Reads as additive but **the adversarial review identified a hidden bifurcation**: the existing R4 `revise` option is structurally scoped to Architecture only (`SKILL.md:77`). Adding Findings at the gate without splitting the gate produces a logical hole — what does `approve` mean when the user agrees with Findings but rejects Architecture, or vice versa? Combination 1 ("A + F") silently inherits this scoping gap and would need to either (i) split revise into revise-findings vs revise-architecture, or (ii) accept that Findings is informational-only and revise still targets Architecture.

**Tradeoffs**:
- Complexity: looks low (two prose files) but the second-source-of-truth question is non-trivial.
- Maintenance: Findings/Architecture coherence drift becomes an authoring discipline; without a structural test, drift is invisible.
- Risk: `grep -c "^## Findings$" >= 1` passes trivially with an empty heading; the user-facing assertion is unverifiable by grep.

### Option B — Restructure existing Architecture vocabulary in place

**Mechanism**: rename `### Pieces` → `### Key Structural Elements` (or `### What Needs To Change`), `### Integration shape` → `### How It Fits Together`, etc. Preserve structure; change surface labels.

**Files**: `skills/discovery/references/research.md`, `skills/discovery/references/decompose.md` (downstream consumes new names), no helper-module change.

**Classification**: Replacing #195's vocabulary but not its structure.

**Tradeoffs**:
- Complexity: very low.
- Risk: relabeling doesn't address the surfacing problem if the actual content authored under the new labels is still mechanism-focused. The friction quote ("summarize your findings") was about content shape, not just labels. B alone is unlikely to resolve the friction.
- **Dominated** by Option A1' (see below) — gate-presentation reorder is the real fix.

### Option C — Topic-shape branching (posture-check / ticket-decomposition / audit)

**Mechanism**: at the end of clarify, classify topic into a shape; route to shape-specific gate.

**Files**: `skills/discovery/references/clarify.md` (add shape determination), `skills/discovery/SKILL.md` (shape-conditional routing), multiple new gate surfaces, helper module (shape-aware events).

**Classification**: replacing #195's unified flow with a shape-polymorphic model.

**Tradeoffs**:
- Complexity: M-L.
- Risk: **disqualified by Agent 2's negative prior-art finding** — no mature tool uses gate-time programmatic topic-shape classification with a determination rule. Mis-classification risk is high. The friction-run artifact's self-label "Posture-check evaluation" is prose authored by the agent, not a typed category.
- **Recommendation**: rule out.

### Option D — Separate `## Recommend` or `## Conclude` phase between Research and Decompose

**Mechanism**: new phase with its own gate. Phase synthesizes research into verdict + recommended action; user approves; if zero-action, discovery terminates.

**Files**: `skills/discovery/SKILL.md` (phase routing), new `skills/discovery/references/recommend.md`, `skills/discovery/references/decompose.md` (Recommend-already-approved note), helper module (new phase events), tests.

**Classification**: replacing #195's two-phase model with a three-phase model. The Architecture-at-decompose-input is preserved; the gate sequencing is restructured.

**Tradeoffs**:
- Complexity: M.
- Maintenance: adds a phase to the state machine; agents must learn three phases. Recommend artifact is a new durable output class.
- Risk: Recommend could drift into mini-Architecture (agents want to name pieces in Recommend). Could become bureaucracy if every ticket-bearing topic gets the extra round-trip without value.

### Option E — Remove/relocate Architecture from the gate

**Mechanism**: gate asks "is research complete?" without re-presenting Architecture sub-sections. User approves or revises the research artifact as a whole. Architecture stays in research.md as decompose input.

**Files**: `skills/discovery/SKILL.md` (gate rewrite), `skills/discovery/references/decompose.md` (consumes Architecture without re-gating).

**Classification**: replacing #195's Architecture-focused gate.

**Tradeoffs**:
- Complexity: low.
- **Loss**: #195's deliberate Architecture-approval affordance is removed. User loses the targeted lever (revise Architecture) and is left with coarse-grained options (revise everything, drop).
- Risk: weak Architecture sections pass the gate undetected; problems surface downstream in decompose or later.

### Option F+G (merged) — New gate-level affirmative exit that writes zero-piece `decomposed.md`

**Mechanism** (collapsed from Agent 4's F and G): add one new closed-set value to `_RESPONSE_VALUES` (candidate names: `finalize-findings`, `accept-as-no-action`, `no-tickets-verdict`). On this response, the helper writes `decomposed.md` with `decomposition_verdict: zero-piece`, a `## Verdict` section, and a one-sentence rationale supplied by the user. The structural difference between F and G is one line of frontmatter; the option is the same.

**Files**: `skills/discovery/SKILL.md` (gate adds new option + prose), `skills/discovery/references/decompose.md` (note the gate-shortcut zero-piece path), `cortex_command/discovery.py` (`_RESPONSE_VALUES` frozenset extended + new helper subcommand to write the zero-piece decomposed.md), `bin/.events-registry.md` (new response value documented under existing event row OR new event row depending on schema choice), tests.

**Classification**: additive to #195. Preserves Architecture flow, decompose flow, and existing gate options. Adds one new option.

**Tradeoffs**:
- Complexity: low. One frozenset entry, one helper subcommand, one event registry update, prose-level gate additions.
- **Critical structural finding**: this is the missing edge in the state machine, not "additive surface" — the zero-piece terminus exists inside decompose but is unreachable without first approving an Architecture the user considers inappropriate. **Adding this gate option closes a real structural gap, not just expands surface for posture-check topics.**
- Risk: user confusion between `drop` (abandon) vs `finalize-findings` (accept). Needs clear prose on when each applies.

### Option H — Gate-presentation reorder (renamed A1')

**Mechanism**: at gate-time, the agent presents the headline finding from research.md **before** Architecture sub-sections. No template change to research.md — the change is in what the gate prose displays. This is **universal** (every topic gets findings-first display), not branched on shape.

**Files**: `skills/discovery/SKILL.md` (gate-presentation prose reorder). No research.md template change. No helper module change.

**Classification**: additive in surface (Architecture still present) but **changes what is displayed at gate-time**.

**Tradeoffs**:
- Complexity: very low. Single prose change to the gate description.
- Maintenance: no new sections, no new structural test gaps. Authors don't need to maintain Findings/Architecture coherence — there's only one durable artifact.
- Risk: gate-presentation reorder relies on the agent surfacing the right finding from research.md. The "headline finding" is not a structured field — it's prose the agent authored. Two failure modes: (1) research.md has no clear headline (agent didn't author one); (2) the gate prompt's "lead with the headline finding" instruction is prose-only and could be skipped under soft positive-routing. Mitigation: dispatch test of the new gate prose before landing.

### Recommended combinations

The adversarial review reframed the analysis from Combination 1 (A + F) to a different shape. Three viable directions:

**Recommended direction (post-adversarial, user-confirmed): Combination R — Option H + Option F+G as one durable design**

Per the Solution horizon principle (`CLAUDE.md:60-62`): both interventions are known to be needed and the helper-module/registry edits would be repeated if staged — propose the durable version. This is one design, not two phases.

- **H** (gate-presentation reorder) addresses #1 (findings buried) at the actual surface where the friction occurred (the gate's prompt), without adding a second source of truth in research.md.
- **F+G** (merged new gate-level affirmative exit) addresses #2 (no clean terminus) by closing the structural gap that makes the zero-piece path unreachable from the gate.

**Why this beats the original Combination 1 (A + F)**:
- Avoids creating Findings/Architecture as two gate sources of truth (the revise-scoping ambiguity the adversarial review surfaced)
- Doesn't ship a structurally-untestable prose section (Findings whose contents grep-only acceptance cannot verify)
- Treats the underlying issue as structural-edge-completion rather than additive-surface-expansion
- Is universal — every topic benefits from findings-first gate presentation, not just topics labeled "posture-check"
- Per-option classification matches the user's "research decides per option" answer: H is structurally additive (gate prose adds a leading sentence, Architecture stays in place); F+G is structurally additive (new closed-set value, no removal)

**Fallback path** (if H proves insufficient via dispatch test): escalate to Option A (`## Findings` section in research.md) **with** a gate-split into revise-findings vs revise-architecture, plus a structural test that asserts the section contains specified content tokens (verdict line, ≥3 findings bullets, ≥1 recommended-action, ≥0 honest-gaps). This is the original Combination 1 hardened against the adversarial-review failures. Larger scope; only justify by dispatch evidence that H is fragile.

**Escalation path** (if recurrence justifies): if posture-check-like topics recur frequently and Combination R leaves residual friction, escalate to Option D (Recommend phase) — but only with evidence of recurrence, not as a precaution.

**Ruled out**: Option C (topic-shape branching) — no prior-art support; Option E (remove Architecture from gate) — loses #195's deliberate affordance; Option B (re-vocab only) — dominated by H.

## Adversarial Review

### Failure modes the primary analysis missed

1. **The friction-run artifact already has its headline finding at line 5, above the Architecture section at line 116.** The user read the findings. The user still dropped. This empirically falsifies "the gate buries findings behind Architecture vocabulary" as the primary mechanism in its template form — findings *are* surfaced in research.md, just not at the gate-presentation surface. The fix is gate-presentation, not research.md template. (Citation: `cortex/research/artifact-format-evaluation/research.md:5`)

2. **The zero-piece path is genuinely unreachable from the gate.** Per `skills/discovery/references/decompose.md:83-88`, the zero-piece `## Verdict` path executes only inside the decompose phase. `cortex/research/artifact-format-evaluation/` has no `decomposed.md`. The user's `drop` (per `events.log:1`) terminated discovery before decompose could write the verdict. The "no clean terminus" framing is correct **structurally**, not just rhetorically — the state machine has an unreachable terminal state for posture-check outcomes.

3. **Combination 1 (A + F) creates a second source of truth at the gate.** The existing `revise` option is scoped to Architecture only (`SKILL.md:77`). Adding `## Findings` at the gate without splitting revise creates a logical hole: what does `approve` mean when the user agrees with Findings but rejects Architecture? Combination 1 is not actually "low-complexity additive" — it's a quiet bifurcation of gate semantics.

4. **F-vs-G is a fake distinction.** Agent 4 separated them but the mechanism is identical: both write `decomposed.md` with a zero-piece-style verdict via a gate-time shortcut. The only difference is one line of frontmatter (`decomposition_verdict: zero-piece` vs `decomposition_verdict: findings-only`). Treating them as two options biased the recommendation toward "A + F or A + G" when the actual question is "do we add one new response value, and what do we name it?"

5. **The user's `drop` is under-determined.** `events.log:1` contains exactly one event with no `drop_reason` field. Three possible explanations: (a) the user didn't know about the zero-piece path; (b) the user knew but couldn't reach it without approving Architecture they considered inappropriate; (c) the user wanted to abandon entirely. The recommendation depends on which is true. (a) → fix is documentation. (b) → fix is the new exit option. (c) → no fix needed. The single-line evidence base cannot discriminate.

6. **Posture-check is descriptive, not operationalizable.** The friction-run artifact self-labels "Posture-check evaluation" at line 3 — this is prose authored by the agent, not a typed category. Agent 2's negative prior-art finding for gate-time shape classification confirms this. The honest implication: if posture-check isn't operationalizable, the friction is not "posture-check topics need a special path" — it is "all topics can end with no actionable work, and the gate should expose that exit."

7. **No discovery-side kept-pauses parity test exists.** Lifecycle has `tests/test_lifecycle_kept_pauses_parity.py` enforcing its inventory; discovery does not. Adding a new gate option is a new kept-user-pause that drifts from inventory silently. Establishing this test is invisible scope in Agent 4's "very low complexity" classification of F+G.

8. **The new prose-only enforcement is fragile against soft positive-routing.** Per CLAUDE.md, soft form must be **tested** before claiming it routes correctly. There is no precedent dispatch confirming Opus 4.7 will follow "lead with the headline finding" prose without imperative escalation. Spec must call out whether dispatch verification is in scope.

9. **The `## Findings` section in research.md has no structural test.** A grep-only acceptance (`grep -c "^## Findings$" >= 1`) passes trivially with an empty heading. The thing the user actually cares about — verdict + reasoning + actions + gaps — is unverifiable by grep without content-token assertions. Combination 1 ships with structurally-untestable prose, violating CLAUDE.md's structural-separation principle.

10. **Anchoring bias in the source prompt.** The lifecycle prompt led with Option A fully specified and others as one-liners; Agent 4 attempted elaboration but the asymmetry leaked into the recommendation. Without independent re-elaboration of B, E, H to comparable depth, the "Combination 1 best" conclusion is not falsifiable. The post-adversarial reframe to Combination R (H + F+G) directly corrects this anchoring.

### Recommended mitigations (lifted from Agent 5)

1. Before locking the spec, ground the user-intent question — ask the user explicitly which of (a)/(b)/(c) explains the `drop`, or plan a second friction run to measure whether the user reaches for the new affordance.
2. Collapse F and G to one option; pick a name and one `decomposition_verdict` value.
3. Reframe A from "add a Findings section to research.md" to "at gate-time, present the headline finding before the Architecture sub-sections" — a gate-presentation change, not a template change.
4. Specify Combination R as: (i) gate-presentation reorder; (ii) new closed-set response value with helper subcommand; (iii) helper writes zero-piece `decomposed.md` from the gate. This is one design, not "A + F additive."
5. Make the new exit testable by structure — assert the new helper subcommand writes `decomposed.md` with `decomposition_verdict: zero-piece`, a `## Verdict` section, and zero new backlog files for the discovery.
6. Establish a discovery-side kept-pauses parity test alongside `_RESPONSE_VALUES` updates, mirroring `tests/test_lifecycle_kept_pauses_parity.py`. Budget the scope explicitly.
7. Test the new gate prose with a dispatch before landing. If Opus 4.7 routes correctly to the new option on a posture-check shape, land the soft form. Otherwise specify escalation in the same PR with events.log F-row evidence.
8. Document the one-line-of-evidence limit explicitly. The spec should name "evidence-thin" as a constraint and identify what the second data point would look like.

## Open Questions

1. **What was the user's actual reason for `drop` on the artifact-format-evaluation run?** **Resolved**: post-research interview with the user established that the proximate cause was friction #1 (Architecture-vocabulary gate framing), not #2 (no-tickets terminus). The drop was a protest against committing downstream of a gate the user had just declared unhelpful — not abandonment, not zero-piece-path-ignorance. Per the user: the durable spec direction is Combination R (H + F+G merged) as one design rather than a staged H-now/F+G-later, because (i) H addresses the proximate cause of the observed friction-run, (ii) F+G closes the structural-edge gap for the legitimate zero-piece class that exists independent of the friction-run example, and (iii) staging would repeat the helper-module and registry edits twice. This decision is grounded in the new `Solution horizon` principle in `CLAUDE.md:60-62` (and `cortex/requirements/project.md` Philosophy of Work) — when both interventions are known to be needed, propose the durable version, not the stop-gap.

2. **What is the name for the new closed-set response value?** **Resolved**: `finalize-findings`. Rationale: "finalize" carries terminal-state semantics distinct from `drop` (abandon) and `approve` (commit-to-decompose); "findings" names what is being accepted. Reads naturally in event payloads (`response: finalize-findings`).

3. **Should the gate-presentation reorder (Option H) be specified as a procedural narration ("present headline finding, then Architecture") or as a decision criterion ("the gate prompt's first section is the agent-selected headline finding from research.md")?** **Deferred**: will be resolved in Spec through structured interview. CLAUDE.md's "What and Why, not How" principle (lines 64-70) prefers decision criterion; spec should encode this as such, not step-sequence narration.

4. **Does the discovery-side kept-pauses parity test exist or need to be created as part of this work?** **Deferred**: will be resolved in Spec. Scope decision — is the parity test in scope for this lifecycle or a follow-up? Per Solution horizon, if the absence of the test is a known constraint that the same patch would apply to, surface in spec and propose the durable version.

5. **What is the structural test surface for "the gate presents findings before Architecture"?** **Deferred**: will be resolved in Spec. Options: (i) snapshot test of gate prompt prose; (ii) dispatch-based behavior test; (iii) accept as a "soft" change and rely on subjective re-run. Spec should pick.

6. **Should the helper write `decomposed.md` with `decomposition_verdict: zero-piece` or introduce a new verdict value (e.g., `findings-only`)?** **Deferred**: will be resolved in Spec. Reusing `zero-piece` is simpler; introducing a new value preserves the semantic distinction. Spec should pick.

7. **Soft-form gate prose dispatch verification — in scope or out?** **Deferred**: will be resolved in Spec. Per CLAUDE.md MUST-escalation policy, soft positive-routing is default but should be verified. Spec must decide whether dispatch test is gating before merge.

## Considerations Addressed

- **Classify each candidate option against both readings of "additive to #195" and recommend a per-option stance**: addressed throughout the Tradeoffs section. Each option (A, B, C, D, E, F+G merged, H) has an explicit additive-vs-replacing classification with the specific #195 surface it touches or preserves. Per-option stance carried through to the Recommended combinations sub-section.

- **Evaluate (a) reach existing zero-piece path more directly vs. (b) new gate-level exit that skips decompose; recommend one**: addressed in the Adversarial Review section (point 2: zero-piece path is genuinely unreachable from gate) and Option F+G (merged). Recommendation: option (b) — new gate-level closed-set response value that writes zero-piece `decomposed.md` from the gate — because the existing path's gate-unreachability is a real structural-edge missing, not just a discoverability issue.

- **Elaborate each candidate option to comparable depth — do not anchor on the most-detailed alternative**: attempted in the Tradeoffs section. The adversarial review caught residual anchoring (point 10) and the recommendation was reframed from Combination 1 (A + F) to Combination R (H + F+G) as a result. Each of the eight options has the same five-element treatment (mechanism, files, classification, tradeoffs, risk).

- **Investigate whether posture-check / ticket-decomposition / audit is operationalizable**: addressed in Web Research (negative prior-art finding for gate-time shape classification) and Adversarial Review (point 6: "posture-check" is prose authored by the agent, not a typed category). Recommendation: treat topic-shape branching as a non-starter; the fix should be universal (all topics get findings-first gate presentation + an affirmative no-action exit), not branched on shape.

- **Inventory cortex_command/discovery.py subcommand surfaces and tests/test_discovery_*.py baseline**: addressed in Codebase Analysis (helper module subcommands, `_RESPONSE_VALUES` frozenset, `_CHECKPOINT_VALUES`, validation functions, 14 tests in `test_discovery_module.py`, coverage gaps for decompose-commit checkpoint and R15 response options, no kept-pauses parity test analog).

- **Acceptance signal is subjective re-run; structural tests gate merge but experiential validation is user's reaction**: addressed in Open Questions (point 5: structural test surface for findings-first gate presentation is hard; subjective re-run is the experiential validation; the spec should call this out explicitly). The Open Questions also note that "evidence-thin" is a constraint that should be documented in the spec.
