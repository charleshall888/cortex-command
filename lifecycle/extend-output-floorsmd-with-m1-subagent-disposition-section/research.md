# Research: Extend output-floors.md with M1 Subagent Disposition section

## Epic Reference

Parent: [`research/opus-4-7-harness-adaptation/research.md`](../../research/opus-4-7-harness-adaptation/research.md). This ticket narrows the epic to a single deliverable: codify M1 (audience/routing) as a scoped section in `claude/reference/output-floors.md` — one file, M1 only, M2/M3 explicitly deferred.

## Codebase Analysis

### Files that will change

- **Primary**: `claude/reference/output-floors.md` — add a new section codifying M1 dispositions.
- **Possibly required** (see Open Questions 2, 4): `claude/Agents.md` — the conditional-loading trigger row at line 25 may need update; `claude/reference/output-floors.md` — the document-level Applicability block at lines 69–75 may need revision (it currently excludes `critical-review` and `research`, which are cited as M1 sites in the epic).

### Current structure of `claude/reference/output-floors.md`

Section order: title + preamble → Phase Transition Floor → Approval Surface Floor → Overnight File-Based Addendum → Downstream Consumption → Applicability.

Existing "Floor" sections share a consistent shape:
- `## [Name] Floor` heading
- Preamble sentence
- 2-column markdown table `| Field | What to include |` listing **required output fields**
- Closing scope/applicability note

Length per existing floor section: ~10 lines.

**Document-level Applicability block** (lines 69–75):
```
Output floors apply to skills that produce phase transitions or approval surfaces:
- `lifecycle` (phase transitions + approval surfaces)
- `discovery` (phase transitions — per-skill calibration via #052)

Skills without phase transitions (commit, pr, backlog, dev) are not subject to these floors.
```

**Downstream Consumption block** names #052 (skill-prompt audit) and #053 (subagent output formats) as consumers.

### Agents.md conditional-loading row for output-floors.md

`claude/Agents.md` line 25:
> Writing phase transition summaries, approval surfaces, or editing skill output instructions → `~/.claude/reference/output-floors.md`

This trigger is ambiguous for the new use case. "Editing skill output instructions" reads as "instructions to a skill about its own output" (already covered). A dispatch-skill author writing a subagent prompt is plausibly outside this phrasing — they're writing instructions given TO a subagent about ITS output.

### Real post-fix phrasings in #067/#068/#069 (worked-example source)

- **#067** — `skills/critical-review/SKILL.md` lines 215–219: count-only Dismiss line (`Dismiss: N objections`), direction-oriented Apply verbs (`strengthened, narrowed, clarified, added, removed, inverted`), "Omit the Dismiss line when N = 0."
- **#068** — `skills/lifecycle/references/clarify-critic.md` lines 81–88: "The sole output of the dispositioning step is the structured YAML artifact. It is not free-form prose." Dismiss rationales route to `dismissals[].rationale` inside the `clarify_critic` event — "never in the user-facing response surface."
- **#069** — `skills/lifecycle/references/specify.md` lines 55, 61–71, 79: "All checks are silent on pass"; "on failure, surface only the specific failing claim or unresolved item as a single terse bullet (≤15 words) — no preamble, no restatement of the check, no pass-side narration."

### Epic research — M1 vocabulary (per `research/opus-4-7-harness-adaptation/research.md` lines 74–79)

M1 defined as "explicit positive routing" with three observed shapes: `log-only`, `silent re-run, surface pass/fail`, `absorb into internal state, emit nothing`. DR-6 (lines 232–239) recommends extending `output-floors.md` over adding a new reference file.

### Integration points

- `output-floors.md` is conditionally loaded via `Agents.md:25`; it's not eagerly loaded.
- No skill currently cites a subagent-disposition floor by name (it doesn't exist yet).
- The document-level Applicability block is implicitly load-bearing for the two existing floors.

### Conventions

- Direct, prescriptive tone (`must include`, `do not`).
- Terse sections (~10 lines each).
- Cross-references in prose (`per the Approval Surface Floor`), not markdown links.

## Web Research

- **No established multi-agent framework has a named vocabulary for "log-only", "silent", "absorb" as prompt-level dispatch-disposition terms.** The problem (parent must shape subagent returns) is widely acknowledged: Anthropic Agent SDK docs, huuhka.net, dev.to, Google ADK "Developer's guide to multi-agent patterns," OpenAI Agents SDK all discuss it — but none name a closed disposition taxonomy.
- **Closest prior-art anchors**:
  - OpenAI Agents SDK "agent-as-tool vs. handoff" — a binary architectural choice (manager retains voice vs. ownership transfer).
  - OpenAI Agents SDK `custom_output_extractor` — programmatic post-processing of a subagent's return before it enters the parent. Closest mechanism to "absorb into internal state."
  - LangChain `return_direct=True` — tool output bypasses the agent's post-tool LLM step. Opposite-end knob.
  - Google ADK scatter-gather with synthesizer pattern — governs aggregation, not per-dispatch disposition.
- **Anthropic's only first-party guidance** on routing (Claude Agent SDK subagents doc): "The parent receives the subagent's final message verbatim as the Agent tool result, but may summarize it in its own response. To preserve subagent output verbatim in the user-facing response, include an instruction to do so in the prompt or `systemPrompt`." This addresses preserve-verbatim only — not silent/log-only/absorb.
- **Honest bottom line**: codifying "audience/routing" as a named taxonomy would be a genuine project-native contribution. The spec should be explicit that the vocabulary is cortex-command-specific, not a reference to any canonical external standard.

## Requirements & Constraints

- **`requirements/project.md:19–22` (Complexity principle)**: "Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." Load-bearing for the premature-abstraction concern (see Open Question 5).
- **`requirements/project.md:46` (In Scope)**: "Global agent configuration (settings, hooks, reference docs)" — reference-doc work is in scope.
- **No requirements file governs reference-doc content**, conditional-loading trigger wording, or the M1/M2/M3 taxonomy. The taxonomy originates in `research/opus-4-7-harness-adaptation/research.md` and the backlog item — these are the sources of authority.
- **Extend-not-add precedent**: backlog #086 cites DR-6's rationale — avoid adding conditional-loading weight. This supports extension over a new reference file but does not by itself support the extension happening *now*.

## Tradeoffs & Alternatives

Four dimensions were explored. Post-adversarial review, the initial leanings carry material caveats.

### Dimension 1 — Placement within output-floors.md

| Option | Summary | Caveat |
|---|---|---|
| A: Dedicated top-level section at document top | Highest discoverability | Breaks the file's narrative arc; signals that M1 is the central topic |
| B: Nested subsection under an existing Floor | Minimizes churn | Semantic mismatch — Phase Transition governs orchestrator output to user; M1 governs subagent return to orchestrator |
| C: New peer section appended after Approval Surface Floor | Structurally consistent with existing `## X Floor` headings | "Floor" label is a mild stretch; dispositions like `emit nothing` are upper bounds, not lower bounds |

Initial lean: **C**. Adversarial caveat: "Floor" framing is a **categorical mismatch**, not just a stretch. The existing floors define minimum output fields (lower bounds); M1 governs routing metadata on input prompts (often upper bounds). Forcing M1 into a `Floor` either requires (a) a document-level reframing sentence at line 7 to widen the doc's scope, or (b) a different section title (e.g., `Subagent Disposition Rule`, `Dispatch Prompt Contract`).

### Dimension 2 — Normative vocabulary

| Option | Summary |
|---|---|
| A: Accept backlog's enumerated list verbatim (`log-only`, `silent re-run`, `absorb and surface pass/fail`, `emit only Ask items`, "etc.") | Matches what's already socialized; "etc." dilutes the "explicit" message |
| B: Use DR-6's three narrower phrasings as canonical | Anchored to research; three terms may not cover future cases |
| C: Archetype-per-case from F1/F4/F5 | Overfits to three observations |
| D: Open-ended — state the rule without a closed vocabulary | Maximum flexibility; risks being too abstract |

Initial lean: **D with illustrative B examples**. Adversarial caveat: even option D cannot prevent M2/M3 drift, because two of the three DR-6 phrasings themselves mix routing with output-gating. "Silent re-run, surface pass/fail" combines routing (surface pass/fail) with length (no narration, M2). "Absorb into internal state, emit nothing" combines routing with output-gate (M3). The taxonomic line between M1 and M3 is not crisp in the epic research — see Open Question 1.

### Dimension 3 — Worked-example format

| Option | Summary |
|---|---|
| A: Verbatim quotes from post-fix skill files | Citation drift as skill files evolve |
| B: Paraphrased patterns with `see #0NN` citations | Reference-doc convention; depends on reader being able to resolve the citation |
| C: Synthetic minimal archetypes with ticket references as case-study citations | Citation-stable; synthetic feel may weaken authority |

Initial lean: **B**. Adversarial caveat: overnight agents conditionally loading `output-floors.md` do NOT automatically load `lifecycle/067/`, `lifecycle/068/`, `lifecycle/069/`. The citation is effectively inert for the target audience (overnight agents authoring new dispatch skills). Either the paraphrase must be self-sufficient (carrying the pattern without needing the citation to resolve), or the examples must be inlined verbatim and accept the drift risk. Option B as initially leaning is under-specified on this point.

### Dimension 4 — Applicability scope

| Option | Summary |
|---|---|
| A: Inherit document-level Applicability | Zero redundancy; consistent with existing floors |
| B: New section declares its own Applicability block | Faithful to DR-6's narrower scope but sets a per-section precedent |
| C: Refine document-level Applicability, then inherit | One block, more precise; touches load-bearing text |

Initial lean: **A with in-body clarifier**. Adversarial caveat: the document-level Applicability explicitly names `lifecycle` and `discovery` only and excludes `commit, pr, backlog, dev`. `critical-review` and `research` are peer skills that **are not named** — and they are cited as M1 sites in the epic research (critical-review specifically). A new M1 section that inherits the document-level Applicability would spuriously **not** apply to the only worked-example source site outside lifecycle (`critical-review/SKILL.md`, #067). In-body clarifier cannot override a document-level exclusion list. This dimension needs **C** (refine document-level) or **B** (new section declares its scope explicitly).

### Recommended combination (post-adversarial)

No single combination dominates. The recommendation above (C + D-with-B-examples + B + A-with-clarifier) does not survive adversarial review cleanly — at minimum, D4 must shift to B or C, D1 may need a doc-level reframing or a non-"Floor" title, and D3 needs a decision on inline vs. cited examples. Several of these are genuinely spec-phase decisions; see Open Questions.

## Adversarial Review

The adversarial agent found that multiple agent-4 "leanings" rest on unchallenged assumptions, and that the ticket as scoped may not deliver coherent output without scope expansion. The core concerns:

- **Floor framing is a categorical mismatch**, not just handwaving. The existing floors inventory minimum output fields; M1 is routing metadata on input prompts, often an upper bound.
- **Applicability scope is incoherent with the ticket's own worked examples**: the document-level Applicability excludes `critical-review`, but #067 (cited as a worked example) lives in `critical-review/SKILL.md`.
- **Agents.md trigger row will likely under-fire** for the new use case under 4.7's literal reading. The ticket does not list an Agents.md update as a deliverable — this is a scope miss.
- **M1/M2/M3 collapse may be incoherent**: two of the three canonical M1 phrasings mix routing with gating/length. The "60% of failures are M1" figure in the epic research depends on this collapse.
- **Paraphrase + citation assumes readers can resolve the citation.** Overnight agents don't eagerly load cited lifecycle dirs. The citation is effectively inert for the target audience.
- **Adding a load-bearing section to a globally-loaded reference doc carries a precedence-collision risk** with the inline dispositions in #067/#068/#069.
- **Premature-abstraction case is stronger than Agent 3 allowed**: the harm is already prevented at the only three observed sites. Codification is preventive for a sixth hypothetical site. `requirements/project.md`'s "Must earn its place by solving a real problem that exists now" is a load-bearing criterion.
- **Stable reference docs citing volatile lifecycle dirs inverts drift direction**: reference docs should be anchors, not citers.

The adversarial agent recommended mitigations (drop the "Floor" label, fix Applicability scope explicitly in the same ticket, update Agents.md in the same ticket, inline examples rather than cite, resolve the M1/M3 collapse, consider defer). The research author does NOT preempt these — they are scope-expansion or scope-reduction decisions that belong to the user at spec phase.

## Open Questions

Each question below is **deferred to spec-phase** (or user disposition before spec): the research has surfaced the question and identified the source material; the user decides the disposition.

1. **M1 vs. M2/M3 boundary — is the epic-research taxonomy coherent, or does it pre-collapse M1/M3 in a way that undermines the codification?** The three DR-6 phrasings (`log-only`, `silent re-run surface pass/fail`, `absorb into internal state emit nothing`) mix routing with gating and length. F4 and F5 fixes in `specify.md` are predominantly output-gating (`silent on pass`, `≤15-word bullet on fail`), not pure routing. Options: (a) accept the existing taxonomy and codify M1 as "routing including gating-as-routing"; (b) narrow the section to pure routing only (log-only + absorb), excluding the gating-colored phrasings; (c) reopen DR-6 upstream and defer #086 pending taxonomy resolution. **Deferred: user decides at spec.**

2. **Access-path semantics — does `claude/Agents.md:25` need update in the same ticket?** Current trigger: "Writing phase transition summaries, approval surfaces, or editing skill output instructions." Under 4.7 literal-reading (the epic's motivating model, OQ5), a dispatch-skill author writing a subagent prompt is plausibly outside this trigger. Options: (a) ship #086 without updating Agents.md and accept that the new section may not fire for its intended audience; (b) expand the trigger row to explicitly name subagent-dispatch authoring; (c) add a new trigger row for `output-floors.md`. The backlog item does NOT currently list this as a deliverable. **Deferred: user decides at spec — scope expansion.**

3. **Applicability scope — the document-level block excludes `critical-review`.** Backlog #086 says "Applicability: lifecycle and discovery skills (matching `output-floors.md`'s existing scope)." But the only `critical-review` worked example (#067) cannot be codified by a rule whose Applicability excludes `critical-review`. Options: (a) refine the document-level Applicability block to include `critical-review` and `research` as dispatch skills (expands scope of #086 to touch the existing block); (b) give the new section its own explicit Applicability block naming dispatch skills: `lifecycle`, `discovery`, `critical-review`, `research` (sets per-section precedent); (c) drop the #067 worked example and scope the section to lifecycle + discovery only. **Deferred: user decides at spec.**

4. **Floor framing — is the new section structurally a "Floor"?** Existing floors inventory minimum output fields; M1 governs routing metadata on input prompts. Options: (a) call it `Subagent Disposition Floor` and accept the framing stretch; (b) call it `Dispatch Prompt Contract` or `Subagent Disposition Rule` (drops "Floor" — might require widening the document's opening preamble at line 7); (c) restructure `output-floors.md` into two parts (Output-Field Floors, Dispatch-Prompt Contracts) with separate preambles. **Deferred: user decides at spec.**

5. **Premature abstraction — should #086 be deferred until a second site emerges?** The harm is already prevented in the three observed sites (#067/#068/#069 landed). Codification is preventive for a sixth hypothetical site. `requirements/project.md` favors the simpler path when in doubt. Options: (a) ship #086 now (codify-forward posture); (b) defer #086 until a sixth dispatch-skill site surfaces naturally; (c) defer and revisit after 60 days / after next overnight cycle lands another dispatch skill. **Deferred: user decides before spec (may close #086).**

6. **Worked-example format — inline or cite?** Overnight agents conditionally loading `output-floors.md` do not auto-load `lifecycle/067/`, `lifecycle/068/`, `lifecycle/069/`. Options: (a) inline three verbatim snippets (higher drift risk, self-sufficient for reader); (b) inline synthetic archetypes + ticket citations (medium drift risk, synthetic feel); (c) paraphrase + citation and accept that citations are inert for most readers (lowest self-sufficiency). **Deferred: user decides at spec.**

7. **Precedence-collision risk — does a new load-bearing section alter the inline behavior of #067/#068/#069?** The existing document preamble at line 9 says "the expanded definitions here supersede the inline names." Under 4.7's literal reading, a new Subagent Disposition Floor may supersede the deliberate inline wording chosen in #067/#068/#069. Options: (a) explicitly scope the new section to NOT supersede inline dispositions in already-remediated skills (adds a scope carve-out); (b) accept that the new section does supersede and verify #067/#068/#069 remain compliant with the general rule; (c) remove or soften the "supersede" phrasing in the doc preamble. **Deferred: user decides at spec — non-trivial regression surface.**

8. **Drift-direction inversion — should `output-floors.md` cite lifecycle dirs at all?** Reference docs are meant to be stable anchors cited BY skill and lifecycle files. A citation from `output-floors.md` into `lifecycle/067/` inverts the dependency direction and creates a new drift vector (archived/renamed lifecycles silently break the reference). Options: (a) accept the inversion and add a test guarding citation validity; (b) cite by ticket number only (no lifecycle-dir path), accepting that readers cannot follow the citation; (c) inline verbatim without any citation to lifecycle artifacts. **Deferred: user decides at spec.**
