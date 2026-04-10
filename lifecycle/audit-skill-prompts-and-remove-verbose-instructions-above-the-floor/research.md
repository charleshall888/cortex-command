# Research: Audit skill prompts and remove verbose instructions above the floor

**Clarified intent**: Audit SKILL.md files in 9 skills (lifecycle, discovery, critical-review, research, pr-review, overnight, dev, backlog, diagnose) and remove verbose instructions that don't earn their place — using the #050 output floors as the formal rubric for `lifecycle` and `discovery`, and the stress-test principle ("would Opus 4.6 produce acceptable output without this instruction?") for the other 7. In both branches, preserve instructions consumed by downstream skills, approval gates, hooks, or overnight observability surfaces. Uncertain cases are flagged in the audit output for later resolution.

## Epic Reference

Epic research: `research/agent-output-efficiency/research.md`. This ticket is the **stress-test gate (DR-6)** from the epic — before adding new output constraints (DR-1, DR-2), empirically test whether removing verbose-by-default instructions produces acceptable output from Opus 4.6. Other tickets in the epic (#053 subagent output formats, #054+ compression) depend on #052's findings to decide whether further intervention is needed.

## Codebase Analysis

### Files in scope (9 SKILL.md + references)

| Skill | SKILL.md | Reference files |
|-------|----------|-----------------|
| lifecycle | `skills/lifecycle/SKILL.md` | `references/{clarify,clarify-critic,research,specify,plan,implement,review,complete,orchestrator-review}.md` |
| discovery | `skills/discovery/SKILL.md` | `references/{clarify,research,decompose,orchestrator-review}.md` |
| critical-review | `skills/critical-review/SKILL.md` | (none) |
| research | `skills/research/SKILL.md` | (none) |
| pr-review | `skills/pr-review/SKILL.md` | `references/protocol.md` |
| overnight | `skills/overnight/SKILL.md` | (none) |
| dev | `skills/dev/SKILL.md` | (none) |
| backlog | `skills/backlog/SKILL.md` | `references/schema.md` |
| diagnose | `skills/diagnose/SKILL.md` | (none) |

Total corpus: ~2185 lines across the 9 SKILL.md files (reference files add more).

### Integration points (downstream consumers)

- **`claude/overnight/report.py`**: reads events.log for session start, feature transitions, completions; parses `phase_transition` event names.
- **`claude/pipeline/metrics.py`**: parses `phase_transition` events to derive phase durations (line 21).
- **Dashboard** (`claude/dashboard/`): reads `overnight-state.json`, `pipeline-events.log`, per-feature `events.log`, `plan.md`, `active-session.json` — schemas are load-bearing (observability.md:31).
- **Morning report** (`claude/overnight/report.py`): constructs `morning-report.md` from events.log, state.json, deferral files.
- **`skills/morning-review/references/walkthrough.md`**: human-facing consumer of phase transition narrative fields (Decisions/Scope delta/Blockers/Next). **Detected by adversarial review — grep across Python code does NOT catch this consumer.**
- **`/refine`** delegation: reads lifecycle artifacts, runs Clarify→Research→Specify.
- **Overnight runner**: reads `lifecycle/{slug}/research.md`, `lifecycle/{slug}/spec.md` for feature eligibility.
- **Complexity escalation checks** (lifecycle/SKILL.md lines 245-258): count bullet items under `## Open Questions` in research.md and `## Open Decisions` in spec.md. Removing these section headers would silently break escalation.
- **Hooks**: `update-item.py`, `create-item.py` consume backlog frontmatter schema.

### Per-skill candidate removals (REVISED after adversarial review)

Each candidate below has an initial verdict from codebase analysis AND a counter-argument from adversarial review. The final spec phase will resolve each to a definitive keep/remove/flag verdict. Many codebase-phase "REMOVE" verdicts are overturned by adversarial analysis.

#### lifecycle (#050 floor rubric)

- **L1** — Line 75: "If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase."
  - Initial: REMOVE (Opus 4.6 would naturally report phase on resume)
  - Counter: This may be the only instruction that triggers user-visible phase reporting; without it the skill may resume silently. Verify it's not the single source of user feedback on resume.
  - **Status**: Flag for spec phase

- **L2** — Line 196: "If `epic_research_path` was found, announce: 'Found epic research at `{epic_research_path}` — will use as background reference...'"
  - Initial: REMOVE (purely informational announcement)
  - Counter: **Defense-in-depth against frontmatter poisoning.** The announcement is a user-visible checkpoint before loading a file path from backlog frontmatter. Removing it trades a single line for a silent path read on a malicious or mistaken `discovery_source:` entry.
  - **Status**: Keep (preserve security-adjacent disclosure)

- **L3** — Lines 272-278: "After completing a phase artifact, announce the transition and proceed... Between phases, include these minimum fields in the transition summary: Decisions / Scope delta / Blockers / Next"
  - Initial: UNCERTAIN (whether "announce" is separate from event logging)
  - Counter: The four floor fields lack Python consumers but ARE consumed by morning-review/walkthrough.md and human readers of events.log. "Announce the transition" IS the floor rubric. Keep intact.
  - **Status**: Keep

- **L4** — Line 280: "If the user invokes `/lifecycle <phase>` to jump to a specific phase, honor the request but warn if prerequisite artifacts are missing"
  - Initial: REMOVE (warn-on-missing-prerequisites as error handling)
  - Counter: **Safety rail.** Only instruction preventing silent plan-without-research states when user jumps phases. Removing invites entering Plan without research.md present.
  - **Status**: Keep

#### discovery (#050 floor rubric)

- **D1** — Line 62: "commit the `research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically"
  - Initial: UNCERTAIN
  - Counter: This IS the per-skill-calibrated phase transition floor for discovery ("discovery (phase transitions — per-skill calibration via #052)" in output-floors.md). "Summarize findings" is the lightweight calibration.
  - **Status**: Keep (this is the floor)

- **D2** — Line 71: discovery→lifecycle contract documentation
  - Initial: PRESERVE
  - **Status**: Keep

#### critical-review (stress-test rubric)

- **CR1** — Lines 87-89: Distinct-angle rule ("Each angle must be distinct... reference specific sections")
  - Initial: REMOVE (Opus 4.6 naturally derives distinct angles)
  - Counter: **Load-bearing for the skill's differentiator.** The distinct-angle rule is the contract that makes parallel critical-review valuable over `/devils-advocate` ("More thorough because parallel agents remove anchoring bias"). Sub-agents may run on Sonnet, not Opus 4.6.
  - **Status**: Keep

- **CR2** — Lines 172-173: "Do not soften or editorialize"
  - Initial: REMOVE (Opus 4.6 naturally delivers direct adversarial feedback)
  - Counter: **Fights Opus 4.6 warmth training.** Anthropic explicitly describes Opus 4.5/4.6 as "warmer, more conciliatory, more balanced." The instruction counteracts the baseline — it earns its place precisely because baseline moved away from it. Removing invites the orchestrator to round off adversarial edges on display.
  - **Status**: Keep

#### research (stress-test rubric)

- **R1** — Lines 59-61 / injection-resistance instruction (appears 6× total)
  - Initial: PRESERVE
  - Counter: **Security-critical. Out of scope entirely.** Do not remove, consolidate, or reword injection instructions in this audit. Defer to a security-reviewed follow-up.
  - **Status**: Keep (explicit scope exclusion)

- **R2** — Lines 177-184: Empty/failed agent handling
  - Initial: REMOVE (Opus 4.6 naturally reports missing findings)
  - Counter: These define the exact fallback string format (`⚠️ Agent [N] returned no findings`). Removing loses output determinism. Control flow, not prose.
  - **Status**: Keep

- **R3** — Lines 186-188: Contradiction handling under `## Open Questions`
  - Initial: REMOVE
  - Counter: **This instruction feeds the Spec phase's Open Questions section**, which lifecycle's complexity escalation counts. Load-bearing.
  - **Status**: Keep

#### pr-review (stress-test rubric)

- **PR1** — Line 39: "The main agent presents the synthesis output and keeps all prior agent outputs available for follow-up questions."
  - Initial: REMOVE
  - Counter: Instructs the orchestrator not to discard context after synthesis. Removing invites orchestrator context compaction to drop prior outputs.
  - **Status**: Flag for spec phase (moderate confidence keep)

#### overnight (stress-test rubric)

- **O1** — Lines 83-86: "Regenerate the backlog index so that feature selection... operates on up-to-date metadata."
  - Initial: REMOVE (explanation is verbose)
  - Counter: Without the "so that" the model may skip the step under time pressure. Justifications prevent helpful-optimization-away.
  - **Status**: Flag for spec phase

- **O2** — Lines 149-150: Batch Spec Review preamble
  - Initial: REMOVE
  - Counter: Same as O1 — removal loses justification that prevents step removal.
  - **Status**: Flag for spec phase

#### dev (stress-test rubric)

- **DV1** — Lines 89-90: "(This is a conversational suggestion — lifecycle runs its own full assessment in Step 3)"
  - Initial: REMOVE (parenthetical caveat)
  - Counter: Cross-check line numbers — ensure the criticality heuristic table (load-bearing for downstream /lifecycle invocation) is not conflated with conversational preamble.
  - **Status**: Flag for spec phase

- **DV2** — Lines 116-118: Conversational template for criticality suggestion
  - Initial: REMOVE
  - Counter: Verify no downstream consumer.
  - **Status**: Flag for spec phase

#### backlog (stress-test rubric)

- **B1** — Line 40: "present the available actions via `AskUserQuestion`"
  - Initial: REMOVE (Opus 4.6 naturally prompts for missing input)
  - Counter: **Output-channel directive, not prose.** Instructs use of the structured `AskUserQuestion` tool vs. free-text listing. Removing breaks the UX contract.
  - **Status**: Keep

- **B2** — Lines 93-94: "use a second `AskUserQuestion`"
  - Initial: REMOVE
  - Counter: Same as B1 — output channel directive.
  - **Status**: Keep

#### diagnose (stress-test rubric)

- **DG1** — Lines 13-14: "ALWAYS find root cause before attempting fixes"
  - Initial: PRESERVE (core principle)
  - Counter: Agreed, but note the inconsistency with DG2 — both are exhortations of the same character.
  - **Status**: Keep

- **DG2** — Lines 24-26: "Don't skip past errors, read stderr completely"
  - Initial: REMOVE (Opus 4.6 naturally reads errors)
  - Counter: **Diagnose is invoked by lifecycle during implement retries — sub-agent audience may be Sonnet/Haiku, not Opus 4.6.** The "read stderr completely" targets the time-pressured, context-compacted retry model, not the Opus orchestrator.
  - **Status**: Keep

- **DG3** — Lines 82-92: Competing-hypotheses team offer conditions
  - Initial: REMOVE (offer language is verbose)
  - Counter: **Control flow gates, not prose.** Env var availability check, user confirmation gate, "skip entirely when running autonomously" — the last prevents overnight runner hanging on a phantom confirmation prompt.
  - **Status**: Keep

### Revised removal candidates after adversarial review

After the adversarial pass, the candidates actually worth removing reduce significantly. The dominant finding is that most "verbose" instructions are load-bearing in ways grep-based detection missed:
- Sub-agent prompts dispatched to Sonnet/Haiku (not Opus 4.6)
- Control flow gates that look like prose
- Output-channel directives (AskUserQuestion, file writes)
- Defense-in-depth for frontmatter poisoning
- Counteracting Opus 4.6 warmth/conciliatory training
- Justifications that prevent helpful-optimization-away
- Morning-review human-facing consumers of events.log narrative fields

**High-confidence removal candidates** (after adversarial review):
- *None with high confidence.* Every candidate has at least one counter-argument worth surfacing in the spec interview.

**Flag-for-spec candidates** (worth discussing with user in spec phase):
- lifecycle L1 (resume phase reporting)
- pr-review PR1 (prior-outputs context)
- overnight O1, O2 (rationale preambles)
- dev DV1, DV2 (conversational caveats)

**Explicit keep decisions** from adversarial review:
- All security/injection instructions
- All output-channel directives (AskUserQuestion)
- All control flow gates
- All defense-in-depth disclosures
- Critical-review anti-warmth instructions
- Diagnose sub-agent-targeted methodology
- Floor field names (human consumer via morning-review)
- Load-bearing section headers (`## Open Questions`, `## Open Decisions`, `## Epic Reference`)

### A possible separate pattern worth capturing

Agent 2 identified a **clean, low-risk mechanical rewrite table** from Anthropic's own migration plugin (`claude-opus-4-5-migration/prompt-snippets.md`):

| Before | After |
|--------|-------|
| `CRITICAL: You MUST use this tool when...` | `Use this tool when...` |
| `ALWAYS call X before...` | `Call X before...` |
| `You are REQUIRED to...` | `You should...` |
| `NEVER skip this step` | `Don't skip this step` |
| `think about` (when thinking disabled) | `consider` |
| `think through` (when thinking disabled) | `evaluate` |

This is a **separate axis** from "remove verbose instructions" — it is "rewrite imperative intensity" per Anthropic's own migration guidance. May fit within #052's scope (removes verbosity character from existing instructions) or may deserve its own ticket. Flagged for spec phase.

## Web Research

Key findings from Agent 2 (full citations in agent output):

- **Anthropic migration plugin** (`github.com/anthropics/claude-code/blob/main/plugins/claude-opus-4-5-migration/skills/claude-opus-4-5-migration/references/prompt-snippets.md`) ships a direct before/after rewrite table for this exact migration. Rationale: "prompts designed to reduce undertriggering on previous models cause Opus 4.5 to overtrigger." Motto: "migrations should generally simplify prompts rather than add complexity."
- **Opus 4.6 tutorial** (claude.com/resources/tutorials/get-the-most-from-claude-opus-4-6): "Say it once." Skip reinforcement phrases, skip role-setting, explain intent not rules.
- **Skill authoring best practices** (platform.claude.com): Three audit questions for every paragraph of SKILL.md:
  - Does Claude really need this explanation?
  - Can I assume Claude knows this?
  - Does this paragraph justify its token cost?
- **Leaked Opus 4.6 system prompt**: baseline already bakes in "Claude avoids over-formatting responses with elements like bold emphasis, headers, lists, and bullet points. It uses the minimum formatting appropriate." Any SKILL.md instruction like "be concise" or "use bullet points sparingly" is fighting an already-loaded default.
- **Opus 4.5+ thinking sensitivity**: "think about" / "think through" phrases trigger thinking-mode when extended thinking is disabled. Replace with "consider" / "evaluate".
- **Skill-creator SKILL.md** (anthropics/skills): canonical minimal-prompt reference; progressive disclosure with reference files above 500 lines; explain intent over rules.

**Anti-patterns to target**:
1. All-caps imperatives (ALWAYS/NEVER/MUST/CRITICAL/REQUIRED) — actively harmful on Opus 4.5/4.6.
2. Brevity/formatting meta-instructions already in baseline system prompt.
3. Reinforcement phrases ("And remember to...", "Always remember...").
4. Role-setting boilerplate ("You are an expert...").
5. Thinking-mode-sensitive phrasing when extended thinking is off.
6. Over-specification via rigid templates when task has high degrees of freedom.

## Requirements & Constraints

### Direct mandates supporting the audit

- **project.md:19** — "Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."
- **project.md:30** — "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows."
- **project.md:21** — "ROI matters — the system exists to make shipping faster, not to be a project in itself."

### Load-bearing schemas (do not trim instructions that emit/consume these)

- **events.log schema**: `phase_transition`, `lifecycle_start`, `complexity_override`, `criticality_override`, `clarify_critic`, `feature_complete` event names and fields — consumed by `report.py`, `metrics.py`.
- **Orchestrator rationale convention** (pipeline.md:127 → output-floors.md): `rationale` field on non-obvious feature-selection decisions.
- **Dashboard input files** (observability.md:31): `overnight-state.json`, `pipeline-events.log`, per-feature `events.log`, `plan.md`, `active-session.json`. "Feature status badges, model, and phase progress reflect actual state within 7s of a state file change" (observability.md:32-38).
- **Deferral file schema** (pipeline.md:91): severity / context / question / options / action / default choice.
- **Review artifact schema** (pipeline.md:60): `review.md` with verdict JSON; `review_verdict` event.
- **learnings/progress.txt** (multi-agent.md:67): context-hygiene writes for retry loops.
- **Resource caps** (multi-agent.md:68): stderr 100 lines, learnings 2000 chars.
- **Review agent write scope** (pipeline.md:63): review agent writes only `review.md`.

### Handoff-readiness requirement

**project.md:13** — "A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. **The spec is the entire communication channel.**"

This is the governing constraint: any trimming that weakens a skill's ability to produce self-contained lifecycle artifacts for zero-context reviewers violates handoff readiness.

### Out of scope for this audit

- Hooks, settings.json, statusline, dashboard, notification scripts, overnight runner code
- Requirements docs themselves
- `claude/reference/output-floors.md` (editing there shifts requirements, not trims)
- Security/injection instructions (defer to security-reviewed follow-up)

## Tradeoffs & Alternatives

### Execution strategy

**Recommended: Hybrid — single audit document, atomic commits per skill.**

The adversarial review overturned Agent 4's single-PR-single-commit recommendation. Atomic per-skill commits preserve `git bisect` capability for the 9 high-risk files. A single dispatch session maintains rubric consistency while atomic commits preserve operational recoverability. Same PR is fine; separate commits are the safety margin.

- Rejected: **Parallel dispatch (9 subagents)** — rubric drift risk; 2185 total lines fit in one agent; no context-capacity pressure.
- Rejected: **Sequential read-edit-commit** — risk of rubric drift across skills 1-9 as calibration matures.

### Verification strategy

**Recommended: Multi-point dry-run verification, NOT "one spot check."**

The adversarial review rejected Agent 4's "one spot check" recommendation as confirmation bias on a happy path. The actual verification list:

1. Dry-run `/lifecycle` through a phase transition; verify all four floor fields render.
2. Dry-run `/critical-review` on a plan; diff adversarial stance before/after qualitatively.
3. Dry-run `/diagnose` in a simulated 3-failed-fixes scenario with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` unset; confirm architecture-discussion branch.
4. Dry-run `/research` with 5 agents; verify injection-resistance instruction present in every sub-agent prompt.
5. Run `just test` — verify the existing skill/hook test suite passes.
6. Dry-run `/overnight` eligibility-criteria rendering.

### Uncertain case handling

**Recommended: Preserve on uncertainty + record in audit artifact.**

Matches the ticket's explicit instruction: "Uncertain cases get a flagged note in the audit output for later resolution — not silently deferred." Audit document lives in `lifecycle/{slug}/plan.md` (or a dedicated audit.md), not a new backlog ticket. Conservative removal is the matching stance to the "trust Opus 4.6" verification strategy — you cannot simultaneously defer validation AND remove uncertain instructions.

Explicitly rejected: **Comment-out rather than delete** — Markdown has no prose-safe comment syntax; git history is the correct rollback mechanism.

### Scope of "verbose"

**Recommended: Instruction sentences only; section headers and templates OUT OF SCOPE.**

Templates/example output blocks are "examples are pictures worth a thousand words" assets — removing them is a design decision that belongs in #053 (subagent output formats). Section headers are load-bearing in this codebase more often than grep suggests:
- `## Open Questions` counted by lifecycle's complexity escalation
- `## Open Decisions` counted by lifecycle's complexity escalation
- `## Epic Reference` specified by lifecycle's epic-context injection
- `## Phase Transition` field names cross-referenced by `output-floors.md`

Keeping #052 to sentence-level surgical removal maintains chore scope and evaluable rubric.

### Additional axis: imperative intensity rewrite

Agent 2 surfaced Anthropic's own migration plugin with a direct rewrite table (CRITICAL→plain, ALWAYS→simple form, etc.). Two options:
- **(a)** Include within #052 scope — removes verbosity character from existing instructions; mechanically applies per Anthropic's own migration guidance.
- **(b)** Defer to a separate ticket — keeps #052 scoped to sentence removal, not rewriting.

Option (a) has higher value per unit effort but expands scope. Option (b) keeps #052 evaluable. Flagged for spec phase.

## Adversarial Review

Agent 5 identified structural weaknesses in the codebase agent's analysis. The most important findings:

### Rubric unfalsifiability

The stress-test principle ("would Opus 4.6 produce acceptable output without this instruction?") is unfalsifiable in the proposed verification regime. A single spot-check on one skill proves nothing about the other 8. The rubric also implicitly assumes the Opus 4.6 recipient — but many of these skills dispatch to Sonnet or Haiku sub-agents. Agent 2's Opus 4.6 behavioral evidence is silent on smaller models.

**Mitigation**: For each removal candidate, identify the destination model. Instructions destined for Sonnet/Haiku sub-agents do NOT benefit from the Opus 4.6 argument. `/research` dispatches 3-5 sub-agents (baseline Sonnet/Haiku); `/critical-review` dispatches reviewer agents then an Opus synthesizer; `/pr-review` runs Haiku triage + Sonnet reviewers + Opus synthesizer; `/diagnose` is invoked during lifecycle implement retries where tier/criticality may downshift. The Opus 4.6 trust argument applies only to instructions consumed by the primary orchestrator Opus session.

### Critical-review warmth interaction

Opus 4.6 is explicitly trained warmer and more conciliatory. Skills like critical-review, diagnose, pr-review that require adversarial/critical output may need MORE aggressive framing with Opus 4.6, not less. Removing "Do not soften or editorialize" is not trimming redundant guidance — it is removing the guardrail against baseline warmth.

### Load-bearing detection gaps

Grep-based detection misses:
- **Human readers of outputs** — floor fields Decisions/Scope delta/Blockers/Next have no Python consumers but ARE consumed by morning-review/walkthrough.md and human morning-report readers.
- **Runtime pattern matching** — hooks tail events.log and regex on exact event name spellings.
- **Tests that assert on prompt content** — Agent 1 did not report running `just test`.
- **Cross-skill coupling via reference docs** — morning-review references walkthrough.md that references floor fields.

### Control flow misidentified as prose

Several "verbose" candidates are actually control flow:
- `research` empty-agent handling (lines 177-184): defines exact fallback string format.
- `diagnose` competing-hypotheses conditions (lines 82-92): env var check + user confirmation gate + "skip entirely when running autonomously" guard for overnight context.
- `backlog` AskUserQuestion directives (lines 40, 93-94): output-channel directives, not prose.

Removing any of these trades verbose text for a silent behavioral regression.

### Security-adjacent disclosure

`lifecycle` line 196 (epic-research announcement) is a user-visible checkpoint before loading a file path from backlog frontmatter. Removing it trades one line for a silent path read on a malicious or mistaken `discovery_source:` entry. Defense-in-depth.

### Mitigations applied to the audit plan

1. **Explicit scope exclusions** (declared upfront):
   - Security/injection instructions — out of scope entirely
   - Output-channel directives (AskUserQuestion, file writes) — out of scope
   - Control flow gates (env checks, availability checks, confirmation gates) — out of scope
   - Floor field names — out of scope (human consumer via morning-review)
   - Sub-agent prompt content destined for Sonnet/Haiku — out of scope unless explicit evidence of Opus receipt
2. **Multi-point verification** (replaces "one spot check")
3. **Atomic commits per skill** (preserves bisect)
4. **Did-not-remove appendix** — for every candidate the audit considered and did NOT remove, record the reason. Prevents re-litigation.

## Open Questions

*Resolved to the spec phase for structured interview.*

1. **Sub-agent model destinations**: For each removal candidate, which model will receive the prompt? (Orchestrator Opus 4.6? Dispatched Sonnet? Dispatched Haiku?) The stress-test rubric only applies cleanly to Opus 4.6 destinations. Need explicit per-candidate destination annotation before applying the rubric. Deferred: requires per-skill trace through the dispatch chain.

2. **Scope exclusion declaration**: Should the audit document explicitly declare these categories out of scope upfront?
   - Security/injection instructions
   - Output-channel directives (AskUserQuestion, structured file writes)
   - Control flow gates (env checks, conditional skips, confirmation prompts)
   - Floor field names (even without Python consumers)
   - Defense-in-depth disclosures (e.g., path announcements)

3. **Imperative intensity rewrite axis**: Anthropic's migration plugin ships a mechanical rewrite table (CRITICAL→plain, ALWAYS→plain, "think about"→"consider", etc.). Include within #052 scope or defer to a separate ticket? This is orthogonal to sentence removal but touches the same files.

4. **Verification strategy definition**: Which specific dry-runs are required before the audit is considered complete? The spec should enumerate the exact commands to run and the pass criteria for each.

5. **Audit artifact location**: Where does the audit document live?
   - Option (a): Embedded in `lifecycle/{slug}/plan.md` as part of the implementation plan
   - Option (b): Separate `lifecycle/{slug}/audit.md` artifact
   - Option (c): Both — audit.md for the line-by-line rubric, plan.md referencing it

6. **Flag-for-spec candidates review**: For the candidates marked "Flag for spec phase" in the per-skill sections (lifecycle L1; pr-review PR1; overnight O1, O2; dev DV1, DV2), the user should review each during spec interview with the counter-arguments attached.

7. **Test suite coverage**: Does `tests/test_skill_contracts.py` assert on any prompt content? Agent 1 did not run the test suite. The spec phase should confirm baseline test state before and after the audit.

8. **Morning-review consumer verification**: Confirm whether `skills/morning-review/references/walkthrough.md` (or similar) actually reads phase transition narrative fields from events.log. Agent 5 flagged this as a suspected human-facing consumer; needs verification before any floor-field edit.
