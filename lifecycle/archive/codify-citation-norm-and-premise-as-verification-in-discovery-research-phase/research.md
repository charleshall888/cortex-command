# Research: Codify citation norm and premise-as-verification in /discovery research phase

## Epic Reference

Scoped from epic `research/audit-and-improve-discovery-skill-rigor/research.md`, DR-1(c) Work Item #1 (Approach A). The epic diagnosed #092's projected-locator failure mode and chose synthesis-time rule edits (A+C) over post-hoc checklist enforcement (B, rejected on empirical H3 evidence) and mechanical grounding probes (F, deferred). This ticket is the A-half; #139 is the C-half. See epic `research.md:37-42, 71, 117-121` for the load-bearing decisions that bound this ticket's scope.

## Clarified Intent

Codify a citation-or-`premise-unverified` rule for codebase-pointing claims in `skills/discovery/references/research.md` §2 Codebase Analysis; require empty-corpus searches reported as a distinct outcome; retarget the Feasibility Prerequisites column (§5 + template at lines 104-107) so codebase-state verification is research-phase work, not deferred-to-implementation sequencing.

## Codebase Analysis

### Current state of the target file

- `skills/discovery/references/research.md:35-42` (§2 Codebase Analysis) — procedural scope instruction only: "Launch a focused codebase exploration to investigate: existing patterns, files affected, dependencies, constraints." No content rule on findings; no citation requirement; no empty-corpus reporting requirement.
- `skills/discovery/references/research.md:66-73` (§5 Feasibility Assessment) — lists four dimensions per approach: risks, unknowns, "dependencies or prerequisites must be in place", effort. No distinction between premise-verification prerequisites and implementation-sequencing prerequisites.
- `skills/discovery/references/research.md:104-107` (§6 template example) — `| Approach | Effort | Risks | Prerequisites |`; Prerequisites is free-form text; no content-type constraint.
- `skills/discovery/references/research.md:134-138` (Constraints table at file bottom) — existing convention-slot for imperative rules: "Read-only", "All findings in the artifact", "Scope: research the topic as described, not adjacent topics". This is the established structural location for artifact-level rules in this file.
- `skills/discovery/references/research.md:83` — precedent for marking null answers in the Research-Questions template: `[Question] → **[Answer or "Unresolved: reason"]**`. The `Unresolved: reason` pattern is a prior art for flagging negative outcomes in research artifacts.

### Existing marker-convention survey

- `NOT_FOUND`: zero occurrences in `skills/**/*.md` (grep).
- `premise-unverified`: zero occurrences in `skills/**/*.md` (grep).
- `unverified` in adversarial-review contexts: `lifecycle/archive/add-subagent-output-formats-compress-synthesis/research.md:246`, `lifecycle/archive/build-setup-merge-local-skill/research.md:205` — both use "unverified" to flag assumptions that could not be checked, but in lifecycle research artifacts, not skill-protocol prose.
- Closest precedent: `lifecycle/references/research.md:125-138` Dependency Verification section has "Capabilities unverified: [Any capabilities the feature needs that could not be confirmed through research]" — the only existing structured slot for "we tried and couldn't confirm."
- No conflicting marker semantics exist; `premise-unverified` is a new coinage without collision risk.

### Sibling-skill authoring-rule patterns

- **Post-hoc checklist rules** (`skills/discovery/references/orchestrator-review.md:109-115`) — tabular, prose Criteria, human-judgment verdicts. R2 at line 112 says "Feasibility grounded in evidence | Feasibility assessment cites specific codebase patterns" but does not verify that citations are actually grounded — this is exactly the R2 that passed for #092 despite a projected locator.
- **Procedural imperative guards** (`skills/lifecycle/references/implement.md:17, 39-41`) — `git status --porcelain`-style conditions with mandatory dispositions. Code-level tests, not prose judgment.
- **Constraints table at file bottom** (`skills/discovery/references/research.md:134-138`) — existing convention for imperative content rules in this exact file. The established slot.

#138's proposed rule would be the first content requirement embedded at the artifact-writing surface itself in `skills/discovery/references/*.md` — existing rules either use post-hoc checklists (orchestrator-review) or procedural guards (implement.md). The Constraints table at the bottom is the nearest structural analogue.

### #139 consumer surface (read-only survey)

- `skills/discovery/references/decompose.md:23` — current Value-field instruction: "What problem this solves and why it's worth the effort. One sentence. If the value case is weak relative to size, say so — this is the moment to flag it before tickets are created."
- `skills/discovery/references/decompose.md:29` — user-approval gate: "Present the proposed work items to the user for review before creating tickets."
- Neither line currently references research.md artifacts or reads any marker from them. #139 will need to add that reading logic; #138 produces the signal but does not wire decompose to consume it.

### Out-of-scope surfaces (verified)

- `skills/discovery/references/orchestrator-review.md` R1-R5 (lines 111-115) — explicitly out of scope per `backlog/138:46` ("The orchestrator-review checklist can be left unchanged — the rule is enforced at the synthesis-writing surface, not post-hoc").
- `skills/research/SKILL.md`, codebase-agent contract — NOT_FOUND for required changes (empty-corpus reporting is enforceable synthesis-side; the synthesis author knows what searches were dispatched and can report results without a contract change).
- No tests or fixtures reference the current §2/§5 structure (grep NOT_FOUND).

## Web Research

### Per-claim marker conventions (external prior art)

- **Wikipedia `{{citation needed}}` family** — inline per-claim placement; `reason=` optional parameter; distinct templates for distinct epistemic states (`{{Citation needed}}`, `{{Dubious}}`, `{{Verify source}}`). Source: https://en.wikipedia.org/wiki/Template:Citation_needed
- **Anthropic Citations API** — per-claim structured citations with explicit character/page/block indices; `cited_text` attached to each text block. https://platform.claude.com/docs/en/build-with-claude/citations
- **RFC 2119 uppercase-keyword convention** — reserves ALL-CAPS tokens for machine-parseable/normative meaning in prose documents. Supports `NOT_FOUND` / `PREMISE-UNVERIFIED` style. https://datatracker.ietf.org/doc/html/rfc2119
- **ContextCite (MIT CSAIL)** — per-claim provenance (claim-by-claim verification rather than document-level). https://news.mit.edu/2024/citation-tool-contextcite-new-approach-trustworthy-ai-generated-content-1209

Convergent external evidence favors inline per-claim markers over section-level or row-status markers when preventing unchallenged drift-by-inference is the goal. Per-claim granularity is the dominant pattern across three independent sources.

### Empty-result reporting conventions

- **PRISMA-S (systematic review literature search extension)** — requires documenting search strategy (databases queried, exact query strings, scope) *separately from* findings; "searched X, found 0" must be structurally distinguishable from "didn't search X." Full reproducibility is the design goal; incomplete reporting is treated as bias risk. https://www.equator-network.org/reporting-guidelines/prisma-s/
- **Null-result scientific reporting** — distinguishes "inconclusive" (underpowered) from "evidence for null" (powered search, found nothing). A bare `NOT_FOUND` without scope is the "inconclusive" failure mode.
- **Daniel Tunkelang on null search results** — causes of null results matter (bad query, missing inventory, failed retrieval strategy); a system that conflates them degrades trust. https://dtunkelang.medium.com/making-sense-of-null-and-low-results-a077f37bf8fc

Convergent recommendation: a negative-result marker must carry `(query, scope)` to be auditable. A bare `premise-unverified` value collapses distinct states.

### Verification-vs-sequencing prerequisites patterns

- **ADR "Open Questions" sections** — an ADR may be accepted with open questions only if resolution is not a short-term priority; structurally distinguishes "unresolved-but-acceptable" (sequencing) from "must-resolve-before-commit" (verification). https://ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html
- **MADR "More Information" / assumptions section** — explicit slot for unverified premises in ADR tradition. https://adr.github.io/madr/decisions/adr-template.html
- **Microsoft Engineering Feasibility Spike** — spikes are *prerequisite investigation* occurring before engineering sprints; output is information, not code. Exactly maps to "verification is research-phase work, not deferred-to-implementation." https://microsoft.github.io/code-with-engineering-playbook/design/design-reviews/recipes/engineering-feasibility-spikes/

### Synthesis-time vs. post-hoc grounding enforcement

Convergent external evidence places primary enforcement at synthesis-time with post-hoc as defense-in-depth:

- Azure/Microsoft 3-layer architecture (input governance + evidence-grounded generation + post-response verification) — treats them as complementary, post-hoc-only explicitly insufficient. https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/best-practices-for-mitigating-hallucinations-in-large-language-models-llms/4403129
- SAVeR (arxiv 2604.08401) — "Verify Before You Commit"; verification before belief commits to action.
- Chain-of-Thought Is Not Explainability (Oxford AIGI) — post-hoc reasoning traces often don't reflect what drove the answer; post-hoc review is structurally limited.
- AgentForge / ADORE — multi-agent validation gates placed at synthesizer checkpoints.
- Citation-Grounded Code Comprehension (arxiv 2512.12117) — advocates mechanically-checked citations validated at generation time against the code.

Validates the epic's synthesis-time choice but not unconditionally: every source treats synthesis-time as primary *with post-hoc as defense-in-depth*, not synthesis-only.

### Search-negative results (NOT_FOUND)

- Query `"not searched" vs "not found" distinction search results machine readable` — no protocol-level prior art; only UX copy about empty SERPs. Closest analogues are academic (PRISMA-S), not machine-readable retrieval specs.
- Query `"assumed" vs "verified" status column feasibility risk register engineering` — no direct prior art; closest is ADR Open-Questions and MADR Assumptions sections.
- Query `inline tag per-claim vs section-level attribution tradeoff documentation` — no direct tradeoff discussion; inference from comparing Wikipedia (per-claim-inline) vs. MADR (section-level).

## Requirements & Constraints

### Files scanned in `requirements/`

`remote-access.md`, `pipeline.md`, `project.md`, `multi-agent.md`, `observability.md`.

### Directly governing requirements

- `requirements/project.md:17` (tangential governing principle): "Daytime work quality: Research before asking. Don't fill unknowns with assumptions — jumping to solutions before understanding the problem produces wasted work." Principle-level support for this ticket.
- `requirements/project.md:25-26` (architectural constraint): file-based state; research artifacts are plain markdown with no database/schema validator. Any rule must be enforced by author discipline or grep-based checks, not by a schema runtime.

### Architectural constraints

- **File-based state** (`requirements/project.md:25-26`): no database/schema validator exists to enforce the marker format. Enforcement is author-side + grep-side.
- **Output-floors convention** (`~/.claude/reference/output-floors.md:54-55`): orchestrator rationale field convention when resolving escalations. Structural analogue for how rationales are surfaced in events, not directly governing this ticket but informs writing style for rule-block prose.
- **Symlink architecture** (CLAUDE.md): `skills/discovery/references/research.md` is symlinked from `~/.claude/skills/...` — the repo copy is the source of truth; no deployment step needed beyond editing the repo file.

### Scope boundaries

- **Research-artifact scope only** (`skills/discovery/references/research.md:136-139` `## Constraints`): "Read-only: Do not modify project files except the research artifact. Scope: Research the topic as described, not adjacent topics." The citation rule targets research artifacts produced by /discovery, not other artifacts.
- **Orchestrator-review is out of scope** (`backlog/138:46`): the rule is enforced synthesis-side, not post-hoc.

### NOT_FOUND (requirements-level)

- `NOT_FOUND(query="empty-corpus OR citation governance in requirements/", scope="requirements/**/*.md")`: no requirements doc governs research-artifact content rules or verification-vs-sequencing distinctions. Governance is principle-level only.
- `NOT_FOUND(query="/discovery skill-authoring convention", scope="requirements/**/*.md")`: no requirements doc governs /discovery skill internals specifically.

## Tradeoffs & Alternatives

Four design questions; for each, candidate options and a conditional recommendation. Selection deferred to spec where contradictions are resolved.

### DQ1: Marker surface — prose-inline vs. table-row vs. both

- **A1a (inline per-claim, prose)**: `[file:line]` citations and `[premise-unverified: query=X, scope=Y, result=empty|not-searched]` inline in §2 Codebase Analysis bullets and Research-Questions answers. Covers the surface where #092's failure actually sat (prose, not table). Enforceability: grep-based (regex for `\[premise-unverified:`). Drift risk: higher than table-row — author must remember per claim.
- **A1b (section-level marker)**: dedicated `### Premise Verification` subsection. Loses which claim is unverified.
- **A1c (Feasibility-row status column)**: new column in `### 5. Feasibility Assessment` table with values `verified | premise-unverified | pending`. Mechanically parseable. **Does NOT cover prose surface.**
- **A1d (YAML frontmatter)**: new convention inconsistent with existing research artifacts.

External prior art (Agent 2) and adversarial analysis (Agent 5 FM1, DW1, DW3) both favor A1a. Agent 4's A1c recommendation optimizes for mechanical enforceability at the cost of covering the primary failure surface. See Open Questions.

### DQ2: Empty-corpus reporting format

- **A2a-bare (`premise-unverified` as single value)**: conflates "not-searched" (block artifact) with "empty-corpus" (legitimate finding). PRISMA-S literature calls this the inconclusive-vs-evidence-for-null bias (Agent 2). Adversarial FM3.
- **A2b-split (`NOT_FOUND: query=X, scope=Y, result=empty` vs. `premise-unverified: not-searched`)**: two distinct values, both structured with query+scope. Aligns with PRISMA-S. Supports #139's gating logic (external endorsement + evidence-for-null is different posture from external endorsement + unchecked).
- **A2c-folded-into-A1c**: no separate empty-corpus field; Feasibility row-status IS the report. Agent 4's choice. Fails for the prose surface where most claims live (Agent 5 FM3, FM4).

External evidence + adversarial review both favor A2b over A2a or A2c. See Open Questions.

### DQ3: Prerequisites-column retargeting

Ticket language (`backlog/138:45`) says "retargeted" — retain the column with revised semantics. Four options against this scope:

- **A3a (binary tag `[verification]` / `[sequencing]`)**: each row carries a tag. Preserves column; enforces semantic split at the row level.
- **A3b (split into two columns)**: "Premise verification (research-phase)" + "Implementation dependencies (sequencing)". Wider table; structural split. Adversarial FM7 notes terminal-wrap concern on existing wide tables.
- **A3c (absorb into §2, sequencing-only in §5)**: Agent 4's recommendation. Removes codebase-state prerequisites from §5 entirely. **Adversarial DW2 flags this as out-of-scope creep**: the ticket says "retarget," not "remove." A3c is a bigger protocol shift than authorized.
- **A3d (rule-level instruction, column unchanged)**: new instruction in §2 saying "Prerequisites describing codebase state must be resolved during §2 and their findings moved there — the §5 row then carries a resolution marker." Retains column structure; enforces via prose rule.

A3a or A3d appear scope-consistent. A3c likely out-of-scope for this ticket. See Open Questions.

### DQ4: Rule encoding style

- **A4a (`### Research Rules` MUST block under §2)**: Agent 4's choice. Visible, mechanically checkable. Adversarial DW5 flags this as a novel structural convention not used elsewhere in `skills/*/references/*.md`.
- **A4b (extend existing `## Constraints` table at research.md:134-138)**: the established convention-slot for imperative rules in this file. Adversarial M5.
- **A4c (weave into §2 narrative)**: rules in prose; aligns with how §1-§5 are written. Visibility moderate; less mechanically checkable.
- **A4d (template-field annotation in §6)**: rules in the template example; easy to miss.

A4b (Constraints table extension) is the honest structural fit per sibling-skill conventions. A4a introduces novelty that would need precedent-setting justification. See Open Questions.

### Integrated option sketches (spec-phase selection)

- **Option Conservative (A1a + A2b + A3d + A4b)**: inline per-claim markers, split empty-corpus, rule-level prerequisite instruction, rules in existing Constraints table. Minimal structural change; covers primary failure surface; aligns with external prior art and existing conventions.
- **Option Structural (A1a + A1c + A2b + A3a + A4a)**: inline per-claim prose markers PLUS Feasibility-row status column + tagged prerequisites + new Rules block. Belt-and-suspenders coverage. More invasive template edits; higher adoption friction.
- **Option Agent-4 (A1c + A2c + A3c + A4a)**: Feasibility-row status only + folded empty-corpus + absorb prerequisites into §2 + Rules block. Highest mechanical enforceability on one surface, but fails to cover prose (primary failure surface) and steps beyond ticket scope on A3c.

Spec-phase selection required.

## Adversarial Review

Summarized from Agent 5. Material challenges that spec must resolve:

- **FM1 — A1c does not cover the #092 failure surface**: #092's inferred locator was in Research-Questions answer prose + Codebase Analysis prose, not in the Feasibility table. A row-status column on Feasibility applies to a single column on one surface; most codebase-pointing claims live in prose. Recommendation: prose-inline markers (A1a) as primary.
- **FM2 — Self-enforcement failure**: synthesis-time rules depend on the author recognizing their own inferences as inferences. Epic H3 established empirically that the author did not recognize this. Synthesis-time enforcement by the same agent may not close the hole that post-hoc enforcement couldn't close. This is a principled challenge to the epic's A+C design, not just this ticket's implementation.
- **FM3/FM4 — `premise-unverified` collapses distinct states and lacks query+scope**: matches PRISMA-S bias finding. Ticket's own success criterion (`backlog/138:44`) requires empty-corpus be "reported as a distinct outcome, not omitted" — a single-value marker fails the ticket's own criterion.
- **DW2 — A3c is out-of-scope creep**: ticket says "retarget," Agent 4 proposes "remove and relocate."
- **DW4 — #139's consumption point is `decompose.md:23` Value field, not research.md Prerequisites**: vendor-endorsement claims live in decompose Value, not research Feasibility. The signal surface must reach the consumption point or #139 cannot consume it.
- **AS3 — #138 cannot "block #139 by convention" as backlog asserts** unless #138 also specifies the format decompose will read. Either #138 pins the format explicitly or #139 must re-open #138.
- **AS4 — 85-95% citation density is lexical, not epistemic**: a projected locator counts as a citation under the lexical measure. The density figure is a measurement artifact, not a safety margin.
- **M3 (re-litigation risk)**: adversarial suggests reviving Approach F (mechanical probe). Epic DR-1/DR-2 explicitly rejected F in favor of A+C. Per rejected-alternatives discipline, a new observation runs to the critic-layer, not to re-open the proposal. Flagging as a possible escalation if #138 implementation surfaces further evidence the rule-edit approach fails. Not a scope change for this ticket.

## Open Questions

Material spec-phase decisions surfaced by cross-agent contradictions:

- **OQ1 (marker surface)**: Prose-inline (A1a) or Feasibility-row status column (A1c) or both? External prior art + adversarial review favor A1a (covers #092's actual surface). Agent 4 favors A1c (mechanical enforceability). **Deferred: resolved in Spec via structured requirements interview.** This is the marker-syntax design decision spec is designed to pin.
- **OQ2 (empty-corpus format)**: Single `premise-unverified` value or split `NOT_FOUND(query, scope)` vs. `premise-unverified: not-searched`? Ticket success criterion + PRISMA-S evidence favor the split. **Deferred: resolved in Spec.** Empty-corpus format is a direct requirements-interview question.
- **OQ3 (Prerequisites retargeting shape)**: Binary tag (A3a), split column (A3b), absorb into §2 (A3c — likely out of scope), or rule-level instruction keeping column unchanged (A3d)? Ticket language "retarget" suggests A3a or A3d. **Deferred: resolved in Spec.** Requirements interview picks the shape consistent with ticket scope.
- **OQ4 (rule encoding)**: New `### Research Rules` subsection (A4a, novel convention) or extend the existing `## Constraints` table at `research.md:134-138` (A4b, conventional fit)? **Deferred: resolved in Spec.** Encoding-style choice is a spec-level requirement.
- **OQ5 (#139 contract surface)**: Does #138 pin a format contract decompose.md will read, or produce the signal and let #139 add its reader? Adversarial DW4 flags that signal-at-research.md does not automatically reach decompose.md's Value field. **Deferred: resolved in Spec.** Whether to include a decompose-consumer contract section in #138's spec is a scope question for the requirements interview.
- **OQ6 (self-enforcement risk acknowledgment)**: Adversarial FM2/AS1 challenge whether synthesis-time enforcement differs from post-hoc when the synthesizer is the same agent. **Resolved: ship rule-edit as scoped (option 1, user-confirmed 2026-04-22).** FM2 is acknowledged as a residual risk documented in the epic's H3 finding; any future recurrence triggers a new ticket for Approach F (mechanical grounding probe). Per rejected-alternatives discipline, this observation runs to the critic/decision-process layer, not to re-opening the epic's DR-1. #138 proceeds at current scope.
- **OQ7 (retroactive vs. prospective)**: 27+ existing research artifacts are non-compliant by default. **Deferred: resolved in Spec.** Scope-of-applicability is a direct requirements-interview question.
