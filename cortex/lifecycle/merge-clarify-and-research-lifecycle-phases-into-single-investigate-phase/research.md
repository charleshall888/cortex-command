# Research: Merge refine's internal Clarify + Research into a single Investigate reference

**Scope anchor (from Clarify)**: Eliminate the duplicated `requirements/` load between refine's internal Clarify and Research steps by merging them into a single Investigate reference, while preserving Clarify's user-blocking question gate as the non-negotiable Step 1 of the merged phase. **Out of scope**: renaming lifecycle's `research` phase string, changing dashboard mappings, parity tests, or overnight tooling. Refine internally executes a single Investigate step (confidence assessment + clarify-critic + question gate → read-only research → exit gate).

## Codebase Analysis

### Files that will change

**Canonical edits**:
- `skills/lifecycle/references/clarify.md` (129 lines) — merge content into surviving file OR delete after consolidation
- `skills/lifecycle/references/research.md` (204 lines) — merge content into surviving file OR delete after consolidation
- `skills/refine/SKILL.md` (210 lines) — collapse §3 (Clarify) + §4 (Research) into one Investigate step; update ~7 internal cross-references to "Step 3" / "Step 4" / "during Clarify" / "during Research"

**Auto-regenerated mirrors** (no manual edits — rsync `--delete` via `just build-plugin`, byte-parity enforced by `tests/test_dual_source_reference_parity.py` which auto-discovers via glob):
- `plugins/cortex-core/skills/lifecycle/references/clarify.md`
- `plugins/cortex-core/skills/lifecycle/references/research.md`
- `plugins/cortex-core/skills/refine/SKILL.md`

**Likely untouched (per user scope)**:
- `skills/lifecycle/SKILL.md` — keeps `research` in phase enum; `phase_transition` template at line 254 (`from: clarify, to: research`) becomes a decision point (see Open Questions)
- `cortex_command/common.py:165, 268` — keeps `"research"` phase string
- `cortex_command/dashboard/seed.py:513–520` — keeps `from: "research"` seed transitions
- `tests/test_lifecycle_phase_parity.py` — keeps `("research", 0, 0, 1, "research")` fixture
- `claude/statusline.sh:413,523,542` — statusline phase-detection bash mirror

### Duplication evidence (the value driver)

The two requirements-loading blocks are 95% byte-identical:

`skills/lifecycle/references/clarify.md` §2 (lines 31–37, ~55 words / ~75 tokens):
```
### 2. Load Requirements Context

Check for a `requirements/` directory at the project root.

- If `requirements/project.md` exists, read it.
- Scan `requirements/` for area docs whose names suggest relevance to this feature. Read any that apply.
- If no requirements directory or files exist, note this and skip to §3.
```

`skills/lifecycle/references/research.md` §0b (lines 22–30, ~75 words / ~100 tokens):
```
### 0b. Load Requirements Context

Check for a `requirements/` directory at the project root.

- If `requirements/project.md` exists, read it for project-level context.
- Scan `requirements/` for area-specific docs. If any area names appear relevant to this feature (based on the feature name and description), read those too.
- Use requirements as context during exploration — they inform what patterns to look for, what constraints to respect, and how this feature fits into the broader project.

If no requirements directory exists, skip this step.
```

**Realistic token savings**: ~70–100 tokens per refine chain (the duplicated paragraph only). Beyond the paragraph, the two files have minimal procedural overlap — each has unique content that survives any merge. The Clarify file has the confidence-assessment, critic-dispatch, question-threshold, output-template, sufficiency-criteria, and write-backs sections; the Research file has the critical-tier parallel research protocol (~95 lines of unique content), web-research handoff, output artifact template, and Open-Questions exit gate. Merging the two files compresses section-numbering and removes one set of frontmatter/closing-tables (~30–50 additional tokens), bringing realistic total per-chain savings to **~100–150 tokens**.

This is significantly smaller than the initial estimate (~700–900 tokens) and reframes the value driver: the case for the merge rests primarily on **clarity-of-flow** (one cohesive pre-spec investigation surface instead of two artificially split phases) and **secondarily** on the modest token saving. The spec should not frame this as a meaningful token-budget win.

### Current gate enforcement mechanism

The "ask the user ≤5 targeted questions before codebase exploration" gate is enforced by **three** mechanisms today, not just prose:

1. **The `AskUserQuestion` tool call itself** — the tool blocks the agent's turn until user input arrives. This is the load-bearing gate. The tool's blocking behavior is preserved regardless of how the reference files are organized.
2. **Prose ordering** in `clarify.md` §4 ("Wait for user answers before continuing").
3. **Two-skill-file sequential delegation** in refine SKILL.md (Step 3 reads clarify.md fully, Step 4 reads research.md).

There is **no executable hook** in `hooks/` or `claude/hooks/` that gates `Read`/`Grep` on a "questions answered" signal. After the merge, mechanism (1) survives unchanged, mechanism (2) survives if the prose is preserved verbatim, and mechanism (3) is replaced by intra-file ordering. The net change in gate strength is small: the tool-blocking call remains the actual gate.

### Refine SKILL.md orchestration

Refine's current chain:
- **Step 3** (lines 64–82, "Clarify Phase"): reads `../lifecycle/references/clarify.md`, follows §2–§7, captures clarified intent + complexity + criticality + requirements-alignment-note + open questions. Runs `cortex-update-item` write-back inline.
- **Step 4** (lines 84–150, "Research Phase"): sufficiency check (uses clarify.md §6), delegate to `/cortex-core:research`, alignment-considerations propagation, research exit gate.
- **Step 5** (Spec) currently says "Requirements context was loaded during Clarify (Step 3)" — needs terminology update post-merge.

After merge, Step 3 + Step 4 collapse into a single "Step 3: Investigate Phase" pointing at one reference file. The intermediate Alignment-Considerations Propagation block stays — it bridges clarify-critic's alignment findings into `/cortex-core:research` invocation.

### Cross-references requiring link updates

If `clarify.md` is deleted (i.e., merge consolidates into `research.md` or new `investigate.md`):
- `skills/refine/SKILL.md:39` — `../lifecycle/references/clarify.md §1` (Exit 3 ad-hoc branch)
- `skills/refine/SKILL.md:66` — `../lifecycle/references/clarify.md` (Step 3 main read)
- `skills/refine/SKILL.md:87` — `../lifecycle/references/clarify.md §6` (Research Sufficiency Criteria)

**Hidden cascade risk**: `skills/refine/references/clarify-critic.md` contains ~6 `§`-numbered references to clarify.md's sections (e.g., "§3 confidence challenge", "§4 Q&A merge"). If the merge renumbers clarify's sections, every cross-reference breaks. The `tests/test_clarify_critic_alignment_integration.py:109,132` parity tests grep for section-anchor structure within clarify-critic.md and would also need updates. **Mitigation**: preserve clarify's §1–§7 numbering intact in the merged file; insert research's procedural content as §4a / §4b / §4c (between §4 Question Threshold and §5 Produce Output). This sidesteps the cascade entirely.

### Discovery skill independence

Discovery has its own `skills/discovery/references/clarify.md` (66 lines, 619 words) and `skills/discovery/references/research.md` (154 lines, 840 words). Discovery's SKILL.md uses `${CLAUDE_SKILL_DIR}/references/clarify.md`, i.e., `skills/discovery/references/clarify.md` — **not** lifecycle's. Discovery is fully independent. Its two-step structure serves a different purpose (gap-finding before research, not intent-gating) and is load-bearing for discovery's own failure mode.

**Forcing function needed** to prevent incremental drift: an explicit ADR-style note in the merged file ("Discovery's separate Clarify+Research is intentional. Do not align discovery to this pattern without explicit lifecycle re-evaluation.")

### Plugin-mirror implications

`justfile:514` runs `rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"`. This means:
- (a) **New `investigate.md` + delete clarify.md/research.md**: rsync `--delete` removes deletions from mirror; new file appears. Clean.
- (b) **Repurpose research.md, delete clarify.md**: rsync removes clarify.md from mirror; research.md overwritten in place.

The `tests/test_dual_source_reference_parity.py` test auto-discovers all `skills/*/references/*.md` files via glob (line 90) — adds/removes don't require test code changes. The narrower `tests/test_plugin_mirror_parity.py` tracks specific files (`plan.md`, `specify.md`, `orchestrator-review.md`) and doesn't reference clarify.md or research.md.

### Phase string is load-bearing in 7+ consumers

Beyond the explicitly-out-of-scope surfaces, the literal string `"research"` is consumed as a phase value by: `cortex_command/common.py:157,165,268` (default phase detection), `cortex_command/backlog/generate_index.py:143,166` (`lifecycle_phase` frontmatter field), `cortex_command/overnight/backlog.py:316,360` (overnight runner frontmatter read), `claude/statusline.sh:413–414,523,542` (statusline display fallback), `cortex_command/dashboard/seed.py:441,513` (dashboard seed), `cortex_command/dashboard/data.py:282–331` (dashboard timeline parser). The user's "phase enum / dashboard mappings / parity tests not changed" scope holds **only if** the merged phase continues to emit `"research"` as its phase string in `lifecycle_start` and `phase_transition` events. The reference filename can be renamed; the emitted phase string cannot.

## Web Research

### Sources consulted
- [Anthropic Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Chain complex prompts (Anthropic docs)](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-prompts)
- [Equipping agents with Agent Skills (Anthropic)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [When LLMs Stop Following Steps (arxiv 2605.00817)](https://arxiv.org/html/2605.00817) — instruction-following degradation with step count
- [The Order Effect (arxiv 2502.04134)](https://arxiv.org/html/2502.04134v2) — order-sensitivity in prompt-internal instructions
- [Simple patterns for events schema versioning (event-driven.io)](https://event-driven.io/en/simple_events_versioning_patterns/)
- [Marten Events Versioning](https://martendb.io/events/versioning) — `MapEventType` alias pattern
- [Cursor 2.1 clarifying questions analysis](https://www.digitalapplied.com/blog/cursor-2-1-clarifying-questions-plans)

### Key findings

**Anthropic prefers chaining over collapse for sequential reliability**. The chain-prompts doc states: *"When a single prompt handles everything, Claude can drop steps, but breaking complex tasks into focused subtasks connected in a chain ensures each link gets Claude's full attention."* This is the **strongest published signal against** the merge proposal. However, the doc addresses 5+ step prompts, not 2-step procedures. At 2 steps, the empirical effect from arxiv 2605.00817 is small (accuracy degrades from 61% to ~57% at low step counts, vs. 20% at 95 steps).

**Anti-pattern**: silently collapsing two phases without making the inner gate a named, labeled, separately-testable step. The merge proposal **must** preserve the question gate as an explicitly-named Step 1 inside the merged file. Cursor 2.1's clarifying-questions feature is *advisory* (per-question skippable) and lost in practice — a cautionary example of soft gates.

**Best-practice pattern for renames in event-driven logs**: `MapEventType`-style alias. Register old name as alias for new; historical logs deserialize transparently; no data migration. For cortex's case (events.log audit only, no external consumers), the simpler "additive new event + parser-side tolerance for old names" pattern suffices. **Critical**: do NOT rewrite historical events.log files.

**Skill-authoring guidance** does not directly cover "non-negotiable ordering enforced by prose alone" — the closest documented enforcement primitives are (a) numbered steps with "Only proceed when X passes" prose, (b) copy-into-response checklist for complex workflows where steps could be skipped, (c) explicit MUST language. Cortex's MUST-escalation policy (CLAUDE.md) is in tension with (c) — soft positive-routing phrasing is preferred unless events.log evidence justifies escalation.

## Requirements & Constraints

### Relevant requirements from `requirements/project.md`

- **Workflow trimming (Philosophy of Work)**: *"Workflows that have not earned their place are removed wholesale rather than deprecated in stages. Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers (verified per-PR)."* — Conditional clause does NOT apply (downstream consumers exist: refine SKILL.md, lifecycle SKILL.md, clarify-critic.md). The broader "remove wholesale rather than deprecate in stages" principle DOES apply: the merge is a one-PR rewrite, not a phased deprecation.
- **SKILL.md size cap**: 500 lines, enforced by `tests/test_skill_size_budget.py`. Does **not apply to references files**. refine SKILL.md is currently 210 lines; lifecycle SKILL.md is 365. Both well within budget. Merged reference file (~250–330 lines after dedup) is unconstrained.
- **SKILL.md-to-bin parity enforcement**: No bin scripts reference `clarify.md` or `references/research.md`. `bin/cortex-complexity-escalator:35,243` references the per-feature artifact `lifecycle/{slug}/research.md`, which is unchanged. Bin parity is unaffected.
- **Maintainability through simplicity** (Quality Attributes): *"Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows."* — Aligns with merge.
- **Complexity must earn its place** (Philosophy of Work): *"Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."* — Merging two near-identical procedural surfaces into one fits.
- **Day/night split** and **handoff readiness**: Both unaffected. The merged Investigate phase remains a daytime activity; spec-has-no-open-questions handoff bar is owned by Spec's Research Exit Gate (refine SKILL.md:147–151) and survives the merge.

### MUST-escalation policy (CLAUDE.md)

**Verified empirically**: `clarify.md`, `research.md`, and `refine/SKILL.md` contain **zero existing MUSTs**. The topic-prompt's "MUST preserve" framing was hypothetical. Adding new MUSTs requires: (a) events.log F-row OR transcript-excerpt evidence; (b) effort=high (and effort=xhigh if needed) dispatch attempts recorded. **The merge should use positive-routing phrasing throughout**. The existing prose at `clarify.md:63` ("Wait for user answers before continuing") is sufficient — preserve verbatim.

### Pipeline.md feature-state requirements

The pipeline operates on lifecycle phase enum (`research, specify, plan, implement, review, complete`), not on the refine-internal Clarify-vs-Research distinction. No `"clarify"` literal exists in `cortex_command/` — verified via grep. Pipeline.md's only reference to `research.md` is as the per-feature lifecycle artifact (bin/cortex-complexity-escalator gate input), unaffected by the reference-file merge.

## Tradeoffs & Alternatives

### Alternative A — New `investigate.md`, delete `clarify.md` and `research.md`

Single merged reference file. Refine §3 + §4 collapse into one Investigate step pointing at `investigate.md`. Phase string emitted to events.log stays `"research"` (per user scope) — creates a minor file/phase naming asymmetry (file=`investigate.md`, emitted phase=`"research"`, artifact=`lifecycle/{slug}/research.md`).

- **Implementation complexity**: medium — one new file (~250–330 lines), two deletes, refine SKILL.md §3+§4 rewrite (~80 lines → ~40), ~3 cross-ref path updates (refine SKILL.md lines 39, 66, 87). Plugin mirror auto-regenerates. Byte-parity test auto-discovers.
- **Maintainability**: high — clean naming, no filename/content drift over time. Forcing-function note prevents discovery drift.
- **Performance**: ~100–150 tokens saved per refine chain (corrected from earlier estimate).
- **Alignment with existing patterns**: strong fit for references/ extraction pattern. Resolves latent collision between reference file `research.md` and artifact file `research.md` (per Adversarial finding #3).
- **Gate strength**: preserved if §3-§4 question-threshold prose is kept verbatim. AskUserQuestion is the actual gate; intra-file ordering does not weaken it materially at 2 steps.
- **Risk**: cascade edits in clarify-critic.md if sections renumber → mitigated by preserving clarify's §1–§7 and inserting research content as §4a/§4b/§4c.

### Alternative B — Repurpose `research.md`, delete `clarify.md`

Merge content into existing research.md. Filename stays. Refine §3 reads research.md instead of clarify.md.

- **Implementation complexity**: medium-low. Fewer path updates (research.md path stays valid in most cross-refs).
- **Maintainability**: medium — filename/content mismatch (file named "research.md" contains clarify content too). Latent collision between reference filename and artifact filename persists; future authors may re-introduce a clarify.md duplicating these contents.
- **Performance**: same as A (~100–150 tokens).
- **Alignment with existing patterns**: strong on link continuity (most cross-refs point at research.md); weak on naming clarity.
- **Gate strength**: same as A.
- **Risk**: filename-semantic drift over time.

### Alternative D — Extract `requirements-load.md` only, keep both files

Minimum-scope change. New `skills/lifecycle/references/requirements-load.md` (~15 lines). Both clarify.md and research.md replace their duplicated paragraphs with one-line "Read `requirements-load.md` and apply it."

- **Implementation complexity**: lowest — 1 small new file, 2 tiny edits.
- **Maintainability**: medium — adds one more reference file; indirection adds cognitive cost; doesn't address larger structural duplication.
- **Performance**: ~70–100 tokens saved (only the paragraph; reference files still load fully).
- **Alignment with existing patterns**: strong (mirrors clarify-critic.md, orchestrator-review.md extraction pattern).
- **Gate strength**: untouched.
- **Risk**: minimal — events.log audit trail unchanged, no clarify-critic.md cascade.

### Alternatives C and E

C (repurpose clarify.md) and E (runtime flag) rejected — C inverts dominant filename direction (research.md is the more cross-referenced name); E fights existing prose-encoded skill flow pattern with runtime parameter threading.

### Recommended approach: **Alternative A with section preservation**

Even with corrected token savings (~100–150 not ~700–900), Alternative A is the right choice:

1. **The user explicitly asked to "merge ... into a single Investigate reference"** — Option D underdelivers against stated intent and would invite a follow-up ticket.
2. **Clarity-of-flow value**: one cohesive pre-spec investigation surface beats two artificially-split phases that already chain inside refine.
3. **Filename collision resolution**: `investigate.md` reference + `research.md` artifact eliminates the latent collision that B preserves.
4. **Section preservation mitigation** sidesteps the clarify-critic.md cascade: keep clarify's §1 Resolve Input, §2 Load Requirements, §3 Confidence Assessment, §3a Critic Review, §4 Question Threshold, §5 Produce Output, §6 Research Sufficiency Criteria, §7 Write-Backs intact; insert research's procedural content (Codebase Exploration, Critical-tier parallel research, Web Research) as §4a / §4b / §4c between §4 and §5.
5. **Forcing function** against discovery drift: explicit header note in the merged file.
6. **Phase string preservation**: events.log continues emitting `"research"`; only the reference filename changes.

The complexity-vs-value gate (refine SKILL.md §4) needs honest framing: this is structural cleanup that removes prose duplication and clarifies refine's internal flow, not a meaningful token-budget win. If the user concludes that ~100-token savings doesn't justify the multi-file edit + cascade-risk audit, **Alternative D** is the legitimate fallback that delivers the literal value driver ("eliminate the duplicated requirements/ load") with minimum churn.

## Adversarial Review

### Failure modes the merge does NOT fix

The cited retros (`retros/archive/2026-04-22-2143-lifecycle-140-spec.md:5–9` and `retros/archive/2026-04-21-2108-lifecycle-129.md:13`) do **not** describe gate-skipping. They describe **confidence-calibration failures**: agents rate dimensions High when neither is supported, accept the ticket's framing without verifying against disk state, and require clarify-critic to force a second AskUserQuestion round. The gate fires in both cases. The merge does not address the underlying calibration problem; if anything, putting confidence assessment in the same file as research-execution prose may slightly increase the temptation to defer rigorous confidence work because "we'll probe in research anyway." **Frame the spec honestly**: this is a structural cleanup, not a fix for the gate-quality failure mode.

### Hidden cascade risk in clarify-critic.md

`skills/refine/references/clarify-critic.md` contains ~6 cross-references to `clarify.md`'s sections (lines 105, 117, 124, 126, 216, 226 — "§3 confidence challenge", "§4 Q&A merge", etc.). Section renumbering in the merge cascades into clarify-critic.md edits PLUS `tests/test_clarify_critic_alignment_integration.py:109,132` parity test updates. **Mitigation (load-bearing for the merge plan)**: preserve clarify's §1–§7 numbering intact in the merged file; insert research's content as sub-sections of §4 or as §4a/§4b/§4c.

### Phase string is load-bearing in 7+ consumers

The string `"research"` is consumed by `cortex_command/common.py`, `cortex_command/backlog/generate_index.py`, `cortex_command/overnight/backlog.py`, `claude/statusline.sh`, `cortex_command/dashboard/seed.py`, `cortex_command/dashboard/data.py`, and the `lifecycle_phase` frontmatter field in backlog items. The merge must continue emitting `"research"` as the phase string regardless of whether the reference file is renamed. Causes a minor cognitive asymmetry (file=`investigate.md`, phase=`"research"`, artifact=`lifecycle/{slug}/research.md`) under Alternative A — acceptable, and documented in the merged file's header note.

### Events.log inner-transition orphan

After merge, refine has no internal Clarify→Research boundary. The `phase_transition: from=clarify, to=research` event template at `lifecycle/SKILL.md:254` becomes a phantom event. Three options:
- (a) Keep emitting as back-compat alias — dishonest (event for a transition that doesn't occur); dashboard parsers tolerate it generically.
- (b) Drop entirely — readers see lifecycle_start → research→specify transitions; missing "clarify done" signal.
- (c) Rename to `from: investigate, to: spec` — violates user scope (phase string preservation).

**Recommendation**: drop the inner `clarify→research` event. The lifecycle_start event already marks refine's entry. Lifecycle SKILL.md lines 248–256 need a small edit removing the `clarify→research` template; the `research→specify` and `specify→plan` events stay unchanged.

### Cross-skill drift risk (discovery)

Discovery keeps its own Clarify+Research split. The merge applies only to lifecycle/refine. A future maintainer may try to "fix the inconsistency" by aligning discovery — which is genuinely independent. The merged file's header should contain an explicit ADR-style note: "Discovery's separate Clarify+Research is intentional. Do not align without explicit lifecycle re-evaluation."

### Token-savings claim correction

Initial framing implied 700–900 tokens saved per refine chain. The verified value is **~100–150 tokens**. The duplicated paragraph alone is ~75–100 tokens; merging frontmatter/closing-sections adds another ~30–50 tokens of compression. This is an order of magnitude smaller than the initial estimate and reframes the value driver from "token budget" to "clarity-of-flow."

### Critical-tier parallel research preservation (small architectural win)

`research.md` §0a (lines 15–20) currently re-reads criticality from `events.log` to decide whether to run parallel research. In the merged file, criticality is already determined by the confidence-assessment step (§3) — eliminates a redundant events.log re-read. Small cleanup the merge gets for free.

## Open Questions

- **Q1: Filename — `investigate.md` (Alt A) or `research.md` (Alt B)?**
  Resolution proposed: **`investigate.md`** (Alt A). Resolves latent collision between reference-file name and per-feature artifact name; cleaner long-term naming; rename cost is contained to ~3 cross-references in refine SKILL.md plus plugin-mirror auto-regen. Defer final confirmation to Spec §4 (User Approval) — the user may prefer B for link-continuity reasons.

- **Q2: Inner `clarify→research` phase_transition event — keep, drop, or rename?**
  Resolution proposed: **drop**. lifecycle_start event already marks refine's entry; the inner transition no longer corresponds to a real boundary; keeping a phantom event for back-compat is dishonest and noisy. Lifecycle SKILL.md lines 248–256 need a small edit removing only the `clarify→research` template; `research→specify` and `specify→plan` are unchanged. Defer final confirmation to Spec.

- **Q3: Section numbering in the merged file — preserve clarify's §1–§7 or full renumber?**
  Resolution proposed: **preserve clarify's §1–§7 intact**. Insert research's procedural content (Codebase Exploration, Critical-tier parallel research, Web Research) as §4a / §4b / §4c between §4 (Question Threshold) and §5 (Produce Output). This sidesteps the clarify-critic.md cascade entirely and keeps the question-gate prose at its current section number. Defer final confirmation to Spec.

- **Q4: Discovery skill — does the merge include any discovery-side changes?**
  Resolution: **No** (per user scope). Discovery's separate Clarify+Research is intentional and load-bearing for its different failure mode. The merged file will carry an explicit ADR-style header note locking this in. No follow-up ticket commitment in this spec.

- **Q5: Are new MUSTs needed to enforce the user-blocking gate post-merge?**
  Resolution: **No**. The existing positive-routing prose at `clarify.md:63` ("Wait for user answers before continuing") is sufficient; AskUserQuestion is the actual blocking mechanism; per CLAUDE.md MUST-escalation policy, new MUSTs require events.log F-row evidence which does not exist for this gate. Preserve existing language verbatim.

- **Q6: Token-savings claim — should the spec frame this as a token-budget win?**
  Resolution: **No**. Realistic savings is ~100–150 tokens per refine chain. Frame the value as **clarity-of-flow** (one cohesive pre-spec investigation surface) with token saving as secondary. Honest framing matters for the complexity/value gate in Spec §4.

## Considerations Addressed

(None — no `research-considerations` argument was passed to this invocation, and there were no `origin: alignment` findings in the clarify-critic event since the backlog item has no parent epic.)
