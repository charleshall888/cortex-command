# Research: requirements-skill-v2

> Lifecycle: requirements-skill-v2
> Tier: complex / Criticality: critical
> Parent backlog: [[207-rebuild-requirements-skill-v2]] (follow-up to epic [[009-requirements-management-overhaul]])

## Clarified Intent

Audit and rebuild the `/requirements` skill, the parent `cortex/requirements/project.md`, and the four area sub-docs (multi-agent, observability, pipeline, remote-access) as v2 — addressing four pain points: token efficiency, skill protocol weakness, agent navigability, and drift/accuracy. Single lifecycle (not an epic with siblings). Acceptance criteria are deliberately deferred to the Specify phase, anchored on research findings. The mattpocock/skills repo (especially the "grill-me" skill) is one comparison input among several.

## Considerations from Clarify-Critic

Two clarify-critic Apply'd findings carry into research as background considerations:

- **Criticality is critical, not high**: /requirements is a trunk dependency of lifecycle, refine, discovery, and critical-review. Any interface change must preserve downstream consumption semantics. This is why criticality was bumped HIGH→CRITICAL.
- **Solution Horizon cuts both ways**: v1 shipped only ~5 weeks ago and #013 is the dedicated drift-mitigation mechanism. The v2 case must be grounded in evidence that v1's *format/protocol* (not its enforcement loop) is the proximate cause of the four pain points. Otherwise this rebuild is exactly the premature-redo failure mode Solution Horizon was added to prevent.

## Research Angles

Five parallel research dispatches were run in this phase: codebase audit + token measurement, mattpocock/skills study, industry comparison, #013 effectiveness audit, and adversarial review of the v2 thesis. Findings below.

---

## 1. Codebase Audit + Token Measurements

### 1.1 Current state inventory

| Artifact | Words | Lines | ≈Tokens |
|----------|-------|-------|---------|
| `cortex/requirements/project.md` (parent, always-loaded by consumers) | 1,373 | 75 | ~1,785 |
| `cortex/requirements/multi-agent.md` | 1,184 | 98 | ~1,540 |
| `cortex/requirements/observability.md` | 1,709 | 151 | ~2,222 |
| `cortex/requirements/pipeline.md` | 2,328 | 170 | ~3,026 |
| `cortex/requirements/remote-access.md` | 458 | 60 | ~595 |
| **Area docs subtotal** | 5,679 | 479 | ~7,383 |
| `skills/requirements/SKILL.md` | 804 | 116 | ~1,045 |
| `skills/requirements/references/gather.md` | 1,357 | 232 | ~1,764 |
| **Skill subtotal** | 2,161 | 348 | ~2,809 |
| **Grand total** | 9,213 | 902 | **~11,977** |

### 1.2 Drift audit — spot-checks against current code

Five claims spot-checked across project.md and 2 area docs:

| Claim | Source | Verdict |
|-------|--------|---------|
| "Distributed CLI-first as a non-editable wheel" | project.md:7 | ✓ Confirmed — `cortex_command/install_guard.py` enforces wheel install |
| "Per-repo sandbox registration via fcntl.flock serialization" | project.md:30 | ✓ Confirmed — `cortex_command/init/settings_merge.py:113` implements fcntl.LOCK_EX |
| "Conflict resolution pipeline ~2500 LOC, parallel dispatch, model selection matrix" | project.md:48-50 | ✓ Confirmed — `cortex_command/overnight/conflict_resolver.py`, `pipeline/dispatch.py`, `overnight/model_selection.py` |
| "Session phases: planning → executing → complete; paused sessions resume to phase paused from" | pipeline.md:18-28 | ✓ Confirmed — `cortex_command/overnight/state.py:40` |
| "Agent spawning via Claude Agent SDK; OS-kernel sandbox enforcement per spawn with --settings tempfile" | multi-agent.md:14-24 | ✓ Confirmed — `pipeline/dispatch.py` calls `claude_agent_sdk.query()`; `overnight/sandbox_settings.py` generates per-spawn tempfiles |

**Drift verdict**: 5/5 claims confirmed. No material content drift in spot-checked surfaces. The "drift/accuracy" pain point may be partially perception — the docs *are* currently accurate.

**Scope-documentation gap (not content drift)**: Discovery and backlog are listed In Scope (project.md:49) but have no area requirements docs and are not in the Conditional Loading trigger table. Either they need area docs or the parent's coverage claim should be clarified.

### 1.3 Consumer audit (load patterns)

| Consumer | File | Load pattern |
|----------|------|--------------|
| Lifecycle clarify | `skills/lifecycle/references/clarify.md` §2 | Reads project.md; scans area docs by name relevance — **heuristic, not tag-based** |
| Lifecycle specify | `skills/lifecycle/references/specify.md` Step 4 | Same heuristic name-matching — **not tag-based** |
| Lifecycle review | `skills/lifecycle/references/review.md` §1 lines 12-16 | **Tag-based structured loading**: reads index.md's `tags:` array, matches case-insensitively against Conditional Loading phrases — explicit list of loaded docs with match rationale |
| Discovery clarify | `skills/discovery/references/clarify.md` | Heuristic name-matching — **not tag-based** |
| Discovery research | `skills/discovery/references/research.md` | Parent always; area docs by heuristic — **not tag-based** |
| Critical-review | `skills/critical-review/SKILL.md` | Reads parent's Overview section (~250 words); **no area docs at all** |
| Python `report.py` | `cortex_command/overnight/report.py:559,635` | Read-only via `_read_requirements_drift()` — extracts drift state from review.md |

**Smoking gun**: Only *one* of seven consumers (lifecycle review) uses the tag-based Conditional Loading protocol that the parent doc's trigger table is supposed to drive. All other consumers fall back to "scan area docs whose names suggest relevance" — a heuristic that breaks silently if (a) a trigger phrase doesn't match the area-doc filename, (b) the area scope drifts but the filename doesn't, or (c) the consumer doesn't notice a newly-relevant area doc.

This single finding likely explains most of the "agent navigability" pain point and significantly more of the perceived "drift" than v1's actual content accuracy would suggest.

---

## 2. #013 Drift-Detection Effectiveness Audit

**Scope**: 143 lifecycle review.md files (post-#013, since 2026-04-03).

**Field compliance**:
- With `requirements_drift` field: **127 / 143 (88.8%)**
- Missing entirely: 16 (11.2%) — all pre-#013 artifacts relocated by commit `c8110de5`

**Field values** (127 with field):
- `requirements_drift: none`: **99 (77.9%)**
- `requirements_drift: detected`: **26 (20.5%)**
- Malformed/empty: 2 (1.6%)

**Drift instances with structured suggestions**: 18 / 26 (69.2%) include the `## Suggested Requirements Update` section. The other 8 are protocol breaches — drift was flagged without an actionable update path.

**Auto-apply mechanism**: Wired in `review.md` §4a; firing in recent overnight sessions (lifecycles 188, 189 on 2026-05-11). Historical drift suggestions from April do not appear in project.md updates because auto-apply post-dated the early detected-drift artifacts.

**Verdict**:
- ✓ #013 is firing reliably (88.8%)
- ✓ Machine-readable JSON output is parseable
- ✓ Morning report surfacing works (`_read_requirements_drift`)
- ✗ 8/26 detected drifts breach the "include Suggested Update" protocol
- ✗ Historical drift from April was never auto-applied (mechanism added later)
- ✗ No parity audit between "suggested updates" and "actual file changes"

**Recommendation** (from audit agent): Tighten #013 in v2 — elevate "Suggested Requirements Update" section from soft prompt to enforced via post-dispatch validation; wire auto-apply backfill at overnight launch; add a parity audit comparing suggested-update counts against actual changes. **Do not replace #013** — the core mechanism is load-bearing and working.

---

## 3. Industry Comparison

| Tool / spec | Parent doc budget | Conditional loading | Drift detection |
|-------------|-------------------|---------------------|-----------------|
| **Cursor rules** (`.cursor/rules/*.mdc`) | ≤500 lines (rule-level); `alwaysApply` rules ≤200 words | 4-mode taxonomy: Always / Auto Attached (globs) / Agent Requested (description match) / Manual (`@`-mention) | None automated |
| **Aider CONVENTIONS.md** | No budget | Single file loaded via `--read` or `.aider.conf.yml` | None — silent aging |
| **AGENTS.md spec** | No budget | Monolithic at repo root; nested files in subdirs | None |
| **llms.txt / llms-full.txt** | Short index; sub-docs separate | Parent links + explicit `## Optional` H2 partitioning for prunable content | None |
| **Anthropic skill-authoring** | SKILL.md ≤500 lines; references one-level deep; large refs need ToC | 3-tier: metadata preloaded → SKILL.md on relevance → references on demand | None — "observe how Claude navigates" |
| **OpenAI Model Spec** | ~14,000 words (system-level only) | 4-tier authority tagging (Platform > Developer > User > Guideline) | Date-versioned, manual updates |

### Convergent patterns

1. **Length budget** — convergence around 500 lines / 5,000 words for the readily-loaded parent. Both Anthropic and Cursor name this explicitly. AGENTS.md and Aider don't, and their failure mode is bloat.

2. **Conditional loading mechanisms** — three recurring shapes:
   - **Glob-based** (Cursor `globs:`, llms.txt sub-doc URLs by path)
   - **Description-triggered semantic match** (Cursor `description:`, Anthropic skill description)
   - **Explicit reference links** (Anthropic `See FORMS.md`, llms.txt link-list with descriptions, OpenAI authority tags acting as in-line filters)

   Cursor's four-mode taxonomy is the most fully realized typology — directly transferable.

3. **Drift detection** — *none* of the six tools automate it. They all rely on humans editing docs and noticing discrepancies. **This is where cortex's #013 already exceeds the industry baseline**, and it's where v2 should preserve the lead rather than rebuild from scratch.

### Failure modes by tool

- **Aider**: silent drift, no structure
- **AGENTS.md**: monolithic, no progressive disclosure, balloons over time
- **llms.txt**: web-focused; doesn't port cleanly to repo-internal requirements
- **Cursor**: glob-based loading misfires on cross-cutting concerns that don't map to file paths
- **Anthropic skills**: the 500-line ceiling is sometimes ignored; deeply nested references silently get partial-read
- **OpenAI Model Spec**: 14,000-words-always-loaded is only viable because it's the system spec, not project-level

---

## 4. mattpocock/skills Study — "grill-me"

### What grill-me does

A 4-line SKILL.md that produces a single-shot conversational interview. Walks the design tree depth-first; asks one question at a time with a recommended answer attached; substitutes codebase exploration whenever a question is answerable from code.

### Quotable patterns (for v2 design)

> *"Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer."*
> — `mattpocock/skills/skills/productivity/grill-me/SKILL.md`

> *"If a question can be answered by exploring the codebase, explore the codebase instead."*
> — same file

> *"Your glossary defines cancellation as X, but you seem to mean Y — which is it?"*
> — `mattpocock/skills/skills/engineering/grill-with-docs/SKILL.md`

> *"Create files lazily — only when you have something to write."*
> — same file

### Transferable patterns

1. **Recommend-before-asking** — forces the agent to commit a position before asking, which sharpens specificity and converts the user's reply from author to editor. Cortex's `gather.md` lists question categories without modeling this cadence. **Strong candidate for v2 protocol**.
2. **Codebase trumps interview as one load-bearing rule** — Pocock compresses to one sentence; cortex spreads it across Step 3 + multiple paragraphs of gather.md.
3. **Lazy artifact creation** — `Create files lazily — only when you have something to write`. Cortex Step 5 implies always-write-after-Step-4.
4. **Three-gate test pattern for boundary calls** — Pocock's ADR three-question gate is a transferable shape for the cortex requirements-vs-spec and requirements-vs-CLAUDE.md boundary calls.
5. **Split synthesis from interview** — Pocock has `grill-me` (interview only) and `to-prd` (synthesize-only). Cortex bundles both in one 7-step protocol. Splitting would let refine/specify reuse the interview without duplicating it.
6. **Inline glossary-conflict callouts** — `"Your glossary defines X, but you seem to mean Y"`. Cortex has no glossary; adding one + interrupt-on-conflict is borrowable straight from `grill-with-docs`.

### Not transferable

- Pocock's skills are stateless and single-pass — no list/update/replace, no scope hierarchy. Cortex needs all of these.
- No downstream-consumer contract — Pocock's PRDs are read by humans in flat triage. Cortex requirements are loaded by lifecycle/discovery/pipeline at phase gates; the trigger-table structure is genuinely required.
- No re-gather workflow — Pocock's tracker model makes drift irrelevant; cortex's "Re-Gather Triggers" section (gather.md:136-149) is a genuine cortex contribution.

### Where cortex already beats Pocock

- Explicit scope hierarchy (project vs area, Conditional Loading triggers)
- Downstream-consumption contract encoded
- Requirements vs CLAUDE.md vs spec separation articulated

### Where Pocock beats cortex

- **Brevity** — grill-me is 4 lines and conveys more conviction than gather.md's 232 lines. Per cortex's own *"prescribe What and Why, not How"* principle, much of gather.md is over-specified procedure.
- **Composition** — Pocock's `triage` calls `grill-with-docs` rather than re-implementing interview logic. Cortex's `/requirements` is monolithic.
- **Recommend before asking** as an interview-quality forcing function — cortex has no analog.

---

## 5. Adversarial Findings — Load-Bearing Objections to v2

The adversarial dispatch produced 7 steel-manned objections. Three are load-bearing — if research does not address them, v2 ships with the same failure mode v1 has.

### Objection 2 (most load-bearing): "Drift is a process problem, not a format problem"

- *Risk*: v2 accumulates the same drift v1 did, because humans/agents don't re-run /requirements after every relevant change.
- *Rebuttal test*: Invalid if research shows v1's *format* actively prevents mechanical drift detection.
- **Research verdict**: Partially refuted. The codebase audit found 5/5 spot-checked claims accurate, and the #013 audit found the drift mechanism firing at 88.8% compliance. **Drift is more a process-tightening problem (8/26 protocol breaches, missing parity audit) than a format problem.** The remaining gap on the format side is consumer-loading inconsistency (only review.md uses tag-based loading) — but that's an *agent navigability* gap, not a drift gap.

### Objection 6: "Acceptance criteria deferred to Specify is a clarify-gate failure"

- *Risk*: Choosing "Define during Specify" means the inviter cannot articulate what v2 success looks like.
- *Rebuttal test*: Invalid if the user can now articulate ≥3 measurable success criteria.
- **Research verdict**: After research, measurable criteria are now articulable. Candidate criteria (for Specify to consider):
  - **Token efficiency**: Parent project.md ≤ X tokens (current: ~1,785; Cursor "tight" budget ~260; Anthropic guideline ≤500 lines is structural, not token-based).
  - **Agent navigability**: ≥6 of 7 consumer skills/scripts use tag-based or description-triggered loading (current: 1/7).
  - **Drift catchment**: #013 detected-with-suggestion rate ≥ 95% (current: 18/26 = 69.2%); auto-apply parity audit lands.
  - **Skill protocol weight**: gather.md ≤ 100 lines (current: 232) or compressed into a recommend-before-asking pattern matching grill-me's brevity.

### Objection 1: "Premature rebuild — v1 hasn't had a fair shake"

- *Risk*: v1 at 5 weeks judged on aesthetics, not function.
- *Rebuttal test*: Invalid if there are ≥3 documented instances across distinct sessions where v1 demonstrably failed a *consumer* skill.
- **Research verdict**: Indirect evidence supports the rebuild case. The consumer audit reveals 6 of 7 consumers don't use tag-based loading — every lifecycle/discovery/refine session in the last 5 weeks has been silently navigating around v1's parent-trigger table. The 8/26 drift-without-suggestion artifacts are also failures in active use. **This isn't aesthetic frustration — it's measurable infrastructure underperformance.** The v2 case stands.

### Secondary objections (3, 4, 5, 7)

These shape *how* v2 scopes but do not gate *whether* it proceeds:

- **Objection 3 (token efficiency is a 30% trim)**: Partially valid. A trim experiment is cheaper than a rebuild. v2 should incorporate a "trim-first" hypothesis test in the Specify phase — quantify how much can be cut without changing structure.
- **Objection 4 (industry comparison is cargo-culting)**: Valid concern; mitigated by the convergent-pattern finding above. Cursor's 4-mode taxonomy, Anthropic's 3-tier disclosure, and llms.txt's `## Optional` partitioning are *structurally* matched to cortex's consumer-driven loading model — they're not just borrowed for being trendy.
- **Objection 5 (blast radius)**: Valid. v2 should ship in layers — start with the consumer-loading fix (lowest risk, highest navigability win), then parent doc trim, then skill protocol rewrite, then area docs. This lets each layer prove itself before the next ships.
- **Objection 7 (user's pain may be session-local)**: Partially refuted — the 6-of-7 consumer-loading inconsistency is durable infrastructure pain, not session-local.

---

## 6. Synthesis — What v2 Should Actually Be

Research has substantially refined the v2 thesis from "rebuild all four pain points" to a more targeted, evidence-grounded scope:

### Where v2 is genuinely needed

1. **Consumer-loading consistency (highest priority)** — extend tag-based Conditional Loading from review.md to all 6 other consumers (lifecycle clarify/specify, discovery clarify/research, critical-review). This is the single largest navigability win and the most defensible change against Objection 1.

2. **Skill protocol weight reduction** — apply mattpocock-style brevity to `gather.md` and `SKILL.md`. Adopt "recommend before asking", split interview from synthesis, lazy artifact creation. This addresses "skill protocol weakness" without touching the consumer contract.

3. **Parent doc trim + Optional partitioning** — apply llms.txt's `## Optional` H2 pattern to the parent so consumers under token pressure have explicit prunable surface. Target Cursor-style trim of always-loaded content (~30%).

### Where v2 should *tighten*, not rebuild

4. **Drift detection** — tighten #013, do not replace. Three changes from the audit recommendation:
   - Elevate "Suggested Requirements Update" from soft prompt to enforced post-dispatch validation
   - Wire auto-apply backfill at overnight launch (catch pending updates from prior sessions)
   - Add parity audit comparing suggested-update counts to actual file changes

### Where v2 should *probably not*

5. **Replace area sub-docs wholesale** — the codebase audit found no material content drift. Audit each against current code and patch where needed; do not rewrite from scratch.

6. **Build a fundamentally new framework** — cortex's downstream-consumer contract, scope hierarchy, and re-gather workflow already beat every comparison point. Cursor, Aider, AGENTS.md, llms.txt, and even Anthropic's own skill guidance don't have these. Don't trade the lead for cargo-culted patterns.

### Phased delivery (Objection 5 mitigation)

Suggested layering (Specify will refine):
- **Layer A** (lowest risk): Extend tag-based loading to clarify/specify/discovery/critical-review. Pure additive change to consumer skills.
- **Layer B**: Trim parent project.md, add `## Optional` partitioning.
- **Layer C**: Rewrite skill protocol (SKILL.md + gather.md) with mattpocock patterns. Compose-split into `gather` + `write` sub-skills if warranted.
- **Layer D**: Audit and patch (not rewrite) the 4 area sub-docs against current code.
- **Layer E**: Tighten #013 — enforce Suggested Update section; wire auto-apply backfill; add parity audit.

Each layer is independently shippable and reviewable. Layers A and E provide the most durable navigability + drift catchment improvements; B and C are quality-of-life; D is hygiene.

---

## 7. Open Questions for Specify

The following questions were surfaced in research. Each is annotated with its current disposition.

- **Acceptance criteria binding**: Which candidate measurable criteria (token target, navigability ratio, drift catchment rate, skill protocol weight) are must-haves vs. should-haves? Set numeric thresholds now or as direction-of-travel?
  - **Deferred**: User selected "Define during Specify" in the clarify-critic Ask round. The Specify §4 structured interview will resolve.

- **Trim-first hypothesis**: Should Specify include a trim-first experiment as a gate before the full rewrite layers?
  - **Deferred**: Subsumed in the layer-ordering decision below. Specify §4 will resolve as part of layer planning.

- **Composition vs monolith for the skill**: Adopt Pocock's split (`gather` interview + `write` synthesize) or keep monolithic?
  - **Resolved**: SPLIT into `gather` (interview) + `write` (synthesize). The composition value (refine reusing gather without re-implementing) was decisive. Spec must define the two surfaces' contracts and how the existing `/requirements` entry point transitions (e.g., does it become a thin orchestrator over the two, or get retired in favor of explicit `/requirements-gather` + `/requirements-write` invocations?).

- **Layer ordering**: A→B→C→D→E order, or E first, or trim-first experiment?
  - **Deferred**: User selected "Specify decides" — the Specify-phase interview will determine ordering based on dependency analysis and layer-A's consumer-loading-fix evidence.

- **Area-doc scope decisions**: Discovery and backlog are listed In Scope but lack area docs. Add docs or trim the scope claim?
  - **Deferred**: Resolved during Specify §4 — depends on whether the scope claim is accurate (discovery and backlog ARE substantial subsystems) or aspirational.

- **Authority tagging?**: Import OpenAI Model Spec's Platform/Developer/User/Guideline tagging for cortex requirements?
  - **Deferred**: Specify §4 will judge against cortex's scale. Likely over-engineering for current single-user single-repo posture; revisit if multi-user/multi-repo emerges.

## 8. Citations / Sources

**Internal**:
- `skills/requirements/SKILL.md`, `skills/requirements/references/gather.md`
- `cortex/requirements/project.md`, `cortex/requirements/{multi-agent,observability,pipeline,remote-access}.md`
- `skills/lifecycle/references/{clarify,specify,review}.md`
- `skills/discovery/references/{clarify,research}.md`
- `skills/critical-review/SKILL.md`
- `cortex/lifecycle/archive/wire-requirements-drift-check-into-lifecycle-review/spec.md`
- `cortex_command/overnight/report.py`, `cortex_command/init/settings_merge.py`, `cortex_command/overnight/state.py`, `cortex_command/pipeline/dispatch.py`, `cortex_command/overnight/sandbox_settings.py`
- 143 `cortex/lifecycle/*/review.md` and `cortex/lifecycle/archive/*/review.md` files (post-#013)
- `cortex/backlog/009-requirements-management-overhaul.md`, `011-redesign-requirements-skill-and-rewrite-project-md.md`, `012-gather-area-requirements-docs.md`, `013-wire-requirements-drift-check-into-lifecycle-review.md`

**External**:
- mattpocock/skills: `productivity/grill-me/SKILL.md`, `engineering/grill-with-docs/SKILL.md`, `engineering/to-prd/SKILL.md`, `engineering/grill-with-docs/{CONTEXT-FORMAT,ADR-FORMAT}.md`
- Cursor docs: https://cursor.com/docs/context/rules
- Aider conventions: https://aider.chat/docs/usage/conventions.html
- AGENTS.md: https://agents.md
- llms.txt: https://llmstxt.org
- Anthropic skill-authoring: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- Anthropic engineering blog: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- OpenAI Model Spec 2025-02-12: https://model-spec.openai.com/2025-02-12.html
- GitHub PR/issue templates: https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates
- Cursor community deep dive: https://forum.cursor.com/t/a-deep-dive-into-cursor-rules-0-45/60721
