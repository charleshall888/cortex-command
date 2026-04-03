# Research: harness-design-long-running-apps

## Key Finding Up Front

The article's primary innovation — context resets via fresh agent spawning and file-based state handoff — is **already correctly implemented** in cortex-command. The thin orchestrator pattern, per-round fresh spawning, and per-feature worker isolation are all present and working. This reframes the rest of the analysis: rather than asking "which patterns should we import?", the right question is "given that tests already provide objective evaluation, what actual failure modes remain?"

---

## Research Questions

1. Does the overnight runner use a planner/generator/evaluator pattern, or something simpler? Where does evaluation happen today?
   → **Planner + Generator, no evaluator. Orchestrator (planner) is a fresh agent per round that writes a batch plan and exits. Feature workers (generators) are dispatched by batch_runner.py. Evaluation is implicit: merge gate (tests pass), not a dedicated agent. Brain agent handles post-failure triage, not quality judgment.**

2. Is there a context reset mechanism during long overnight sessions, or does the agent run until context fills?
   → **Already implemented correctly — this is the strongest finding. Per-round fresh orchestrators prevent context saturation in the planner role. Per-feature fresh workers prevent cross-contamination. File-based state (overnight-state.json, events.log, spec/plan files) is the handoff medium. The thin orchestrator pattern explicitly instructs the orchestrator not to accumulate implementation details. No changes needed here.**

3. Do lifecycle specs already function as explicit pre-negotiated success criteria?
   → **Partially. Specs are pre-written success criteria with verification strategies, and the orchestrator hard-fails if a spec is missing. But specs are written by humans in the daytime — they are not negotiated between agents. There is no agent-side spec quality gate before overnight dispatch begins. The simpler fix (stricter spec template) was not explored before recommending an agent-based gate — see DR-3.**

4. Is there a mechanism for stress-testing and pruning harness components as Claude's baseline improves?
   → **No formal mechanism. Morning report auto-creates follow-up backlog items for failures. Lifecycle review phase (APPROVED/CHANGES_REQUESTED/REJECTED) exists for individual features but not for harness components. No scheduled "is this scaffolding still load-bearing?" review. A lightweight ritual is feasible but costs more than S if its output is acted on — see DR-4.**

5. Would an explicit evaluator agent catch failures the current system misses?
   → **Theoretical yes, but not demonstrated. The two proposed failure modes — (a) spec-compliant but behaviorally wrong implementations that pass tests; (b) self-evaluation bias where the feature worker marks its own work complete prematurely — are imported from the article's UI domain and have not been observed in cortex-command's overnight runner history. Before adding an evaluator, the simpler question is: could the verification strategy in plan.md be tightened to encode those compliance checks as tests rather than prose?**

6. What is the blast radius of adding evaluator separation or context resets?
   → **Context resets: no change needed — already implemented. Evaluator agent: L effort — affects runner.sh (new post-batch phase), batch_runner.py (pending_evaluation status), state.py (new FeatureStatus), new evaluator prompt, plus timeout/crash handling for a new agent phase. Pre-execution spec quality gate: M effort if agent-based; S if template-based. Component pruning ritual: S to write; M-L to execute if output is acted on.**

## Codebase Analysis

**Existing patterns:**
- Orchestration: `claude/overnight/runner.sh` — sequential round loop; spawns fresh orchestrator per round (`claude -p "$FILLED_PROMPT" --max-turns 50`)
- Feature dispatch: `claude/overnight/batch_runner.py` — async parallel dispatch via Agent SDK; manages retry budget per task
- Post-failure triage: `claude/overnight/brain.py` — spawns fresh brain agent after retry exhaustion; returns SKIP/DEFER/PAUSE verdict
- State persistence: `claude/overnight/state.py` — `OvernightState` + `OvernightFeatureStatus` dataclass; written to JSON after each round
- Spec/plan as success criteria: `lifecycle/{feature}/spec.md` + `lifecycle/{feature}/plan.md` — verification strategy section in plan.md drives post-implementation checks
- Orchestrator self-limiting: `prompts/orchestrator-round.md` line ~8 — "Thin orchestrator: You read state files and status codes only. Do NOT accumulate implementation details in your context."
- Escalation cycle-breaker: orchestrator detects repeated identical questions from a worker and promotes them to human-escalation, preventing loops

**Files/modules that would be affected by each proposed change:**

| Change | Files | Effort |
|--------|-------|--------|
| Evaluator agent (post-task) | runner.sh, batch_runner.py, state.py, new `prompts/evaluator.md`, timeout/crash handling | L |
| Stricter plan.md verification requirements | `skills/lifecycle/SKILL.md` or template in lifecycle | S |
| Agent-based spec quality gate (in /refine) | `skills/refine/SKILL.md`, spec quality rubric | M |
| Template-based spec quality gate | spec template in lifecycle | S |
| Component pruning ritual (checklist) | `skills/morning-review/SKILL.md` or new `skills/harness-review/` | S (writing) / M-L (acting on output) |

**Integration points:**
- Evaluator would plug between batch_runner completing and map_results.py running — introduces a new 3-way state dependency that is not crash-safe under the current file-based state architecture
- Spec quality gate would plug into orchestrator-round.md plan-generation step (already has a deferral path for ambiguous specs)
- Template-based improvements have no system integration — purely authoring-time changes

**Constraints:**
- File-based state is the architectural constraint — any evaluator must read/write JSON state, not pass objects in memory; a crashed evaluator mid-write leaves OvernightFeatureStatus undefined
- Each agent is ephemeral — evaluator must receive full context via prompt files, not in-memory handoff
- Overnight runner already at ~800 lines (runner.sh); a new agent phase requires timeout handling, crash recovery, and state validation — not minimal additions
- The brain agent's cycle-breaker (worker → orchestrator escalation) does not extend to evaluator loops; an evaluator that consistently rejects valid work would exhaust retry budgets and trigger brain triage for features that have no implementation problem

## Domain & Prior Art Analysis

**Anthropic article findings (source material):**

The article reports three distinct problems and their solutions:

| Problem | Solution | Status in cortex-command |
|---------|----------|--------------------------|
| Context saturation / "context anxiety" | Context resets (fresh agent + file handoff) | **Already solved** — thin orchestrator + per-round fresh spawning |
| Self-evaluation bias (generator praises own work) | Separate generator from evaluator | Theoretical gap — not observed in practice; may not apply to software delivery domain |
| Subjective criteria unmeasurable | Weighted scoring rubric + live evaluator | Not applicable — software delivery has binary test outcomes |

**Why the evaluator transfer is weaker than it appears:**

The article's evaluator solved a problem unique to generative UI work: aesthetic quality cannot be measured by automated checks. The rubric (four weighted criteria: design quality, originality, craft, functionality) was the core invention. The evaluator was the mechanism for applying it. In software delivery, tests already provide objective evaluation signal. The evaluator adds value only for spec compliance issues that tests don't encode — but the prior question is whether tightening the verification strategy in plan.md would capture those checks as tests instead, at zero runtime cost.

**Key article principle that does apply:**
> "As models improve, harness assumptions become stale. Regularly stress-test whether components remain load-bearing. Remove unnecessary scaffolding."

This is a discipline, not a feature — and cortex-command has no explicit practice for it. The morning report creates follow-up backlog items for *failures*, but not for *unnecessary complexity*.

**The sprint contract gap (real but simpler to address than it appears):**
The cortex-command flow is: human writes spec → orchestrator checks existence → worker implements → tests pass. The article's flow adds: evaluator validates spec quality before implementation. The simpler equivalent is a stricter spec template that forces humans to write measurable acceptance criteria, explicit out-of-scope, and concrete success conditions at authoring time — without any runtime agent call.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| Evaluator agent (post-task, pre-merge) | L | Cost (extra call/feature), evaluator crash corrupts state, false-negative retry cascade exhausts brain agent budget, evaluator loops with no cycle-breaker, rubric undefined | **Rubric must be defined before implementation** — this is blocking, not a detail |
| Stronger plan.md verification requirements | S | Spec authors may not write tests for compliance cases | None |
| Agent-based spec quality gate (in /refine) | M | Over-deferral if too strict; skippable if /refine is bypassed | Spec quality rubric |
| Template-based spec quality gate | S | Humans may not fill in required sections | None |
| Component pruning ritual (checklist) | S to write the ritual | Risk of false positives on coupled state architecture; M-L to execute on any pruning decision | Pruning rubric (what makes a component "no longer load-bearing"?) |
| Context resets / handoff improvements | None needed | — | Already implemented correctly |

## Decision Records

### DR-1: Should an evaluator agent be added to the overnight runner?
- **Context:** Feature workers self-evaluate their work via the plan verification strategy. The article found this causes self-evaluation bias in UI work. Whether this manifests in software delivery is unverified — no overnight runner failure has been identified where a worker incorrectly self-certified completion while tests passed.
- **Prerequisite (blocking):** The evaluator rubric must be defined before implementation is estimated. Without a rubric, the evaluator cannot function and cannot be prototyped. The rubric is the invention; the agent is just the mechanism. Until the rubric can be specified, this recommendation should not advance to implementation.
- **Options considered:**
  - No evaluator (current): binary merge gate (tests pass/fail); brain agent for triage only
  - Stronger plan.md verification requirements: require verification strategies to encode compliance checks as runnable tests, not prose — closes the "tests don't capture spec compliance" gap at zero runtime cost
  - Post-task evaluator agent: fresh agent reads spec.md + diff + test output; verdict = accept / retry / escalate — requires rubric, state.py changes, crash handling, cycle-breaker for evaluator loops
  - Mid-task evaluator: more granular but much higher cost and complexity
- **Recommendation:** Before prototyping the evaluator, investigate whether tightening plan.md verification strategy requirements (option 2) closes the spec compliance gap. The evaluator addresses a problem not yet observed in practice, in a domain where tests already provide strong objective signal. If observed failures accumulate that tests miss, the rubric definition question becomes tractable and the evaluator becomes worth the complexity.
- **Trade-offs:** Evaluator adds latency, cost, and new failure modes to a system running unattended overnight. Verification strategy improvements require no runtime changes and improve specs permanently.

### DR-2: Should context resets or handoff mechanisms be changed?
- **Context:** The article identifies context resets as the key improvement over compaction.
- **Recommendation:** No change. Cortex-command already implements the correct pattern: thin orchestrator per round, fresh workers per feature, file-based handoffs.
- **Trade-offs:** None — this is the strongest finding of this research.

### DR-3: Where should the spec quality gate live — /refine or template?
- **Context:** The orchestrator defers features with ambiguous specs at runtime (overnight), wasting a round. Pre-flight spec validation would catch this earlier.
- **Options considered:**
  - Stricter spec template: required sections (acceptance criteria, explicit out-of-scope, measurable success conditions) in the lifecycle spec template eliminate ambiguity at authoring time with zero runtime cost
  - Add spec quality check to /refine skill (daytime, before overnight planning): agent validates spec quality before overnight; skippable if /refine is bypassed, making it only as reliable as human compliance with the workflow
  - Add spec quality check inside orchestrator-round.md (runtime, per-round): catches issues at overnight time, wastes a round
- **Recommendation:** Start with a stricter spec template. It is more robust than a skippable /refine gate — the template is present every time a spec is written, not only when /refine is used. The /refine gate can be added as a second-pass check if template-based improvements prove insufficient.
- **Trade-offs:** Template improvement requires updating the spec template and any existing specs that don't conform. The /refine gate adds an agent call but catches ambiguity the template didn't prevent.

### DR-4: Should component pruning be formalized?
- **Context:** The article explicitly recommends regular "stress-test whether components are still load-bearing" as models improve. Cortex-command has no practice for this.
- **Cost note:** Writing the ritual is S effort. Acting on its output is not. Removing a component from an 800-line shell orchestrator with coupled JSON state flow between runner.sh, batch_runner.py, brain.py, state.py, and orchestrator-round.md is M-L effort and carries non-trivial recovery cost if the pruning judgment is wrong. The ritual's risk is not "None" — it is bounded by how often it produces actionable output and how reliable the pruning rubric is.
- **Recommendation:** Add a pruning checklist to the morning-review skill or as a lightweight standalone. The checklist should surface candidates for human review, not auto-create backlog tickets. Human judgment is required before a pruning candidate advances. The checklist question "Given current Claude baseline, would we build this component the same way today?" requires a rubric for what "load-bearing" means — this should be part of the checklist definition, not deferred.
- **Trade-offs:** Low effort to write; requires the pruning rubric to be defined as part of writing it, not after.

## Open Questions

- If the evaluator is pursued: what is the rubric? Software evaluation is mostly binary (tests) — what are the specific spec compliance scenarios tests cannot encode that would justify an L-effort agent addition?
- For the pruning checklist: what makes a component "no longer load-bearing"? (e.g., "this component compensated for model limitation X — if the model no longer needs compensation, remove it") — the rubric should be captured in the checklist definition.
- If /refine adds a spec quality gate as a second pass: what makes a spec "good enough"? lifecycle.config.md has review criteria — can those be reused or adapted?
- Should the component pruning ritual trigger on a calendar schedule or from morning report data? (Note: data-driven trigger requires morning report data to surface pruning signals — separate implementation work.)
