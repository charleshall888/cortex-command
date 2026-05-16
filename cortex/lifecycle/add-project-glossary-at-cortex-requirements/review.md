# Review: add-project-glossary-at-cortex-requirements

## Stage 1: Spec Compliance

### Requirement 1: `## Global Context` schema section in `project.md` template
- **Expected**: `requirements-write/SKILL.md` template enumeration includes `## Global Context` between `## Conditional Loading` and `## Optional` with a documented content rule. Acceptance: `grep -c "^## Global Context" skills/requirements-write/SKILL.md` ≥ 1.
- **Actual**: Line 34 enumerates `## Global Context` as item 7 between `## Conditional Loading` (item 6) and `## Optional` (item 8). Content rule is present: "Bulleted list of paths under `cortex/requirements/` that are always loaded by every consumer regardless of tag matches." A reinforcing `### Global Context schema entry` block at lines 37–43 repeats the verbatim H2 and content rule. `grep -c "^## Global Context"` returns 1 (the schema-entry heading; the enumeration row is backtick-quoted on a numbered list line, which is expected since the template enumeration is bullet-form, not raw H2). Acceptance command satisfied.
- **Verdict**: PASS

### Requirement 2: `## Global Context` section seeded in `cortex/requirements/project.md`
- **Expected**: A `## Global Context` section with `glossary.md` as its sole entry. Acceptance: `awk '/^## Global Context$/{flag=1; next} /^## /{flag=0} flag' cortex/requirements/project.md | grep -c "glossary.md"` = 1 AND `grep -c "^## Global Context$" cortex/requirements/project.md` = 1.
- **Actual**: `## Global Context` H2 exists at line 70, between `## Conditional Loading` (line 63) and `## Optional` (line 74), with a single bullet `- glossary.md`. Both grep acceptances return 1. `cortex/requirements/glossary.md` is intentionally absent (lazy-creation invariant), which the loader handles as "skipped: file absent" per Req 3.
- **Verdict**: PASS

### Requirement 3: `load-requirements.md` extension to read `## Global Context`
- **Expected**: Step 1 prose reads both `project.md` and Global Context paths; absent entries recorded as `<path> (skipped: file absent)`. Acceptance: `grep -c "Global Context"` ≥ 1 AND `grep -c "skipped: file absent\|skipped because absent"` ≥ 1.
- **Actual**: Step 1 at line 9 of `skills/lifecycle/references/load-requirements.md` explicitly enumerates Global Context loading with the verbatim "skipped: file absent" notation. Both greps return 2 — comfortably ≥ 1. The downstream contract (drift-check + reviewer-dispatch consumers) is named.
- **Verdict**: PASS

### Requirement 4: Matching Semantics counterpart for Global Context
- **Expected**: `## Matching Semantics` block documents Global Context's list-of-paths semantics distinct from Conditional Loading's substring-match semantics. Acceptance: `grep -c "Global Context"` ≥ 2 AND `pytest tests/test_load_requirements_protocol.py` exits 0.
- **Actual**: Matching Semantics block at line 24 carries "Global Context uses list-of-paths semantics, not phrase matching." documenting that each bullet is a repo-root-relative path read on every invocation, with absent paths recorded as skipped. `grep -c "Global Context"` returns 2 (one occurrence in Step 1, one in Matching Semantics). `pytest tests/test_load_requirements_protocol.py` passes with 10/10 tests.
- **Verdict**: PASS

### Requirement 5: `tests/test_load_requirements_protocol.py` step-count assertion updated
- **Expected**: `test_load_requirements_md_enumerates_*_protocol_steps()` continues to pass with the updated protocol; the step-count invariant is not preserved by silently embedding Global Context inside step 1's pre-existing prose. Acceptance: `pytest tests/test_load_requirements_protocol.py -k enumerates --exitfirst` exits 0.
- **Actual**: The test was renamed to `test_load_requirements_md_enumerates_protocol_steps_with_global_context()` at line 121, explicitly asserting that step 1 covers `project.md + Global Context` plus the four other steps, asserting the noun set `{"project.md", "Global Context", "tags", "Conditional Loading"}` is present, and asserting the skipped-entry contract via regex `skipped: file absent|skipped because absent`. The protocol still has five numbered steps; step 1's invariant has been re-expressed (no longer "single unconditional load") and the test docstring explicitly names this redefinition. Acceptance command passes.
- **Verdict**: PASS

### Requirement 6: `requirements-gather/SKILL.md:33` contract narrowed (D2 form)
- **Expected**: Replace no-filesystem contract with positive grant enumerating the writable set, preserving Q&A abandon-safety, naming project.md/area-docs as excluded, and stating mid-interview abandonment semantics for glossary writes. Acceptance: `grep -c "cortex/requirements/glossary.md"` ≥ 1 AND `grep -c "Lazy artifact creation still applies"` = 1 AND `grep -c "durably persisted\|partial-monotonic"` ≥ 1.
- **Actual**: Lines 35–39 of `skills/requirements-gather/SKILL.md` carry: (a) explicit writable set: "`cortex/requirements/glossary.md` per-term append, with lazy file creation"; (b) abandon-safety preserved verbatim: "Lazy artifact creation still applies to project.md and area docs"; (c) project.md/area-docs explicit exclusion: "`cortex/requirements/project.md` and area docs under `cortex/requirements/` are explicitly excluded"; (d) mid-interview semantic named: "each per-term append is durably persisted at the moment it fires; entries appended before abandonment remain in the file. Partial-monotonic-growth is the documented behavior". Grep counts: 2 / 1 / 1 — all ≥ acceptance thresholds.
- **Verdict**: PASS

### Requirement 7: Inline-write rule with term-already-exists probe
- **Expected**: Prose adds (a) glossary-existence read, (b) term-already-exists conflict surfacing, (c) binary classifier with project-specific append on absence. Acceptance: `grep -c "term-already-exists\|already present\|conflict"` ≥ 1 AND `grep -ci "project-specific"` ≥ 1.
- **Actual**: The `### Inline glossary write with term-already-exists probe` section at lines 41–43 reads "probe before writing: read `cortex/requirements/glossary.md` if it exists, and check whether the term is already present. If it is, use the existing entry verbatim, or surface the conflict via `AskUserQuestion`...". The classifier section at lines 45–47 names the binary rule explicitly: "Pocock's rule: project-specific terms get written, general programming terms do not." with worked examples. Grep counts: 2 / 3 — both exceed acceptance.
- **Verdict**: PASS

### Requirement 8: User-confirmation gate before inline write
- **Expected**: Inline-write rule includes a gate excluding "Recommended answer:" lines from triggering writes; only user-named/user-confirmed terms persist. Acceptance: `grep -c "user-named\|user-confirmed\|confirmation"` ≥ 1, with explicit "Recommended answer:" exclusion.
- **Actual**: The `### User-confirmation gate` section at lines 49–51 reads "A term that surfaced only in a `Recommended answer:` line and was never user-named or user-confirmed does NOT trigger an inline write — the recommendation alone is not consent to persist." All required substrings are present. `grep -c "user-named\|user-confirmed\|confirmation"` returns 4.
- **Verdict**: PASS

### Requirement 9: `requirements-write/SKILL.md:4` contract phrasing narrowed for parity
- **Expected**: Phrasing narrowed from "only sub-skill that touches the filesystem" to "only sub-skill that writes to project.md or area docs" with glossary-write attribution to requirements-gather. Acceptance: `grep -c "glossary" skills/requirements-write/SKILL.md` ≥ 1 in description/when_to_use frontmatter.
- **Actual**: Line 4 (`when_to_use`) reads: "and is the only sub-skill that writes to project.md or area docs under `cortex/requirements/`. `/requirements-gather` appends glossary entries to `cortex/requirements/glossary.md`; all other filesystem writes under `cortex/requirements/` remain `/requirements-write`'s." The frontmatter carries the narrowed contract. `grep -c "glossary"` returns 2 — the when_to_use frontmatter line contributes one, and the H2 schema section contributes the other.
- **Verdict**: PASS

### Requirement 10: `requirements/SKILL.md` orchestrator passive-artifact framing updated
- **Expected**: Add a sentence noting glossary as a producer-managed exception while preserving the passive-on-read semantic for consumers. Acceptance: `grep -ci "glossary" skills/requirements/SKILL.md` ≥ 1.
- **Actual**: Line 29 (in Routing step 5) carries: "The glossary (`cortex/requirements/glossary.md`) is a producer-managed exception to the passive-artifact framing: it grows inline during requirements interviews via per-term appends by `/requirements-gather`, but consumers still treat it as passive on read (load via the tag-based protocol, no consumer-driven writes)." Three glossary mentions in total across the orchestrator (list handling, routing rationale).
- **Verdict**: PASS

### Requirement 11: `requirements/SKILL.md` `list` subcommand handling
- **Expected**: Update `list` subcommand to either include glossary.md with a scope marker OR explicitly exclude it with rationale. Acceptance: `grep -ci "glossary" skills/requirements/SKILL.md` reflects the chosen handling.
- **Actual**: Line 21 (Argument shapes) and line 25 (Routing step 1) document the exclusion: "The enumeration explicitly excludes `glossary.md` — it is a producer-managed vocabulary artifact with a per-term append lifecycle rather than a scope-level requirements doc, and surfacing it alongside project/area docs would conflate two different artifact lifecycles." The implementation is consistent: the `list` step both excludes and re-states the rationale, so the chosen handling (option b — explicit exclusion with one-line rationale) is applied consistently across documentation and implementation prose.
- **Verdict**: PASS

### Requirement 12: `critical-review/SKILL.md` Step 2a reads glossary's Language section with content constraint
- **Expected**: Step 2a reads `## Language` only (not Relationships/Example dialogue/Flagged ambiguities); silent skip when absent. Language-content constraint added to requirements-gather: definitional, not classification-shaped. Acceptance: `grep -c "glossary" skills/critical-review/SKILL.md` ≥ 1 in Step 2a region AND `grep -c "Language section"` ≥ 1 AND `grep -c "definitional, not classification-shaped\|content constraint" skills/requirements-gather/SKILL.md` ≥ 1.
- **Actual**: Step 2a at line 39 reads: "If `cortex/requirements/glossary.md` exists, read it **Language-section-only**: extract the Language section (`## Language`) verbatim... Do NOT read `## Relationships`, `## Example dialogue`, or `## Flagged ambiguities`... Silently skip when the file is absent." The Language-content constraint at lines 53–55 of requirements-gather reads: "Entries written into the glossary's `## Language` section must be definitional, not classification-shaped... Anchor pair: `phase_transition: the named event emitted when ...` is admitted... `phase_transition — genuinely-domain term; contract-shaped in lifecycle.md` is rejected". Grep counts: 2 / 1 / 2 — all ≥ acceptance thresholds.
- **Verdict**: PASS

### Requirement 13: `critical-review/SKILL.md:41` exemption rationale narrowed
- **Expected**: Anchor phrase preserved; rationale narrowed to "not vocabulary"; explicit clause admitting Language section as definitional. Acceptance: `grep -c "Requirements loading: deliberately exempt"` = 1 AND `grep -c "not vocabulary"` ≥ 1 AND `pytest -k exemption --exitfirst` exits 0.
- **Actual**: Line 42 anchor preserved verbatim. Rationale at line 42 narrowed: "broader project context (priorities, area-specific tags, decisions, **not vocabulary**) would dilute that focus and anchor reviewers to existing reasoning. Vocabulary (the glossary's `## Language` section) is admitted because it is definitional rather than reasoning-shaped." Grep counts: 1 / 1. Exemption parity test passes.
- **Verdict**: PASS

### Requirement 14: Consumer-rule prose added to non-exempt consumers
- **Expected**: Each of six consumers (lifecycle clarify/specify/review, discovery clarify/research, refine SKILL.md) carries "If a concept you need is not yet defined in the glossary, treat the absence as a signal to surface the term in the next requirements interview." Acceptance: each file returns `grep -c "absence as a signal\|surface the term"` ≥ 1.
- **Actual**: All six consumers carry the prose, each at the load-requirements citation site:
  - `skills/lifecycle/references/clarify.md:35` (after §2 Load Requirements)
  - `skills/lifecycle/references/specify.md:11` (after §1 Load Context)
  - `skills/lifecycle/references/review.md:13` (in §1 Gather Review Inputs)
  - `skills/discovery/references/clarify.md:17` (after §2 Load Requirements)
  - `skills/discovery/references/research.md:29` (after §1a Load Requirements)
  - `skills/refine/SKILL.md:70` (in Step 3 Clarify Phase)
  - Each file `grep -c` returns 1. Test `test_six_consumer_references_carry_consumer_rule_prose` passes.
- **Verdict**: PASS

### Requirement 15: `tests/test_load_requirements_protocol.py` parity updates
- **Expected**: Test updated for Global Context, step-count, Matching Semantics counterpart, consumer-rule prose presence; deliberate-exemption anchor still passes. Acceptance: `pytest tests/test_load_requirements_protocol.py` exits 0.
- **Actual**: The file at lines 121–162 carries the new `test_load_requirements_md_enumerates_protocol_steps_with_global_context()` test; lines 81–101 carry `test_six_consumer_references_carry_consumer_rule_prose()` for Req 14 coverage; the deliberate-exemption test at lines 104–118 preserves the anchor parity check. All 10 tests pass.
- **Verdict**: PASS

### Requirement 16: `tests/test_lifecycle_kept_pauses_parity.py` anchor tolerance preserved
- **Expected**: Consumer-rule citations in specify.md leave AskUserQuestion anchors within LINE_TOLERANCE=35. Acceptance: `pytest tests/test_lifecycle_kept_pauses_parity.py` exits 0.
- **Actual**: Adding the single-line prose at line 11 of specify.md shifts subsequent line numbers by ~1, well within tolerance. The parity test passes (2/2).
- **Verdict**: PASS

### Requirement 17: `tests/test_requirements_skill_e2e.py` simulation alignment
- **Expected**: Either extend simulation to write a stub `glossary.md` at inline-write points, OR document explicit out-of-scope marking for hermeticity. Acceptance: `pytest tests/test_requirements_skill_e2e.py` exits 0 AND `grep -ci "glossary" tests/test_requirements_skill_e2e.py` ≥ 1.
- **Actual**: Option (a) was chosen — `_simulate_write()` accepts a `glossary_terms` parameter (CANNED_GLOSSARY_TERMS at lines 259–271 provides definitional fixtures), and lazily writes a stub `glossary.md` to `tmp_path` when terms are non-empty. The new `test_e2e_inline_glossary_write_is_lazy_when_no_terms_resolved()` test covers the empty-terms path (no file produced). The hermeticity assertion is preserved — the stub lives under `tmp_path`, never under the live `cortex/requirements/`. All 12 tests pass; `grep -ci "glossary"` returns 30.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. The new `### Inline glossary write with term-already-exists probe`, `### Project-specific vs general programming`, `### User-confirmation gate`, and `### Language-content constraint` H3 subsections follow the existing H3 convention in `requirements-gather/SKILL.md`. The new `Global Context` section parallels `Conditional Loading` in both `project.md` and the schema entry at `requirements-write/SKILL.md`. Pocock's binary-classifier framing is named explicitly and aligns with the research artifact's vocabulary.
- **Error handling**: Lazy-file-creation contract is enforced uniformly — the loader records absent Global Context entries as `<path> (skipped: file absent)` rather than warning or failing. `critical-review` Step 2a silently skips absent glossary. The producer's inline-write path creates the file lazily on first resolved term. The Phase 1/Phase 2 separation deliberately ships schema + load-rule before the producer wires, and acceptance tests are presence-grep based for Phase 1 with end-to-end runtime tests via the simulation in Phase 2. No silent omissions; the skipped-entry notation is explicit and surfaces in the loaded-files list step 4 produces.
- **Test coverage**: Strong. All four named parity tests pass (`test_load_requirements_protocol.py`, `test_lifecycle_kept_pauses_parity.py`, `test_requirements_skill_e2e.py`, and the cascade points `test_skill_callgraph.py` + `test_check_events_registry.py`). The simulation in `test_requirements_skill_e2e.py` now covers the producer's inline-write path that previously had zero automated coverage at any phase — critical-review's gap-flagging surfaced this and Req 17 addressed it. The lazy-creation contract has a dedicated negative test. Total: 10 + 2 + 12 + cascade = 24+ tests covering this feature.
- **Pattern consistency**: Follows the established CLAUDE.md "Prescribe What and Why, not How" principle — the new prose surfaces describe decisions (whether a term is project-specific) and intent (definitional, not classification-shaped) rather than step-by-step procedure. Soft positive-routing per the MUST-escalation policy is used throughout — no MUST/CRITICAL/REQUIRED escalations introduced. The two-phase ship (schema in Phase 1, producer in Phase 2) matches the technical-constraints note that Phase 1's runtime behavior is end-to-end testable only after Phase 2's producer ships. Solution-horizon principle observed: `## Global Context` is the durable shape for any future always-load file, and the section-scoped awk acceptance pattern survives section growth.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
