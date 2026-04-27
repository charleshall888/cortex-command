# Research: Disambiguate orchestrator prompt tokens to stop lexical-priming escape

> Rename the overloaded `{plan_path}` prompt token in `claude/overnight/prompts/orchestrator-round.md` so session-level paths (pre-filled by `fill_prompt()` in `runner.sh`) are distinguishable from per-feature paths (substituted by the orchestrator agent at runtime from `state.features[<slug>]`); update `fill_prompt()` to match the renamed session-level token; add an explicit instruction block before the per-feature dispatch block naming which tokens the orchestrator substitutes — eliminating the lexical-priming + name-collision mechanism that caused session `overnight-2026-04-21-1708`'s `feature_start` failure.

## Epic Reference

- Parent: [research/orchestrator-worktree-escape/research.md](../../research/orchestrator-worktree-escape/research.md) (epic 126). The epic classifies this ticket as the **cheapest, highest-leverage** of the five worktree-escape fixes (research §"Repair tickets", DR-1). The epic's substitution-contract analysis is the ground truth for the session-level-vs-per-feature split; this ticket's research deliberately does not re-derive that material — it extends it with the implementation-level enumeration, alternatives comparison, and adversarial review required at complex + critical tier. Content covered by adjacent tickets in the epic (pre-commit hook enforcement, morning-report commit un-silence, followup-item persistence, frontmatter rollback, PR-gating, worktree GC) is explicitly out of scope here.

---

## Codebase Analysis

### Complete token enumeration in `orchestrator-round.md`

Classification by whether `fill_prompt()` at `runner.sh:385–391` pre-fills the token. That function handles exactly six tokens: `{state_path}`, `{plan_path}`, `{events_path}`, `{session_dir}`, `{round_number}`, `{tier}`. All other tokens are either orchestrator-substituted at runtime from state, or are prose references to downstream tokens in other prompts.

| Token | Line number(s) | Class | Notes |
|---|---|---|---|
| `{round_number}` | 1, 3, 165, 247, 311, 329 | **Session-level** (pre-filled) | Via `runner.sh:390` from `$ROUND_NUM`. |
| `{state_path}` | 13, 128, 130, 154, 321 | **Session-level** (pre-filled) | Via `runner.sh:386` from `$STATE_PATH` (absolute via `realpath` at `runner.sh:195`). |
| `{plan_path}` | 14, 110, 216, 269 | **Overloaded** — 14/110/216 session-level; 269 per-feature | Session occurrences pre-filled via `runner.sh:387` from `$PLAN_PATH`. Line 269 is inside the Step 3b sub-agent dispatch template (lines 260-285) and is expected to be substituted by the orchestrator at runtime from `state.features[<slug>]["plan_path"]`. **This is the acute collision.** |
| `{events_path}` | 15, 254, 332 | **Session-level** (pre-filled) | Via `runner.sh:388` from `$EVENTS_PATH`. |
| `{session_dir}` | 19, 20, 185, 311 | **Session-level** (pre-filled) | Via `runner.sh:389` from `$SESSION_DIR`. Lines 19-20 are the HTML comment documenting the substitution. |
| `{tier}` | *(none in template text; registered)* | **Session-level** (pre-filled) | Via `runner.sh:391` from `$TIER`. Currently a dead substitution hook — no `{tier}` literal appears in the prompt body. |
| `{feature}` | 89, 102, 108, 109, 115, 136, 148, 261 | **Overloaded** — 89-148 are Python-variable references inside example code; 261 is a per-feature sub-agent token | Lines 89-148 sit inside Step 0 Python example blocks where `entry["feature"]` surrounds the literal, making the intent "live variable interpolation" rather than template substitution. Line 261 is inside the dispatched sub-agent template where the orchestrator is expected to substitute a feature name. **Same-class collision as `{plan_path}` but within a single scope (per-feature).** |
| `{slug}` | 265, 266, 291 | **Per-feature** (orchestrator substitutes) | References `lifecycle/{slug}/research.md`, learnings paths, and deferral filename `deferred/{slug}-plan-q001.md`. |
| `{spec_path}` | 264 | **Per-feature** (orchestrator substitutes) | From `state.features[<slug>]["spec_path"]`. |
| `{N}` | 102, 148 | **Per-feature** (orchestrator substitutes) | Numeric index for deferral filename. |
| `{learnings}` | 115 | **Prose reference** | Refers to a downstream sub-agent's token in `claude/pipeline/prompts/implement.md:65`; not substituted by `orchestrator-round.md` or its callers. |
| `{session_id}` | 20 | **Documentation-only** | Inside the HTML comment example; never substituted. |

**Line-number drift note**: the ticket body cites dispatch block lines 258-285; the file on main is 260-285 with `{plan_path}` at line 269 (research-verified).

### `{plan_path}` occurrence audit

| Line | Context | Class |
|---|---|---|
| 14 | `- **Session plan**: \`{plan_path}\`` in the "## State Files" header | **Session-level** |
| 110 | `- \`{plan_path}\` — the session overnight plan.` — 3rd bullet in Step 0d escalation resolution | **Session-level** |
| 216 | `Read \`{plan_path}\` to understand batch assignments...` — sole line of "### 2. Read Session Plan" | **Session-level** |
| 269 | `write a complete plan to {plan_path}` — inside the Step 3b sub-agent dispatch template | **Per-feature** |

### `fill_prompt()` caller chain

`fill_prompt()` is defined at `runner.sh:379-393` and called at a single site: `runner.sh:633` inside the `while [[ $ROUND -le $MAX_ROUNDS ]]` round loop. Each invocation re-reads the template file from `PROMPT_TEMPLATE` (set once at `runner.sh:97` to `claude/overnight/prompts/orchestrator-round.md`).

`PLAN_PATH` initialization (consumed by `fill_prompt` via env-var indirection):

```
runner.sh:99   PLAN_PATH=""                                        # declaration
runner.sh:239  PLAN_PATH="${SESSION_DIR}/overnight-plan.md"         # default
runner.sh:278  PLAN_PATH="$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/overnight-plan.md"
               # cross-repo override: writes plan to the HOME repo even when
               # running in a target-repo worktree
runner.sh:381  STATE_PATH=... PLAN_PATH="$PLAN_PATH" ...            # exported into subshell
runner.sh:387  t = t.replace('{plan_path}', os.environ['PLAN_PATH'])
```

**Asymmetry**: `fill_prompt()` re-reads the template each round, so prompt-file edits take effect mid-session. `runner.sh` itself is loaded once by bash and is NOT re-read mid-session — any rename change to `runner.sh` requires a full runner restart. This is load-bearing for the deploy-atomicity concern in the Open Questions below.

### `DEFAULT_PLAN_PATH` and `BATCH_PLAN_PATH` are unrelated

- `plan.py:27`: `DEFAULT_PLAN_PATH = _LIFECYCLE_ROOT / "overnight-plan.md"` — Python module constant for the session-plan writer's fallback directory. Used at `plan.py:263` and `plan.py:498` only. **Not related** to the prompt token or the shell `$PLAN_PATH`.
- `BATCH_PLAN_PATH` in `smoke_test.py:30` and `runner.sh:697-770` refers to the per-round batch plan (e.g., `batch-plan-round-1.md`), not the session plan. **Not related** to the `{plan_path}` prompt token.

### Other overnight prompt templates (lexical-priming survey)

`claude/overnight/prompts/` contains exactly three files:
- **`orchestrator-round.md`** — the subject of this ticket. Has dual-layer substitution (shell pre-fill + agent runtime-fill using identical `{token}` syntax). **Unique offender in the repo.**
- **`batch-brain.md`** — all tokens pre-filled by `brain.py:214` via `_render_template()`. Single-layer; no priming vulnerability.
- **`repair-agent.md`** — all tokens pre-filled by `conflict.py:290-298` via chained `.replace()`. Single-layer; no priming vulnerability.

Adjacent pipeline prompts (`claude/pipeline/prompts/implement.md`, `review.md`) are filled by `feature_executor.py:560` / `_render_template`. Single-layer; no vulnerability.

**Conclusion**: Only `orchestrator-round.md` has the dual-layer substitution contract. Recurrence coverage for any fix applied only to this file is "zero for other prompts today" — because no other prompt has the vulnerability today.

### External references to `{plan_path}` and `PLAN_PATH`

Prompt-token references (literal `{plan_path}`):
- `claude/overnight/prompts/orchestrator-round.md` — 4 sites (14, 110, 216, 269).
- `claude/overnight/runner.sh:387` — the single `str.replace` line. **This is the only code that must change if the session-level token is renamed.**
- `research/overnight-layer-distribution/_codebase-report.md:150`, `research/orchestrator-worktree-escape/research.md` (multiple descriptive mentions), `backlog/126-*.md:28`, `backlog/127-*.md:30-31`, `lifecycle/*/research.md` stale-line-number mentions — **documentation only**; not code paths.

Env-var references (`$PLAN_PATH` / `PLAN_PATH=`):
- `runner.sh` lines 99, 194, 239, 276-278, 381, 387. The env-var name stays the same under a prompt-token rename; only the template string in the `str.replace` call changes.

Unrelated identifiers (must NOT be renamed):
- `DEFAULT_PLAN_PATH`, `BATCH_PLAN_PATH`, `state.features[<slug>].plan_path` (state schema field — Python attribute, not a template token).

### Tests that touch the prompt file

- `tests/test_runner_signal.py:86` writes a stub prompt containing `{round_number}` and `{state_path}` only. No `{plan_path}` reference — unaffected by the rename.
- `tests/test_events_contract.py:20` pattern-matches `log_event(` occurrences in `orchestrator-round.md` for event-name contract validation. Unaffected by token renames (doesn't read substitution placeholders).

No test file asserts on `{plan_path}` as a template token. This is both a green light (no mechanical test breakage) and a gap (no automated validation that `fill_prompt()` correctly substitutes the renamed session-level token). See §Verification below.

### Instruction-block placement conventions

No existing prompt in the repo contains a "you substitute these tokens from state" preamble. The closest analog is the HTML comment at `orchestrator-round.md:19-20` which documents *pre-filled* tokens (opposite direction). This ticket introduces a new convention. The research's feasibility-table entry (§"Repair tickets" row 1) names the target placement as "before line 258" — i.e., immediately adjacent to the Step 3b dispatch block (currently line 260 with drift).

---

## Web Research

### Major LLM frameworks: flat namespace, no surface distinction

- **LangChain `PromptTemplate.partial` / `partial_variables`** ([docs](https://python.langchain.com/api_reference/core/prompts/langchain_core.prompts.prompt.PromptTemplate.html)): partial binding is a method call, not a syntactic marker. All variables use `{var}`; you cannot tell by reading the template which have been partialed.
- **LlamaIndex `partial_format`** ([docs](https://docs.llamaindex.ai/en/stable/module_guides/models/prompts/usage_pattern/)): same pattern — partial is a Python method, no prompt-surface distinction.
- **LangSmith prompt format** ([docs](https://docs.langchain.com/langsmith/prompt-template-format)): supports both f-string and Mustache; mixing them within a single template is a known footgun.
- **Anthropic Claude prompt templates** ([docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompt-templates-and-variables)): `{{double_brackets}}` syntax; the Agent SDK does not document a two-tier substitution mechanism.

**Implication**: by the time the prompt reaches the model, any syntactic marker of "this was already filled" vs "this needs filling" has been erased. If the distinction must be visible to the agent, **the prompt author must put it there explicitly** — no framework does it automatically.

### Two-tier substitution: distinct delimiter is the template-engine consensus

- **Azure Pipelines** ([docs](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/runtime-parameters?view=azure-devops)): solved the multi-phase substitution problem by assigning each phase its own syntax — `${{ x }}` for compile-time, `$(x)` for macro-time, `$[x]` for runtime. **Distinct substitution phases get distinct delimiters, not distinct names within the same delimiter.**
- **dbt "Don't nest your curlies"** ([docs](https://docs.getdbt.com/best-practices/dont-nest-your-curlies)): the direct analog to this ticket's bug. Reusing the same delimiter across two substitution phases is explicitly labeled an anti-pattern. Quote: "This is probably not what you actually want to do!"
- **Python `string.Template` vs `str.format`**: `string.Template` (`$name`) was designed specifically so format strings *don't* collide with curly-brace-heavy content. `str.format` uses `{{` / `}}` to escape literal braces — same mechanism.
- **Jinja2** (`{% raw %}...{% endraw %}`) and **Mustache/Handlebars** (delimiter-swap `{{=<% %>=}}`): both provide an in-template way to change the delimiter when content collides.

### Lexical priming in LLM prompts is documented

- **"Pattern Priming in Prompting"** ([AightBits, 2025](https://aightbits.com/2025/05/09/pattern-priming-in-prompting-how-to-shape-llm-output-with-statistical-cues/)): direct characterization of the mechanism. "Models don't maintain perfect attention across all previous tokens… behavior becomes increasingly shaped by previously generated tokens rather than original intent." Identical token forms prime uniform substitution behavior.
- **arXiv 2510.00508 "Copy-Paste to Mitigate LLM Hallucinations"** ([link](https://arxiv.org/html/2510.00508)): inverse-correlation evidence that models readily copy surface forms from context.
- **OWASP LLM Prompt Injection Prevention** ([link](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)): recommends structural separation with strict role-specific tokens/delimiters when same-surface-form text has different semantic roles.
- **arXiv 2504.02052 "From Prompts to Templates"**: "non-semantic placeholder names such as 'text' and 'input' are still commonly used in prompt templates, hindering prompt understanding and maintenance."

### Instruction placement: recency bias + adjacent pairing

- **arXiv 2505.21091 "Position is Power"** and [Lars Wiik on instruction placement](https://medium.com/@lars.chr.wiik/llm-instruction-placement-in-prompts-it-matters-a-lot-3b57580756ee): in long prompts, the first 20% of tokens receive only 12-18% of effective attention. Early-prompt instructions drift out of attention by the time the agent acts.
- **Anthropic XML-tag guidance** ([docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)): wrap data and instructions in distinct XML tags so Claude parses them as distinct roles. Recommends placing the instruction *immediately adjacent* to the data block it governs, not in a global preamble.

### Takeaway

Template-engine consensus says *change the delimiter*, not just the name. LLM-prompt guidance says *place the instruction adjacent to the template block, preferably with XML wrapping*. These converge: the cheapest robust fix combines (a) a distinct delimiter or wrapping convention for per-feature tokens, (b) a scope-prefixed token name, and (c) an adjacent instruction block.

---

## Requirements & Constraints

Relevant requirements from `requirements/`:

| Source | Quote | Why it applies |
|---|---|---|
| `project.md` (Philosophy of Work) | "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." | Bears directly on rename-vs-restructure — favors a minimal, targeted fix over broader refactoring. |
| `project.md` (Philosophy of Work) | "A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. The spec is the entire communication channel." | Supports adding an explicit "you substitute these" instruction block — the orchestrator prompt IS the communication channel to a zero-prior-context agent. |
| `project.md` (Quality Attributes) | "Maintainability through simplicity: Complexity is managed by iteratively trimming skills and workflows." | Disambiguating overloaded tokens improves navigability; the rename backs the maintainability mandate. |
| `project.md` (Architectural Constraints) | "File-based state: Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter)." | Prompt templates are plain markdown; the rename fits the file-based model. |
| `multi-agent.md` (Parallel Dispatch) | "Filtering happens at round-planning time (orchestrator prompt), not at dispatch time" | Confirms the orchestrator prompt is the load-bearing locus of per-feature decision-making — any rename must preserve this. |
| `multi-agent.md` (Architectural Constraints) | "Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents." | The instruction block must reinforce (not relax) orchestrator-as-dispatcher. |
| `pipeline.md` (Non-Functional) | "Orchestrator rationale convention … requires orchestrator prompt changes." | Editing `orchestrator-round.md` is an acknowledged enforcement surface. |

### Silent-on notes

Requirements are silent on:
- Token naming conventions for prompt templates.
- Shell (`runner.sh`) vs Python layer (`claude/overnight/*.py`) separation of concerns. Only `orchestrator.py` is named as "the overnight runner" in requirements; `runner.sh` and `fill_prompt()` are not documented at requirements level.
- Prompt template file structure, instruction-block conventions, or pre-filled-vs-agent-filled substitution semantics.
- Observability contracts for prompt-token names (so a rename has no documented observability surface to preserve).
- Prompt-template correctness as a worktree-isolation mechanism.

The Spec phase can treat all of the above as **unconstrained** — the ticket has latitude to choose a naming scheme, instruction-block format, and placement without conflicting with a documented requirement.

---

## Tradeoffs & Alternatives

Four approaches evaluated. Full expansion below; summary table first.

| Dimension | A: Rename | B: Different delimiter | C: Build-time inline | D: Tool-call dispatch |
|---|---|---|---|---|
| LOC estimate | ~15-25 | ~10-15 | 100-300 | 200-500+ |
| Files touched | 2 | 1-2 | 3-5 | 5-10+ |
| Eliminates name collision | Yes | Yes | Yes (no tokens) | Yes (no tokens) |
| Eliminates lexical priming | Partial (instruction block mitigates) | Mostly (syntactic class distinct) | Fully | Fully |
| Reversibility | Trivial | Trivial | Moderate | Poor |
| Project-philosophy fit | Strong | Moderate-Strong | Weak | Poor |
| Recurrence coverage | None (others already single-layer) | Moderate (if convention codified) | None | High (but coverage of a hypothetical class) |
| Time estimate | ~30 min-1h | ~30-45 min | ~1-2 days | ~3-7 days |

### A: Rename — `{plan_path}` → `{session_plan_path}` / `{feature_plan_path}` + instruction block

**Implementation**: 4 edits in `orchestrator-round.md` (lines 14, 110, 216 → session; 269 → feature), 1 edit in `runner.sh:387`, plus a ~10-line instruction block before line 260. Total ~15-25 LOC across 2 files.

**Robustness**: Removes the name collision. Residual lexical-priming pressure remains because the per-feature dispatch block still uses `{token}` syntax — the instruction block counters this via Anthropic XML-tag-style adjacent instruction, but it is belt, not suspenders.

**Blast radius**: Small. No Python API, no state schema, no other prompts. `PLAN_PATH` env var name can stay — only the template-facing token string changes.

**Reversibility**: Trivial. Git revert restores 2 files.

**Philosophy fit**: Strong. "Simpler solution is correct when in doubt" directly applies.

**Recurrence coverage**: None for other prompts (they're already single-layer) and nothing for future dual-layer templates a developer might introduce.

### B: Different delimiter for per-feature tokens

**Subvariants**:
- B1: `{{plan_path}}` double-brace — lowest edit cost; mild Python `str.format` confusion risk (current code uses `str.replace`, so no immediate collision).
- B2: `<feature.plan_path>` angle-bracket dotted — most visually distinct; no format-string confusion; clean structural separation.
- B3: Jinja-style `{{ plan_path }}` with spaces — requires template-engine semantics to be honored across the codebase; partial adoption would be inconsistent.

**Implementation**: ~10-15 LOC in `orchestrator-round.md` only. No `fill_prompt()` change needed (its `str.replace` hits `{...}` tokens only; wouldn't touch `<...>` tokens). If combined with A (rename + angle-bracket for per-feature), adds ~5 more LOC.

**Robustness**: Stronger than A alone against priming because the syntactic class changes, not just the identifier. Maps directly onto the priming mechanism (priming is on shape, not name). Aligns with template-engine consensus (Azure Pipelines, dbt, Python `string.Template` vs `str.format`).

**Blast radius**: Slightly larger conceptually (second token syntax convention), slightly smaller in code.

**Philosophy fit**: Moderate-Strong. Adds a single convention to solve a documented class of bug; earns its place via template-engine consensus.

**Recurrence coverage**: Moderate — if codified ("session-fill uses `{X}`, agent-fill uses `<X>`"), future dual-layer prompts inherit disambiguation.

### C: Build-time inline (eliminate agent substitution)

**Implementation**: Rewrite `fill_prompt()` (or add a pre-dispatch Python helper) to read `state.features`, iterate the feature list for this round, and render per-feature blocks with literal paths before the orchestrator ever sees the prompt. Dispatch template becomes a repeatable section.

**Problem**: This significantly shifts the orchestrator's semantic role. Currently the orchestrator decides *which* features to dispatch at runtime via Step 1 (`features_to_run` filter) and Step 2a (intra-session dependency gate). Inlining per-feature blocks requires either (a) running the filter in Python before the orchestrator (moving responsibility out of the prompt) or (b) inlining ALL pending features — wasteful and doesn't solve priming (agent still picks).

**Estimated LOC**: 100-300. Files: `runner.sh`, `orchestrator-round.md`, likely a new Python helper.

**Philosophy fit**: Weak. Disproportionate to the observed 1-prompt, 1-collision bug.

### D: Tool-call / structured-output dispatch

**Implementation**: Replace the orchestrator → sub-agent dispatch with a tool call (e.g., `spawn_plan_agent(slug, spec_path, plan_path)`). Sub-agent prompt is a sealed template; orchestrator never substitutes. Or: orchestrator emits structured JSON, runner parses and dispatches.

**Problem**: Major change to the runner's dispatch architecture — the most load-bearing overnight component. Loses the orchestrator's current ability to dispatch plan-gen sub-agents in parallel via the Task tool.

**Estimated LOC**: 200-500+. Poor reversibility; touches `docs/overnight-operations.md` (source of truth per project CLAUDE.md).

**Philosophy fit**: Poor. Heavy machinery for a name collision.

### Recommendation

**Primary: A + B2 hybrid — rename session-level AND change per-feature delimiter**.

Rationale:
1. **Templating consensus is strong** (Azure Pipelines, dbt, Python `string.Template`): different substitution phases get different syntactic forms. The critic review's strongest finding is that "rename alone with same delimiter" is inference from n=1; template-engine consensus is direct evidence. B2 (`<feature.plan_path>` etc.) severs the collision at the shape layer at ~5-LOC additional cost over A.
2. **A alone is acceptable, but exposes residual priming** because the syntactic class stays the same. The adversarial finding on residual priming is real but bounded (adjacent instruction block mitigates it).
3. **B2 without A is insufficient** because `{plan_path}` still names two different things — confusing for future maintainers even if mechanically disambiguated.
4. **C and D are over-engineered** for the observed bug and its blast radius. Defer C/D to a future ticket only if a second priming occurrence arises after A+B2 lands.
5. **Recurrence coverage does not load-bear** because only `orchestrator-round.md` has the dual-layer pattern; other prompts are single-layer.

**Acceptable fallback: A alone (rename only, same delimiter) + adjacent instruction block**. This matches the ticket body's proposed approach and the research feasibility table's ~30-min estimate. Spec phase decides between A+B2 and A-only based on criticality weight and the critic-review outcome.

---

## Adversarial Review

- **Failure mode / Concern**: `feature_executor.py:518` hardcodes `plan_path = Path(f"lifecycle/{feature}/plan.md")`, ignoring `state.features[<slug>].plan_path`. Meanwhile, `orchestrator-round.md:234` states "read its `plan_path` and `spec_path` from the overnight state (these are stored per-feature and reflect the actual artifact locations, which may differ from `lifecycle/<feature-slug>/`)." The orchestrator DOES use state's per-feature `plan_path` for existence-check (line 244) and for writing the generated plan (line 269). But the executor then reads from a hardcoded path that may not match. Result: **the per-feature `{plan_path}` token the rename targets may be semantically ungrounded** if the executor ignores it.
  - Evidence: `feature_executor.py:518`, `orchestrator-round.md:234`, `orchestrator-round.md:244`.
  - **Resolution**: Spec phase must reconcile. Options: (a) narrow the ticket — pin the per-feature `{plan_path}` to a literal `lifecycle/{slug}/plan.md` in the dispatch template and remove it as a substitutable token (executor is authoritative); (b) widen the ticket — change `feature_executor.py:518` to read from state; or (c) defer — document the inconsistency as out-of-scope and ship the rename. **This is the single most consequential open question the spec must resolve.** See Open Questions below.

- **Failure mode / Concern**: The dispatch block (lines 260-285) mixes `{feature}` (line 261) and `{slug}` (lines 265, 266, 291) as per-feature tokens. If the new instruction block says "substitute `{slug}`, `{spec_path}`, `{feature_plan_path}` from state", the orchestrator may not substitute `{feature}` on line 261.
  - Evidence: `orchestrator-round.md:261, 265, 266, 291`.
  - **Resolution**: Spec phase must enumerate every per-feature token in the dispatch block in the instruction block's "you substitute these" list. Prefer collapsing `{feature}` → `{slug}` across lines 261/265/266/291 for consistency (the slug IS the feature identifier in `state.features` keys).

- **Failure mode / Concern**: Cross-repo `PLAN_PATH` override at `runner.sh:278` means session-level `{plan_path}` (to-be-renamed `{session_plan_path}`) resolves to a home-repo path even when the orchestrator runs in a target-repo worktree. A future reader of `{session_plan_path}` might assume the path is session-local.
  - Evidence: `runner.sh:274-279`.
  - **Resolution**: Name is clear enough as-is (`{session_plan_path}` refers to the session's plan, whose storage location is an implementation detail documented in the runner). No action needed; status quo semantics preserved by rename. Alternative name suggestion: `{home_session_plan_path}` is too verbose; `{session_plan_path}` with a prompt-header note is sufficient.

- **Failure mode / Concern**: Deploy atomicity hazard. `fill_prompt()` re-reads the prompt file each round, so prompt edits take effect mid-session. But `runner.sh` itself is loaded once by bash and stays loaded. A deploy window where only the prompt has rolled out would see `runner.sh`'s `fill_prompt()` still replacing `{plan_path}` while the prompt uses `{session_plan_path}` — the `{session_plan_path}` literal would bleed through unsubstituted.
  - Evidence: `runner.sh:97,383,385` (prompt re-read); `runner.sh:99,239,276-278,381,387` (shell loaded once).
  - **Resolution**: Spec must mandate **one of** the following deploy strategies:
    1. **Single-commit deploy with no active overnight sessions** — safest; match the project's standard practice of landing overnight-runner changes when no session is running.
    2. **Transitional substitution** — `fill_prompt()` substitutes BOTH `{plan_path}` and `{session_plan_path}` to the same value during the transition; remove the old substitution line in a follow-up commit once no active session could reference the old prompt.
  - Recommendation for spec: take option 1 (single-commit, no-active-session). The runner's standard deploy window is "between overnight sessions" anyway.

- **Failure mode / Concern**: Agent 2's template-engine consensus (distinct delimiter) vs Agent 4's "rename + instruction block is sufficient" is a direct tension. Agent 4's rationale rests on the observation that `{plan_path}` is the acute vector — but session 1708 is n=1, and the research explicitly notes orchestrator "stochastic behavior" (epic research.md intro) can produce variable outcomes.
  - **Resolution**: The recommendation has been revised above to prefer **A + B2 hybrid** (rename + delimiter change for per-feature tokens). Spec phase can fall back to A-only if implementation cost or additional-convention concerns outweigh the robustness gain — but should not treat A-only as "evidently sufficient." Acceptance: document the falsification criterion — if a second priming occurrence arises post-deploy, upgrade to B2.

- **Failure mode / Concern**: Instruction-block placement, format, and XML wrapping are underspecified. "Before the dispatch block" is not precise enough given Anthropic's adjacency guidance (the instruction block must be immediately next to the dispatch template, not 10-20 lines above it).
  - **Resolution**: Spec phase must specify (a) exact insertion point: immediately before the ``` that opens the sub-agent prompt at line 260; (b) format: prefer an XML-tagged block (`<substitution_contract>…</substitution_contract>`) to match Anthropic XML-tag-structured-prompts guidance; (c) content: an enumerated list of the per-feature tokens the orchestrator must substitute, each mapped to its state field, plus a warning "do not copy session-level absolute paths from earlier in this prompt."

- **Failure mode / Concern**: State-field injection vector. `state.features[<slug>].spec_path` and `plan_path` flow into sub-agent prompts without validation. The instruction block legitimizes substitution from state but doesn't address validation.
  - Evidence: `state.py:126` has `plan_path: Optional[str] = None` with no validator.
  - **Resolution**: **Out of scope** for this ticket. Spec must explicitly flag this in a "Deferred / Out-of-Scope" section so downstream reviewers don't interpret the instruction block as a security hardening. Track separately if/when a threat model demands it. Note this is true pre-ticket and remains true post-ticket — the rename does not regress security posture.

- **Failure mode / Concern**: Acceptance criterion 3 ("re-run of a failed-plan-parse style scenario produces correctly-substituted per-feature paths") has no concrete verification path. A unit test on `fill_prompt()` catches session-level rename but not agent-substitution behavior.
  - **Resolution**: Spec must define verification as **two tiers**:
    1. **Unit test** — `tests/test_fill_prompt.py` (new or extended): assert that after `fill_prompt()` runs, the output contains no `{session_plan_path}` literal, and contains the substituted `$PLAN_PATH` value at line-14/110/216 positions. This is automated and CI-gated.
    2. **Live validation** — the first overnight session post-deploy is the integration test. Document the validation criterion: "features that previously dispatched but failed at plan parse with literal `{slug}` in the path should now dispatch successfully." This is observed, not automated. Accept slow feedback.
  - No mock-orchestrator integration test is proposed — the dispatch behavior is emergent from the prompt and cannot be meaningfully mocked without reproducing the full runner+orchestrator loop.

- **Failure mode / Concern**: `tests/test_events_contract.py:20` pattern-matches the prompt file for `log_event(` occurrences. The rename does not touch `log_event()` calls, so this test is unaffected — but the spec must verify this explicitly before shipping.
  - **Resolution**: Confirm pre-shipment via local test run; no preemptive action needed in spec.

---

## Open Questions

Each item is tagged **Resolved** (answered inline) or **Deferred to Spec** (will be resolved in the Spec-phase structured interview with the user, with a research-recommended default).

1. **Reconcile the per-feature `{plan_path}` token with `feature_executor.py:518`'s hardcoded `lifecycle/{feature}/plan.md`**. The executor ignores `state.features[<slug>].plan_path`, making the per-feature token semantically advisory-only.
   - **Deferred to Spec**. Three options the spec interview must choose between: (a) narrow — pin per-feature plan path to a literal in the dispatch template and treat the token as a name placeholder; (b) widen — change `feature_executor.py:518` to read from state (small code change, larger scope creep); (c) defer — document as out-of-scope for this ticket. **Research recommendation: option (a)** (minimal change, matches ticket scope), with an optional standalone ticket for (b) if state/executor alignment becomes needed later.

2. **Collapse `{feature}` / `{slug}` inconsistency on lines 261, 265, 266, 291 of the dispatch block**. The two names refer to the same thing.
   - **Deferred to Spec**. **Research recommendation**: rename `{feature}` → `{slug}` on line 261 for consistency (one-line edit inside this ticket's scope). Spec interview confirms.

3. **Choose between A-alone and A+B2 hybrid** (rename vs rename-plus-delimiter-change). Template-engine consensus favors B2; ticket body suggests A-alone.
   - **Deferred to Spec**. **Research recommendation**: A+B2 hybrid (`<feature.plan_path>`, `<feature.spec_path>`, `<feature.slug>`) at ~5-LOC additional cost. Acceptable fallback: A-alone with a stronger XML-tagged instruction block. Spec interview decides.

4. **Deploy strategy — single-commit vs transitional**. Mid-session prompt/runner skew is a real hazard.
   - **Resolved**: single-commit deploy, land when no active overnight session is running. This matches project practice for runner-edge changes.

5. **Instruction-block format, placement, and content**.
   - **Resolved** at high level: placement is immediately before the ``` that opens the dispatch template at line 260; format is an XML-tagged block (`<substitution_contract>…</substitution_contract>`) consistent with Anthropic XML-tag guidance; content enumerates every per-feature token in the dispatch block with its state-field source. Spec may refine the exact wording.

6. **Verification strategy** for the rename.
   - **Resolved**: two-tier — (a) unit test `tests/test_fill_prompt.py` asserts no literal `{session_plan_path}` remains in the filled prompt and the substituted `$PLAN_PATH` value appears at the expected positions; (b) post-deploy, first overnight session acts as integration test with explicit observation criteria documented in the spec.

7. **State-field injection risk** from unchecked `state.features[<slug>]` values flowing into sub-agent prompts.
   - **Deferred** (scope note: pre-existing risk, not introduced by this fix; tracked separately if a threat model demands hardening).

8. **Session-level token rename naming**. Confirm `{session_plan_path}` is the chosen name.
   - **Resolved**: `{session_plan_path}` (session-level) and `{feature_plan_path}` or `<feature.plan_path>` (per-feature) per the ticket body's recommendation and research DR-1. The angle-bracket variant applies if A+B2 is chosen in (3).

9. **Existing test impact**.
   - **Resolved** (no impact): `tests/test_runner_signal.py:86` does not reference `{plan_path}`; `tests/test_events_contract.py:20` pattern-matches `log_event(` unaffected by token renames; `tests/test_batch_plan.py` uses `feature_plan_paths` as a separate Python API name, disjoint from the template token. Confirm pre-shipment via local test run.
