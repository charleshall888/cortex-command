# Plan: skill-suite-dedup

## Overview
Apply the spec's risk-first-then-fat-first edit program to the core skill constellation (lifecycle, refine, critical-review, research, discovery): fix two path-resolution bugs, then prune AI-authored How, coin leading words, single-source four duplicated rules, and trim description synonyms — all at lifecycle behavior parity. Each phase ends with `just build-plugin` (mirror regen) + `just test` (guard pinned surfaces) + a commit before the next begins.
**Architectural Pattern**: pipeline

## Outline

### Phase 1: Bugs (tasks: 1, 2, 3)
**Goal**: Fix Bug 1 (refine standalone gate resolution) and Bug 2 (discovery `research.md:104` bare-relative path) — the risk-bearing correctness edits.
**Checkpoint**: `cortex-check-skill-path` clean; `test_critical_review_gate_nonlocal_failsafe` green; mirrors regenerated; `just test` green; committed.

### Phase 2: Fat cuts (tasks: 4, 5, 6, 7)
**Goal**: Prune the three largest AI-bloat sites — research angle roster (R4, disclose conditional templates to a reference), `decompose.md` LEX-1 regex detail (R5), refine §4 gate procedural How (R6, prune in place).
**Checkpoint**: conditional templates relocated with placeholder coverage extended; regex detail gone but LEX-1 rule+example intact; §4 gate `(Recommended)` contract preserved; `just test` green; committed.

### Phase 3: Leading words + dedup (tasks: 8, 9a, 9b, 9c, 9d, 10)
**Goal**: Coin `tier ratchet` / `fresh-eyes` and collapse adversarial triads (R7); single-source the four duplicated rules while preserving all binds and the three model-resolution contracts (R8), pinned by a new wiring test.
**Checkpoint**: each coined term defined once and referenced by token; four rules single-sourced with citations; new model-resolution wiring test green; `just test` green; committed.
**Serialization note**: Tasks 8, 9a, 9c all write `skills/refine/SKILL.md` and are race-safe ONLY via the single-predecessor chain 8→9a→9c encoded in the `Depends on` edges below — this is NOT a parallel batch. 9b and 9d run parallel to that chain (disjoint files). The implement phase must honor the full transitive `Depends on` graph, not phase membership.

### Phase 4: Description trims (task: 11, 12)
**Goal**: Trim description synonyms to one-trigger-per-branch across the five skills, respecting fixture pins and the L1 surface ratchet.
**Checkpoint**: `test_l1_surface_ratchet` passes at equal-or-lower budget; routing fixture green; `just test` green; committed.

## Tasks

### Task 1: Fix Bug 1 — refine standalone gate resolution (R1)
- **Files**: `skills/refine/SKILL.md`, `skills/refine/references/specify.md`
- **What**: Make standalone `/cortex-core:refine` resolve the two lifecycle-sibling gate references itself instead of relying on lifecycle SKILL.md's manifest (which refine lacks off-repo). Add both targets to refine's Step 5 adaptation block as body-resolved sibling paths, and reword specify.md's three manifest-naming lines to reference "the propagated `<target>` path" without naming lifecycle's manifest, so both callers (lifecycle-wrapped and standalone-refine) satisfy it.
- **Depends on**: none
- **Complexity**: simple
- **Context**: refine SKILL.md's Step 5 block (`skills/refine/SKILL.md:142-149`) currently resolves only `criticality-matrix` at `:146` (`${CLAUDE_SKILL_DIR}/../lifecycle/references/criticality-matrix.md`); `orchestrator-review` and `critical-review-gate` are unresolved. Add an adaptation bullet mirroring the `:146` pattern that resolves both as `${CLAUDE_SKILL_DIR}/../lifecycle/references/{orchestrator-review,critical-review-gate}.md` and states specify.md's "propagated `<target>` path" phrasing binds to these. In `skills/refine/references/specify.md`, lines `:149` (orchestrator-review), `:153` (criticality-matrix), `:164` (critical-review-gate) each say "use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest" — reword to "the propagated `<target>` path" (target-neutral, caller-agnostic). Honor ADR-0009: no bare-relative or `../` paths introduced in the reference file itself — resolution stays in the body. `test_critical_review_gate_nonlocal_failsafe` pins the specify.md §3b heading + backend-read ordering (±35-line tolerance via kept-pauses parity) — keep edits local and do not move the §3b heading.
- **Verification**: `grep -c '\${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md' skills/refine/SKILL.md` ≥ 1 AND `grep -c '\${CLAUDE_SKILL_DIR}/../lifecycle/references/critical-review-gate.md' skills/refine/SKILL.md` ≥ 1 AND `grep -c 'propagation manifest' skills/refine/references/specify.md` = 0 — pass if all three hold.
- **Status**: [x] done

### Task 2: Fix Bug 2 — discovery research.md:104 path (R2)
- **Files**: `skills/discovery/references/research.md`
- **What**: Resolve the bare-relative `references/orchestrator-review.md` at `:104` consistently with discovery SKILL.md's sibling-path-propagation section, or document it as intentionally bare with a one-line rationale.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `skills/discovery/references/research.md:104` reads "read and follow `references/orchestrator-review.md` for the `research` phase" — a CWD-relative path. Discovery has its OWN `skills/discovery/references/orchestrator-review.md` (a delta file), but discovery SKILL.md's sibling-path-propagation section (`skills/discovery/SKILL.md:63-68`) resolves the **orchestrator-review** token to the lifecycle canonical (`${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`) at `:67`. Decide which the `:104` consumer intends: if the lifecycle canonical, reword `:104` to "the propagated **orchestrator-review** path" matching the SKILL.md manifest (same shape as Task 1's specify.md reword); if genuinely discovery's own delta file, keep `references/orchestrator-review.md` but add a one-line rationale comment that it intentionally targets discovery's local delta, not the propagated canonical. Same failure class as Bug 1, smaller blast radius. ADR-0009 applies.
- **Verification**: `grep -n 'references/orchestrator-review.md' skills/discovery/references/research.md` shows either zero bare-relative occurrences at `:104`, OR the line is accompanied by a rationale comment — pass if a bare unqualified `references/…` path no longer stands unexplained at `:104`.
- **Status**: [x] done

### Task 3: Phase 1 gate — regenerate mirrors, test, commit
- **Files**: `plugins/cortex-core/` (regenerated), `cortex/lifecycle/skill-suite-dedup/`
- **What**: Run `just build-plugin` to regenerate the cortex-core mirror from the edited canonical `skills/` sources, run the full `just test` suite to confirm no regression, then commit Phase 1 via `/cortex-core:commit`.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Dual-source enforcement — canonical edits under `skills/` must regenerate `plugins/cortex-core/` mirrors before commit, or the pre-commit Phase-4 drift loop blocks the commit and `test_dual_source_reference_parity` / `test_plugin_mirror_parity` fail. Order: `just build-plugin` first (so mirror-parity tests see fresh mirrors), then `just test`, then commit. This gate task owns the phase's single commit; Tasks 1–2 do not commit individually.
- **Verification**: `just build-plugin && just test` — pass if exit 0 and the aggregate summary reports all suites green (specifically `test_critical_review_gate_nonlocal_failsafe`, `test_plugin_mirror_parity`, `test_dual_source_reference_parity`, and the `cortex-check-skill-path` lint).
- **Status**: [x] done

### Task 4: Prune research angle roster (R4)
- **Files**: `skills/research/SKILL.md`, `skills/research/references/angle-templates.md` (new), `tests/test_dispatch_template_placeholders.py`
- **What**: Disclose the two conditional angle-prompt templates (Tradeoffs & Alternatives, Adversarial) to a new reference file, keeping the three always-fired core templates (Codebase, Web, Requirements & Constraints) inline. Update the Step 3 Dispatch protocol to read the relocated template back at dispatch time before substituting/dispatching. Extend the placeholder test to cover research/SKILL.md's markers, which it currently omits.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**: `skills/research/SKILL.md:73-192` holds the angle roster. Core (always-fired): "Codebase (core)" `:73`, "Web (core)" `:97`, "Requirements & Constraints (core)" `:119`. Conditional: "Tradeoffs & Alternatives (canonical example of an orchestrator-chosen angle)" `:139`, "Adversarial (always last for high/critical)" `:158`. Move the two conditional prompt blocks verbatim into `skills/research/references/angle-templates.md` and replace them inline with a pointer that names the file and the fire-conditions (orchestrator-chosen / high-critical-only). **Preserve each template's OWN placeholders, which differ per template — do NOT normalize them:** Tradeoffs carries `{topic}` + `{INJECTION_RESISTANCE_INSTRUCTION}` only; Adversarial carries `{topic}` + `{summarized_findings_from_other_agents}` + `{INJECTION_RESISTANCE_INSTRUCTION}`. `{research_considerations_bullets}` is **core-only** per the `:63-65` "considerations inject into the mandatory core angles only" contract — it stays in the three inline core templates and must NOT be added to the relocated conditional templates. The `{INJECTION_RESISTANCE_INSTRUCTION}` canonical-text definition at `:59` and the core templates stay in SKILL.md. **Wiring (load-bearing, not just the lint):** the Step 3 Dispatch protocol at `:180-192` constructs the Adversarial dispatch and substitutes `{summarized_findings_from_other_agents}` — once the template lives in `angle-templates.md`, the orchestrator must Read that file at dispatch to obtain the body before substituting; add that read step to the dispatch protocol, resolved as `${CLAUDE_SKILL_DIR}/references/angle-templates.md` (mirroring how `:51/:69/:182` resolve `fanout.md`), so SP001/SP002 passes and the dispatch still functions. `tests/test_dispatch_template_placeholders.py` currently covers only critical-review and lifecycle plan/review (see `test_req10*` functions) — add test(s) asserting: the three inline core templates in SKILL.md still carry `{topic}` / `{INJECTION_RESISTANCE_INSTRUCTION}` / `{research_considerations_bullets}`; and each relocated template in `angle-templates.md` carries its own correct marker set (Tradeoffs: `{topic}`+`{INJECTION_RESISTANCE_INSTRUCTION}`; Adversarial: those two plus `{summarized_findings_from_other_agents}`) — assert `{research_considerations_bullets}` is ABSENT from the relocated templates, not present.
- **Verification**: `grep -c 'You are the Adversarial research agent' skills/research/SKILL.md` = 0 AND `grep -c 'You are the Adversarial research agent' skills/research/references/angle-templates.md` = 1 AND `grep -c 'You are the Codebase research agent' skills/research/SKILL.md` = 1 AND `grep -c '{summarized_findings_from_other_agents}' skills/research/references/angle-templates.md` ≥ 1 AND `grep -c 'angle-templates.md' skills/research/SKILL.md` ≥ 1 (dispatch-read wired) AND the new/extended `test_dispatch_template_placeholders.py` research cases pass under `just test` AND `just check-skill-path` clean — pass if all hold.
- **Status**: [x] done

### Task 5: Trim decompose.md LEX-1 regex detail (R5)
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Delete the tool-maintainer regex-level detail from the LEX-1 prescriptive-prose rule while keeping the rule statement and at least one worked example inline (or, if a scanner needs it, relocate the regex to a scanner-spec reference — delete is preferred per the spec's How-pruning minimums).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `skills/discovery/references/decompose.md:95-114` states the LEX-1 rule plus tool-maintainer regex internals (~2353B). Keep the rule statement + 1-2 examples that let an author apply it; cut the regex the scanner tool owns. The delete-not-prune boundary (Open Decision in spec): cut tool-internal diagnostics/regex; keep the What (the rule) and enough example to apply it. Confirm which test covers the prescriptive-prose scanner and keep it green (do not weaken the rule the scanner enforces).
- **Verification**: In `skills/discovery/references/decompose.md`, the LEX-1 rule statement and ≥1 example remain (`grep -c 'LEX-1' skills/discovery/references/decompose.md` ≥ 1) AND the regex-level detail is absent — pass if the rule+example survive and the regex block is gone; the prescriptive-prose scanner test stays green under `just test`.
- **Status**: [x] done

### Task 6: Prune refine §4 complexity/value gate How (R6)
- **Files**: `skills/refine/SKILL.md`
- **What**: Prune procedural narration from the §4 complexity/value gate **in place** (no relocation — sole consumer is refine). Preserve the full What/Why AND every user-facing output contract of the gate (enumerated below) — cut only restated procedure and step-by-step method.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `skills/refine/SKILL.md:147` is the §4 gate (~1493B). The `(Recommended)` suffix (single leading space, capital R) and its preceding rationale clue are pinned by `test_refine_skill.py` within 35 lines of the gate anchor. **The keep-list is behavior + output-contract, not just the four originally-listed items — a naive four-item prune deletes real user-facing behavior and still passes a `(Recommended)` grep.** Keep ALL of: (1) the fire-conditions (3+ new state surfaces / new persistent format / ongoing per-feature upkeep); (2) the default-to-full-scope-else-smallest-downsize recommendation logic; (3) the `AskUserQuestion`-only-when-not-full-scope-or-low-confidence decision; (4) the `Confirm current scope (Recommended)` / `… (Recommended)` label strings; (5) the announcement **format contract** — the rationale is stated "phrased `\"I recommend X because Y.\"` — before any user-facing question"; (6) the else-branch **fold behavior** — when the check does not fire the AskUserQuestion, "fold the announcement into the existing approval surface (Approve / Request changes / Cancel) with no intervening pick-menu"; (7) the **downsize-alternatives menu** — "drop entirely", "bugs-only", "minimum viable", and the instruction to say so when one doesn't apply. Items (5)-(7) are output contract / decision behavior, NOT prunable How. Cut only restated procedure and method narration. Keep edits local — `test_lifecycle_kept_pauses_parity` sweeps `skills/refine/` with ±35-line tolerance.
- **Verification**: `grep -c '(Recommended)' skills/refine/SKILL.md` ≥ 1 AND `grep -c 'AskUserQuestion' skills/refine/SKILL.md` ≥ 1 AND `grep -c 'I recommend' skills/refine/SKILL.md` ≥ 1 (announcement format contract, item 5) AND `grep -c 'no intervening pick-menu' skills/refine/SKILL.md` ≥ 1 (fold behavior, item 6) AND `grep -Ec 'drop entirely|bugs-only|minimum viable' skills/refine/SKILL.md` ≥ 1 (downsize menu, item 7) AND the §4 gate byte count is reduced vs. baseline — pass if all hold; `test_refine_skill.py` and `test_lifecycle_kept_pauses_parity` green under `just test`.
- **Status**: [x] done

### Task 7: Phase 2 gate — regenerate mirrors, test, commit
- **Files**: `plugins/cortex-core/` (regenerated), `cortex/lifecycle/skill-suite-dedup/`
- **What**: `just build-plugin`, then full `just test`, then commit Phase 2 via `/cortex-core:commit`.
- **Depends on**: [4, 5, 6]
- **Complexity**: simple
- **Context**: Same dual-source discipline as Task 3. This gate additionally confirms the R4 placeholder-test extension and R6's `test_refine_skill.py` pins. Order: build-plugin → test → commit.
- **Verification**: `just build-plugin && just test` — pass if exit 0 and all suites green (notably `test_dispatch_template_placeholders.py`, `test_refine_skill.py`, `test_lifecycle_kept_pauses_parity`, mirror-parity).
- **Status**: [x] done

### Task 8: Coin leading words — tier ratchet, fresh-eyes, adversarial (R7)
- **Files**: `skills/critical-review/SKILL.md`, `skills/refine/SKILL.md`, `skills/refine/references/specify.md`, `skills/refine/references/seed-reconcile-gate-ordering.md`, `skills/refine/references/clarify-critic.md`, `skills/critical-review/references/reviewer-prompt.md`, `skills/critical-review/references/synthesizer-prompt.md`, `skills/critical-review/references/fallback-reviewer-prompt.md`
- **What**: Coin `tier ratchet` for the seed→reconcile→gate invariant and `fresh-eyes` for critical-review's no-anchoring concept, defining each exactly once and referencing by token thereafter; collapse the "don't be balanced" adversarial restatements that appear in ORCHESTRATOR-context prose onto the established `adversarial` token — but see the verbatim-prompt carve-out below.
- **Depends on**: [7]
- **Complexity**: complex
- **Context**: `tier ratchet` — restated at `skills/refine/SKILL.md:58` and `:135-138`, `skills/refine/references/specify.md:162`, and `skills/refine/references/seed-reconcile-gate-ordering.md`; "ratchet" already appears in the vocabulary. Define once (recommend: at seed-reconcile-gate-ordering.md, the rationale home) and reference by token elsewhere. `fresh-eyes` — critical-review's no-anchoring concept at `skills/critical-review/SKILL.md:18,36,99`. **Collision guard (spec Edge Case):** `critical-review/SKILL.md:99` "Anchor-checks" means the OPPOSITE, good/evidence sense — the `fresh-eyes` leading word must NOT overwrite or rename it; keep `:99` distinct. `adversarial` — the "don't be balanced" directives live at `skills/refine/references/clarify-critic.md:46,82,95` AND inside three verbatim sub-agent prompts: `reviewer-prompt.md:52`, `synthesizer-prompt.md:48`, `fallback-reviewer-prompt.md:39`. **Verbatim-prompt carve-out (load-bearing):** these prompts are passed to a fresh dispatched agent verbatim ("Pass the critic this prompt verbatim"); that agent has NO glossary in context and cannot resolve a bare `adversarial` token. Do NOT replace the operative in-prompt directive text ("Do not be balanced", the one-sided-critique / no-strengths steer) with a bare token in any file that is injected into a sub-agent prompt — the imperative instruction text must survive as instruction. Collapse restatement ONLY where the reader is the orchestrator (main-context prose), not the dispatched agent. Endorsed by `GLOSSARY.md:134` ("reach for an existing word first") — reuse, not invention. Keep edits local (kept-pauses parity sweeps refine/).
- **Verification**: `tier ratchet` has exactly one definition site — verify with `grep -rn 'tier ratchet' skills/` and inspect that exactly one occurrence is a definition (a sentence defining the term) and the rest are token-references; a bare `wc -l` count is insufficient because it cannot distinguish a definition from a reference. AND `grep -c 'Anchor-checks' skills/critical-review/SKILL.md` ≥ 1 (opposite-sense term preserved at `:99`) AND the three verbatim sub-agent prompts each retain their operative directive: `grep -c 'Do not be balanced' skills/critical-review/references/reviewer-prompt.md` ≥ 1 AND `grep -c 'Do not be balanced' skills/critical-review/references/synthesizer-prompt.md` ≥ 1 AND `grep -c 'Do not be balanced' skills/critical-review/references/fallback-reviewer-prompt.md` ≥ 1 — pass if each coined term has a single definition, Anchor-checks survives distinctly, and no verbatim prompt was reduced to a bare token; `just test` green.
- **Status**: [x] done

### Task 9a: Single-source the corrupted:true rule (R8)
- **Files**: `skills/lifecycle/references/criticality-matrix.md`, `skills/lifecycle/references/critical-review-gate.md`, `skills/lifecycle/references/orchestrator-review.md`, `skills/refine/SKILL.md`
- **What**: Make `criticality-matrix.md` the canonical statement of the `corrupted:true` handling rule; the other three sites cite it instead of restating.
- **Depends on**: [8]
- **Complexity**: simple
- **Context**: The `corrupted:true` rule appears at four sites: `skills/lifecycle/references/critical-review-gate.md:7`, `skills/lifecycle/references/criticality-matrix.md:30`, `skills/lifecycle/references/orchestrator-review.md:9`, `skills/refine/SKILL.md:146`. Keep the full rule at criticality-matrix.md (canonical); replace the other three with a one-line citation pointing to it. Preserve each site's runnable behavior — refine SKILL.md:146 also carries the `cortex-lifecycle-state … --field tier` bind and the criticality-matrix pointer (from Task 1); keep those. **Preserve refine's site-specific control-flow mapping:** refine `:146` maps the corrupted state onto refine's OWN §3b step — "treat the feature as requiring review (run the §3b gate) rather than defaulting to `simple` and skipping". The canonical at `criticality-matrix.md:30` phrases the consequence generically ("run the critical-review / orchestrator-review gate"), so a bare citation loses the §3b-specific steer at refine's tier-detection decision. Keep the "run the §3b gate rather than defaulting to simple and skipping" clause inline at refine `:146` alongside the citation. Depends on Task 8 because both edit `skills/refine/SKILL.md` — serialize to avoid a same-file race.
- **Verification**: The `corrupted:true` rule body appears once (canonical) at `criticality-matrix.md` and the other three sites carry a citation rather than a restatement — `grep -rn 'corrupted' skills/lifecycle/references/ skills/refine/SKILL.md` shows one authoritative definition + citations; `just test` green.
- **Status**: [x] done

### Task 9b: Single-source dispatch-protocol narration to fanout.md (R8)
- **Files**: `skills/research/SKILL.md`, `skills/discovery/references/research.md`, `skills/research/references/fanout.md`
- **What**: Replace the re-narrated dispatch protocol in research/SKILL.md and discovery research.md with pointers to `fanout.md`, keeping at each entry point the runnable model bind AND any site-specific dispatch facts the canonical fanout.md does not carry.
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: `skills/research/SKILL.md:180-192` and `skills/discovery/references/research.md:37-45` re-narrate `fanout.md`'s dispatch protocol. Point both to fanout.md (canonical) and keep the runnable `model=$(cortex-resolve-model …)` capture + `model:` bind each entry point carries per `skills/research/references/fanout.md:37`. **Preserve the searcher degrade-loud contract** (contract iii): the core-wave bind falls back to inherited model on resolve failure and never halts (`skills/research/SKILL.md:118` describes this). **Site-specific fact fanout.md does NOT carry — do not drop it:** `skills/research/SKILL.md:190` states "No `isolation: \"worktree\"`; agents are read-only." `fanout.md` never mentions worktree or read-only, so pointing to it cannot restore this; keep the read-only/no-worktree instruction inline at the research entry point. (Discovery's `research.md:37` carries its own copy — verify whether it too has a read-only/no-worktree note and preserve it if present.) Both entry points collapse two DIFFERENT narrations — verify each independently rather than assuming symmetry. Disjoint from Task 8's and 9a's files → may run parallel with them within Phase 3.
- **Verification**: `grep -c 'cortex-resolve-model' skills/research/SKILL.md` ≥ 1 (research bind survives) AND `grep -c 'cortex-resolve-model' skills/discovery/references/research.md` ≥ 1 (discovery bind survives — checked symmetrically, not only for the pointer) AND `grep -c 'fanout.md' skills/research/SKILL.md` ≥ 1 AND `grep -c 'fanout.md' skills/discovery/references/research.md` ≥ 1 AND `grep -Ec 'read-only|worktree' skills/research/SKILL.md` ≥ 1 (read-only/no-worktree contract retained at research entry) — pass if all hold; `just test` green.
- **Status**: [x] done

### Task 9c: Single-source backend write-back routing (R8)
- **Files**: `skills/refine/SKILL.md`
- **What**: Extract the backend-gated write-back 3-arm routing shape to a single source within refine, with each call site supplying its own fields — preserving site-specific quirks.
- **Depends on**: [9a]
- **Complexity**: simple
- **Context**: The backend-gated write-back 3-arm routing (cortex-backlog / none / external) is restated at `skills/refine/SKILL.md:71-79` and `:161-173`; `clarify.md:87` already names Step 3 "the canonical copy". Extract the routing shape once; each site supplies its fields. **Preserve site-specific quirks**: `:171`'s empty-`--areas` clearing (`cortex-update-item {slug} --areas` with no values clears the list) must survive at its site. Depends on Task 9a — both edit `skills/refine/SKILL.md`; serialize.
- **Verification**: The 3-arm routing appears once as a shared shape with per-site field supply, and the empty-`--areas` clearing behavior remains at `:171`'s site — `grep -c 'passing `--areas` with no values clears' skills/refine/SKILL.md` ≥ 1 (or equivalent phrasing) AND the routing narration is not duplicated verbatim; `just test` green.
- **Status**: [x] done

### Task 9d: Pin model-resolution contracts with a wiring test (R8)
- **Files**: `tests/test_model_resolution_wiring.py` (new)
- **What**: Add a static wiring test that pins each model-resolution call site's `--role` / `--criticality`-presence / halt-vs-degrade shape and the single-source-plus-citation structure of the R8 rules, so the three distinct contracts survive future narration collapses.
- **Depends on**: [9a, 9b, 9c]
- **Complexity**: simple
- **Context**: Three model-resolution contracts must be preserved (do NOT collapse ii into i — breaks standalone critical-review, which has no lifecycle state to read): (i) criticality-keyed + halt at `implement.md:165`, `review.md:22`, `orchestrator-review.md:45`, `competing-plans.md:16`; (ii) synthesizer no-criticality + halt at `competing-plans.md:61`, `critical-review/SKILL.md:70`; (iii) searcher degrade-loud never-halts at `research/fanout.md:32`. No existing test covers this. Add `tests/test_model_resolution_wiring.py` asserting each call site's `--role`/`--criticality`-presence and halt-vs-degrade shape, plus each single-sourced rule's one-definition-plus-citation structure. Depends on 9a/9b/9c so it pins post-edit state. **Manual invariant (not test-caught, per the `test_*_wired` disclaimer that runtime under-trigger is unassertable):** the per-site runnable bind must survive the narration collapse — reviewer confirms manually.
- **Verification**: `just test` runs `tests/test_model_resolution_wiring.py` and it passes, asserting all three contracts are present with correct halt-vs-degrade shape — pass if the new test is collected and green and the full suite stays green.
- **Status**: [x] done

### Task 10: Phase 3 gate — regenerate mirrors, test, commit
- **Files**: `plugins/cortex-core/` (regenerated), `cortex/lifecycle/skill-suite-dedup/`
- **What**: `just build-plugin`, then full `just test`, then commit Phase 3 via `/cortex-core:commit`.
- **Depends on**: [8, 9a, 9b, 9c, 9d]
- **Complexity**: simple
- **Context**: Same dual-source discipline as Tasks 3/7. Confirms the new `test_model_resolution_wiring.py`, kept-pauses parity, and mirror parity all green after the leading-word + single-source edits.
- **Verification**: `just build-plugin && just test` — pass if exit 0 and all suites green (notably `test_model_resolution_wiring.py`, `test_lifecycle_kept_pauses_parity`, mirror-parity, `test_competing_plans_wired`, `test_refine_reconcile_wiring`).
- **Status**: [x] done

### Task 11: Trim description synonyms (R9)
- **Files**: `skills/lifecycle/SKILL.md`, `skills/refine/SKILL.md`, `skills/critical-review/SKILL.md`, `skills/research/SKILL.md`, `skills/discovery/SKILL.md`
- **What**: Trim description synonyms to one-trigger-per-branch across the five skills, respecting the `skill_trigger_phrases.yaml` pins and keeping the lifecycle mirror-regen maintenance note (governance-load-bearing ambient context) unless relocated.
- **Depends on**: [10]
- **Complexity**: complex
- **Context**: The five skill `description`/`when_to_use` fields carry 6-11 synonyms per branch. **Fixture-constrained**: `tests/fixtures/skill_trigger_phrases.yaml` pins several lifecycle phrases — trim only the free (unpinned) synonyms; do not remove a pinned phrase. Keep the lifecycle description's mirror-regen note (it is governance-load-bearing) unless relocated. **L1 surface ratchet**: `test_l1_surface_ratchet.py` requires equal-or-lower byte budget — trims must not regrow; critical-review sits at its 795B cluster ceiling, so its description must not grow. Confirm the routing fixture still resolves each skill's intended triggers after the trim.
- **Verification**: `just test` runs `test_l1_surface_ratchet.py` (equal-or-lower passes) and the routing fixture, both green, AND each trimmed skill's pinned `skill_trigger_phrases.yaml` phrases still present — pass if the ratchet holds at equal-or-lower budget and routing/fixture tests stay green.
- **Status**: [x] done

### Task 12: Phase 4 gate — regenerate mirrors, test, commit
- **Files**: `plugins/cortex-core/` (regenerated), `cortex/lifecycle/skill-suite-dedup/`
- **What**: `just build-plugin`, then full `just test`, then commit Phase 4 via `/cortex-core:commit`.
- **Depends on**: [11]
- **Complexity**: simple
- **Context**: Final gate. Confirms `test_l1_surface_ratchet.py`, the routing fixture, and mirror parity green. Completes the edit program.
- **Verification**: `just build-plugin && just test` — pass if exit 0 and the aggregate summary reports all suites green.
- **Status**: [ ] pending

## Risks
- **R6 §4-gate pruning near the pinned `(Recommended)` string** — `test_refine_skill.py` pins the format string within 35 lines of the gate anchor and `test_lifecycle_kept_pauses_parity` enforces a ±35-line tolerance. Over-aggressive deletion breaches parity. Mitigation: prune in place, keep all seven enumerated keep-list elements (Task 6 items 1–7, including the announcement phrasing, no-pick-menu fold, and downsize menu), keep edits local. If the parity tolerance is breached, the gate must be re-pruned more conservatively rather than the test relaxed.
- **R8 model-resolution collapse** — collapsing the synthesizer contract (ii) into the criticality-keyed one (i) silently breaks standalone critical-review off-repo. Mitigation: Task 9d's wiring test pins all three contracts; the manual per-site-bind invariant is called out for reviewer confirmation.
- **Verification pins strings, not runtime behavior (review through-line)** — the per-task grep checks and `just test` are static guards; several named tests (`test_critical_review_gate_nonlocal_failsafe`, `test_competing_plans_wired`, `test_refine_reconcile_wiring`) disclaim runtime coverage in their own docstrings. No gate drives the wrapped lifecycle→refine path behaviorally. Mitigation: the strengthened per-task greps (Tasks 4/6/8/9a/9b) now pin the specific semantic tokens each dropped span carried; the residual behavioral confidence rests on the implementer/reviewer manually confirming the wrapped path still fires — this is an accepted limitation, not a closed gap.
- **Verbatim sub-agent prompt integrity (R7)** — collapsing an adversarial directive onto a bare token inside a prompt injected into a fresh dispatched agent strips the steer (the agent has no glossary). Mitigation: Task 8's verbatim-prompt carve-out forbids token-only collapse in `reviewer-/synthesizer-/fallback-reviewer-prompt.md` and `clarify-critic.md`; verification greps each prompt for its surviving `Do not be balanced` directive.
- **Scope call — R3 dropped.** `implement.md §1a` is intentionally untouched (spec Non-Requirement): ~zero recoverable fat against unconditional `test_lifecycle_step_v_ordering.py` failure. Do not reopen it in this lifecycle. If the operator wants §1a addressed, it is a separate ticket.
- **New reference-file reachability + dispatch-read (R4)** — `skills/research/references/angle-templates.md` must be body-resolved from research SKILL.md per ADR-0009 (or `cortex-check-skill-path` SP001/SP002 flags it), AND the Step 3 dispatch protocol must Read it back at dispatch time so the relocated Adversarial template body is available for `{summarized_findings_from_other_agents}` substitution. Mitigation: Task 4 wires both; verification greps the pointer and runs the lint.
- **Line-anchor drift across phases** — Phase-1/2 edits above lines 161–173 shift the `:171` empty-`--areas` anchor that Phase-3 Task 9c cites. Mitigation: every line locator in the plan is paired with a content anchor (e.g. "`:171`'s empty-`--areas` clearing"); implementers must grep the content anchor, not seek the literal line.

## Acceptance
The wrapped lifecycle→refine path is byte-reduced and its behavior is preserved to the limit of the project's static guards: every phase gate (`just build-plugin` clean + `just test` fully green) passes; standalone `/cortex-core:refine` in an off-repo consumer now resolves its orchestrator-review and critical-review gates (Bug 1 fixed — verified: refine and lifecycle ship co-located in the cortex-core plugin, so the sibling reference paths resolve); the four single-sourced rules each have one authoritative definition with citations, with each site's runtime-runnable binds and site-specific facts retained; and the three model-resolution contracts are pinned by a passing wiring test. **Parity qualifier:** the guards are static-string/ordering checks, not runtime behavioral simulation — "no intended change to lifecycle control flow or gate behavior" (R10) is enforced by the strengthened per-task semantic-token greps plus manual confirmation of the enumerated keep-lists, not by a test that drives the wrapped path end-to-end.
