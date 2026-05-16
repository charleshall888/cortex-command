# Plan: add-project-glossary-at-cortex-requirements

## Overview

Documentation-only feature implemented across three sequential phases: loading infrastructure (extends the `load-requirements.md` protocol with a `## Global Context` schema section in `project.md`), producer wiring (narrows `requirements-gather`'s no-filesystem contract to permit per-term `glossary.md` appends with a binary classifier, term-already-exists probe, user-confirmation gate, and Language-content constraint), and consumer surfaces (adds a Language-section-only read to `critical-review` Step 2a, narrows the exemption rationale, and seeds one-line consumer-rule prose in six non-exempt consumers). The implementation diff is entirely prose and tests; `cortex/requirements/glossary.md` itself is lazily created at the first producer-resolved term and is intentionally not authored by this plan.

## Outline

### Phase 1: Loading infrastructure (tasks: 1, 2, 3)
**Goal**: Wire the consumer-side schema and protocol so a (later-lazy-created) `glossary.md` will be loaded by every requirements consumer.
**Checkpoint**: `pytest tests/test_load_requirements_protocol.py` exits 0; `grep -c "^## Global Context$" cortex/requirements/project.md` = 1; `grep -c "Global Context" skills/lifecycle/references/load-requirements.md` ≥ 2.

### Phase 2: Producer wiring (tasks: 4, 5, 6, 7)
**Goal**: Narrow `requirements-gather`'s no-filesystem contract to a positive grant for `glossary.md` per-term appends; cascade the contract narrowing into `requirements-write` and the orchestrator's framing/listing; align e2e test simulation.
**Checkpoint**: `grep -c "cortex/requirements/glossary.md" skills/requirements-gather/SKILL.md` ≥ 1; `pytest tests/test_requirements_skill_e2e.py` exits 0.

### Phase 3: Consumer surfaces (tasks: 8, 9, 10, 11)
**Goal**: Inject the Language-section-only read into `critical-review` Step 2a, narrow the exemption rationale, and seed one-line consumer-rule prose in the six non-exempt consumers; update parity tests.
**Checkpoint**: `pytest tests/test_load_requirements_protocol.py tests/test_lifecycle_kept_pauses_parity.py` exits 0; for each of the six non-exempt consumers, `grep -c "absence as a signal\|surface the term" <file>` ≥ 1.

## Tasks

### Task 1: Add `## Global Context` schema entry to requirements-write template
- **Files**: `skills/requirements-write/SKILL.md`
- **What**: Extend the project.md template enumeration (currently at `:36-46`) to include a new `## Global Context` H2 positioned between `## Conditional Loading` and `## Optional`. Document the content rule: bulleted list of paths under `cortex/requirements/` that are always loaded by every consumer regardless of tag matches.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The existing template enumeration sits inside the description of how `/requirements-write` synthesizes project.md. Insertion order is: `## Conditional Loading` → **`## Global Context` (new)** → `## Optional`. Keep the prose tight (≤6 lines for the new H2 explanation). The classifier instruction (project-specific vs general programming) is producer-side and does NOT belong here — `requirements-write` only documents the schema.
- **Verification**: `grep -c "^## Global Context" skills/requirements-write/SKILL.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 2: Seed `## Global Context` in cortex/requirements/project.md
- **Files**: `cortex/requirements/project.md`
- **What**: Add a `## Global Context` H2 section between `## Conditional Loading` and `## Optional`, with `glossary.md` as its sole entry. The file does not need to exist for the entry to be valid; the loader handles absence silently.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Match the H2 placement Task 1 documented. One-line body: a single bullet `- glossary.md`. Do NOT add explanatory prose about the loader's absent-file behavior — that lives in `load-requirements.md` per Task 3.
- **Verification**: `awk '/^## Global Context$/{flag=1; next} /^## /{flag=0} flag' cortex/requirements/project.md | grep -c "glossary.md"` = 1 AND `grep -c "^## Global Context$" cortex/requirements/project.md` = 1 — pass if both true. (The awk pattern reads until the next H2 boundary so it stays correct as the section grows past its single initial entry.)
- **Status**: [ ] pending

### Task 3: Extend load-requirements.md protocol and update its parity test
- **Files**: `skills/lifecycle/references/load-requirements.md`, `tests/test_load_requirements_protocol.py`
- **What**: (a) Modify step 1's prose to read both `cortex/requirements/project.md` AND the files enumerated in its `## Global Context` section, with skipped (absent) entries recorded as `<path> (skipped: file absent)` in the loaded-files list step 4 produces. (b) Extend the `## Matching Semantics` block with a counterpart paragraph documenting Global Context's list-of-paths semantics. (c) Update `test_load_requirements_md_enumerates_*_protocol_steps()` to match the new step shape — either rename and rescope to the new step count or rescope to match the new section name. Do NOT preserve the count by hiding the Global Context read inside step 1's prose; that would silently redefine step 1's "single unconditional load" invariant.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: `load-requirements.md` is 27 lines today; step 1 is L9, Matching Semantics is L19-L23. The test file's step-count assertion is at `tests/test_load_requirements_protocol.py:91-114`. The deliberate-exemption anchor test at `:74-88` must NOT be touched here — that test remains intact through this task (it gates Task 9's exemption-rationale narrowing). The new "skipped: file absent" recording must be explicit prose, not silent omission, because downstream drift-check and reviewer-dispatch consumers cited in step 4 have a contract for the distinction.
- **Verification**: `grep -c "Global Context" skills/lifecycle/references/load-requirements.md` ≥ 2 AND `grep -c "skipped: file absent\|skipped because absent" skills/lifecycle/references/load-requirements.md` ≥ 1 AND `pytest tests/test_load_requirements_protocol.py -k enumerates --exitfirst` exits 0 — pass if all three.
- **Status**: [ ] pending

### Task 4: Narrow requirements-gather contract; add inline-write rule, probe, gate, Language-content constraint
- **Files**: `skills/requirements-gather/SKILL.md`
- **What**: Five interrelated edits to the same file: (a) Replace the `:33` no-filesystem contract with D2's explicit positive grant — writable set is `cortex/requirements/glossary.md` per-term append (lazy file creation), with project.md and area docs named as explicitly excluded; preserve abandon-safety for Q&A via a "Lazy artifact creation still applies to project.md and area docs" sentence; name the mid-interview abandonment semantic ("each per-term append is durably persisted; entries appended before abandonment remain in the file"). (b) Add prose for the inline-write rule with term-already-exists probe — on term resolve, read `glossary.md` if it exists; if the term is present, use the existing entry verbatim or surface the conflict via AskUserQuestion before reclassifying; if absent, apply the binary classifier (project-specific vs general programming) and on project-specific verdict, append. (c) Add the user-confirmation gate — model-introduced terms (surfaced in a "Recommended answer:" line and never user-named or user-confirmed) do NOT trigger inline write. (d) Add the Language-content constraint — entries written into the glossary's `## Language` section must be definitional, not classification-shaped; the example pair `phase_transition: the named event emitted when ...` (admitted) vs `phase_transition — genuinely-domain term; contract-shaped in lifecycle.md` (rejected) anchors the rule.
- **Depends on**: [2, 3]
- **Complexity**: complex
- **Context**: requirements-gather/SKILL.md is 72 lines today; expected growth +60-100 lines (well under the 500-line cap per the size-budget test). The existing decision-criteria prose at `:21-33` uses soft positive-routing throughout; preserve that register. Soft positive-routing is required for all new prose per CLAUDE.md's MUST-escalation default — no MUST/CRITICAL/REQUIRED escalations without effort=high evidence (none expected). The binary-classifier choice (vs four-bucket) is settled by the spec's Non-Requirements; the four-bucket Cortex synthesis is documented only in research.md and is NOT built. The Language-content constraint added here is consumed by Task 8's critical-review Step 2a read. To make each sub-edit's prose independently checkable, the new prose must use a unique anchor phrase per sub-edit: "writable set" (contract narrowing), "term-already-exists probe" (inline-write rule with probe), "binary classifier" (classifier), "user-confirmation gate" (gate), "Language-content constraint" (Language-content rule).
- **Verification**: All eight checks must pass (each anchor pinned with `= 1` to prevent inflation, and the spec-required tokens preserved at `≥ 1` for back-compat with spec acceptance):
  - `grep -c "cortex/requirements/glossary.md" skills/requirements-gather/SKILL.md` ≥ 1 (spec Req 6 acceptance)
  - `grep -c "writable set" skills/requirements-gather/SKILL.md` = 1 (sub-edit a anchor)
  - `grep -c "Lazy artifact creation still applies" skills/requirements-gather/SKILL.md` = 1 (sub-edit a abandon-safety preservation)
  - `grep -c "term-already-exists probe" skills/requirements-gather/SKILL.md` = 1 (sub-edit b anchor)
  - `grep -ci "binary classifier" skills/requirements-gather/SKILL.md` = 1 (sub-edit c anchor)
  - `grep -c "user-confirmation gate" skills/requirements-gather/SKILL.md` = 1 (sub-edit d anchor)
  - `grep -c "Language-content constraint" skills/requirements-gather/SKILL.md` = 1 (sub-edit e anchor)
  - `grep -c "definitional, not classification-shaped" skills/requirements-gather/SKILL.md` = 1 (sub-edit e content rule)
- **Status**: [ ] pending

### Task 5: Narrow requirements-write/SKILL.md exclusive-write claim
- **Files**: `skills/requirements-write/SKILL.md`
- **What**: Narrow the `:4` description/when_to_use phrasing from "the only sub-skill that touches the filesystem" to "the only sub-skill that writes to project.md or area docs under `cortex/requirements/`. `/requirements-gather` appends glossary entries to `cortex/requirements/glossary.md`; all other filesystem writes under `cortex/requirements/` remain `/requirements-write`'s."
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The frontmatter description and the when_to_use block at the top of the file both carry the "only sub-skill" claim — both need narrowing for coherence. Caller enumeration: this contract phrasing is cited by `skills/requirements/SKILL.md` (Task 6's territory), `tests/test_requirements_skill_e2e.py` (Task 7), and indirectly by the orchestrator's three-tier architecture documentation. No callers beyond Task 6's and Task 7's scope need editing here.
- **Verification**: `grep -c "glossary" skills/requirements-write/SKILL.md` ≥ 1 — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 6: Update requirements/SKILL.md orchestrator framing and list subcommand handling
- **Files**: `skills/requirements/SKILL.md`
- **What**: (a) Add a sentence at `:5` (the passive-artifact framing) noting that the glossary is a producer-managed exception: it grows inline during requirements interviews; consumers still treat it as passive on read. (b) Update the `list` subcommand at `:21` (which enumerates `cortex/requirements/*.md`) to either (i) include `glossary.md` in the enumeration with a scope marker or (ii) explicitly exclude it with a one-line rationale. The choice should be made in the implementer's context — both options are spec-compliant. Document the choice in the file.
- **Depends on**: [4, 5]
- **Complexity**: simple
- **Context**: `skills/requirements/SKILL.md` is the orchestrator that routes `gather → write`. The `:5` framing currently treats requirements as passive artifacts; the glossary's producer-managed exception narrows but does not invert that framing. The `list` subcommand is implementation prose in the orchestrator, not a separate binary — edit the prose to reflect the chosen handling.
- **Verification**: `grep -ci "glossary" skills/requirements/SKILL.md` ≥ 2 — pass if count ≥ 2 (one for the framing sentence, one for the list-subcommand handling).
- **Status**: [ ] pending

### Task 7: Extend test_requirements_skill_e2e.py simulation to cover glossary write path
- **Files**: `tests/test_requirements_skill_e2e.py`
- **What**: Extend `_simulate_write()` at `:301-345` to also write a stub `glossary.md` when an inline-write would have occurred in real runtime. This is option (a) of spec Req 17. The plan commits to (a) rather than (b) because option (b) (a one-line hermeticity comment) would leave the producer's inline-write path with zero automated coverage at any phase — critical-review surfaced this as a fix-invalidating gap.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The simulation today writes only project.md or area-template artifacts — see `:86-101` for invocation and `:301-345` for the writer. Modeling per-term appends keeps the simulation runtime-faithful at modest test-code cost. Match the existing tmp_path discipline; the stub glossary lives inside the tmp_path used by other simulation outputs, not under `cortex/requirements/`.
- **Verification**: `pytest tests/test_requirements_skill_e2e.py` exits 0 AND `grep -ci "glossary" tests/test_requirements_skill_e2e.py` ≥ 1 AND `grep -ci "_simulate_write" tests/test_requirements_skill_e2e.py | head -1` shows the function is still defined (sanity that the edit landed inside the right symbol) — pass if all three.
- **Status**: [ ] pending

### Task 8: Extend critical-review Step 2a with Language-section-only read; narrow exemption rationale
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Two coupled edits to the same file: (a) Extend Step 2a (`:34-39`) to read `cortex/requirements/glossary.md`'s `## Language` section when the file exists, and include it inline in the assembled `## Project Context` block. Do NOT read `## Relationships`, `## Example dialogue`, or `## Flagged ambiguities` — those could approach "existing reasoning" territory. Silent skip when the file is absent. (b) Narrow the rationale prose at `:41` from "broader project context (priorities, area-specific tags, decisions) would dilute that focus" to "broader project context (priorities, area-specific tags, decisions, **not vocabulary**) would dilute that focus." Add an explicit clause: "Vocabulary (the glossary's `## Language` section) is admitted because it is definitional rather than reasoning-shaped." The literal anchor phrase "Requirements loading: deliberately exempt" stays preserved verbatim (parity-pinned at `tests/test_load_requirements_protocol.py:84`).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: critical-review/SKILL.md is 115 lines today; Step 2a is at `:33-40` and the exemption notice is at `:41`. The Language-content constraint added in Task 4 is what makes (a) safe — entries in `## Language` are definitional, so reading them does not anchor reviewers to existing reasoning. The exemption anchor phrase is parity-pinned; only the rationale prose around it is in scope to edit. To force both edits to be independently checkable: introduce the anchor phrase "Language-section-only" in Step 2a and the anchor phrase "not vocabulary" in the `:41` rationale; verify each independently.
- **Verification**: All five checks must pass:
  - `grep -c "glossary" skills/critical-review/SKILL.md` ≥ 1 (spec Req 12 acceptance)
  - `grep -c "Language section" skills/critical-review/SKILL.md` ≥ 1 (spec Req 12 acceptance)
  - `grep -c "Language-section-only" skills/critical-review/SKILL.md` = 1 (Step 2a sub-edit anchor)
  - `grep -c "Requirements loading: deliberately exempt" skills/critical-review/SKILL.md` = 1 (parity-pinned anchor preserved)
  - `grep -c "not vocabulary" skills/critical-review/SKILL.md` = 1 (`:41` rationale-narrowing sub-edit anchor)
- **Status**: [ ] pending

### Task 9: Add consumer-rule prose to lifecycle consumers (3 of 6)
- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/review.md`
- **What**: For each of the three files, add a single-line prose rule near the existing `load-requirements` citation: "If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview." This is the only signal-handling path for absent terms — there is no spec-side parking artifact and no automated promotion.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Existing load-requirements citations: `clarify.md:33`, `specify.md:9`, `review.md:12`. Place the new prose line within 10 lines of each citation. Keep wording verbatim across all three so Task 11's parity grep can use a single pattern. NOTE: adding ~1-2 lines to `specify.md` near `:9` will shift `specify.md`'s later `AskUserQuestion` anchors — Task 11 verifies these stay within `test_lifecycle_kept_pauses_parity.py`'s LINE_TOLERANCE=35 window. (The plan reference numbers AskUserQuestion anchors loosely as the inventory in `skills/lifecycle/SKILL.md` rounds them; the actual call-site line numbers are what the parity test reads against.)
- **Verification**: For each of the three files, a single proximity check: `awk -v f="<file>" '/load-requirements/{lc=NR} /absence as a signal|surface the term/{if(lc && NR-lc>=0 && NR-lc<=10){print f": OK"; exit 0}} END {exit 1}' <file>` exits 0 — pass if all three files pass. (The awk captures the load-requirements line number, then verifies the consumer-rule prose appears within the next 10 lines.)
- **Status**: [ ] pending

### Task 10: Add consumer-rule prose to discovery and refine consumers (3 of 6)
- **Files**: `skills/discovery/references/clarify.md`, `skills/discovery/references/research.md`, `skills/refine/SKILL.md`
- **What**: For each of the three files, add the same single-line prose rule near the existing `load-requirements` citation: "If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview." Wording must match Task 9's verbatim so Task 11's parity grep finds all six.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Existing load-requirements citations: `discovery/references/clarify.md:15`, `discovery/references/research.md:27`, `refine/SKILL.md:68`. The refine citation is in a chain reference (refine → lifecycle clarify → load-requirements); the prose still belongs at the local cite, placed within 10 lines of it.
- **Verification**: For each of the three files, the same proximity-check awk: `awk -v f="<file>" '/load-requirements/{lc=NR} /absence as a signal|surface the term/{if(lc && NR-lc>=0 && NR-lc<=10){print f": OK"; exit 0}} END {exit 1}' <file>` exits 0 — pass if all three files pass.
- **Status**: [ ] pending

### Task 11: Update test_load_requirements_protocol.py for consumer-rule prose and verify kept-pauses tolerance
- **Files**: `tests/test_load_requirements_protocol.py`, `tests/test_lifecycle_kept_pauses_parity.py`
- **What**: (a) Extend assertions in `tests/test_load_requirements_protocol.py` to cover the new consumer-rule prose presence in each non-exempt consumer (the six files Tasks 9-10 edited), referencing the existing `CONSUMER_REFS` tuple at `:38-45`. Confirm the existing deliberate-exemption anchor test at `:74-88` still passes (it should — Task 8 preserved the literal anchor phrase). (b) Run `tests/test_lifecycle_kept_pauses_parity.py` and confirm the `AskUserQuestion` anchors in `specify.md` (kept-pauses inventory near `:36, 67, 155`) stay within LINE_TOLERANCE=35 after Task 9's insertion. If any anchor drifts outside tolerance, update the inventory in `skills/lifecycle/SKILL.md` (under "Kept user pauses") in lockstep — do NOT change `test_lifecycle_kept_pauses_parity.py` itself except for the same lockstep update if its inventory is duplicated there.
- **Depends on**: [8, 9, 10]
- **Complexity**: complex
- **Context**: `CONSUMER_REFS` at `tests/test_load_requirements_protocol.py:38-45` enumerates the six non-exempt consumers. The new assertion can be a single loop checking `grep -c "absence as a signal\|surface the term" <file>` ≥ 1 for each. The kept-pauses parity is tested by `tests/test_lifecycle_kept_pauses_parity.py` (LINE_TOLERANCE=35); the canonical inventory is in `skills/lifecycle/SKILL.md` under "Kept user pauses" — the parity test reads that file as its source of truth. If anchors drift, update the inventory's line numbers, NOT the tolerance value.
- **Verification**: `pytest tests/test_load_requirements_protocol.py` exits 0 AND `pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0 — pass if both.
- **Status**: [ ] pending

## Risks

- **Task 4 size**: Task 4 bundles five interrelated edits to `requirements-gather/SKILL.md` (contract narrowing, inline-write rule with probe, binary classifier, user-confirmation gate, Language-content constraint). The +60-100 line growth puts it at the upper edge of the 5-15 minute target. Splitting would yield finer-grained review but multiplies commits on a single small file. Kept as one task because the four producer-internal edits (a–d) cross-reference each other; the Language-content constraint (e) is a leaf rule that could theoretically split off but the file remains coherent only if all five land together. Per-sub-edit anchor-phrase verification (in Task 4's Verification clause) keeps each sub-edit independently checkable despite the bundling.
- **Task 9 and Task 10 split**: The six consumer-rule prose insertions are split 3+3 to honor the ≤5-file-per-task guidance. The two tasks could be merged into one 6-file task with an explicit override note, or split further into six single-file tasks. The 3+3 split feels right because the lifecycle trio and the discovery+refine trio are conceptually-grouped consumer surfaces.
- **glossary.md is intentionally not created**: Per spec Non-Requirements, `cortex/requirements/glossary.md` is lazily created at the first producer-resolved term. No task here writes that file. Runtime behavior of the producer-and-consumer chain is end-to-end testable through Task 7's extended `_simulate_write()` (option a of spec Req 17) — Phase 1's acceptance is presence-grep based, Phase 2 adds the simulation runtime gate.
- **Task 6's list-subcommand handling is a choice**: Include glossary in the `list` enumeration with a scope marker, OR exclude it with a rationale line. Both options are spec-compliant; the choice falls to the implementer in their local context.
- **Task 11 contingent inventory update**: If Task 9's insertions shift `specify.md` anchors outside LINE_TOLERANCE=35, Task 11 must update the inventory in `skills/lifecycle/SKILL.md` in lockstep. This is a defensive contingency; the expected insertion size is small enough to stay well within tolerance.
- **Inventory-correctness is not gated by the parity test**: `test_lifecycle_kept_pauses_parity.py` verifies that the inventory matches actual `AskUserQuestion` line positions (within tolerance) — but if an implementer updates the inventory to match drifted lines without auditing whether the new placement preserves the kept-pause semantic intent, the test still passes. The kept-pauses inventory is a human-judgment surface; the parity test gates parity, not intent. Task 11's Context names this contingency; no automated gate exists.

## Acceptance

- All 17 spec acceptance grep checks (Requirements 1-17) pass after the eleventh task lands. Spec-Requirement → Task crosswalk: Req 1 → Task 1; Req 2 → Task 2; Reqs 3, 4, 5 → Task 3; Reqs 6, 7, 8 → Task 4; Req 9 → Task 5; Reqs 10, 11 → Task 6; Req 17 → Task 7; Reqs 12, 13 → Task 8 (Req 12's Language-content constraint portion → Task 4); Req 14 (consumer-rule prose for 6 files) → Tasks 9 + 10; Reqs 15, 16 → Task 11. Each of the 17 acceptance grep checks lives in `spec.md` Requirements 1-17 and is subsumed by the listed task's Verification (or by the post-task pytest run in the same task).
- `pytest tests/test_load_requirements_protocol.py tests/test_lifecycle_kept_pauses_parity.py tests/test_requirements_skill_e2e.py tests/test_skill_callgraph.py tests/test_check_events_registry.py tests/test_skill_size_budget.py` exits 0.
- `grep -c "^## Global Context$" cortex/requirements/project.md` = 1 AND the same section enumerates `glossary.md` as a bullet entry; the file `cortex/requirements/glossary.md` does NOT exist (lazy-creation invariant).
- For each of the six non-exempt consumers (`clarify.md`, `specify.md`, `review.md` under `lifecycle/references/`; `clarify.md`, `research.md` under `discovery/references/`; `refine/SKILL.md`), the proximity-check `awk` from Tasks 9/10 exits 0 (consumer-rule prose appears within 10 lines of the file's `load-requirements` citation).
- `bin/cortex-check-parity` passes pre-commit on every intermediate task commit.
