# Research: Decide and document two durable post-4.7 policy norms (OQ3 MUST-escalation, OQ6 tone)

> Generated: 2026-04-29. Topic from #91. Background context: epic research at `research/opus-4-7-harness-adaptation/research.md` (DR-3, OQ3, OQ6) and the completed #85 audit at `lifecycle/archive/audit-dispatch-skill-prompts-and-reference-docs-for-47-at-risk-patterns/` (candidates.md, review.md, research.md). Five agents dispatched (complex + high → 5).

## Codebase Analysis

### Audit empirical surface (OQ3 input)

`#85` audit ring-fenced 10 anchored MUST/negation strings as preservation-excluded. They cluster into three load-bearing categories:

- **Verbatim subagent-dispatch contracts** (P5 SKIPs): `lifecycle/references/{research,plan,implement}.md` each contain "do not omit, reorder, or paraphrase" — semantic substitution would break prompt templates.
- **Distinct-angle / anti-soften anchors**: `critical-review/SKILL.md` "Do not soften or editorialize", "Do not cover other angles" — load-bearing for per-angle reviewer behavior.
- **Phase-order gates**: `diagnose/SKILL.md` "ALWAYS find root cause before attempting fixes" — correctness-critical pre-condition gate.

Most other imperatives in dispatch skills were either softened to positive routing (M1) or normalized via explicit format spec (M2). Outside dispatch skills, no systematic post-#85 audit has been performed (DR-2 deliberately scoped).

### Current CLAUDE.md surface (target #1)

`/Users/charlie.hall/Workspaces/cortex-command/CLAUDE.md` is 50 lines, structured as: What This Repo Is → Repository Structure → Distribution → Commands → Dependencies → Conventions. Conventions include commit rules, skill-frontmatter requirements, hook executable enforcement, dual-source enforcement for `bin/`. **No tone or voice directives exist anywhere in the codebase**. Adding two policy paragraphs adds ~20 lines (40% growth).

### Rules-file surface (target #2)

`~/.claude/rules/cortex-global.md` and `~/.claude/rules/cortex-sandbox.md` exist as deployed files but are dangling symlinks: `git show --stat 08d1102` confirms `claude/rules/global-agent-rules.md` (10 lines) and `claude/rules/sandbox-behaviors.md` (39 lines) were deleted on 2026-04-23. The deleted `global-agent-rules.md` content was generic git-commit help, not policy — so "re-establish" is net-new authoring inside a directory that no longer exists. `git log --oneline --all -- 'plugins/cortex-interactive/rules/'` returns empty: no plugin-rules mirror has ever existed. The cortex-deployment-only-rules convention is governed by completed tickets #120/#121, but the rules-file mechanism itself has no source-of-truth in the repo today.

### Effort-parameter infrastructure (absent)

`grep -rE "effort|reasoning_effort|xhigh"` in `skills/`, `CLAUDE.md`, `docs/` finds zero policy hits. The `docs/setup.md` mention of `effortLevel` is a personal-preference setting cortex does not own. No effort-selection convention exists, and no SDK wiring confirms whether effort can be passed through the dispatch path (Q2 from epic research is unresolved).

## Web Research

### OQ3 — MUST-escalation reconciliation

Anthropic has **not** published a single-doc reconciliation of skills-best-practices ("escalate on observed failure") vs. prompting-best-practices ("dial back aggressive language"). Assembled posture across published sources (all fetched 2026-04-29):

- **prompt-engineering best practices** (canonical, header explicitly covers Opus 4.7): *"Where you might have said 'CRITICAL: You MUST use this tool when…', you can use more normal prompting like 'Use this tool when…'."*
- **4.5 migration plugin** (`anthropics/claude-code/plugins/claude-opus-4-5-migration/.../prompt-snippets.md` — most recent codified guidance; verified via `gh api` that no `claude-opus-4-7-migration` plugin exists yet): the table replaces `CRITICAL: You MUST` → `Use`, `ALWAYS` → bare verb, `REQUIRED to` → `should`, `NEVER` → `Don't`. Crucially: *"Only apply these snippets if the user explicitly requests them or reports a specific issue. By default, the migration should only update model strings."*
- **4.7 prompting section adds a new lever** — `effort`. Documented guidance: *"If you observe shallow reasoning on complex problems, raise effort to high or xhigh rather than prompting around it."* This reframes prompt-text escalation as the *second* lever, not the first.
- **4.7 literal-following note**: *"It will not silently generalize an instruction from one item to another… If you need Claude to apply an instruction broadly, state the scope explicitly."*

Community pushback (KeepMyPrompts, rentierdigital, 2026) argues against wholesale-soften reading: MUST stays appropriate when failure mode is omission of a required behavior. Endorses MUST for under-triggered tools.

**Bottom-line for OQ3**: Anthropic's published norm = soften-by-default with surgical escalation only on observed failure; 4.7 changes the recommended *first* lever from prompt-edits to effort-tuning; existing escalations should be reviewed for whether the issue might be solved by raising `effort` or by stating scope explicitly before being kept as MUST.

### OQ6 — Tone change and remediation efficacy

Officially documented in three docs with consistent wording — `whats-new`, migration guide, prompting best-practices: *"More direct, opinionated tone with less validation-forward phrasing and fewer emoji than Claude Opus 4.6's warmer style."* Anthropic's recommended remediation, verbatim: *"Use a warm, collaborative tone. Acknowledge the user's framing before answering."*

**But**: per support.tools "Claude Code System Prompt Architecture" analysis (2026), CLAUDE.md tone overrides *"do NOT reliably work for tone, verbosity, and reasoning-style overrides."* Reasoning: *"In transformer models, instructions injected at the system-prompt level carry stronger positional weight during attention than instructions that arrive later as context."* Claude Code ships its own ~320-token "Output and tone" section in the built-in system prompt; CLAUDE.md tone directives are fighting earlier-injected instructions and lose. The article identifies what *does* work: output-style modes and `--system-prompt` flag — i.e. tone instructions delivered at system-prompt level, not via CLAUDE.md or rules files.

4.7's literal-following change makes hedge-style tone instructions ("consider being warm") weaker, not stronger — so any directive added must be imperative and concrete, mirroring Anthropic's exact phrasing.

**Bottom-line for OQ6**: tone change is officially acknowledged. CLAUDE.md is structurally weak for tone. Rules files load via the same memory pipeline as CLAUDE.md (post-system-prompt), so they likely have the same weakness — needs empirical verification before relying on a rules-file path. The structurally strong levers (output styles, `--system-prompt`) are not currently shipped by cortex.

## Requirements & Constraints

- **project.md**: file-based state; bin/cortex-* parity enforcement (drift is a pre-commit-blocking failure); no requirement explicitly addresses CLAUDE.md or rules-file content.
- **multi-agent.md**: defines model-escalation ladder (haiku→sonnet→opus, no downgrade); prompt-substitution contract (single-brace session tier vs. double-brace per-feature tier). Single-layer prompts not bound by the contract.
- **CLAUDE.md (repo) line 22**: *"It no longer deploys symlinks into `~/.claude/`."* — confirms post-117 retirement of `just deploy-skills`/`deploy-hooks` symlink architecture.
- **Auto-memory `project_rules_only_not_claudemd.md`**: Cortex deploys to `~/.claude/rules/cortex-*.md`; never touches `~/.claude/CLAUDE.md` (user-owned). The convention is about *file ownership*, not deployment surface.
- **Tickets #120/#121** (both `complete`): establish the cortex-deployment-only-rules convention via plugins. The rules-deployment mechanism is governed by these tickets, not by an existing in-tree symlink convention.
- **Backlog #91 scope**: "Two decisions, not three"; "policy documentation only, no code changes"; "paragraph or two each."

OQ3 and OQ6 are **policy decisions, not technical requirements**.

## Tradeoffs & Alternatives

### OQ3 — alternatives

| # | Approach | Pros | Cons |
|---|----------|------|------|
| A | Default soft, escalate on observed failure (the inferred reconciliation) | Reconciles both Anthropic docs; matches what #85 actually executed; aligns with #053 preservation taxonomy | Codifies an inference; "observed failure" is squishy without an artifact requirement |
| B | Always normalize, re-observe under 4.7 | Fully aligned with migration-guide letter; produces empirical evidence | Knowingly regresses #85's preservation rules (R10 ring-fenced anchors); high blast radius; wastes #053+#85 audit work |
| C | Always escalate (keep MUST as default) | Zero ambiguity for authors | Contradicts both Anthropic guidance and #053; reintroduces literal-overcompliance hazard; #85 reversals required |
| D | Per-pattern decision tree (explicit criteria) | Most rigorous; audit-checkable; aligns with #85's implicit categories | Highest authoring effort; risk of pseudoscience; needs updating per model |
| E | No policy entry, case-by-case | Zero work; preserves flexibility | Defeats ticket purpose; the inference gets re-debated every lifecycle |

### OQ6 — alternatives

| # | Approach | Pros | Cons |
|---|----------|------|------|
| F | Warmth directive in repo CLAUDE.md (project scope) | Lowest blast radius; easy to remove | Solves problem only when working IN cortex-command repo (~5% of cortex surface) |
| G | Warmth directive in `~/.claude/rules/cortex-*.md` (global cortex rule) | Wide blast radius matches actual problem surface | **Gating prereq**: source-of-truth file deleted in `08d1102`; would need to be net-new-authored in a plugin-deployed `rules/` directory that does not exist. Imposes one user's preference on every cortex installer. **Likely structurally weak** — rules files load post-system-prompt, same as CLAUDE.md (per support.tools finding) — needs empirical verification before promising leverage. |
| H | Warmth directive in personal `~/.claude/CLAUDE.md` (user self-action) | Universal reach; user retains full control | Out-of-scope for cortex to ship; valid only as a *recommendation to user* |
| I | Accept the regression — no policy entry | Zero work; tone is preference not correctness; preserves Anthropic calibration | Leaves UX regression unaddressed; user-facing surfaces may feel cold |
| J | Conditional warmth (user-facing surfaces only) | Targets actual UX problem | Significantly higher authoring complexity; risks P2-style ambiguous-bypass; hard to verify |

### Cross-cutting question — target file routing

Per-policy is the right framing, not uniform. OQ3 is contributor-facing (governs how cortex skills get authored) → repo `CLAUDE.md`. OQ6 is user-facing (governs how Claude communicates) → if any directive is added, the natural target is `~/.claude/rules/cortex-*.md` for blast-radius reasons — but per the adversarial finding, that path is gated on infrastructure work AND likely structurally weak for tone specifically.

## Adversarial Review

### Verified factual claims

- **`08d1102` deletion confirmed but reframed**: the deleted `claude/rules/global-agent-rules.md` was 10 lines of generic git-commit help, not tone or escalation policy. So "re-establishing" the rules-file mechanism is net-new authoring inside a deleted directory — a deliberate architectural decision shipped in service of #120/#121, not an oversight to repair.
- **No plugin-rules mirror exists**: `git log --all -- 'plugins/cortex-interactive/rules/'` returns empty.
- **Effort-parameter has zero policy hooks**: would be net-new infrastructure to wire.

### Failure modes the spec must address

- **FM-1 — "Observed failure" is self-attesting**: Alternative A+D-criteria's "observed-failure pointer" can be satisfied by an author writing "I observed Claude skipping this" with no artifact, link, or events.log row. Without a hard artifact requirement (events.log F-row OR retro entry OR linked transcript), the criterion disciplines nothing.
- **FM-2 — OQ3↔OQ6 coupling**: if OQ3 codifies "escalate on observed failure" and OQ6 codifies "accept the regression," the first cold/abrupt user-facing surface creates an OQ3-eligible escalation trigger that OQ6 forbids. Spec must carve out tone perception as a non-OQ3 trigger.
- **FM-3 — System-prompt-positional-weight undercuts both OQ6 alternatives**: rules files likely load via the same pipeline as CLAUDE.md (post-system-prompt). If true, **Alternative G is structurally weak** for tone specifically. Spec needs to verify empirically before recommending G as a future-trigger path.
- **FM-4 — #85 categories without reasoning capture**: codifying "preserve anchored MUST" bakes in 4.5/4.6-era judgment as 4.7-era doctrine. The #85 research itself flagged that anchored preservation rationale is *contingent on model version* and may need re-audit per release.
- **FM-5 — Effort-parameter omission**: Anthropic's documented hierarchy is *raise effort → reduce instruction count → only then add MUST*. If OQ3 ships without an effort-first clause, it sanctions imperatives where the actual remedy is a parameter change.
- **FM-6 — CLAUDE.md bloat threshold**: 50 lines today; two policy paragraphs adds ~40% growth. At ~5 such tickets, CLAUDE.md doubles and shifts from "project conventions" to "policy archive." Spec should set a threshold or justify CLAUDE.md as the durable home regardless.
- **FM-7 — Personal-preference convention argues against shipping G**: the rules-only convention's underlying logic (file ownership) actually argues that personal-preference dimensions like tone belong in user-owned files, not cortex-owned ones — a stronger case for Alternative I than the tradeoffs agent surfaced.
- **FM-8 — "Empirical input" is choice-aligned, not evidence-aligned**: #85's candidates.md is an inventory of authoring decisions, not a calibration dataset. There are no measured outcomes ("after softening this, the skill behaved better/worse"). Codifying a policy from this is inferring from authoring choices, not from outcomes.

## Open Questions

The 10 questions surfaced during research were triaged at the Research Exit Gate (2026-04-29). Items the orchestrator could resolve unambiguously from synthesis are marked **Resolved**; items that turn on user preference or load-bearing policy choices are marked **Deferred** to the Spec interview.

1. **OQ3 alternative selection**: Alternative A (default soft, escalate on observed failure), B, C, D, or E? *Recommendation*: A with the FM-1 artifact requirement and FM-5 effort-first clause baked in. *Why*: matches what #85 already executed, aligns with both Anthropic posture and the published lever hierarchy. **Deferred**: this is the central policy decision the ticket asks the user to make; not appropriate for orchestrator pre-decision. Spec interview will elicit and confirm.

2. **OQ3 escalation evidence bar**: what counts as "observed failure"? Options: (a) any logged events.log F-row OR retro entry OR commit-linked transcript; (b) lifecycle-only F-row pointer; (c) author self-attestation acceptable. *Recommendation*: (a). **Resolved: (a)**. (c) collapses the discipline (FM-1). (b) is too narrow — retros are legitimate evidence. (a) is the only option that is both artifact-bound and broad enough to cover the actual evidence channels in use.

3. **OQ3 effort-first clause**: include "before adding/restoring a MUST, the author must consider whether raising effort would resolve the failure; the escalation note records why effort tuning is insufficient" — yes/no? *Recommendation*: yes. **Resolved: yes**. Aligns with Anthropic's documented 4.7 lever hierarchy (raise effort → reduce instructions → only then add MUST). The clause is a posture, not an infrastructure requirement — does not depend on existing effort-selection wiring.

4. **OQ3↔OQ6 coupling carve-out**: include "OQ3's escalation rule applies to correctness, control-flow, and routing failures only; tone perception falls under OQ6 and does not constitute an OQ3 trigger" — yes/no? *Recommendation*: yes. **Resolved: yes**. Costs nothing and prevents a real failure mode (FM-2) where the first cold-tone observation would create an OQ3-eligible escalation trigger that OQ6's accept-answer forbids.

5. **OQ6 alternative selection**: F, G, H (recommend-only), I, or J? *Recommendation*: I (accept), with explicit user-self-action note pointing to H. *Why*: tone is preference not correctness; G is gated AND likely structurally weak; rules-only convention's file-ownership logic argues tone belongs in user-owned files. **Deferred**: this is the second central policy decision the ticket asks the user to make. Spec interview will elicit and confirm.

6. **OQ6 re-evaluation trigger**: under what observed signal would the policy revisit? *Recommendation*: revisit if 4.8 further regresses tone OR if 3+ retro entries cite cold/abrupt user-facing output OR if a specific surface (commit/PR confirmation) is identified as load-bearing-for-warmth. **Partially Resolved: yes, set a re-evaluation trigger; specific threshold deferred to Spec** (threshold depends on OQ5 outcome — if user picks I, the trigger is what would flip the answer; if user picks F/G, the trigger is what would deprecate the directive).

7. **Target file for OQ3**: repo `CLAUDE.md` or somewhere else (e.g., a new `docs/skill-authoring-policy.md`)? *Recommendation*: repo `CLAUDE.md`. **Resolved: repo `CLAUDE.md`**. Matches existing CLAUDE.md content shape (repo-scoped contributor conventions like commit rules, skill structure). The bloat concern (FM-6) does not yet fire — current 50 lines + ~20 lines for two policy paragraphs = ~70 lines, below the OQ9 threshold.

8. **Target file for OQ6**: repo `CLAUDE.md` (co-locate the "we declined to act" entry with OQ3) or close in the ticket without writing? *Recommendation*: co-locate in `CLAUDE.md`. **Resolved: co-locate in `CLAUDE.md`**. Even an "accept and decline" entry is durable-norm material; co-locating with OQ3 keeps the durable-norm inventory legible. Closing in ticket history alone loses the policy.

9. **Bloat threshold for future epic-82 policy tickets**: set a line-count threshold above which CLAUDE.md splits to a sibling `docs/policies.md`, or accept CLAUDE.md as policy archive? *Recommendation*: declare a threshold (e.g., 100 lines). **Resolved: declare a 100-line threshold**. Sets the precedent now while the cost is zero; only acts on the split when crossed. 100 lines is round and gives ~30 lines of headroom past this ticket's expected addition.

10. **Rules-file empirical test (gating Alternative G as future path)**: does the spec require running an empirical test (write a tone directive in a rules file, run a known-cold prompt under 4.7, compare outputs) to confirm whether rules files have any leverage on tone? *Recommendation*: not required for #91 (out of "policy documentation only" scope), but flag the gap so a follow-up ticket can be filed if OQ6 revisits. **Resolved: not for #91; flag for follow-up if OQ6 revisits**. Empirical test is implementation work that goes beyond the ticket's "policy documentation only, no code changes" scope.

### Triage summary

- **Resolved (7)**: OQ2, OQ3, OQ4, OQ7, OQ8, OQ9, OQ10. These are inputs to the Spec phase; Spec writes them through without re-asking.
- **Partially Resolved (1)**: OQ6 — direction resolved (yes, set a trigger), specific threshold deferred (depends on OQ5).
- **Deferred (2)**: OQ1 (OQ3 alternative selection) and OQ5 (OQ6 alternative selection). These are the two central policy decisions the ticket asks the user to make; Spec's structured interview will elicit them with the recommendations as starting positions.
