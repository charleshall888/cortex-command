# Review: skill-suite-dedup

## Stage 1: Spec Compliance

### Requirement R1 (Bug 1): refine standalone gate resolution
- **Expected**: refine SKILL.md Step 5 block resolves `orchestrator-review.md` and `critical-review-gate.md` itself as body-resolved `${CLAUDE_SKILL_DIR}/../lifecycle/references/…` paths; `specify.md:149/153/164` reworded to "the propagated `<target>` path" without naming lifecycle's manifest.
- **Actual**: A new `§3a/§3b gate references` bullet in refine SKILL.md resolves both targets as `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md` and `…/critical-review-gate.md`. `specify.md` §3a, §3b, and the criticality-matrix read all reworded to "the propagated `<target>` path"; `propagation manifest` count in specify.md is now 0.
- **Verdict**: PASS
- **Notes**: greps hold (orchestrator-review sibling =1, critical-review-gate sibling =1, propagation manifest =0). `test_critical_review_gate_nonlocal_failsafe` green; ADR-0009 honored (resolution stays in the body, no bare-relative/`../` introduced in the reference file).

### Requirement R2 (Bug 2): discovery research.md:104 path
- **Expected**: no bare-relative `references/…` path stands unexplained at `:104`, OR a one-line rationale is present.
- **Actual**: An HTML-comment rationale was added at `:104` documenting that `references/orchestrator-review.md` intentionally targets discovery's OWN local delta file (which itself reads the lifecycle canonical via SKILL.md propagation), so it is deliberately not in the lifecycle-sibling manifest.
- **Verdict**: PASS
- **Notes**: This is the "documented as intentionally bare with rationale" branch of the acceptance criterion — a legitimate resolution. The rationale is accurate: discovery has its own delta at `skills/discovery/references/orchestrator-review.md`. `cortex-check-skill-path` green.

### Requirement R3: DROPPED — verify NOT implemented
- **Expected**: `implement.md §1a` untouched (Non-Requirement; unconditional `test_lifecycle_step_v_ordering.py` failure risk).
- **Actual**: `skills/lifecycle/references/implement.md` does not appear in the diff at all.
- **Verdict**: PASS (correctly not implemented)
- **Notes**: Confirmed via `git diff --stat` — implement.md is not in the changed-file set.

### Requirement R4: prune research angle roster
- **Expected**: the two conditional templates (Tradeoffs, Adversarial) relocated to a reference; core templates + placeholder markers intact; dispatch protocol reads the relocated file; placeholder test extended.
- **Actual**: Both conditional prompt blocks moved verbatim into new `skills/research/references/angle-templates.md`; three core templates stay inline. Dispatch protocol now Reads `${CLAUDE_SKILL_DIR}/references/angle-templates.md` for both waves before substituting. `{research_considerations_bullets}` correctly stays core-only (3× inline, absent from relocated file).
- **Verdict**: PASS
- **Notes**: All greps hold (Adversarial in SKILL =0, in angle-templates =1; Codebase inline =1; angle-templates ref =3). Three new placeholder tests added and green — they pin the per-template marker sets and the core-only-considerations absence, non-tautological.

### Requirement R5: trim decompose.md LEX-1 regex detail
- **Expected**: regex-level detail absent; LEX-1 rule statement + ≥1 example present.
- **Actual**: The "LEX-1 regex specification" block (Pattern 1/2/3, section-boundary detection) deleted; replaced by a one-line pointer that the scanner owns the exact patterns. Rule statement, forbidden/permitted section list, and the full "Worked examples" (PASSES/FLAGS) survive.
- **Verdict**: PASS
- **Notes**: `grep -c 'regex'` = 0; LEX-1 rule + worked examples present. Delete-not-prune boundary honored per spec's How-pruning minimums.

### Requirement R6: prune refine §4 gate How in place
- **Expected**: gate stays in refine SKILL.md; all SEVEN keep-list elements survive (fire-conditions, default-recommendation logic, AskUserQuestion decision, `(Recommended)` strings, "I recommend X because Y." announcement, "no intervening pick-menu" fold, "drop entirely"/"bugs-only"/"minimum viable" downsize menu).
- **Actual**: Gate pruned in place. All seven elements present: fire-conditions (3+ state surfaces / new format / ongoing upkeep), default-full-scope-else-smallest-downsize logic, AskUserQuestion-only-when-not-full-scope-or-low-confidence decision, ` (Recommended)` suffix string, `"I recommend X because Y."`, "no intervening pick-menu", and the drop-entirely/bugs-only/minimum-viable menu.
- **Verdict**: PASS
- **Notes**: All five greps hold; `test_refine_skill.py` + `test_lifecycle_kept_pauses_parity` green. Byte-reduced (~399→357B description window plus body prose collapse) at output-contract parity.

### Requirement R7: coin tier ratchet / fresh-eyes; collapse adversarial triads
- **Expected**: each term defined exactly once and referenced by token thereafter; `:99` "Anchor-checks" (opposite sense) preserved distinctly; verbatim sub-agent prompts retain their operative "Do not be balanced" directive (not reduced to a bare token).
- **Actual**: `tier ratchet` defined once in `seed-reconcile-gate-ordering.md:5` (the rationale home), referenced by token at refine SKILL.md:58 and :138. `fresh-eyes` coined at critical-review SKILL.md:18, referenced at :36. `Anchor-checks` preserved (count =1). All three verbatim prompts (reviewer/synthesizer/fallback-reviewer) retain `Do not be balanced` (each =1).
- **Verdict**: PASS
- **Notes**: The verbatim-prompt carve-out was respected — the operative imperative text survives as instruction in every injected prompt; only orchestrator-context restatements were collapsed onto the token.

### Requirement R8: single-source four rules; preserve three model-resolution contracts
- **Expected**: `corrupted:true` → criticality-matrix canonical (three sites cite); dispatch narration → fanout.md while keeping each site's runnable `cortex-resolve-model` bind; write-back routing single-sourced with `:171` empty-`--areas` quirk preserved; refine's §3b-specific corrupted mapping survives; read-only/no-worktree fact survives at research entry; three contracts (i criticality-keyed+halt / ii synthesizer no-criticality+halt / iii searcher degrade-loud never-halts) remain distinct; new wiring test added.
- **Actual**: `corrupted:true` body single-sourced at criticality-matrix.md:30; the three other sites carry citations. refine SKILL.md:146 keeps the "run the §3b gate rather than defaulting to `simple` and skipping" clause inline alongside the citation. research/discovery dispatch narrations point to fanout.md while keeping their own `cortex-resolve-model --role searcher` binds; research entry keeps "No `isolation: \"worktree\"`; agents are read-only." Write-back routing defined once in Step 3, referenced from Step 5, with the empty-`--areas` clearing preserved at its site. New `test_model_resolution_wiring.py` pins all three contracts with correct halt-vs-degrade shape and the single-source structure.
- **Verdict**: PASS
- **Notes**: All greps hold. The wiring test's contract-(ii) assertions explicitly guard against collapsing synthesizer into criticality-keyed (the standalone-critical-review break), and contract (iii) asserts absence of "halt and escalate" in the searcher window — a meaningful, non-tautological distinction.

### Requirement R9: trim description synonyms
- **Expected**: one-trigger-per-branch across the five skills; respect `skill_trigger_phrases.yaml` pins; keep lifecycle mirror-regen note; `test_l1_surface_ratchet` (equal-or-lower) + routing fixture green.
- **Actual**: Synonyms trimmed across all five descriptions (refine ~399→357B, critical-review ~411→368B, discovery ~597→495B, lifecycle mirror-regen note retained, research unchanged at ceiling). `test_l1_surface_ratchet.py` green (20 tests).
- **Verdict**: PASS
- **Notes**: critical-review description shrank (368B, below its 795B cluster ceiling — did not regrow). Routing fixture green.

### Requirement R10 (invariant): no lifecycle control-flow / gate-behavior change
- **Expected**: only deliberate behavior change is Bug 1 (standalone refine off-repo gate resolution); every phase ends `just build-plugin` clean + `just test` green.
- **Actual**: Diff is byte reduction, single-sourcing, coined vocabulary, and the two bug fixes. No gate fire-condition, skip rule, or control-flow edge was altered. Mirror-parity and dual-source-parity tests green (mirrors regenerated). Full `just test` is green except one network-dependent suite (see notes).
- **Verdict**: PASS
- **Notes**: `just test` reported 6/7 suites pass; the sole failure is `test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero`, which fails on a DNS lookup to `pypi.org` (`uv run --script` fetching the `mcp` package) — an environment/sandbox network restriction, NOT a code regression. No MCP files were touched by this lifecycle. All requirement-relevant pinned suites pass directly (136 tests: model-resolution-wiring, dispatch-template-placeholders, refine-skill, kept-pauses-parity, critical-review-gate-nonlocal-failsafe, l1-surface-ratchet, plugin-mirror-parity, dual-source-reference-parity).

## Stage 2: Code Quality
- **Naming conventions**: Consistent with project skill-authoring conventions. Coined tokens (`tier ratchet`, `fresh-eyes`) are bolded, defined once at their rationale home, and referenced by token — matching GLOSSARY's "reach for an existing word first" posture. ADR-0009 path resolution honored throughout: `${CLAUDE_SKILL_DIR}`-rooted paths resolve in bodies and propagate; new `angle-templates.md` is body-resolved via markdown link, no bare-relative or `../` paths introduced in reference files. Prescribe-What/Why-not-How respected — the R6 gate prune cut method narration while keeping decision + fire-conditions + output contract; no new MUST/CRITICAL/REQUIRED escalations added (diff count =0).
- **Error handling**: The three model-resolution contracts' distinct failure shapes (halt vs. degrade-loud) are preserved verbatim at their sites and now pinned by a static test. Bug-fix edits preserve the non-local seed-tier fail-safe and corrupted-state handling.
- **Test coverage**: Both new/extended tests are meaningful pins, not tautologies. `test_model_resolution_wiring.py` asserts positive presence AND negative absence (e.g. `--role synthesizer --criticality` must NOT appear; "halt and escalate" must be absent from the searcher window) — it would catch the exact collapse the spec warned against. The placeholder-test extension asserts each relocated template's own marker set and the core-only absence of `{research_considerations_bullets}`. Both honestly disclaim runtime coverage (matching the `test_*_wired` precedent).
- **Pattern consistency**: Single-source citations follow existing conventions (canonical body + one-line "follow the canonical rule in X" pointers). The write-back routing single-source names Step 3 as canonical and references it from Step 5, mirroring how `clarify.md:87` already names Step 3 "the canonical copy." Reference-pointer shape (`${CLAUDE_SKILL_DIR}/references/…` markdown links) matches sibling fanout.md references.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
