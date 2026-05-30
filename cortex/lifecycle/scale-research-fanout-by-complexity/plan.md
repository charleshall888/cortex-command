# Plan: scale-research-fanout-by-complexity

<!--
PLAN-OF-THE-PLAN (recorded per high-criticality rule; proceeded automatically):
- Phase 1 (Shared fan-out engine): ~7 tasks. Riskiest = Task 3 (research SKILL.md Step 3/4 rewrite — dispatch + dynamic output schema; must preserve the `## Open Questions` contract and injection-resistance/considerations-injection fragments). Parallelizable: T4 (test), T5/T6 (doc reconciliation), T7 (clarify sufficiency phrasing) all depend only on T1 and can run concurrently with the T2→T3 SKILL.md chain.
- Phase 2 (Discovery integration): ~4 tasks. Riskiest = Task 9 (clarify→research assessment persistence — net-new plumbing; the integration review flagged this as the one concrete data-flow hole). Mostly sequential (T8→T9→T10→T11) because they thread one assessment value through clarify→persist→research→test.
- Hard phase boundary: Phase 1 must be fully green (`just test` exits 0) before any Phase 2 task starts — Phase 2 consumes T1's reference and carries the integration risk.
- Uncertainty: exact persistence mechanism for the discovery assessment (events.log via cortex-discovery helper vs a clarify-output file) is left to implementation per What/Why-not-How; T9 states the contract, not the mechanism.
-->

## Outline

### Phase 1: Shared fan-out engine (Tasks 1–7)
**Goal**: Replace `/research`'s `max()` count model with a shared 2D matrix + hybrid angle selection in one canonical reference, add a regression test, and reconcile the stale single-vs-parallel docs. `/refine` and `/lifecycle` inherit automatically via existing delegation.
**Tasks**: 1, 2, 3, 4, 5, 6, 7
**Checkpoint**: `skills/lifecycle/references/fanout.md` exists with the 8-cell matrix (floor 3, corner 10); `grep -c 'max(tier_count' skills/research/SKILL.md` = 0; `skills/research/SKILL.md` cites fanout.md; the new matrix test passes; no reconciled doc still claims research is "single" for high criticality or parallel-only-for-critical; `just test` exits 0.

### Phase 2: Discovery integration (Tasks 8–11)
**Goal**: Add an upward-biased research-sizing complexity/criticality assessment to discovery's Clarify, persist it across the clarify→research boundary, and rewrite discovery's Research phase to dispatch via the shared fan-out engine while preserving its `## Architecture` synthesis schema.
**Tasks**: 8, 9, 10, 11
**Depends on**: Phase 1 complete and green (hard boundary).
**Checkpoint**: discovery clarify.md emits the two assessments with the `medium` criticality floor and epic-leverage rationale; the assessment persists at clarify and is read at research entry (with a safe default when absent); discovery research.md cites fanout.md and retains `## Architecture`/`### Pieces`/`### How they connect`; `cortex-discovery generate-brief` still succeeds; `just test` exits 0.

## Tasks

### Task 1: Create the canonical fan-out reference
**Status**: [ ]
**Depends on**: none
**Files**: `skills/lifecycle/references/fanout.md` (new)
**Context**: New shared reference, sibling to existing shared references `skills/lifecycle/references/load-requirements.md` and `orchestrator-review.md` (both consumed by multiple skills). It must contain three things: (a) the **count matrix** (spec R1) — an 8-cell table, rows `simple`/`complex` × columns `low`/`medium`/`high`/`critical`, values `simple{3,4,5,6}` and `complex{5,6,8,10}`; (b) the **hybrid angle-selection** rule (spec R3) — mandatory core = Codebase, Web, Requirements & Constraints (always); an Adversarial/critique agent always present for high/critical, dispatched last over a summary of the others' findings; the remaining matrix-bought slots chosen by the orchestrator per task as distinct, non-redundant angles, with one illustrative subdivision example (e.g. codebase-by-subsystem) and no topic→angle keyword router; (c) a **dispatch protocol** — parallel core first, then the always-last adversarial wave for high/critical. Write in What/Why-not-How register; soft routing (no new MUST). State the cap-10 rationale (concurrency/diminishing-returns ceiling) in one line.
**Action**: Author `fanout.md` with sections for the matrix table, hybrid angle selection, and dispatch protocol per the context above.
**Verification**: `test -f skills/lifecycle/references/fanout.md` && `grep -c 'mandatory core' skills/lifecycle/references/fanout.md` ≥ 1 && the table contains a `10` in the complex+critical position and `3` in simple+low (manual scan / `grep -E '\*\*complex\*\*.*10' skills/lifecycle/references/fanout.md` returns the complex row).

### Task 2: Rewrite /research Step 2 (count) + frontmatter to consume the matrix
**Status**: [ ]
**Depends on**: 1
**Files**: `skills/research/SKILL.md`
**Context**: Step 2 ("Determine Agent Count", lines ~47–57) currently holds `tier_count`/`criticality_count`/`agent_count = max(...)`. Replace it with a citation to `skills/lifecycle/references/fanout.md` and the 2D matrix lookup (read tier × criticality → count from the matrix). Remove the `max()` formula entirely. Also update the frontmatter `description` (line ~6) "3–5 parallel agents" range to the new range (3–10).
**Action**: Replace Step 2's max() body with a matrix-lookup instruction citing fanout.md; update the frontmatter range string.
**Verification**: `grep -c 'max(tier_count' skills/research/SKILL.md` = 0 && `grep -c 'fanout.md' skills/research/SKILL.md` ≥ 1 && `grep -c '3–5\|3-5' skills/research/SKILL.md` = 0.

### Task 3: Rewrite /research Step 3 (dispatch) + Step 4 (dynamic output) + line-194 self-doc
**Status**: [ ]
**Depends on**: 1, 2
**Files**: `skills/research/SKILL.md`
**Context**: Step 3 ("Dispatch Agents") currently hardcodes Agents 1–5 with a count-keyed dispatch protocol; rewrite it to reference the hybrid angle selection + dispatch protocol in fanout.md (mandatory core, orchestrator-chosen remaining angles, always-last adversarial for high/critical). PRESERVE verbatim: the `{INJECTION_RESISTANCE_INSTRUCTION}` fragment and the per-agent `research-considerations` injection rules. Step 4 ("Synthesize Findings", output structure ~lines 211–244) currently lists fixed headings; change it to emit one section per *dispatched* angle (mandatory core always; chosen angles labeled by selected angle; Adversarial when present). PRESERVE the `## Open Questions` heading and its semantics (consumed by `cortex_command/lifecycle/complexity_escalator.py`) and the empty/failed-agent + contradiction handling. Reword the self-doc at line ~194 ("Step 4's `### Output structure` block is the canonical schema source") to state the schema is angle-driven and only `## Open Questions` is a fixed contract heading.
**Action**: Rewrite Step 3 to delegate angle selection/dispatch to fanout.md (keeping injection-resistance + considerations injection); rewrite Step 4 for per-angle sections (keeping Open Questions + failure handling); fix the line-194 self-doc.
**Verification**: `grep -c 'Open Questions' skills/research/SKILL.md` ≥ 1 && `grep -c 'INJECTION_RESISTANCE_INSTRUCTION' skills/research/SKILL.md` ≥ 1 && `grep -c 'canonical schema source' skills/research/SKILL.md` = 0 && `just test` exits 0 (size-budget + dual-source parity hold).

### Task 4: Add the matrix-invariants regression test
**Status**: [ ]
**Depends on**: 1
**Files**: `tests/test_research_fanout_matrix.py` (new)
**Context**: No regression test asserts the agent count today (confirmed: grep of `tests/` for count vars is empty). The test parses the 8-cell grid from `skills/lifecycle/references/fanout.md` and asserts spec R2 invariants: (a) every cell ≥ its left neighbor and ≥ its upper neighbor (monotonic on both axes); (b) floor (simple+low) = 3; (c) corner (complex+critical) = 10; (d) no cell exceeds 10. Follow existing test conventions in `tests/` (pytest, repo-root-relative path resolution).
**Action**: Write the test parsing fanout.md's table and asserting (a)–(d).
**Verification**: `python3 -m pytest tests/test_research_fanout_matrix.py -q` exits 0; `just test` exits 0.

### Task 5: Reconcile lifecycle-side stale single-vs-parallel docs
**Status**: [ ]
**Depends on**: 1
**Files**: `skills/lifecycle/references/criticality-matrix.md`, `skills/lifecycle/assets/model-selection.md`
**Context**: `criticality-matrix.md` Scaled-behaviors column (lines ~17–20) says "Single research" for low/medium/high and "Parallel research" only for critical — already wrong under the graduated formula. `model-selection.md` (lines ~16, ~58) implies parallel research is critical-only. Update both to reference the matrix in fanout.md (research is parallel and matrix-sized at every tier/criticality; "single" framing removed).
**Action**: Reword the Scaled-behaviors column and the model-selection parallel-research rows to point at the matrix; drop the binary single/parallel framing.
**Verification**: `grep -ci 'single research' skills/lifecycle/references/criticality-matrix.md` = 0 && both files reference the matrix/fanout concept (`grep -c 'fanout\|matrix' skills/lifecycle/references/criticality-matrix.md skills/lifecycle/assets/model-selection.md` ≥ 1 each).

### Task 6: Reconcile docs-side stale claims
**Status**: [ ]
**Depends on**: 1
**Files**: `docs/agentic-layer.md`, `docs/skills-reference.md`
**Context**: `docs/agentic-layer.md` criticality table (lines ~116–119) carries the same binary "Single / Parallel" framing. `docs/skills-reference.md:47` says "Dispatches 3–5 agents" — stale range. Update both to the matrix-based reality (range 3–10, scaled by tier × criticality).
**Action**: Update the agentic-layer table rows and the skills-reference range string.
**Verification**: `grep -c '3–5\|3-5' docs/skills-reference.md` = 0 && the agentic-layer criticality table's research column no longer reads "Single" for any row (`grep -nE '\| *(low|medium|high)\b.*Single' docs/agentic-layer.md` returns no research-column match) && `just test` exits 0.

### Task 7: Decouple research-sufficiency signals from the fixed Codebase-Analysis heading
**Status**: [ ]
**Depends on**: 1, 3
**Files**: `skills/lifecycle/references/clarify.md`
**Context**: Signals (b) and (c) of the Research Sufficiency Criteria (lines ~99–100) reference "research.md's codebase analysis", which assumes the fixed `## Codebase Analysis` heading that Task 3 makes angle-driven. Reword to "codebase findings present anywhere in research.md" so the sufficiency check survives the dynamic schema.
**Action**: Reword signals (b)/(c) to not name a fixed heading (e.g. "codebase findings").
**Verification**: `grep -c 'codebase findings' skills/lifecycle/references/clarify.md` ≥ 1 && the sufficiency signals (b)/(c) no longer contain the literal "codebase analysis" phrase (`grep -ci 'codebase analysis' skills/lifecycle/references/clarify.md` reflects no sufficiency-signal usage); `just test` exits 0.

### Task 8: Add upward-biased research-sizing assessment to discovery Clarify
**Status**: [ ]
**Depends on**: 1 (and Phase 1 complete — hard boundary)
**Files**: `skills/discovery/references/clarify.md`
**Context**: Discovery Clarify currently emits no complexity/criticality and explicitly refuses to (Thought/Reality row at lines ~62–66: "Discovery Clarify does not assess implementation complexity"). Add two named clarify outputs: complexity (`simple|complex`) and criticality (`low|medium|high|critical`), scoped as **research-sizing only** (distinct from implementation-complexity). Encode the user's upward-bias directive (spec R7): criticality floors at `medium` (never `low`), rises to `high`/`critical` when the topic seeds a whole epic or sets multi-ticket direction; complexity skews `complex` for multi-faceted/epic-seeding topics. State the *why* (discovery sets epic direction; wrong direction propagates) so the model applies judgment. Reword the stale Thought/Reality row to scope the carve-out.
**Action**: Add the two assessments + upward-bias guidance to clarify.md; reword the stale row.
**Verification**: `grep -ci 'research-sizing\|research sizing' skills/discovery/references/clarify.md` ≥ 1 && `grep -ci 'epic' skills/discovery/references/clarify.md` ≥ 1 && `grep -ci 'does not assess implementation complexity' skills/discovery/references/clarify.md` = 0.

### Task 9: Persist the discovery assessment across the clarify→research boundary
**Status**: [ ]
**Depends on**: 8
**Files**: `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`, `skills/discovery/SKILL.md` and/or `cortex_command/discovery.py` (mechanism-dependent)
**Context**: Discovery supports independent phase entry (`/cortex-core:discovery research`), so the assessment must survive a resume — conversation context alone is insufficient (integration review's one concrete data-flow hole). Persist at Clarify time and read at Research entry. Mechanism is left to implementation (What/Why-not-How): either discovery's `events.log` via a `cortex-discovery` helper subcommand (mirroring lifecycle's `lifecycle_start`/`complexity_override`) or a small clarify-output store — pick the lower-friction option consistent with how discovery already routes events through `cortex_command/discovery.py`. Define the default: if Research is entered with no persisted assessment (legacy dirs or direct phase-jump before Clarify), fall back to the floor (simple/medium given the discovery `medium` floor) or re-prompt — never an unhandled missing-input failure. If a new event type is added, register it in `bin/.events-registry.md`.
**Action**: Implement the write at Clarify and the read+default at Research entry via the chosen mechanism; register any new event.
**Verification**: a write exists at Clarify and a read exists at Research entry (`grep` in the discovery references and/or `cortex_command/discovery.py` shows both sides); `just test` exits 0.

### Task 10: Rewrite discovery Research to use the shared fan-out engine, keep its schema
**Status**: [ ]
**Depends on**: 1, 9
**Files**: `skills/discovery/references/research.md`
**Context**: Discovery's Research phase (`skills/discovery/references/research.md`) is today a sequential single-orchestrator §2–§5 investigation. Rewrite it to dispatch parallel agents sized by the matrix in `fanout.md`, using the persisted assessment (Task 9). PRESERVE the existing synthesis schema exactly — `## Architecture` with `### Pieces` and `### How they connect`, plus Research Questions / Feasibility — because `cortex_command/discovery.py` machine-parses `## Architecture`/`### Pieces`/`### How they connect` (and `## Headline Finding`, a pre-existing parse target — do not drop it if present) for the R4 brief and `score-corpus`, and decompose.md treats `### Pieces` as the decomposition source of record. Discovery shares the fan-out *engine* (count + angle selection), not `/research`'s output schema.
**Action**: Rewrite research.md to fan out via fanout.md while synthesizing into the unchanged Architecture schema.
**Verification**: `grep -c 'fanout' skills/discovery/references/research.md` ≥ 1 && `grep -c '### Pieces' skills/discovery/references/research.md` ≥ 1 && `grep -c '### How they connect' skills/discovery/references/research.md` ≥ 1 && `just test` exits 0.

### Task 11: Tests — brief generation + resume-without-assessment default
**Status**: [ ]
**Depends on**: 9, 10
**Files**: `tests/` (extend `tests/test_discovery_brief.py` if present, else new test), and the resume-default assertion for Task 9
**Context**: Confirm the discovery research rewrite did not break the machine-parsed Architecture contract: `cortex-discovery generate-brief` must still succeed against a discovery research.md shaped by the new schema (Architecture/Pieces/How-they-connect intact). Also cover Task 9's safe default: entering Research with no persisted assessment yields the floor default (not a crash).
**Action**: Add/extend tests asserting generate-brief succeeds against the new schema and the missing-assessment default path resolves to the floor.
**Verification**: `python3 -m pytest tests/test_discovery_brief.py -q` (or the new test) exits 0; `just test` exits 0.

## Acceptance

- `/research` sizes its fan-out from the 2D matrix in `skills/lifecycle/references/fanout.md` (range 3–10, corner complex+critical = 10); `grep -c 'max(tier_count' skills/research/SKILL.md` = 0.
- `/refine` and `/lifecycle` inherit the new sizing with no edits to their own dispatch (they delegate to `/research`).
- Hybrid angle selection is in effect: mandatory core always runs; adversarial always-last for high/critical; remaining slots orchestrator-chosen and distinct; no topic→angle keyword router exists.
- A regression test asserts the matrix invariants (monotonic both axes, floor 3, corner 10, none > 10).
- Discovery Clarify produces an upward-biased research-sizing complexity/criticality assessment (criticality floor `medium`), it persists across a clarify→research resume, and discovery Research fans out via the shared engine while `cortex-discovery generate-brief` still succeeds.
- All stale single-vs-parallel framing and "3–5" range strings are reconciled to the matrix; `just test` exits 0.
