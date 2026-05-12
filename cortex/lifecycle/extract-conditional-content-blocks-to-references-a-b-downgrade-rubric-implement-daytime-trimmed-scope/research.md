# Research: Extract conditional content blocks to references/ (a-b-downgrade-rubric + implement-daytime — trimmed scope)

Backlog #179. Parent epic #172. Tier: complex. Criticality: high.

Scope under research: move two conditional content blocks out of the hot-path into dedicated `references/*.md` files —

- **Extract A**: `skills/lifecycle/references/implement.md` §1a Daytime Dispatch (lines 54–171, 118 lines on disk) → `skills/lifecycle/references/implement-daytime.md`
- **Extract B**: `skills/critical-review/SKILL.md` 8 worked examples for the A→B downgrade rubric (lines 229–277, ~49 lines on disk; the ticket's "212–260" span is wrong) → `skills/critical-review/references/a-b-downgrade-rubric.md`

Each parent gets explicit trigger prose so the reference is loaded only on the relevant code path. Goal: hot-path skill-context reduction without behavioral regression.

## Codebase Analysis

### Files that will change

**New canonical files** (auto-mirrored by `just build-plugin` into `plugins/cortex-core/skills/*/references/`):

- `skills/lifecycle/references/implement-daytime.md` — receives Extract A content
- `skills/critical-review/references/a-b-downgrade-rubric.md` — receives Extract B content
- Auto-mirrored to `plugins/cortex-core/skills/lifecycle/references/implement-daytime.md` and `plugins/cortex-core/skills/critical-review/references/a-b-downgrade-rubric.md`

**Modified files**:

- `skills/lifecycle/references/implement.md` — §1a (lines 54–171) replaced with a stub + trigger prose; line 46 (selection dispatcher: "proceed to §1a below") needs updating to point to the new file. Line 47 backreference likewise.
- `skills/critical-review/SKILL.md` — Worked examples 1–8 (lines 229–277) replaced with a 2–3-line pointer inside the synthesizer prompt template body. Must remain inside the `---`-bracketed template at lines 205/299 (the template is dispatched verbatim to the synthesizer subprocess).
- `tests/test_daytime_preflight.py` — `test_skill_contracts` (lines 315–416) reads `skills/lifecycle/references/implement.md` and searches §1a. The regex anchor at line 339 is **`r"### 1a\..*?(?=\n### )"`** (anchored on `### 1a.` followed by a sibling `### ` header). After extraction the section header pattern may not survive in the new file — see Adversarial Review failure mode #1 below.
- `tests/test_critical_review_classifier.py` — `_extract_synthesizer_template` (lines 195–212) and `test_synthesizer_rubric_deterministic` (line 215+) extract the synthesizer template and dispatch it via `claude -p --model opus`. The deterministic test uses a Trigger 1 (absent) fixture — Triggers 2/3/4 are unverified.

### Relevant existing patterns

**Trigger-prose placement in cortex's progressive-disclosure skills**:

Cortex uses **unconditional imperative pointers** in every existing reference call (verified via grep across `skills/`):

- `discovery/SKILL.md:31` — `**If no topic was provided**: read \`${CLAUDE_SKILL_DIR}/references/auto-scan.md\``
- `backlog/SKILL.md:30` — `Read \`${CLAUDE_SKILL_DIR}/references/schema.md\` when creating or validating items`
- `lifecycle/references/research.md:187` and `plan.md:247` — `Before proceeding, read and follow \`references/orchestrator-review.md\` for the \`research\` phase`
- `refine/SKILL.md:66` — `Read \`../lifecycle/references/clarify.md\` and follow its full protocol (§2–§7)`

Notation: skill-internal references use `${CLAUDE_SKILL_DIR}/references/X.md`; cross-skill references use relative paths (`../lifecycle/references/X.md`).

**No existing cortex skill uses**:
- A conditional `if X then read Y.md` pattern (closest precedent: discovery's bolded affordance label `**If no topic was provided**: read ...` — but the read is unconditional within the block).
- A `references/X.md` pointer **inside a sub-agent prompt template** dispatched via `claude -p`. Extract B as scoped would be the first such precedent in the codebase.

**Reference-file header convention** (skills/refine/references/clarify-critic.md, skills/discovery/references/auto-scan.md, all skills/lifecycle/references/*.md):

```
# {Phase Name}

{One-sentence summary of purpose}.

{Optional: "Runs only when..." or "Loaded when..." trigger condition sentence}.
```

No file currently has a frontmatter or explicit "trigger condition" callout box. The strongest precedent for a trigger sentence is `skills/discovery/references/auto-scan.md` line 5: "Runs only when `/cortex-core:discovery` is invoked with no topic argument."

### Integration points and dependencies

**Dual-source parity** (`tests/test_dual_source_reference_parity.py`):
- Auto-discovers via glob at lines 89–91: `skills/*/SKILL.md`, `skills/*/references/*.md`, `skills/*/assets/*.md`.
- `lifecycle` and `critical-review` are both in `cortex-core` plugin's SKILLS tuple (lines 49, 57). **No PLUGINS-dict edits needed.**
- Marginal cost per new reference file: 1 new pytest parametrize id (auto-discovered). 0 new test functions.

**Pre-commit drift hook** (`.githooks/pre-commit`):
- Phase 2 detects staged `skills/*` paths and sets `BUILD_NEEDED=1`.
- Phase 3 runs `just build-plugin`.
- Phase 4 runs `git diff --quiet plugins/$p/` per plugin (not per file).
- Marginal cost per new reference file: **0 new drift-check entries** (the check is per-plugin, not per-file).

**build-plugin recipe** (`justfile` lines 491–523):
- Uses `rsync -a --delete "skills/$s/" "plugins/$p/skills/$s/"` per skill.
- `--delete` means new files are auto-picked-up and removed files vanish from mirror.
- **Caveat**: the empty-to-populated `references/` directory transition for `critical-review` has no precedent in the codebase (critical-review has no `references/` subdir today). Behavior under `rsync --delete` for first-creation of a `references/` subdir is expected to work but is not validated by existing tests.

**Parity linter** (`bin/cortex-check-parity`, invoked by Phase 1.5 of the pre-commit hook): scans for `bin/cortex-*` references. **Not affected** — no `bin/` scripts added or removed.

**Contract-pinning test** (`tests/test_daytime_preflight.py::test_skill_contracts`): pins §1a content via grep gates against `skills/lifecycle/references/implement.md`. Required marker counts: `dispatch_id ≥2`, `30 iterations ≥1`, `implementation_dispatch ≥1`, `dispatch_complete ≥1`. The current §1a has 29 contract-marker occurrences. **This test is a hard dependency** of Extract A — see Adversarial failure mode #1 for the regex-anchor concern.

**Synthesizer-test contract** (`tests/test_critical_review_classifier.py::_extract_synthesizer_template` + `test_synthesizer_rubric_deterministic`): the template is extracted by `---` delimiters at lines 205/299. The deterministic test uses a Trigger 1 (absent) fixture, which would pass even without worked examples inline — see Adversarial failure mode #3.

### §1a duplication assessment (against `cortex_command/overnight/daytime_pipeline.py`)

Per Agent 1's reading (with Agent 5 corrections):

**Conceptually overlapping with `daytime_pipeline.py`** (~25–50% of §1a):
- §1a.i plan.md prerequisite check ↔ `run_daytime` lines 352–362
- §1a.ii double-dispatch guard (PID liveness) ↔ `_read_pid` / `_is_alive` (lines 367–381)
- §1a.iv Step 1 (mint UUID) ↔ `_check_dispatch_id` (line 268)
- §1a.iii active-session check (4-step Bash) ↔ `active_session.py` (or equivalent helper) — agent 5 identifies this as duplication
- §1a.vii outcome enumeration (merged/deferred/paused/failed/unknown) ↔ `daytime_result_reader`'s output schema

**Unique to §1a** (~50–75%):
- AskUserQuestion-based menu and routing (§1 lines 19–46)
- Overnight-concurrent guard against `~/.local/share/overnight-sessions/active-session.json` — pure skill-side prose
- Polling loop with user-pause-at-30-iterations (§1a.vi) — requires interactive AskUserQuestion
- `implementation_dispatch` and `dispatch_complete` event-log writes (§1a.v, §1a.viii) — main-session work, not subprocess work
- Tier-1/3 outcome-display prose (§1a.vii)

**Verdict**: §1a is NOT a thin shell over the Python module. Wholesale collapse to a Python-module pointer (Alternative B in Tradeoffs) loses ~50–75% of unique main-session orchestration content and frontally violates #177's contract-preservation rationale. The duplication framing in epic #172's audit is **partially correct but overstated**.

### Verification surface

**Extract A (daytime dispatch)**:
- `tests/test_daytime_preflight.py::test_skill_contracts` — 6 document invariants (a–f) on §1a content. After extraction, must update to read from `references/implement-daytime.md` (or split into two tests if Hybrid C path is chosen).
- Other `test_daytime_preflight.py` tests verify Python-helper behavioral contracts (`daytime_dispatch_writer`, `daytime_result_reader`) — unaffected.
- Ticket §70: manual transcript check — "A fresh daytime-dispatch implement-phase run correctly loads references/implement-daytime.md."
- No automated trigger-precision test exists.

**Extract B (a-b-downgrade-rubric)**:
- `test_synthesizer_rubric_deterministic` covers Trigger 1 only. Triggers 2/3/4 are **unverified by automated tests**.
- The deterministic test would pass even WITHOUT worked examples inline (Trigger 1 is mechanically detectable from the rubric bullets alone). It gives false confidence about the safety of the extraction.
- The synthesizer subprocess receives the prompt as a single blob with no `${CLAUDE_SKILL_DIR}`, no progressive-disclosure loader. For Extract B to save tokens at synthesizer time, either (a) the orchestrator inlines the rubric file at dispatch time (loses synthesizer-side savings, preserves only main-context savings), or (b) the sub-agent reads via Read tool with an absolute path (requires Read in `allowed_tools` and a path resolvable in sub-agent CWD — no existing cortex pattern does this).
- No manual transcript check is in the ticket's verification list for Extract B.

### Validation against ticket numbers

- Ticket claim "8 worked examples ~line 212–260" → **REFUTED**. Actual span is lines 229–277 (Agent 1) or 229–281 with trailing blank (Agent 4). ~49–53 lines.
- Ticket claim "§1a spans lines 54–171" → **CONFIRMED**.
- Ticket claim "implement.md ~286 post-#177" → **APPROXIMATE**. Actual current state is 302 lines (16 lines over the ticket's expected post-#177 baseline; either the trim was looser than estimated or subsequent commits added small content).
- Ticket claim "critical-review/SKILL.md 365 lines" → **OFF-BY-4**. Actual: 369 lines.
- Ticket claim "12 mirror entries; 6 new pre-commit drift checks" (trimmed scope risk language) → **FACTUALLY WRONG for the 2-extraction trimmed scope**. Actual marginal cost: 2 mirror files (auto-rsync'd), 2 new pytest parametrize ids (auto-discovered), **0 new drift checks** (drift is per-plugin, not per-file), 0 new test code. The "12 / 6" framing applied to the original 6-extraction scope and was not recalibrated when the scope trimmed to 2.

## Web Research

### Anthropic's published guidance on SKILL.md progressive disclosure

- [Skill authoring best practices (docs.claude.com)](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — definitive source:
  - **500-line cap is explicit**: "Keep SKILL.md body under 500 lines for optimal performance. If your content exceeds this, split it into separate files."
  - **Three documented progressive-disclosure patterns**: (1) high-level guide with reference pointers ("**Form filling**: See [FORMS.md] for complete guide"), (2) domain-specific organization (`reference/finance.md` vs `reference/sales.md` — Claude routes by descriptions), (3) conditional details with **bolded affordance labels** ("**For tracked changes**: See [REDLINING.md]").
  - **Critical constraint**: "Avoid deeply nested references. Keep references one level deep from SKILL.md." Nested references trigger `head -100` partial reads.
  - **TOC requirement** for any reference file >100 lines.
  - **Conditional workflow pattern** uses bold labels at decision points ("**Creating new content?** → Follow 'Creation workflow' below"), NOT imperative if-then.
  - **MUST vs soft**: doc shows both. Iteration example explicitly suggests "using stronger language like 'MUST filter' instead of 'always filter'" when soft phrasing observably fails. Aligned with cortex's OQ3 escalation policy.
- [Equipping agents with Agent Skills (Anthropic engineering)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — three-level system framing; emphasizes Claude *chooses* to read referenced files based on task relevance, not on explicit author triggers.
- [Anthropic skills repo (skill-creator SKILL.md)](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) — uses plain "See `references/schemas.md` for the full schema" pointers; explicit rule: "Information should live in either SKILL.md or references files, **not both**."

### Opus 4.7 instruction-following / literalism — external evidence

The project's "Opus 4.7 literalism" framing is **empirically grounded**:

- [What's new in Claude Opus 4.7 (official)](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7): *"More literal instruction following, particularly at lower effort levels. The model will not silently generalize an instruction from one item to another, and will not infer requests you didn't make."* Also: *"Fewer tool calls by default, using reasoning more. Raising effort increases tool usage."* Directly supports the project's effort-first escalation policy.
- [Best practices for using Claude Opus 4.7 with Claude Code (Anthropic)](https://claude.com/blog/best-practices-for-using-claude-opus-4-7-with-claude-code): "positive examples of the voice you want work better than negative 'Don't do this' instructions"; for tool usage, "explicitly describe when and why the tool should be used."
- [Simon Willison — System-prompt diff 4.6 vs 4.7](https://simonwillison.net/2026/Apr/18/opus-system-prompt/) — independent confirmation; new `tool_search` directive; "make a reasonable attempt now, not to be interviewed first."
- [SuperClaude Framework issue #554](https://github.com/SuperClaude-Org/SuperClaude_Framework/issues/554) — concrete reproduction: under 4.7, a YAML anti-pattern block (showing "wrong behavior" indented as a peer to rules) gets executed literally as a valid behavioral branch. **Direct evidence that 4.7 literalism breaks instruction structures that 4.6 handled gracefully.** Particularly relevant to Extract B, where a rubric embedded inside a sub-agent prompt template carries the same risk.
- [claudefa.st — Opus 4.7 best practices](https://claudefa.st/blog/guide/development/opus-4-7-best-practices): *"Reliability is bimodal. 4.7 is excellent with constrained, well-specified prompts and frustrating with vague ones."*

### Verification approaches for prompt-conditional behavior

- [promptfoo Agent Skills integration](https://www.promptfoo.dev/docs/integrations/agent-skill/) — **direct match for the verification question**. Two distinct eval types: (1) **trigger precision** (does Claude activate the right skill?) — Anthropic's `skill-creator` plugin ships a Python eval system run via `python run_eval.py --eval-set agents/eval-set.json --skill-path ./skills/<skill>`; (2) **quality eval** for outputs once triggered — `npx promptfoo eval`. Promptfoo normalizes Claude Skill tool invocations into `response.metadata.skillCalls` so a `skill-used` assertion can verify activation. **This is the missing-verification piece for the rubric extraction.**
- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — pass/fail outcome tests + transcript grading via model-based rubric graders.
- [Anthropic skill-creator plugin (anthropics/skills)](https://github.com/anthropics/skills/) — ships the eval harness for skill-trigger verification.

### Known patterns and anti-patterns

**Endorsed**:
- Bolded affordance labels at decision points (Pattern 3 in Anthropic best-practices doc) — closest match for cortex's user-gated daytime-dispatch case.
- Domain-organized references (Pattern 2) where Claude routes from a descriptive table.
- Keep references one level from SKILL.md; reference files >100 lines need a TOC.
- For observed-failure cases, Anthropic's iteration loop endorses upgrading "always X" to "MUST X" — consistent with cortex's OQ3 effort-first-then-MUST escalation in CLAUDE.md.

**Anti-patterns**:
- **Nested references** trigger partial reads (`head -100`). A two-hop chain (`implement.md` → `references/implement-daytime.md` → `daytime_pipeline.py`) would create this anti-pattern. Specifically warns against the thin-pointer collapse for §1a.
- **Anti-example blocks inside instruction structures** (SuperClaude #554) — 4.7 reads them literally as alternate branches. Directly relevant to Extract B: a rubric embedded in a synthesizer prompt template, if it contains "wrong-output examples," is at risk of being executed under 4.7.
- **Vague descriptions** under-trigger; Anthropic's own guidance is to be deliberately "pushy."
- **Negative instructions** ("don't do X") are unreliable under 4.7; convert to positive form.

## Requirements & Constraints

### Relevant rules and their interaction with this work

**SKILL.md 500-line cap** (`requirements/project.md` line 30; enforced by `tests/test_skill_size_budget.py`): *"Default remediation is extracting content to `skills/<name>/references/`; a marker is appropriate only when the SKILL.md inherently exceeds the cap."* This is the **only** requirements-file rule that endorses the extract-to-references pattern. It frames extraction as **cap-remediation**, not as an independent hot-path-context-reduction goal. Neither target file (302, 369) is over the cap. Project-level requirements do not separately mandate hot-path context reduction; that goal originates in epic #172's discovery audit.

**SKILL.md-to-bin parity enforcement** (`requirements/project.md` line 29): N/A — this work adds no `bin/` scripts.

**Workflow trimming** (`requirements/project.md` line 23): *"Hard-deletion is preferred over deprecation notices, tombstone skills, or env-var soft-deletes when the surface has zero downstream consumers."* Relevant only if §1a's user-facing affordance were removed wholesale; it has a runtime consumer (a daytime-dispatch run from the AskUserQuestion menu), so wholesale removal is off the table. Combined with the user's memory entry "user-facing affordances are load-bearing even when artifact production is empty," this is a brake against classifying §1a as ceremonial before identifying its user-blocking gate behavior.

**Complexity** (`requirements/project.md` line 19): *"Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."* Applies directly to the relocate-vs-thin-pointer question for §1a and the proceed-vs-defer question for Extract B.

**Quality bar** (`requirements/project.md` line 21): *"Tests pass and the feature works as specced."* Forces the verification updates that follow from Extract A's regex-anchor coupling and Extract B's deterministic-test-coverage gap.

**multi-agent.md — Agent Spawning**: sub-agents do NOT inherit `${CLAUDE_SKILL_DIR}` resolution. The synthesizer prompt template is substituted into the dispatch payload at `critical-review/SKILL.md` Step 2d (lines 201–299) and the sub-agent reads the prompt as a single blob. **An "if X read references/Y.md" trigger inside a sub-agent prompt template does NOT work the same way as it does in main-conversation context** — the parent dispatch must either (a) inline the rubric file's contents into the prompt at dispatch time, or (b) ensure the sub-agent has file-read tools and the path resolves in its CWD.

**No automatic gate verifies trigger-prose pointers** from a parent SKILL.md to a new references/ file for behavioral correctness; verification is transcript-only.

### CLAUDE.md policies that interact

**MUST-escalation policy** (CLAUDE.md lines 51–59): Trigger-prose phrasing should default to **soft positive-routing language** under the post-Opus-4.7 policy. A directive like *"If the user selects 'Implement in autonomous worktree', read `references/implement-daytime.md` and follow its protocol"* is already in positive-routing soft form. Adding MUST/REQUIRED language requires: (a) an events.log F-row showing Claude skipped the soft form, and (b) an `effort=high` dispatch result showing the soft form fails. **No MUST-escalation is anticipated for this work** — the trigger prose is positive-routing by nature.

**Tone policy** (CLAUDE.md lines 61–65): N/A.

**CLAUDE.md 100-line cap** (CLAUDE.md line 67): CLAUDE.md is at 68 lines; no risk. `docs/policies.md` not required.

### Scope boundaries

- **In scope** per `project.md` lines 43–53: "AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)" — this work sits inside the skills/ tree.
- **Out of scope** per `project.md` lines 55–59: not applicable.

## Tradeoffs & Alternatives

Six candidate approaches considered (numbers reference Agent 4's labels):

**Alt A — Wholesale relocation (ticket's stated remedy)**: move §1a verbatim to `implement-daytime.md`; move worked examples to `a-b-downgrade-rubric.md`. Maximum headline savings (~113 + ~49 = ~162 lines off hot path) but the savings on the binding paths (daytime-dispatch loads the reference; synthesizer re-loads the rubric) are roughly neutral — the non-illusory benefit is reduced lifecycle-context bloat on the non-autonomous-worktree path. Updates `test_skill_contracts` regex anchor (`### 1a.` → header that survives in the new file). Adds Extract B's sub-agent trigger-reliability risk.

**Alt B — Thin pointer for §1a + wholesale for Extract B**: collapse §1a to a 5-line pointer at `daytime_pipeline.py`. **Frontally violates #177's contract-preservation contract** (which explicitly requires guards, dispatch_id semantics, outcome map, polling-pause behavior, event schemas to remain in skill prose). Adversarial review and the duplication-assessment data both reject this option — Python module docstrings are not in Claude's context on the orchestrator path, and §1a is 50–75% unique main-session orchestration not implemented by the Python module.

**Alt C — Hybrid for §1a (keep contract inline, extract recipe)**: split §1a roughly down the middle. Keep guards / dispatch_id semantics / outcome map / polling-pause / event schemas inline; move procedural step-by-step recipe to `implement-daytime.md`. Smaller savings (~50–60 lines moved). **Split-point ambiguity** is the cost: the boundary between "contract" and "recipe" is judgment-dependent and re-fires on every subsequent edit. Parallels the deferred state-init.md split that the ticket itself called too risky.

**Alt D — Status quo for Extract B + variant for A**: leave the 8 worked examples inline in the synthesizer prompt template; pursue Alt A or Alt C for §1a only. Eliminates Extract B's sub-agent-trigger-reliability risk entirely. 1 fewer dual-source pair. Synthesizer cost is ~0 because the synthesizer would re-load the rubric anyway on its dedicated path.

**Alt E — Drop both extractions entirely**: zero behavioral risk; forfeits all savings. Reconciles the asymmetry the clarify-critic raised (why are these 2 kept-in while 4 sibling extractions are deferred on the same risk class?) by treating them the same way. The cost of dropping is ~1/3 of epic #172's already-trimmed ~325-line target.

**Alt F — Extract A via hybrid (Alt C-style) + defer Extract B**: captures the larger savings at the lower risk. Adversarial review challenges "defer" as soft-punt that pays the analysis cost twice; recommends instead recording a hard precondition ticket (e.g., "add Trigger-2/3/4 deterministic tests for the A→B downgrade rubric") before Extract B becomes viable.

### Recommended approach (with adversarial-review correction)

Two surviving candidates after the adversarial review:

**Path 1 — In-place trim of §1a + drop Extract B with a precondition ticket** (Adversarial M1+M2 option b):
- Do NOT relocate §1a. Instead, trim §1a in place: collapse helper-module-contract documentation that is mirrored in Python (the 25–50% conceptual overlap with `daytime_pipeline.py`) to pointer sentences, keeping the unique skill-side orchestration intact. Net savings: ~30–50 lines off implement.md without creating a new dual-source pair.
- Drop Extract B from #179's scope. Open a precondition backlog ticket: "Add deterministic tests for Triggers 2 (restates), 3 (adjacent with/without straddle), and 4 (vague) of the A→B downgrade rubric in `test_critical_review_classifier.py`." Without that test, Extract B is unverifiable; with it, Extract B becomes a candidate after the test lands.
- Largest behavioral safety margin; smallest blast radius.

**Path 2 — Wholesale relocation for §1a + drop Extract B with a precondition ticket** (Adversarial M1+M2 option a):
- Relocate §1a wholesale to `implement-daytime.md`. **Required: update `test_skill_contracts`'s regex anchor at `tests/test_daytime_preflight.py:339` from `### 1a.` to a top-level header that survives in the new file (e.g., `# Daytime Dispatch (Alternate Path)` as the new file's H1).** Re-target the test to read `references/implement-daytime.md`. Update the line-46 / line-47 backreferences in implement.md.
- Drop Extract B with the same precondition-ticket gate as Path 1.
- Larger headline savings (~113 lines off implement.md) but bigger blast radius (regex anchor, test re-targeting, the empty-to-populated `references/` directory transition is unvalidated — though only relevant to Extract B which is being dropped).

**Recommendation**: **Path 1 (in-place trim + drop Extract B with precondition ticket)** is the safer move; **Path 2 is the larger-savings alternative**. The decision between them is the central spec-time question.

The Hybrid Alt C (split §1a's contract vs recipe) is **not recommended** — the split-point ambiguity that the ticket itself cited as the reason to defer the state-init extraction applies to §1a too. Either keep §1a whole (Path 1) or move it whole (Path 2), not split it.

## Adversarial Review

Net failure modes surfaced by independent challenge of the other four agents' findings:

1. **`test_skill_contracts` regex anchor `### 1a.` is a hidden coupling.** At `tests/test_daytime_preflight.py:339`, the test anchors on the literal `### 1a.` header and requires a sibling `### ` header to terminate. If §1a is wholesale-relocated, the new file's H1 is likely `# Daytime Dispatch` (no `### 1a.` substring) and there is no sibling `### ` boundary. The test fails. Mitigation: **rename the anchor to a header that survives in the new file** (e.g., re-shape the new file's structure to retain a `### 1a.` sub-heading, or update the regex to `## Daytime Dispatch` etc.).

2. **Extract B is structurally embedded mid-prompt, not a trailing block.** Worked examples (lines 229–277) sit between Step 3's rubric body (line 220) and Step 4 (line 278) with no blank line. Any inserted trigger-prose pointer must live inside the rubric body, inside the `---`-bracketed dispatch blob. The dispatched sub-agent receives the prompt as a single blob and can resolve neither `${CLAUDE_SKILL_DIR}` nor relative paths.

3. **The deterministic synthesizer test gives false confidence.** `test_synthesizer_rubric_deterministic` (line 216) uses a Trigger 1 (absent) fixture — the lowest-bar case. Trigger 1's bullet text survives at line 222 even after worked-examples extraction, so the test passes WITHOUT the worked examples. The worked examples are most load-bearing for Triggers 2, 3, 4 (the cases Opus 4.7's literalism is most fragile on). **A passing test does not validate the extraction's safety.**

4. **Opus 4.7 literalism interacts badly with conditional-load prose.** With `effort=low` (lifecycle's default for many calls), 4.7 is both more literal AND more likely to eagerly pre-fetch references because it reads "follow its protocol" as a precondition. The conditional-load discipline is **structurally fragile** in a way no agent named.

5. **The empty-to-populated `references/` directory transition for `critical-review` is unvalidated.** `build-plugin` uses `rsync -a --delete`; the first-creation of a `references/` subdir under a skill that doesn't currently have one is unprecedented in the codebase. Expected to work; not test-covered. Mitigation M4: add a directory-presence assertion to `test_dual_source_reference_parity.py`.

6. **The "75% unique" claim about §1a undercounts duplication.** Three additional duplications: polling-loop iteration counter (§1a.vi), active-session check (§1a.iii vs `active_session.py`-equivalent), outcome enumeration (§1a.vii vs `daytime_result_reader`'s schema). Truly unique share is closer to 40–50%, which strengthens the in-place-trim case (Path 1) over wholesale relocation (Path 2).

7. **Anti-pattern: `references/X.md` pointers inside sub-agent prompt templates have no cortex precedent.** Extract B would establish one. Future readers will mis-generalize. Mitigation M5: if Extract B ever proceeds, document the dispatched-prompt inlining mechanism as a deliberate exception.

8. **Asymmetric treatment of Extract A and Extract B in the same spec muddies policy.** If A proceeds and B drops, the spec must include explicit reasoning ("sub-agent prompt templates are NOT eligible for the same extraction pattern as skill-side content"), not just "we did the easy one."

9. **Phase-boundary content is hardest to extract.** §1a documents the boundary between "user steered" execution (implement on current branch) and "autonomous" execution (daytime worktree). The documentation captures the BOUNDARY, not either of the two regimes — splitting weakens it. This is the "user-facing affordances are load-bearing" memory entry applied at phase-boundary granularity. Reinforces the case for Path 1 (in-place trim) over relocation.

## Open Questions

1. **Scope shape**: Path 1 (in-place trim of §1a + drop Extract B with precondition ticket), Path 2 (wholesale relocation of §1a + drop Extract B with precondition ticket), or revive the ticket's original scope (both extractions) and absorb the adversarial-review risks?
   - **Resolution (proposed)**: pending user confirmation at spec phase entry. Research-side recommendation is Path 1: behavioral-safety margin, no regex-anchor risk, no phase-boundary splitting, respects #177's contract-preservation contract, still advances epic #172's hot-path goal by ~30–50 lines off implement.md. Path 2 is the larger-savings alternative if the user prefers the bigger cut and is willing to take on the test_skill_contracts regex-anchor update.
2. **Extract B disposition**: drop with a precondition ticket (Adversarial M1), defer in-place (pays re-litigation cost), or proceed despite the verification gap?
   - **Resolution (proposed)**: pending user confirmation. Research-side recommendation is **drop with a precondition ticket** ("Add deterministic tests for Triggers 2 (restates), 3 (adjacent with/without straddle), and 4 (vague) of the A→B downgrade rubric in `test_critical_review_classifier.py`"). Without that test, Extract B's deterministic safety net is a false-confidence Trigger-1-only check, and the sub-agent-prompt-template trigger-prose pattern would be a first-in-codebase precedent.

The following questions are **deferred to spec phase** — their answers depend on the Q1/Q2 resolution above and belong in the spec's structured interview, not the research artifact:

3. **If Path 2 chosen**: how to update `test_skill_contracts`'s regex anchor at `tests/test_daytime_preflight.py:339` (rename anchor; split test; restructure new file to retain `### 1a.` substring). **Deferred** — only fires if Path 2 is chosen.
4. **Trigger-prose phrasing** (if any extraction proceeds): Anthropic-style bolded affordance label vs cortex-precedent unconditional imperative. **Deferred** — both are positive-routing acceptable forms; the spec will pick one with the user.
5. **Directory-transition test** (Adversarial M4) for the empty-to-populated `references/` subdir: include in this ticket, defer to a separate ticket, or skip. **Deferred** — only relevant if Extract B proceeds (Q2 resolution forecloses it under the recommended drop-with-precondition disposition).
6. **Verification additions**: manual transcript check for Path 2. **Deferred** — the spec will land the verification list based on the chosen path.

## Considerations Addressed

- **Investigate whether §1a is more cleanly addressed as a thin pointer to `cortex_command/overnight/daytime_pipeline.py`** — Investigated. §1a has 25–50% conceptual overlap with the Python module but 50–75% unique main-session skill-side orchestration (AskUserQuestion menu, overnight-concurrent guard against active-session.json, polling-loop user-pause, event-log writes, three-tier outcome display). A thin-pointer collapse would lose the unique content AND frontally violate #177's contract-preservation rationale (which is enforced by `test_skill_contracts`'s grep gates against `implement.md`). **Resolved**: thin pointer is rejected; choices reduce to in-place trim, wholesale relocation, or status quo.

- **Discover existing convention for trigger-prose placement and reference-file headers** — Investigated. Cortex uses unconditional imperative pointers (`Read ${CLAUDE_SKILL_DIR}/references/X.md and follow ...`); no conditional `if X then Y` pattern exists; no reference-file-pointer-inside-sub-agent-prompt-template pattern exists. Anthropic's official guidance recommends bolded affordance labels at decision points. Reference-file headers are H1 + 1-paragraph summary + optional "Loaded when..." sentence (precedent: `skills/discovery/references/auto-scan.md` line 5).

- **Validate on-disk span and baselines** — Investigated. Ticket's "212–260" is wrong; actual worked-examples span is 229–277 (~49 lines). Baselines: `implement.md` = 302 lines (ticket said ~286), `critical-review/SKILL.md` = 369 lines (ticket said 365). Verification targets recompute: post-extraction implement.md would land ~232 (wholesale) or ~252–272 (hybrid/in-place-trim); critical-review/SKILL.md would land ~320 if Extract B proceeds, unchanged if dropped.

- **End-to-end verification of the a-b-downgrade-rubric trigger** — Investigated. Significant gap: the deterministic test uses a Trigger 1 fixture, which passes even without worked examples inline. Triggers 2/3/4 are unverified by automated tests. The synthesizer subprocess has no `${CLAUDE_SKILL_DIR}`, no progressive-disclosure loader. Recommended mitigation (Adversarial M1): drop Extract B from #179 and open a precondition ticket for Trigger-2/3/4 deterministic tests.

- **Auto-discovery in `test_dual_source_reference_parity.py`** — Investigated and CONFIRMED. The test's `_discover_pairs()` glob (lines 88–91) picks up new `skills/*/references/*.md` without registration. The PLUGINS dict already contains `lifecycle` and `critical-review` under cortex-core (lines 49, 57). Pre-commit drift check is per-plugin not per-file. Marginal cost per new reference file: 1 new pytest parametrize id, 0 new test functions, 0 new drift checks. The ticket's "12 mirror entries / 6 drift checks" framing is factually wrong for the 2-extraction trimmed scope (the framing applied to the original 6-extraction scope). One caveat: the empty-to-populated `references/` directory transition for `critical-review` is unvalidated by existing tests (only relevant if Extract B proceeds).
