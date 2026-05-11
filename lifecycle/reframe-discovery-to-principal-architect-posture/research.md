# Research: Reframe discovery to principal-architect posture (#195)

Lifecycle research artifact for backlog item #195. The authoritative DR-1 spec is `research/discovery-architectural-posture-rewrite/research.md`; this file consolidates lifecycle-phase research with adversarial findings and surfaces the decisions the spec phase must make.

## Codebase Analysis

### Files that will change

**Primary targets** (the three discovery reference files):
- `skills/discovery/SKILL.md` (73 ln) — unchanged in structure; phase routing at §3 table stays stable.
- `skills/discovery/references/clarify.md` (65 ln) — edit §6 (lines 42–56) to add an **optional** "Scope envelope" output (In scope / Out of scope or "No envelope needed") as the fifth output, after the requirements-alignment note.
- `skills/discovery/references/research.md` (155 ln) — insert new `## Architecture` section after the Feasibility section (after line 107, before Decision Records). Sub-sections: `### Pieces` (one bullet per piece, named by role), `### Integration shape`, `### Seam-level edges`, `### Why N pieces` (conditional — fires when piece_count > 5 via falsification framing: "for each adjacent pair, attempt to merge; if nothing blocks, merge").
- `skills/discovery/references/decompose.md` (142 ln) — heavy rewrite:
  - **Remove**: R2(a)/R2(b)/E9 at :24-27 (value-grounding stack), R3 per-item-ack at :37-42, R4 cap at :35, R5 flag propagation at :70, R7 flag-event-types at :46-52, E10 invariant. NOTE: the research artifact lists "R7 flag events" as live, but **the R7-era event types (`decompose_flag` / `decompose_ack` / `decompose_drop`) were already deprecated in commit 239b080** with sunset rows in `bin/.events-registry.md:104-106` — the removal of R7 from prose is housekeeping, not a load-bearing trim.
  - **Rewrite** §2 (Identify Work Items, :11-31) to consume the approved Architecture-section piece list; specify the uniform body template (Role / Integration / Edges / optional Touch points).
  - **Augment** §4 (Grouping) with single-piece (no-epic single-ticket path) and zero-piece (fold-into-#N or no-tickets verdict) branches.
  - **Replace** lexical-headers ban at :147 with section-partitioned prescriptive-prose check (run at decompose-§5 ticket-write time; same check also runs at research-§6 architecture-write time).

**New files**:
- `bin/cortex-check-prescriptive-prose` — Python lexical scanner. Modeled on `bin/cortex-check-events-registry` shape: `--staged` for pre-commit, `--root` for tests, exit codes 0/1, stdlib-only. Scans body sections (Role / Integration / Edges) for `path:line` citations, section-index citations (`§Nx`, `R\d`), and quoted-prose-patch fenced blocks. Touch points section exempted.
- Possible new helper module `cortex_command/discovery.py` — event-emission subcommands; warranted if the `prescriptive_check_run` event's nested `flag_locations[]` payload meets project.md L33 "collapse when LLM would paraphrase" criterion. **Open question** — see below.

**Registry**:
- `bin/.events-registry.md` — add three new rows. Schema is a 10-column markdown table (event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner). **The `target` enum used in production is `per-feature-events-log` / `overnight-events-log` — there is no precedent for `research/{topic}/events.log` as a target.** See Open Questions §EVT-1.

### Existing patterns to follow

- **Lexical-scanner shape**: `bin/cortex-check-events-registry` (90 ln) and `bin/cortex-check-parity` (~360 ln) — argparse with `--staged` (pre-commit critical path) and `--audit` (off-path) modes, `--root` override for tests, stdlib-only, scan globs as a module-level constant, exit codes 0/1.
- **Pre-commit wiring**: `.githooks/pre-commit` auto-mirrors `bin/` → `plugins/cortex-core/bin/`. New `bin/cortex-check-prescriptive-prose` is canonical; the mirror is automatic.
- **Justfile recipes**: pair `check-prescriptive-prose` (staged-mode wrapper) + optional `check-prescriptive-prose-audit` per the two-mode gate pattern in project.md.
- **Skill-reference file structure**: H3 numbered sections (§1, §2 …), H4 sub-sections, Constraints table at end (Thought/Reality format), signal formats documented inline for downstream consumers.
- **Skill-helper module precedent**: `cortex_command/critical_review.py` — atomic subcommands fusing validation + mutation + telemetry per project.md L33; `cortex_command/common.py` for shared helpers.

### Integration points and downstream-reader contracts

- `skills/lifecycle/references/discovery-bootstrap.md` reads frontmatter only (`discovery_source`, `research`, `type`, `spec`). **Does not parse ticket body section names.**
- `skills/refine/SKILL.md` reads `discovery_source` as background context (the `research:` and `discovery_source:` frontmatter fields) and reads `lifecycle/{slug}/research.md` directly. **Does not parse body section names.**
- `skills/refine/references/clarify-critic.md` reads `parent:` frontmatter and the parent epic body via `bin/cortex-load-parent-epic`. **Does not parse discovery-produced section names.**
- **Caveat surfaced by adversarial review**: `tests/test_decompose_rules.py` (~239 lines, ~25 placement-test functions) DOES enforce specific body-section content in `decompose.md` itself — not in produced tickets, but in the protocol prose being trimmed. The "aggressive trim" deletes content these tests verify. Test rewrites are mandatory and were not surfaced in the ticket's touch-points list. See Open Questions §TEST-1.

### Worked-example corpora available under `research/`

- `research/vertical-planning/` — 9-piece mixed-stream decomposition (`research.md` 257 ln, `decomposed.md` 90 ln, `audit.md` 46 ln). Primary load-bearing exemplar for the spec-phase re-walk.
- `research/repo-spring-cleaning/` — 3-piece surface-anchored hygiene (`research.md` 350 ln, `decomposed.md` 52 ln). Strong candidate for the alternative-corpus re-walk because it stresses Touch-points-heavy bodies.
- `research/opus-4-7-harness-adaptation/` — policy-heavy (`research.md` 287 ln, `decomposed.md` 60 ln). Candidate for a third re-walk; tests the "permissive paragraph for non-constructive topic shapes" guidance.
- `research/discovery-skill-audit/` — prior session audit identifying the over-decompose / undersized / prescriptive failure modes that motivated DR-1.

## Web Research

### Principal-architect prompting — strong prior art

- **MetaGPT's Architect role** is the canonical published precedent: the Architect emits File List + Data Structures + Interface Definitions + sequence diagram before the Project Manager carves tasks. The decomposition unit is *modules with defined fields/methods/interaction sequences* — direct shape-match for Role/Integration/Edges.
- **Anthropic's lead-agent decomposition discipline** ([engineering blog](https://www.anthropic.com/engineering/multi-agent-research-system)): the lead must decompose with "surgical precision — an objective, an output format, guidance on tools and sources, and clear task boundaries." Documented anti-patterns: over-spawning, vague boundaries → redundant work. The scaling rules embedded in the lead prompt are how Anthropic prevents over-decomposition.
- **CrewAI vs AutoGen split** — hierarchical role-based decomposition (CrewAI's `Process.hierarchical`) matches the principal-architect framing; AutoGen's dynamic-selector group chat is the opposite. 2025-era guidance: most production agent systems cap at two hierarchy levels.
- **Boundary-Control-Entity (BCE) pattern** — concrete role-naming taxonomy that maps onto "name the pieces by role" without prescribing internals.

### Phase-boundary approval gate

- **Plan-Validate-Execute** (variant of Plan-and-Execute) is the dominant pattern. Rationale matches DR-1's motivation: "LLMs can generate convincingly wrong plans that appear plausible and well-structured… if a flawed plan is approved, then even with perfect execution, the outcome will be incorrect" ([agentic-patterns.com](https://agentic-patterns.com/), [LangChain](https://blog.langchain.com/planning-agents/)).
- **HITL framework decomposition**: classifier / suspension / schema / surface / hook — useful checklist for the gate.
- **Approval-affordance shapes**: binary or ternary (approve / reject / edit) is the norm; **nested batch approvals are anti-patterned** (timeout handling with default-deny is the recommended fallback).
- **Cloudflare's separation of Workflow approval vs MCP elicitation** — the discovery phase-boundary gate is structurally Workflow approval (durable, multi-step), not inline elicitation.

### Falsification framing — thin direct prior art, structural support

- 2025-era Popperian-architecture framing has academic support but flags two failure modes: (a) falsification weaponized as change-aversion ("this signal refutes the conjecture"), (b) reduced to "auxiliary issue" dismissal protecting fragility.
- **Constraint-satisfaction literature**: adjacent-clique merging in SDP decomposition is evaluated by "does the merge reduce dimension and linking constraints?" — *structural cost*, not narrative justification. Citation cover for "if nothing blocks, merge."
- **Failure mode not surfaced in DR-1**: independent-but-coherent pieces with no merge-blocker but also no merge benefit. See Adversarial §5.

### Lexical scanners

- **Vale** is the dominant prose-discipline tool with section-scoped `existence` rules and `~heading & ~blockquote` selectors. Ruled out by Agent 1 in favor of stdlib Python matching the existing `bin/cortex-check-*` shape, but Vale's *rule design* (scope selectors, extension points) is reference material for the scanner's behavior spec.

### Prescriptive vs descriptive ticket prose

- **INVEST's Negotiable criterion**: "keeping the user-story narrative free from implementation details" — direct external authority.
- **"Acceptance criteria should focus on the 'what' not the 'how'"** is well-established (LogRocket, Atlassian, PMI).
- **Anti-pattern**: "split by architectural layer" fails INVEST (one story for UI, another for DB, etc.). One-finding-per-ticket has the same shape — completeness without independent value.
- Cleanest framing: **start descriptive (role + integration + edges), narrow toward prescriptive only during/after planning**.

## Requirements & Constraints

### MUST-escalation policy (CLAUDE.md §"MUST-escalation policy")

- Default to soft positive-routing phrasing for new authoring under epic #82.
- To add a new MUST: commit body or PR description must link evidence — either `lifecycle/<feature>/events.log` F-row showing Claude skipped the soft form, OR a commit-linked transcript URL or quoted excerpt. **Without one, the escalation is rejected at review.**
- Effort-first prerequisite: run a dispatch with `effort=high` (and `xhigh`) on a representative case; escalate only when both fail.
- Scope: all behavior-correctness failures except **tone perception** (OQ6).
- **The ticket's promise that "no MUST language without effort=high evidence" is the right posture** — but a downstream caveat surfaces: the three new gate-instrumentation events targeting `research/{topic}/events.log` cannot serve as MUST-escalation evidence under the current policy, which expects evidence at `lifecycle/<feature>/events.log`. See Open Questions §EVT-2.

### Events registry (`bin/.events-registry.md`)

- 10-column schema; `event_name` matches `[a-z_]+`; `scan_coverage: gate-enforced` triggers `bin/cortex-check-events-registry --staged` validation of `"event": "<name>"` literals in skill prose.
- Adding events requires **≥1 documented consumer** for non-`live` rows; `live` rows with zero consumers are tolerated but accumulate audit-affordance overhead.
- **Existing target enum in production: `per-feature-events-log` / `overnight-events-log`.** No precedent for `research/{topic}/events.log` as a registered target — extension required.

### Bin/ parity enforcement (project.md §SKILL.md-to-bin parity)

- New `bin/cortex-check-prescriptive-prose` must have ≥1 in-scope reference (`CLAUDE.md`, SKILL.md, requirements, docs, hooks, justfile, tests). Default wiring: justfile recipe + decompose.md reference in protocol prose.
- Alternative: `bin/.parity-exceptions.md` row with closed-enum category and ≥30-char rationale. Not the recommended path.

### SKILL.md size cap (project.md §SKILL.md size cap)

- 500-line cap on SKILL.md files only (not reference files). Discovery's SKILL.md is 73 ln — far under cap. Extracting more prose into `skills/discovery/references/` *helps* compliance.

### Workflow trimming (project.md §Philosophy of Work)

- Hard-deletion preferred over deprecation when consumers verified zero (per-PR).
- CHANGELOG entry required for retired surfaces with replacement entry points.
- The ticket's trim (R2-R7 stack) is aligned with this policy *if* per-PR zero-consumer verification holds. Most R-rules are encoded in `tests/test_decompose_rules.py` (not consumers in the runtime sense, but contracts in the test sense) — see Adversarial §1.

### Tone/voice policy (docs/policies.md via CLAUDE.md L60)

- Cortex does **not** ship tone directives; tone is user-self-service via `~/.claude/CLAUDE.md`.
- New approval-gate prompts should not include tone-shaping language (no "be conciliatory," no emoji guidance). Tone complaints are OQ6, not MUST-escalation eligible.

### Skill-helper module pattern (project.md L33)

- When SKILL.md dispatch ceremony is load-bearing enough that a weakly-grounded LLM would skip or paraphrase, collapse to `cortex_command/<skill>.py` atomic subcommands fusing **validation + mutation + telemetry**. New event types emitted by such modules register in `.events-registry.md` even when SKILL.md does not contain literal `"event": "<name>"` strings.
- Relevance: the `prescriptive_check_run` event's `flag_locations: [{ticket, section, signal}]` nested-array payload likely meets the paraphrase-vulnerability threshold; the other two events (`architecture_section_written`, `approval_checkpoint_responded`) are simple key-value emissions.

### Multi-agent and observability

- Features with `intra_session_blocked_by` are filtered at round-planning. No discovery decision should force-dispatch.
- Dashboard polls at ~5s; statusline <500ms; notifications fire-and-forget with 5s curl timeout. New events surfacing in the dashboard require explicit consumer wiring in `cortex_command/dashboard/data.py`.

## Tradeoffs & Alternatives

**Six axes evaluated.** Five have clear picks grounded in re-walk evidence + project philosophy; one is a genuine close call flagged for spec.

| Axis | Pick | Rationale |
|---|---|---|
| **1. Scanner deployment** | New `bin/cortex-check-prescriptive-prose` Python script | Prose-only is empirically rejected by both pre-implementation re-walks; matches existing `bin/cortex-check-*` pattern; dual-source mirror is automated |
| **2. Approval-gate 4th option** ("Promote sub-topic") | **Close call — flag for spec** | Recursive `/cortex-core:discovery` invocation maximally honors carryover #4 but has zero existing mechanism; deferred-stub (file backlog ticket tagged `needs-discovery`) is the minimal-surface alternative honoring project.md's "Complexity must earn its place" |
| **3. Non-constructive topic shapes** (diagnostic/policy/migration) | Single permissive paragraph | Carryover #5 commits to it; branching sub-templates were already cut at critical review; zero-piece exit handles true diagnostic cases |
| **4. "Why N pieces" framing** | Falsification ("attempt merge each adjacent pair") | Re-walk produced the evidence justifying the reframe; justification framing rationalized in the walk; **caveat from Adversarial §5 — independent-but-coherent pieces over-merge under the literal "if nothing blocks" rule.** Mitigation: constrain to "if nothing blocks AND merged piece would be lifecycle-completable in one run, merge" |
| **5. Events emission placement** | Helper module `cortex_command/discovery.py` (atomic emit subcommands) | `prescriptive_check_run.flag_locations[]` nested-array payload triggers project.md L33 collapse criterion; co-locating the simpler two events is cheap and consistent |
| **6. Defense-in-depth both write-times** | **Close call — Adversarial §8 challenges the framing** | Carryover #2 commits to it; Adversarial §8 argues the same agent writes both surfaces sequentially, so the "N+1 revision pass" justification is weakened. Mitigation: pre-commit hook re-run (different actor context) is the real second-actor defense |

## Adversarial Review

Fifteen failure modes identified by an independent agent reviewing the synthesis of agents 1–4. The high-severity findings are surfaced verbatim below; the rest feed Open Questions.

### High-severity (block spec approval without resolution)

**A-1 — Test coupling missed entirely.** `tests/test_decompose_rules.py` (~239 ln, ~25 test functions) enforces specific body-section content in `skills/discovery/references/decompose.md`. It asserts R1's "not sufficient Value" text in §Constraints (line 89), R2's `[file:line]` anchor in §Identify Work Items (line 102), R2's `premise-unverified` and `canonical pattern` anchors (lines 109, 116), R3's `AskUserQuestion` flow (line 142), R4's `more than 3` threshold (line 156) and `all items flagged` (line 163) and `Return to research` offer (line 171), R6's `Present the proposed work items` (line 178), R5's propagation/originating/invariant anchors (lines 198-228), R9's `## Dropped Items` subsection (line 234). **The plan's "aggressive trim" demolishes ~80% of what this file verifies; the ticket touch-points list omits the test file entirely.** Test rewrite is mandatory pre-merge.

**A-2 — Events target inconsistency.** The research artifact specifies events writing to `research/{topic}/events.log`. The registry's allowed `target` values in production are `per-feature-events-log` and `overnight-events-log`. There is no precedent for a research-topic-scoped events log in the existing infrastructure. CLAUDE.md's MUST-escalation policy expects F-row evidence at `lifecycle/<feature>/events.log`. **The asserted MUST-escalation evidence path does not connect** unless either (a) the registry target enum is extended and the checker accepts it, or (b) the three events emit to `lifecycle/{nearest-lifecycle-slug}/events.log` instead.

**A-3 — Ticket #195 self-inconsistency.** The Edges section of `backlog/195-...md` contains `decompose-§5`, `research-§6`, and several `:NN-NN` line-range citations — exactly the section-index and path:line citations the proposed prescriptive-prose gate flags as prescription in body sections. Either the gate must be looser than specified, or #195 itself fails its own check at decompose-§5 time. Mitigation: rewrite the touched ticket bodies to comply, OR refine the gate definition (likely: distinguish "narrative reference to a contract boundary" from "prescription of implementation mechanism" — the regex must support this).

**A-4 — Falsification gate over-merges independent-but-coherent pieces.** Four genuinely-independent pieces with no inter-dependencies: under "if nothing blocks the merge, merge," every adjacent pair gets pressure-merged into a junk drawer because "nothing blocks" is trivially true when pieces don't depend on each other. The re-walk evidence is for the *justification* framing, not the *falsification* framing — the latter has not been empirically walked. Mitigation: add a coherence-check on the *merged* piece ("would the merged piece be lifecycle-completable in one run?"); reject merges where the answer is no.

**A-5 — Approval-gate "revise" path is undefined workflow.** The gate offers approve/revise/drop/promote-sub-topic. "Revise" is unactionable as a single click on a 9-piece architecture section: which piece, what kind of revision, does the agent re-walk, re-run research, prompt for which piece to revise? Spec phase must define the revise loop or drop the option.

**A-6 — "Promote sub-topic to its own discovery" has zero implementation surface.** No existing skill has nested-discovery semantics. Open questions: what happens to the parent's state during the sub-discovery? Does the parent pause? Where does the sub-slug go? When the sub completes, does it return to the parent? Spec phase must scope this — either define the recursion semantics, downgrade to "file as `needs-discovery` backlog ticket" (Tradeoff axis 2 alternative B), or drop the option.

**A-7 — Re-running discovery on a topic — slug `-2` suffix is undefined.** `skills/discovery/SKILL.md:42-46` detects existing `research/{topic}/` and routes to "complete (offer to re-run or update)" — but the carryover claim that re-runs produce `vertical-planning-2` style slugs is not implemented anywhere. Without defined mechanism, second-run will either overwrite (losing audit trail) or fail. Spec phase must define collision behavior.

**A-8 — Complexity assessment is undersized.** This single ticket lands: new bin script + pre-commit wiring + dual-source mirror + parity wiring, three new registry rows + target-enum extension, three new gate-instrumentation event schemas, a helper module (`cortex_command/discovery.py`), three reference-file rewrites, ~25 test rewrites in `test_decompose_rules.py`, an approval-gate prose with 3-4 options + revise-loop semantics, a falsification-gate framing with worked examples + anti-patterns, a uniform ticket-body template, a scope-envelope output, plus a spec-phase re-walk obligation across 2-3 corpora. **This is plausibly an epic with 4 child tickets, not a single feature.** See Open Questions §SCOPE-1.

### Medium-severity (resolvable in spec)

- **A-9 — Lexical scanner false-positive surfaces**: section-boundary detection on markdown variants, narrative-vs-prescription regex precision, Edges naturally referencing constraint files. Spec must specify the regex precisely with worked examples + anti-patterns.
- **A-10 — Defense-in-depth at architecture-write-time is mostly noise**: same agent writes both surfaces sequentially; revision-pass argument depends on independent authoring contexts. Pre-commit hook is the genuine second-actor surface. Spec should justify or drop.
- **A-11 — Heterogeneous backlog transition cost**: existing tickets use Value/What/Why/Findings; new tickets use Role/Integration/Edges/Touch points. No automated migration. Human-readable search across the heterogeneous backlog is lossy. Spec should note as accepted cost or specify a migration plan.
- **A-12 — Multi-epic constraint contradicts let-research-inform**: clarify-time epic split requires the user to know architectural shape pre-research. Spec should either relax to "detect-and-prompt at decompose time" or document the constraint as accepted.
- **A-13 — Three new events with no consumers at ship time**: continues the audit-affordance accumulation pattern. Spec should either define real consumers (dashboard surfacing, report inclusion, test assertions) or explicitly accept `tests-only` consumer rows.
- **A-14 — R7 removal premise inflates the case for three new events**: R7-era events are already deprecated (commit 239b080, sunset 2026-06-10). The "must-replace-not-remove" argument from CLAUDE.md MUST-evidence policy is weakened because the surface being "replaced" no longer exists.
- **A-15 — Sunk-cost in 9-carryover folding**: research artifact shows DR-1 → DR-G → DR-1 reversal with 9 carryovers folded back unchallenged. Project workflow-trimming bias would require evidence each carryover survives independent re-evaluation. Spec should re-justify or cut.

## Open Questions

Questions the spec phase must resolve before implementation lands. Four high-impact items were resolved at research-exit by user decision (2026-05-11):

- **SCOPE-1**: Keep #195 as a single ticket; spec phase re-weighs the coordination defense with `test_decompose_rules.py` rewrite cost in scope and splits only if the re-walk shows the coordinated argument fails.
- **A-3 (ticket self-compliance)**: Spec phase rewrites #195's body to comply with the prescriptive-prose check (move section-index and path:line citations from Edges/Integration into Touch points). If the ticket cannot be rewritten coherently, that is evidence the gate is over-strict — refine the gate definition.
- **EVT-1**: Dual events target — `lifecycle/{slug}/events.log` when discovery is invoked under a lifecycle, falling back to `research/{topic}/events.log` for standalone discovery. Register the dual target in `bin/.events-registry.md`.
- **GATE-1**: Add coherence check to the falsification rule — "if nothing blocks the merge AND the merged piece would be lifecycle-completable in one run, merge; otherwise keep separate." Spec defines lifecycle-completable bound.

### EVT-1 — Events target registration

**Question**: Do the three new events emit to `research/{topic}/events.log` (requires registry target-enum extension + checker update) or to `lifecycle/{nearest-lifecycle-slug}/events.log` (reuses existing infrastructure but couples discovery to lifecycle slug derivation)?

**Decision**: spec phase. **Recommendation**: emit to `lifecycle/{slug}/events.log` when discovery is invoked under a lifecycle, fall back to `research/{topic}/events.log` for standalone discovery. Document the dual target in the registry row.

### EVT-2 — MUST-escalation evidence path

**Question**: If events emit to `research/{topic}/events.log`, can they serve as F-row evidence for future MUST escalation per CLAUDE.md, which references `lifecycle/<feature>/events.log`?

**Decision**: spec phase (interacts with EVT-1).

### EVT-3 — Real consumers for the three new events at ship time

**Question**: Do `architecture_section_written`, `approval_checkpoint_responded`, `prescriptive_check_run` need real consumers (dashboard surface, report inclusion, metrics) at ship time, or is `tests-only` acceptable?

**Decision**: spec phase. If `tests-only`, document the audit-affordance cost in the registry row's rationale.

### TEST-1 — Coverage of trimmed rules in `test_decompose_rules.py`

**Question**: Audit `tests/test_decompose_rules.py` against every line of `decompose.md` the ticket trims; specify which test functions delete, rewrite, or carry forward unchanged.

**Decision**: spec phase MUST audit and produce a delta plan. Implementation cannot land green CI without this.

### SCOPE-1 — Single ticket vs epic

**Question**: Should #195 split into multiple child tickets? Candidate boundaries:
- (a) decompose.md trim + test rewrites — landed on its own with no behavior change to research.md
- (b) Architecture section + approval-gate UX (with revise-loop semantics defined)
- (c) `bin/cortex-check-prescriptive-prose` + parity wiring + tests
- (d) Events plumbing (target registration + helper module + 3 event schemas)

**Decision**: spec phase. The research artifact at `research/discovery-architectural-posture-rewrite/research.md` §"Why coordinated, not split" defends single-ticket coordination, but the defense did not factor `test_decompose_rules.py` overhead (Adversarial A-1). Spec re-evaluation with the test cost in scope may flip the recommendation.

### GATE-1 — Falsification rule for independent-but-coherent pieces

**Question**: Does the "for each adjacent pair, attempt to merge; if nothing blocks, merge" rule need a coherence-check on the merged piece? Adversarial A-4 argues yes — without it, four genuinely-independent pieces with no merge-blockers get pressure-merged into a junk drawer.

**Decision**: spec phase. Recommended rule: "if nothing blocks the merge AND the merged piece would be lifecycle-completable in one run, merge; otherwise keep separate."

### GATE-2 — Approval-gate "revise" semantics

**Question**: What happens when the user picks "revise" on a 9-piece Architecture section?

**Options**:
- (i) Agent asks "which piece(s) to revise" via AskUserQuestion and then re-walks only those pieces in the architecture section.
- (ii) Agent re-runs the entire research phase from scratch.
- (iii) Agent presents the per-piece Role/Integration/Edges and prompts for free-text revision instructions.

**Decision**: spec phase. Recommended: (iii) — minimal mechanism, maximal user control.

### GATE-3 — Promote-sub-topic-to-own-discovery semantics

**Question**: Does the 4th approval option spawn a nested discovery, file a `needs-discovery` backlog ticket, or get dropped?

**Decision**: spec phase. Tradeoff axis 2 covers the options. **Recommended fallback**: scope as "file `needs-discovery` backlog ticket with the piece description and `parent: <current-discovery-topic>` linkage" — minimal surface honoring the affordance without inventing nested-skill semantics.

### GATE-4 — Re-running discovery on existing topic

**Question**: When `research/{topic}/` already exists and the user re-runs `/cortex-core:discovery topic={topic}`, what is the behavior?

**Options**:
- (i) Explicit `-2` suffix on new run; `superseded_by` linkage on prior research artifact.
- (ii) Overwrite-with-archive (move prior to `research/{topic}/.archive/`).
- (iii) Refuse without `--force` flag.

**Decision**: spec phase. Recommended: (i) — matches the carryover language and preserves audit trail.

### LEX-1 — Scanner regex precision and section-boundary detection

**Question**: What exact patterns does `bin/cortex-check-prescriptive-prose` flag, and how does it detect Touch-points boundary?

**Decision**: spec phase MUST specify regex + worked examples + anti-patterns. Per Adversarial A-9 and A-3, the rule must distinguish "narrative reference to a contract boundary" (e.g., "this piece breaks if the lifecycle phase-transition contract changes") from "prescription of implementation mechanism" (e.g., "edit decompose.md:42 to add a check"). The Edges section legitimately references constraint boundaries; that is not the same as prescribing implementation.

### LEX-2 — Defense-in-depth at architecture-write time

**Question**: Does the prescriptive-prose check run twice (at research-§6 + decompose-§5)?

**Decision**: spec phase. Adversarial A-10 argues no (same agent, sequential writes, no second-actor surface); carryover #2 argues yes (catches mechanism leaks before they propagate to N tickets). Recommended: run once at decompose-§5, with pre-commit hook re-run as the second-actor defense; spec should justify or override.

### CORPORA-1 — Alternative corpus for the spec re-walk

**Question**: Which corpus pairs with `research/vertical-planning/` for the spec-phase re-walk obligation?

**Options**:
- (a) `research/repo-spring-cleaning/` — surface-anchored, 3 pieces, stresses Touch-points-heavy bodies.
- (b) `research/opus-4-7-harness-adaptation/` — policy-heavy, tests the "permissive paragraph for non-constructive topic shapes."

**Decision**: spec phase. Recommended: (a) — surface-anchored stresses the uniform-template most.

### MODULE-1 — Helper module necessity

**Question**: Does the events emission warrant a new `cortex_command/discovery.py` helper module, or is inline JSONL in SKILL prose sufficient?

**Decision**: spec phase. Recommended: helper module, gated on the `prescriptive_check_run` event's nested `flag_locations[]` payload — the other two events are simple enough for inline emission, but co-locating is cheaper than splitting.

### MIGRATION-1 — Heterogeneous backlog transition

**Question**: How does the codebase handle the transition between tickets with Value/What/Why structure (existing) and Role/Integration/Edges/Touch-points (new)?

**Decision**: spec phase. Recommended: document as accepted cost. Search-by-section-name is lossy across the heterogeneous backlog; the cost is bounded by the open-ticket count at ship time. Closed tickets are immaterial.
