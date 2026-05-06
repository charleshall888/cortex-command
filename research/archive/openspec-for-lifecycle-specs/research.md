# Research: openSpec for Lifecycle Specs

## Research Questions

1. **What is openSpec — what problem does it solve, who created it, what's its current status?**
   → OpenSpec is an open-source (MIT) framework for Spec-Driven Development by Fission AI (@0xTab). GitHub: github.com/Fission-AI/OpenSpec (~38K stars). npm: `@fission-ai/openspec` v1.2.0. Created August 2025, it adds a lightweight specification layer between humans and AI coding assistants so both sides agree on what to build before code is written. Supports 25+ AI tools (Claude Code, Cursor, Windsurf, Copilot, etc.).

2. **What structural patterns does openSpec use for specifications?**
   → Two-area architecture: `openspec/specs/` (persistent behavioral baseline organized by domain) and `openspec/changes/` (self-contained modification folders). Each change contains four artifacts with explicit dependencies: proposal (why) → specs/delta (what) → design (how) → tasks (steps). Specs use RFC 2119 keywords (SHALL/MUST/SHOULD/MAY) and Given/When/Then scenarios. Changes use delta sections (ADDED/MODIFIED/REMOVED/RENAMED) rather than rewriting full specs. Custom YAML schemas define artifact workflows.

3. **How does openSpec address readability for someone with zero prior context?**
   → Structured markdown with consistent heading patterns (`### Requirement:`, `#### Scenario:`). Behavioral contracts describe observable behavior, not implementation. Project config injection (`openspec/config.yaml`) pipes context and rules into AI prompts via XML tags. The persistent `specs/` layer means an AI can read the current system behavior baseline without investigating the codebase. However, openSpec does not specifically optimize for the "zero prior context overnight handoff" problem — its scenarios are less rigorous than our binary-checkable acceptance criteria.

4. **What elements could directly improve our spec template for overnight agent handoff?**
   → See Decision Records below. The strongest candidates are: persistent behavioral baseline (with an enforcement mechanism for updates) and structured CLI validation. Less applicable: proposal/spec/design three-way split (we already have research→spec→plan), custom YAML schemas (over-engineering for our scale). The post-implementation verify step — initially identified as a gap — is already covered by our review phase's Stage 1 spec compliance check.

5. **Does openSpec include tooling for validation, linting, or machine-actionability?**
   → Yes. `openspec validate` checks structural compliance: heading levels, scenario format, dependency graph integrity, circular dependency detection. Supports `--strict`, `--json`, `--all` flags. The CLI also provides `openspec status` (artifact progress), `openspec view` (interactive terminal dashboard), and `openspec archive` (merge deltas into source of truth). Ecosystem tools include spec-gen (reverse-engineer codebase into specs) and openspec-viewer (browser-based viewer).

6. **What are the trade-offs of openSpec's approach vs. our current lightweight markdown format?**
   → OpenSpec is more flexible and tool-agnostic but less rigorous on acceptance criteria quality. Its "fluid not rigid" philosophy (no phase gates, work on what makes sense) conflicts with our orchestrator review gates, which exist because overnight agents need high-quality handoffs — though it's worth noting that 78% of our orchestrator reviews pass on first check, raising a question about whether all gates are earning their cost. OpenSpec's delta specs are powerful for brownfield maintenance but add structural overhead. Our process has stronger enforcement (binary-checkable criteria, S1-S5 review gates, NDJSON audit trails) but lacks openSpec's persistent behavioral baseline and standalone validation tooling.

## Codebase Analysis

### Current Spec Process

Our spec lifecycle is managed by three key components:

- **Refine skill** (`skills/refine/SKILL.md`): Orchestrates Clarify → Research → Spec pipeline. Classifies complexity (simple/complex) and criticality (low/medium/high/critical). Includes research sufficiency checks and confidence re-evaluation loops.

- **Specify reference** (`skills/lifecycle/references/specify.md`): Defines the spec template with required sections: Problem Statement, Requirements (with binary-checkable acceptance criteria in three formats), Non-Requirements, Edge Cases, Technical Constraints, Open Decisions. Includes pre-write verification checks and research cross-checks.

- **Orchestrator review** (`skills/lifecycle/references/orchestrator-review.md`): Five quality gates for specs: S1 (binary-checkable criteria), S2 (edge cases), S3 (MoSCoW classification), S4 (explicit non-requirements), S5 (grounded technical constraints). Max 2 review cycles before user escalation.

- **Review phase** (`skills/lifecycle/references/review.md`): Two-stage post-implementation review. Stage 1 ("Spec Compliance") performs per-requirement tracing — reads source files, checks acceptance criteria, rates each requirement PASS/FAIL/PARTIAL. Stage 2 covers code quality. Also includes requirements drift detection against `requirements/` docs.

### Current Spec Template Structure

```markdown
# Specification: {feature}

## Problem Statement
## Requirements
  - Each with binary-checkable acceptance criteria:
    (a) command + observable output + pass/fail
    (b) observable state with file/pattern
    (c) "Interactive/session-dependent: [rationale]"
## Non-Requirements
## Edge Cases
## Technical Constraints
## Open Decisions
```

### Strengths of Current Process

1. **Binary-checkable criteria** — Three explicit formats prevent prose-only verification. Enforced by orchestrator review S1. *Recency note*: This three-format system was introduced April 3, 2026 (ticket #019), replacing a looser "objectively evaluable" standard that allowed prose criteria to pass. The tightening was a direct response to documented failures where overnight workers self-attested success against un-checkable criteria. The system is sound in design but has minimal post-tightening track record.
2. **Orchestrator review quality gates** — Content-level review, not just structural validation. Data point: across ~46 features, 78% of orchestrator reviews pass on first check — either evidence of well-calibrated gates or of gates that are largely ceremony. The 22% flag rate is dominated by S3 (MoSCoW classification), not S1 (criteria quality).
3. **Post-implementation spec compliance** — The review phase's Stage 1 performs per-requirement tracing with PASS/FAIL/PARTIAL verdicts against acceptance criteria. This is functionally equivalent to openSpec's `/opsx:verify` step.
4. **Research cross-check** — The specify reference instructs that every behavioral claim in research must appear in spec. *Enforcement note*: This is a prompt instruction in `specify.md` §2b, not a verified behavior — there is no event logged for its completion, no orchestrator review item validating it was performed. It represents design intent, not a guaranteed enforcement mechanism.
5. **Events log** — Full NDJSON audit trail of every phase transition, review, and dispatch.
6. **Complexity/criticality classification** — Determines review depth and model selection. Note: the skip rule (simple+low skips orchestrator review) applies to very few features in practice (~4 of 46), and medium criticality is the default, meaning most features receive full review regardless of actual complexity.

### Differences from openSpec Worth Investigating

1. **No persistent behavioral baseline** — Each feature's spec is self-contained and ephemeral. After implementation, the spec lives in `lifecycle/{feature}/spec.md` but isn't merged into a living system description. Overnight agents must research existing behavior from scratch each time.
2. **No standalone structural validation** — Orchestrator review catches issues but runs inline during the phase, not as a separate pre-flight check.
3. **No delta/change tracking against baseline** — We describe what to build, not what changes about the existing system.

## Web & Documentation Research

### openSpec Core Concepts

**Two-Area Model:**
- `openspec/specs/` — Persistent, domain-organized behavioral contracts ("source of truth")
- `openspec/changes/` — Self-contained modification folders per feature/fix

**Artifact Dependency Chain:**
```
proposal (why) → specs/delta (what) → design (how) → tasks (steps) → implementation (code)
```
Dependencies are "enablers, not gates" — any artifact can be updated at any time.

**Delta Spec System:**
| Section | Meaning | On Archive |
|---------|---------|------------|
| `## ADDED Requirements` | New behavior | Appended to main spec |
| `## MODIFIED Requirements` | Changed behavior | Replaces existing |
| `## REMOVED Requirements` | Deprecated behavior | Deleted from main |
| `## RENAMED Requirements` | Name changes | FROM:/TO: |

**Progressive Rigor:**
- Lite spec (default) — short behavioral requirements, clear scope
- Full spec (higher risk) — cross-team changes, API/contract, security

**Spec Format:**
```markdown
### Requirement: User Authentication
The system SHALL issue a JWT token upon successful login.

#### Scenario: Valid credentials
- GIVEN a user with valid credentials
- WHEN the user submits login form
- THEN a JWT token is returned
```

**Custom Schemas (YAML):**
```yaml
name: my-workflow
version: 1
artifacts:
  - id: proposal
    generates: proposal.md
    requires: []
  - id: tasks
    generates: tasks.md
    requires: [proposal]
```

### openSpec Tooling

| Tool | Purpose |
|------|---------|
| `openspec validate` | Structural compliance (headings, scenarios, dependencies) |
| `openspec archive` | Merge deltas into source of truth, move to archive |
| `openspec status` | Artifact progress tracking |
| `openspec view` | Interactive terminal dashboard |
| `/opsx:verify` | Post-implementation check: completeness, correctness, coherence |
| spec-gen | Reverse-engineer codebase into OpenSpec format |

### Ecosystem Scale

- 25+ tool integrations (Claude Code, Cursor, Windsurf, Copilot, etc.)
- Companion tools: spec-gen (77 stars), openspec-viewer, openspec-flow, openspec-ae
- Active Discord community

## Domain & Prior Art

### Comparison: openSpec vs. Cortex Command Lifecycle

| Dimension | openSpec | Cortex Command |
|-----------|---------|----------------|
| **Philosophy** | Fluid, iterative, no phase gates | Structured phases with orchestrator review gates (78% first-pass rate) |
| **Spec persistence** | Persistent behavioral baseline + deltas | Ephemeral per-feature specs |
| **Acceptance criteria** | RFC 2119 + Given/When/Then scenarios | Binary-checkable in three explicit formats (introduced April 3, 2026) |
| **Validation** | CLI structural validation | Inline orchestrator review (content-level) |
| **Artifact organization** | Two areas (specs/ + changes/) | Single directory per feature (lifecycle/{slug}/) |
| **Why/What/How split** | proposal / spec / design (explicit) | research / spec / plan (similar but different naming) |
| **Post-implementation** | `/opsx:verify` checks against specs | Review Stage 1: per-requirement PASS/FAIL/PARTIAL tracing (equivalent) |
| **Tool scope** | Tool-agnostic (25+ integrations) | Claude Code-specific (can be more opinionated) |
| **Audit trail** | Archive directory with change history | NDJSON events.log per feature |
| **Workflow customization** | YAML schemas | Skill reference files (markdown) |
| **Process weight** | Fluid — any artifact updatable anytime, progressive lite/full | Structured — one-way complexity escalation, medium criticality default |

### What openSpec Gets Right for Our Use Case

1. **Persistent behavioral baseline** — An overnight agent researching "what does the system currently do?" could read `specs/` instead of exploring the codebase from scratch. This is especially valuable for brownfield changes. Critically, openSpec makes this work through its archive workflow — when a change completes, deltas are automatically merged into the baseline. The enforcement mechanism is what makes baselines "living."

2. **Delta-based change tracking** — Explicitly stating what's ADDED, MODIFIED, and REMOVED about system behavior makes specs more precise and reviewable than "here's what we're building."

3. **Standalone validation** — Running structural checks as a pre-flight before the full orchestrator review reduces wasted review cycles.

4. **Fluid process weight** — OpenSpec's approach where dependencies are "enablers, not gates" may be worth studying for a personal tooling project where the stated philosophy is "Complexity must earn its place." Our one-way complexity ratchet (escalation but never de-escalation) and uniform-by-default review path may add more ceremony than the corrective yield justifies.

### What We Already Do Well

1. **Binary-checkable acceptance criteria** — Our three-format system (command/observable-state/interactive-annotation) is more rigorous than RFC 2119 + Given/When/Then for overnight handoff, where an agent must mechanically verify criteria without interpretation. This advantage is real in design but recent in implementation — the system was tightened four days ago in response to documented self-attestation failures.

2. **Post-implementation spec compliance** — Our review phase Stage 1 already performs per-requirement tracing with PASS/FAIL/PARTIAL verdicts. This is functionally equivalent to openSpec's `/opsx:verify` — we do not have this gap.

3. **Overnight handoff optimization** — Our specs are explicitly designed for the "zero prior context agent" problem. openSpec optimizes for human-AI collaboration, not full handoff. Note: this advantage applies only to features that receive orchestrator review (the vast majority, but not simple+low tier features).

4. **Research cross-check** — The specify reference instructs cross-checking behavioral claims between research and spec. This is a design-level advantage (openSpec has no equivalent intent), though it currently operates as an unverified prompt instruction rather than an enforced mechanism.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A: Adopt persistent behavioral baseline (`specs/` directory) | L | Maintenance burden — baselines drift if not updated after each feature. Correctness problem from day one, not a scaling problem. Stale baselines are worse than no baselines. | Define enforcement mechanism (lifecycle hook, review-phase gate, or automated merge). Define which project areas warrant persistent specs. Bootstrap initial specs from existing lifecycle artifacts. |
| B: Add spec structural validation recipe (`just validate-spec`) | S | Low risk — additive, doesn't change existing process | Define validation rules (heading structure, criteria format) |
| C: Add delta sections to spec template | M | Complexity increase for small features with no existing baseline. Only valuable if persistent specs exist (depends on A). | Approach A must be in place first |
| D: Add progressive rigor (lite/full spec) | S | Risk of under-specifying. Our simple/complex tier already partially addresses this, though the skip rule rarely fires in practice. | Evaluate whether medium-criticality default is appropriate. May be redundant if default is recalibrated. |

## Decision Records

### DR-1: Persistent Behavioral Baseline

- **Context**: openSpec's strongest pattern is maintaining `specs/` as a living behavioral contract. Our overnight agents currently research existing behavior from scratch for each feature, which is slow and error-prone.
- **Options considered**: (A) Full openSpec-style specs/ directory per domain with automated delta merging, (B) Lightweight "system context" docs per area in requirements/, (C) Status quo — agents research each time
- **Recommendation**: The concept is valuable but the enforcement mechanism is the make-or-break design question. openSpec solves this with its archive workflow (deltas auto-merge into baseline on completion). Without an equivalent — a lifecycle hook that updates behavioral docs when a feature completes, or a review-phase gate that flags missing baseline updates — behavioral docs will drift. Stale docs are actively harmful: an overnight agent reading a behavioral baseline that is wrong about system state will make decisions grounded in false premises, which is strictly worse than researching from scratch against actual code. **Do not adopt behavioral baselines without first designing the enforcement mechanism.** The project's own architecture demonstrates this principle — orchestrator review gates, commit hooks, and lifecycle state machines all exist because unstructured discipline doesn't work.
- **Trade-offs**: Option A is more viable than B because it includes the enforcement mechanism (delta merging), but has higher setup cost. Option B risks mixing aspirational requirements with factual behavioral descriptions in the same files. Option C is safe but leaves the "research from scratch" inefficiency in place.

### DR-2: Spec Structural Validation

- **Context**: Our orchestrator review catches structural issues but runs inline, wasting review cycles on format problems. openSpec's `validate` command catches these pre-flight.
- **Options considered**: (A) Python validation script as `just validate-spec`, (B) Add structural pre-check to orchestrator review S1 gate, (C) Status quo
- **Recommendation**: Option A — standalone `just validate-spec` recipe. Can run before orchestrator review and in CI. Low effort, immediate value.
- **Trade-offs**: Another tool to maintain. But the rules are simple (heading structure, criteria format, required sections) and unlikely to change frequently.

### DR-3: Delta Spec Sections

- **Context**: openSpec's ADDED/MODIFIED/REMOVED sections make behavioral changes explicit. Currently our specs describe what to build but not what changes about existing behavior.
- **Options considered**: (A) Add delta sections to spec template, (B) Add "Changes to Existing Behavior" section, (C) Status quo
- **Recommendation**: Option B — add a "Changes to Existing Behavior" section that lists what existing behavior is modified or removed. Required for all features that change system behavior, including new additions (a new skill changes the behavioral surface of the skills domain). The greenfield/brownfield distinction is a false boundary — all implemented features change system behavior.
- **Trade-offs**: Less structured than openSpec deltas. No automated merge-on-archive. But fits our lightweight approach. Only becomes fully useful if a persistent behavioral baseline exists (depends on DR-1's enforcement mechanism being solved first).

### DR-4: Progressive Rigor Calibration

- **Context**: openSpec distinguishes lite spec (default) vs. full spec (higher risk). We already have simple/complex tiers and low-to-critical criticality levels.
- **Options considered**: (A) Adopt openSpec's lite/full distinction, (B) Recalibrate existing tiers, (C) Status quo
- **Recommendation**: Option C for now — our existing tier system provides progressive rigor in theory. However, the current calibration deserves scrutiny: medium criticality is the default, the skip rule (simple+low) fires for only ~4 of 46 features, and complexity only escalates (never de-escalates). This means nearly every feature receives the same full review path regardless of actual risk. For a personal tooling project whose requirements state "Complexity must earn its place" and "the system exists to make shipping faster, not to be a project in itself," the default calibration may be inverted — low criticality with opt-in escalation might align better.
- **Trade-offs**: Recalibration risks under-specifying if the default is set too low. The 78% first-pass rate on orchestrator reviews could indicate either well-calibrated gates or redundant ceremony — this data point alone doesn't resolve which interpretation is correct.

## Open Questions

- What enforcement mechanism keeps behavioral baselines current after feature completion? (Lifecycle complete-phase hook? Review-phase gate? Automated delta merge?) This must be answered before adopting DR-1.
- What validation rules should `just validate-spec` enforce beyond heading structure and criteria format?
- Is the 78% orchestrator review first-pass rate evidence of well-calibrated gates or redundant ceremony? What would a controlled experiment look like (e.g., skip review for simple+medium features for a sprint and measure outcomes)?
